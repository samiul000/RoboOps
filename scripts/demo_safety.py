"""Reproducible safety demo for the Drawerrr challenge."""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from mcp_server.robot_fleet_mcp import (
    execute_robot_action,
    get_incident_log_file,
    issue_approval,
    restart_planner,
    safety_invariant_check,
)
from mcp_server.safety_guard import evaluate_safety_constraints


def show(label, value):
    print(f"\n=== {label} ===")
    if isinstance(value, str):
        try:
            print(json.dumps(json.loads(value), indent=2))
        except json.JSONDecodeError:
            print(value)
    else:
        print(value)


def main():
    print("RoboOps physical-world action safety demo")
    show("Unsafe action without approval", execute_robot_action("AMR-04", "clear_costmap"))
    show("Safety invariants", safety_invariant_check("AMR-04"))

    stale = {"battery_pct": 90.0, "last_telemetry_at": 0}
    safe, reason = evaluate_safety_constraints("AMR-04", "clear_costmap", stale)
    show("Stale telemetry decision", {"safe": safe, "reason": reason})

    approval = issue_approval("AMR-04", "clear_costmap", ttl_seconds=60)
    show("Approved action", execute_robot_action("AMR-04", "clear_costmap", operator_approval=approval))
    show("Reused approval is rejected", execute_robot_action("AMR-04", "clear_costmap", operator_approval=approval))
    show("Planner restart without approval", restart_planner("AMR-04", "Zone-2"))
    show("Incident log (path checked)", get_incident_log_file("AMR-04"))


if __name__ == "__main__":
    main()