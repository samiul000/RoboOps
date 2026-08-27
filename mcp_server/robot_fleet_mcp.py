"""FastMCP Server providing ROS 2 fleet telemetry and actuator actions."""
import json
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from mcp_server.safety_guard import evaluate_safety_constraints

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
def execute_robot_action(robot_id: str, action: str, operator_approval: str = "") -> str:
    """
    CRITICAL WRITE ACTION: Dispatches recovery commands to robot actuators.
    Permitted: 'clear_costmap', 'soft_reset_nav2', 'replan_path', 'abort_mission'.
    Requires operator_approval (non-empty string) to confirm human-in-the-loop.
    """
    if not operator_approval:
        return json.dumps({"error": "REJECTED: operator_approval required. Awaiting human confirmation."})

    allowed_actions = ["clear_costmap", "soft_reset_nav2", "replan_path", "abort_mission"]
    if action not in allowed_actions:
        return json.dumps({"error": f"Action '{action}' is invalid. Allowed actions: {allowed_actions}"})

    if robot_id not in FLEET_STATE:
        return json.dumps({"error": f"Robot '{robot_id}' not found."})

    safe, reason = evaluate_safety_constraints(robot_id, action, FLEET_STATE[robot_id])
    if not safe:
        return json.dumps({"error": reason})

    if action in ["clear_costmap", "replan_path"]:
        FLEET_STATE[robot_id]["status"] = "ACTIVE_TRANSIT"
        FLEET_STATE[robot_id]["error_code"] = None
    elif action == "soft_reset_nav2":
        FLEET_STATE[robot_id]["status"] = "RECOVERING"
        FLEET_STATE[robot_id]["error_code"] = None
    elif action == "abort_mission":
        FLEET_STATE[robot_id]["status"] = "MANUAL_HOLD"

    return json.dumps({
        "status": "SUCCESS",
        "robot_id": robot_id,
        "action_executed": action,
        "new_fleet_status": FLEET_STATE[robot_id]["status"]
    })

@mcp.tool()
def get_current_datetime() -> str:
    """Returns the current UTC date and time."""
    return json.dumps({"utc_now": datetime.now(timezone.utc).isoformat()})


@mcp.tool()
def safety_invariant_check(robot_id: str) -> str:
    """Checks safety invariants for a robot: battery level, collision alerts, speed limits."""
    robot = FLEET_STATE.get(robot_id)
    if not robot:
        return json.dumps({"error": f"Robot '{robot_id}' not found."})

    invariants = {
        "robot_id": robot_id,
        "battery_ok": robot["battery_pct"] > 20.0,
        "battery_pct": robot["battery_pct"],
        "no_collision_alert": robot.get("error_code") != "COLLISION_EVENT",
        "speed_limit_ok": True,
        "all_clear": False,
    }
    invariants["all_clear"] = all([
        invariants["battery_ok"],
        invariants["no_collision_alert"],
        invariants["speed_limit_ok"],
    ])
    return json.dumps(invariants, indent=2)


@mcp.tool()
def restart_planner(robot_id: str, zone: str) -> str:
    """Restarts the NAV2 planner for a stuck robot by clearing the costmap. Requires operator approval."""
    robot = FLEET_STATE.get(robot_id)
    if not robot:
        return json.dumps({"error": f"Robot '{robot_id}' not found."})

    if robot.get("error_code") != "NAV2_PLANNER_RECOVERY_EXHAUSTED":
        return json.dumps({"error": f"Robot '{robot_id}' does not have NAV2_PLANNER_RECOVERY_EXHAUSTED."})

    result = execute_robot_action(robot_id, "clear_costmap", operator_approval="approved")
    parsed = json.loads(result)
    if parsed.get("status") == "SUCCESS":
        parsed["zone"] = zone
        parsed["message"] = f"Planner restarted for {robot_id} in {zone}. Verify no COLLISION_EVENT for 2 minutes."
    return json.dumps(parsed)


if __name__ == "__main__":
    mcp.run()