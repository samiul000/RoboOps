"""FastMCP Server providing ROS 2 fleet telemetry and actuator actions."""
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
import json
import os

mcp = FastMCP("RoboOps-Controller")

# In-memory mock representing a live ROS 2 robot fleet state
FLEET_STATE = {
    "AMR-04": {
        "status": "ERROR_NAVIGATION_STUCK",
        "battery_pct": 68.0,
        "error_code": "NAV2_PLANNER_RECOVERY_EXHAUSTED",
        "location": {"x": 14.2, "y": 7.8},
        "target_waypoint": {"x": 28.0, "y": 32.5},
        "incident_log_path": "sandbox/amr_04_incident.json"
    },
    "AMR-02": {
        "status": "ACTIVE_TRANSIT",
        "battery_pct": 91.0,
        "error_code": None,
        "location": {"x": 5.0, "y": 12.0},
        "target_waypoint": {"x": 10.0, "y": 12.0},
        "incident_log_path": None
    }
}

class TelemetryQuery(BaseModel):
    robot_id: str = Field(description="The unique identifier of the robot (e.g., 'AMR-04')")

class RemediationAction(BaseModel):
    robot_id: str = Field(description="Target robot ID")
    action: str = Field(description="Remediation action: 'clear_costmap', 'soft_reset_nav2', 'replan_path', 'abort_mission'")

@mcp.tool()
def get_fleet_telemetry(robot_id: str) -> str:
    """Fetches high-frequency telemetry and status for a specific robot."""
    robot = FLEET_STATE.get(robot_id)
    if not robot:
        return json.dumps({"error": f"Robot '{robot_id}' not found in fleet."})
    return json.dumps(robot, indent=2)

@mcp.tool()
def get_incident_log_file(robot_id: str) -> str:
    """Returns the path to the recorded sensor and odometry log file for sandboxed inspection."""
    robot = FLEET_STATE.get(robot_id)
    if not robot or not robot.get("incident_log_path"):
        return json.dumps({"error": f"No incident logs for '{robot_id}'."})
    return robot["incident_log_path"]

@mcp.tool()
def execute_robot_action(robot_id: str, action: str) -> str:
    """
    CRITICAL WRITE ACTION: Dispatches recovery commands to robot actuators.
    Permitted: 'clear_costmap', 'soft_reset_nav2', 'replan_path', 'abort_mission'.
    """
    allowed_actions = ["clear_costmap", "soft_reset_nav2", "replan_path", "abort_mission"]
    if action not in allowed_actions:
        return json.dumps({"error": f"Action '{action}' is invalid. Allowed actions: {allowed_actions}"})

    if robot_id not in FLEET_STATE:
        return json.dumps({"error": f"Robot '{robot_id}' not found."})

    if action in ["clear_costmap", "replan_path"]:
        FLEET_STATE[robot_id]["status"] = "ACTIVE_TRANSIT"
        FLEET_STATE[robot_id]["error_code"] = None
    elif action == "abort_mission":
        FLEET_STATE[robot_id]["status"] = "MANUAL_HOLD"

    return json.dumps({
        "status": "SUCCESS",
        "robot_id": robot_id,
        "action_executed": action,
        "new_fleet_status": FLEET_STATE[robot_id]["status"]
    })

if __name__ == "__main__":
    mcp.run()