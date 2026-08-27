"""MCAP / ROS2 bag analyzer using the rosbags library."""
from pathlib import Path  # pragma: no cover

import numpy as np  # pragma: no cover
from rosbags.rosbag2 import Reader  # pragma: no cover
from rosbags.typesys import Stores, get_typestore  # pragma: no cover


def parse_real_rosbag(mcap_path: str) -> dict:  # pragma: no cover
    path = Path(mcap_path)
    if not path.exists():
        return {"error": f"Rosbag path not found at {mcap_path}"}
    if not path.is_dir():
        return {"error": f"Expected a rosbag2 directory, got file: {mcap_path}. Point to the directory containing metadata.yaml and storage files."}

    typestore = get_typestore(Stores.ROS2_FOXY)
    pose_covariances = []
    cmd_velocities = []

    with Reader(path) as reader:
        connections = [x for x in reader.connections if x.topic in ["/odom", "/cmd_vel"]]

        for connection, timestamp, rawdata in reader.messages(connections=connections):
            msg = typestore.deserialize_cdr(rawdata, connection.msgtype)
            
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