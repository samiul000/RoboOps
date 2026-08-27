"""MCAP / ROS2 bag analyzer using the rosbags library."""
from pathlib import Path 

import numpy as np  
from rosbags.rosbag2 import Reader  
from rosbags.serde import deserialize_cdr 


def parse_real_rosbag(mcap_path: str) -> dict:
    path = Path(mcap_path)
    if not path.exists():
        return {"error": f"Rosbag file not found at {mcap_path}"}

    pose_covariances = []
    cmd_velocities = []

    with Reader(path) as reader:
        # Filter only required topics to minimize I/O and memory footprint
        connections = [x for x in reader.connections if x.topic in ["/odom", "/cmd_vel"]]
        
        for connection, timestamp, rawdata in reader.messages(connections=connections):
            msg = deserialize_cdr(rawdata, connection.msgtype)
            
            if connection.topic == "/odom":
                # Extract covariance diagonal (pose uncertainty)
                cov = np.array(msg.pose.covariance).reshape(6, 6)
                pose_covariances.append(float(np.trace(cov[:3, :3])))
            
            elif connection.topic == "/cmd_vel":
                cmd_velocities.append({
                    "vx": float(msg.linear.x),
                    "wz": float(msg.angular.z)
                })

    max_cov = float(np.max(pose_covariances)) if pose_covariances else 0.0
    avg_cov = float(np.mean(pose_covariances)) if pose_covariances else 0.0

    return {
        "summary": {
            "max_covariance": max_cov,
            "mean_covariance": avg_cov,
            "total_motion_commands": len(cmd_velocities),
            "is_localized": max_cov < 1.0
        },
        "root_cause_diagnosis": (
            "Severe wheel slip or localization loss detected."
            if max_cov >= 1.0 else "Nominal localization; path planning issue."
        )
    }