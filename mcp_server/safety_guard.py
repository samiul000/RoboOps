# mcp_server/safety_guardrails.py
import time
from collections import defaultdict

# Rate-limit tracker: robot_id -> list of action timestamps
ACTION_HISTORY = defaultdict(list)

MAX_ACTIONS_PER_WINDOW = 3
WINDOW_SECONDS = 300  # 5 minutes
NAVIGATION_ACTIONS = {"clear_costmap", "replan_path", "soft_reset_nav2"}


def evaluate_safety_constraints(robot_id: str, action: str, robot_state: dict) -> tuple[bool, str]:
    now = time.time()

    # 1. Rate Limiting Check — abort_mission is exempt (emergency action)
    if action != "abort_mission":
        history = ACTION_HISTORY[robot_id]
        recent_actions = [t for t in history if now - t < WINDOW_SECONDS]
        ACTION_HISTORY[robot_id] = recent_actions

        if len(recent_actions) >= MAX_ACTIONS_PER_WINDOW:
            return False, f"SAFETY LOCKOUT: Robot {robot_id} has exceeded max recovery actions ({MAX_ACTIONS_PER_WINDOW} in 5 min)."

    # 2. State-Based Invariant Checks — low battery blocks all navigation recovery
    if action in NAVIGATION_ACTIONS and robot_state.get("battery_pct", 0) < 15.0:
        return False, "SAFETY REJECT: Battery too low (<15%) for navigation recovery. Must route to charging dock."

    # 3. Record Action Timestamp
    ACTION_HISTORY[robot_id].append(now)
    return True, "SAFE"