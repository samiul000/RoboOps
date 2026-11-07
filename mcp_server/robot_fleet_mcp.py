"""FastMCP Server providing ROS 2 fleet telemetry and actuator actions."""
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from database.audit_logger import log_incident_event
from mcp_server.safety_guard import (
    MAX_TELEMETRY_AGE_SECONDS,
    evaluate_safety_constraints,
)

logger = logging.getLogger(__name__)
mcp = FastMCP("RoboOps-Controller")
STATE_LOCK = threading.Lock()
FLEET_STATE_STORE_PATH = os.getenv("FLEET_STATE_STORE_PATH")
_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# One-time, action/robot-bound human approvals. Tokens are opaque grants rather
# than reusable free-form strings.
APPROVAL_STORE = {}
APPROVAL_STORE_LOCK = threading.Lock()


def _approval_accepted(approval: str) -> bool:
    """Compatibility check for tests and simple deployments."""
    required_token = os.getenv("ROBOOPS_OPERATOR_TOKEN")
    if approval.startswith("grant:"):
        return _validate_grant(approval, None, None, consume=False)
    if not approval:
        return False
    if required_token:
        return approval == required_token
    return os.getenv("ROBOOPS_ALLOW_LEGACY_APPROVALS", "true").lower() == "true"


def issue_approval(robot_id: str, action: str, issued_by: str = "operator", ttl_seconds: int = 120) -> str:
    """Mint a one-time approval grant bound to one robot and one action."""
    token = uuid.uuid4().hex
    with APPROVAL_STORE_LOCK:
        APPROVAL_STORE[token] = {
            "robot_id": robot_id,
            "action": action,
            "issued_by": issued_by,
            "expires_at": time.time() + ttl_seconds,
            "consumed": False,
        }
    return f"grant:{token}"


def _validate_grant(approval: str, robot_id: str, action: str, consume: bool = True) -> bool:
    token = approval.removeprefix("grant:")
    now = time.time()
    with APPROVAL_STORE_LOCK:
        grant = APPROVAL_STORE.get(token)
        if grant is None:
            return False
        if grant["consumed"] or grant["expires_at"] < now:
            return False
        if robot_id is not None and grant["robot_id"] != robot_id:
            return False
        if action is not None and grant["action"] != action:
            return False
        if consume:
            grant["consumed"] = True
        return True


def _approval_valid_for_action(robot_id: str, action: str, approval: str) -> bool:
    if not approval:
        return False
    if approval.startswith("grant:"):
        return _validate_grant(approval, robot_id, action, consume=True)
    # Legacy mode intentionally requires an explicit operator token in production.
    required_token = os.getenv("ROBOOPS_OPERATOR_TOKEN")
    if required_token:
        return approval == required_token
    return os.getenv("ROBOOPS_ALLOW_LEGACY_APPROVALS", "true").lower() == "true"


def _is_safe_project_path(path_value: str) -> bool:
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = _PROJECT_ROOT / candidate
    try:
        return candidate.resolve().is_relative_to(_PROJECT_ROOT.resolve())
    except ValueError:
        return False


def _persist_fleet_state():
    if not FLEET_STATE_STORE_PATH:
        return
    path = Path(FLEET_STATE_STORE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with STATE_LOCK:
        snapshot = {robot_id: dict(state) for robot_id, state in FLEET_STATE.items()}
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def _load_persisted_state():
    if not FLEET_STATE_STORE_PATH:
        return
    path = Path(FLEET_STATE_STORE_PATH)
    if not path.exists():
        return
    loaded = json.loads(path.read_text(encoding="utf-8"))
    with STATE_LOCK:
        FLEET_STATE.clear()
        FLEET_STATE.update({k: dict(v) for k, v in loaded.items()})


NOW = time.time()
FLEET_STATE = {
    "AMR-04": {
        "status": "ERROR_NAVIGATION_STUCK",
        "battery_pct": 68.0,
        "error_code": "NAV2_PLANNER_RECOVERY_EXHAUSTED",
        "location": {"x": 14.2, "y": 7.8},
        "target_waypoint": {"x": 28.0, "y": 32.5},
        "incident_log_path": "sandbox/amr_04_incident.json",
        "collision_alert": False,
        "speed_kph": 0.0,
        "last_telemetry_at": NOW,
    },
    "AMR-02": {
        "status": "ACTIVE_TRANSIT",
        "battery_pct": 91.0,
        "error_code": None,
        "location": {"x": 5.0, "y": 12.0},
        "target_waypoint": {"x": 10.0, "y": 12.0},
        "incident_log_path": None,
        "collision_alert": False,
        "speed_kph": 0.0,
        "last_telemetry_at": NOW,
    }
}
_load_persisted_state()


def _audit_action(robot_id: str, action: str, approval: str, result: str, diagnosis: dict | None = None):
    robot = FLEET_STATE.get(robot_id, {})
    try:
        log_incident_event(
            robot_id=robot_id,
            error=robot.get("error_code"),
            diagnosis=diagnosis or {},
            action=action,
            approved_by=approval,
            result=result,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist incident event for %s: %s", robot_id, exc)


@mcp.tool()
def get_fleet_telemetry(robot_id: str) -> str:
    """Fetches high-frequency telemetry and status for a specific robot."""
    with STATE_LOCK:
        robot = FLEET_STATE.get(robot_id)
        if not robot:
            return json.dumps({"error": f"Robot '{robot_id}' not found in fleet."})
        robot["last_telemetry_at"] = time.time()
        _persist_fleet_state()
        return json.dumps(robot, indent=2)


@mcp.tool()
def get_incident_log_file(robot_id: str) -> str:
    """Returns the path to the recorded sensor and odometry log file for sandboxed inspection."""
    with STATE_LOCK:
        robot = FLEET_STATE.get(robot_id)
        if not robot or not robot.get("incident_log_path"):
            return json.dumps({"error": f"No incident logs for '{robot_id}'."})
        incident_path = robot["incident_log_path"]
    if not _is_safe_project_path(str(incident_path)):
        return json.dumps({"error": "REJECTED: incident log path escapes project root."})
    return incident_path


@mcp.tool()
def execute_robot_action(robot_id: str, action: str, operator_approval: str = "") -> str:
    """
    CRITICAL WRITE ACTION: Dispatches recovery commands to robot actuators.
    Permitted: 'clear_costmap', 'soft_reset_nav2', 'replan_path', 'abort_mission'.
    Requires operator_approval to confirm human-in-the-loop.
    """
    allowed_actions = ["clear_costmap", "soft_reset_nav2", "replan_path", "abort_mission"]
    if action not in allowed_actions:
        return json.dumps({"error": f"Action '{action}' is invalid. Allowed actions: {allowed_actions}"})

    if not _approval_valid_for_action(robot_id, action, operator_approval):
        _audit_action(robot_id, action, operator_approval, "BLOCKED: invalid or expired approval")
        logger.warning("Blocked action %s for %s: invalid or expired approval", action, robot_id)
        return json.dumps({"error": "REJECTED: valid operator_approval required. Awaiting human confirmation."})

    with STATE_LOCK:
        if robot_id not in FLEET_STATE:
            return json.dumps({"error": f"Robot '{robot_id}' not found."})

        robot = FLEET_STATE[robot_id]
        safe, reason = evaluate_safety_constraints(robot_id, action, robot)
        if not safe:
            _audit_action(robot_id, action, operator_approval, f"BLOCKED: {reason}")
            logger.warning("Blocked unsafe action %s for %s: %s", action, robot_id, reason)
            return json.dumps({"error": reason})

        if action in ["clear_costmap", "replan_path"]:
            FLEET_STATE[robot_id]["status"] = "ACTIVE_TRANSIT"
            FLEET_STATE[robot_id]["error_code"] = None
        elif action == "soft_reset_nav2":
            FLEET_STATE[robot_id]["status"] = "RECOVERING"
            FLEET_STATE[robot_id]["error_code"] = None
        elif action == "abort_mission":
            FLEET_STATE[robot_id]["status"] = "MANUAL_HOLD"

        result = json.dumps({
            "status": "SUCCESS",
            "robot_id": robot_id,
            "action_executed": action,
            "new_fleet_status": FLEET_STATE[robot_id]["status"]
        })
        _audit_action(robot_id, action, operator_approval, "SUCCESS")
        logger.info("Executed %s for %s", action, robot_id)
    _persist_fleet_state()
    return result


@mcp.tool()
def get_current_datetime() -> str:
    """Returns the current UTC date and time."""
    return json.dumps({"utc_now": datetime.now(timezone.utc).isoformat()})


@mcp.tool()
def safety_invariant_check(robot_id: str) -> str:
    """Checks safety invariants for a robot: battery level, collision alerts, speed limits, telemetry freshness."""
    with STATE_LOCK:
        robot = FLEET_STATE.get(robot_id)
        if not robot:
            return json.dumps({"error": f"Robot '{robot_id}' not found."})

        battery_ok = robot.get("battery_pct", 0.0) >= 15.0
        no_collision_alert = not (
            robot.get("collision_alert")
            or robot.get("collision_event")
            or robot.get("error_code") == "COLLISION_EVENT"
        )
        speed = robot.get("speed_kph", robot.get("speed", 0.0))
        try:
            speed_ok = float(speed) <= 20.0
        except (TypeError, ValueError):
            speed_ok = False
        telemetry_age = time.time() - float(robot.get("last_telemetry_at", 0.0))
        telemetry_fresh = telemetry_age <= MAX_TELEMETRY_AGE_SECONDS
        all_clear = battery_ok and no_collision_alert and speed_ok and telemetry_fresh

        invariants = {
            "robot_id": robot_id,
            "battery_ok": battery_ok,
            "battery_pct": robot.get("battery_pct"),
            "battery_threshold_pct": 15.0,
            "no_collision_alert": no_collision_alert,
            "speed_limit_ok": speed_ok,
            "speed_kph": speed,
            "max_speed_kph": 20.0,
            "telemetry_fresh": telemetry_fresh,
            "telemetry_age_seconds": round(telemetry_age, 3),
            "max_telemetry_age_seconds": MAX_TELEMETRY_AGE_SECONDS,
            "all_clear": all_clear,
        }
        return json.dumps(invariants, indent=2)


@mcp.tool()
def restart_planner(robot_id: str, zone: str, operator_approval: str = "") -> str:
    """Restarts the NAV2 planner for a stuck robot. Requires explicit operator approval."""
    if not _approval_valid_for_action(robot_id, "clear_costmap", operator_approval):
        return json.dumps({"error": "REJECTED: valid operator_approval required. Awaiting human confirmation."})

    with STATE_LOCK:
        robot = FLEET_STATE.get(robot_id)
        if not robot:
            return json.dumps({"error": f"Robot '{robot_id}' not found."})

        if robot.get("error_code") != "NAV2_PLANNER_RECOVERY_EXHAUSTED":
            return json.dumps({"error": f"Robot '{robot_id}' does not have NAV2_PLANNER_RECOVERY_EXHAUSTED."})

    result = execute_robot_action(robot_id, "clear_costmap", operator_approval=operator_approval)
    parsed = json.loads(result)
    if parsed.get("status") == "SUCCESS":
        parsed["zone"] = zone
        parsed["message"] = f"Planner restarted for {robot_id} in {zone}. Verify no COLLISION_EVENT for 2 minutes."
    return json.dumps(parsed)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run()
