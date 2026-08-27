# ROS 2 Nav2 Fleet Diagnostics & Recovery Skill

## Domain Diagnostic Rules:

1. **Ghost Costmap Trap:**
   - _Condition:_ `costmap_trapped_footprint == True` and error is `NAV2_PLANNER_RECOVERY_EXHAUSTED`.
   - _Cause:_ A person or pallet moved away, but inflation layer persisted in local costmap.
   - _Solution:_ Call `execute_robot_action` with `clear_costmap` followed by `replan_path`.

2. **Wheel Slip & Odometry Failure:**
   - _Condition:_ `covariance_spike > 1.5` and `amcl_divergence > 2.0m`.
   - _Solution:_ Call `execute_robot_action` with `abort_mission` and request manual teleoperation.

## Critical Safety Protocol:

- **NEVER** dispatch `execute_robot_action` on physical hardware without requesting **Human-In-The-Loop confirmation**.
