# ROS 2 Nav2 Fleet Triage

## Diagnostic Rules

| Fault | Condition | Action |
|---|---|---|
| Ghost Costmap | `costmap_trapped_footprint == True` AND error == `NAV2_PLANNER_RECOVERY_EXHAUSTED` | `clear_costmap` → `replan_path` |
| Wheel Slip / Odometry Loss | `covariance_spike > 1.5` AND `amcl_divergence > 2.0` | `abort_mission` → request manual teleop |

## Safety Protocol

`execute_robot_action` requires **Human-In-The-Loop confirmation** before every dispatch. No exceptions.
