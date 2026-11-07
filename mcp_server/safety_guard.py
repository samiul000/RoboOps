# mcp_server/safety_guard.py
import threading
import time
from collections import defaultdict

# Rate-limit tracker: robot_id -> list of action timestamps
ACTION_HISTORY = defaultdict(list)
ACTION_HISTORY_LOCK = threading.Lock()

MAX_ACTIONS_PER_WINDOW = 3
WINDOW_SECONDS = 300  # 5 minutes
NAVIGATION_ACTIONS = {"clear_costmap", "replan_path", "soft_reset_nav2"}
BATTERY_THRESHOLD_PCT = 15.0
MAX_SAFE_SPEED_KPH = 20.0
MAX_TELEMETRY_AGE_SECONDS = 30.0


def _robot_has_collision_alert(robot_state: dict) -> bool:
    return bool(
        robot_state.get("collision_alert")
        or robot_state.get("collision_event")
        or robot_state.get("error_code") == "COLLISION_EVENT"
    )


def _telemetry_fresh(robot_state: dict) -> bool:
    if "last_telemetry_at" not in robot_state:
        return False
    try:
        age = time.time() - float(robot_state["last_telemetry_at"])
    except (TypeError, ValueError):
        return False
    return age <= MAX_TELEMETRY_AGE_SECONDS


def evaluate_safety_constraints(robot_id: str, action: str, robot_state: dict) -> tuple[bool, str]:
    now = time.time()

    # 1. Rate Limiting Check — abort_mission is exempt (emergency action)
    if action != "abort_mission":
        with ACTION_HISTORY_LOCK:
            history = ACTION_HISTORY[robot_id]
            recent_actions = [t for t in history if now - t < WINDOW_SECONDS]
            ACTION_HISTORY[robot_id] = recent_actions

            if len(recent_actions) >= MAX_ACTIONS_PER_WINDOW:
                return False, (
                    f"SAFETY LOCKOUT: Robot {robot_id} has exceeded max recovery actions "
                    f"({MAX_ACTIONS_PER_WINDOW} in 5 min)."
                )

    # Fail closed on stale or unavailable telemetry.
    if action in NAVIGATION_ACTIONS and not _telemetry_fresh(robot_state):
        return False, (
            f"SAFETY REJECT: Telemetry is stale or unavailable for {robot_id}. "
            "Navigation recovery blocked until fresh telemetry arrives."
        )

    # 2. State-Based Invariant Checks — low battery blocks navigation recovery
    if action in NAVIGATION_ACTIONS and robot_state.get("battery_pct", 0) < BATTERY_THRESHOLD_PCT:
        return False, "SAFETY REJECT: Battery too low (<15%) for navigation recovery. Must route to charging dock."

    # 3. Collision Avoidance — no navigation recovery during collision alert
    if action in NAVIGATION_ACTIONS and _robot_has_collision_alert(robot_state):
        return False, "SAFETY REJECT: Collision alert active. Manual intervention required before recovery."

    # 4. Speed Limit — block recovery while robot is moving too fast
    speed_kph = robot_state.get("speed_kph", robot_state.get("speed", 0.0))
    try:
        speed_value = float(speed_kph)
    except (TypeError, ValueError):
        speed_value = 0.0
    if action in NAVIGATION_ACTIONS and speed_value > MAX_SAFE_SPEED_KPH:
        return False, "SAFETY REJECT: Speed exceeds 20 km/h. Slow robot before recovery."

    # 5. Record Action Timestamp
    with ACTION_HISTORY_LOCK:
        ACTION_HISTORY[robot_id].append(now)
    return True, "SAFE"