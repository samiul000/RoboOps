# RoboOps: Autonomous Fleet Incident Triage & Self-Healing Agent

RoboOps is an autonomous incident triage and recovery agent built on **TrueForge** for ROS 2 Autonomous Mobile Robot (AMR) fleets.

## Key Features

- **Harness:** Powered by TrueForge agent runtime.
- **MCP Tool Integration:** Connects to ROS 2 topic telemetry and actuator actions via FastMCP.
- **Sandboxed Diagnostics:** Isolates odometry and costmap diagnostics inside Daytona sandbox.
- **Human-In-The-Loop:** Enforces operator approval before executing actuator commands.
- **Multi-Provider AI:** Supports local on-premise execution via **Ollama** (`qwen2.5-coder:7b`) and Cloud models (`gpt-4o`).
- **Code Quality:** Governed by **Qodo** PR automated reviews.
