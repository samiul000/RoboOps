# Setup Guide

Step-by-step guide to run RoboOps on Windows with WSL.

## Prerequisites

- Windows 10/11 with WSL2 enabled
- Ubuntu WSL distribution
- Python 3.10+
- Node.js (for TrueForge and mcp-proxy)
- Git

## 1. WSL Setup

Open PowerShell and install WSL if not already done:

```powershell
wsl --install
```

Open your WSL terminal and install dependencies:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv curl
```

## 2. Ollama Setup (Windows)

### Install Ollama

Download and install from [ollama.com](https://ollama.com/download/windows).

### Pull the Model

```powershell
ollama pull qwen2.5-coder:7b
```

### Bind to All Interfaces

Ollama defaults to `127.0.0.1` which WSL cannot reach. Set a persistent env var:

```powershell
[System.Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "User")
```

Then restart Ollama:

1. Right-click Ollama icon in system tray → **Quit**
2. Relaunch Ollama from Start menu

### Verify

```powershell
netstat -ano | findstr :11434
```

Should show `0.0.0.0:11434 LISTENING`.

### Get Windows Host IP for WSL

From WSL:

```bash
cat /etc/resolv.conf | grep nameserver
```

Note the IP (e.g., `10.255.255.254`).

### Test from WSL

```bash
curl http://<windows-host-ip>:11434/api/tags
```

Should return JSON with your installed models.

**If connection fails**, the Windows firewall is blocking it. Run in PowerShell as Admin:

```powershell
New-NetFirewallRule -DisplayName "Ollama WSL" -Direction Inbound -LocalPort 11434 -Protocol TCP -Action Allow
```

## 3. Clone and Setup Project

In WSL:

```bash
# Clone the repo
git clone https://github.com/your-org/roboops_agent.git
cd roboops_agent

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy env file
cp .env.example .env
```

### Configure Environment

Edit `.env`:

```bash
nano .env
```

Set:

```env
ACTIVE_AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://<windows-host-ip>:11434/v1
OLLAMA_MODEL=qwen2.5-coder:7b
```

Replace `<windows-host-ip>` with the IP from the previous step.

## 4. TrueForge Setup

### Install TrueForge

```bash
npm install -g @truefoundry/trueforge
```

Or run directly with npx:

```bash
npx @truefoundry/trueforge@latest
```

### Start TrueForge

```bash
trueforge
# or
npx @truefoundry/trueforge@latest
```

TrueForge starts at `http://localhost:8790`.

### Configure TrueForge UI

1. **Settings → Models**
   - Click **Add Model**
   - Name: `Ollama Local`
   - Provider: **OpenAI Compatible**
   - Base URL: `http://<windows-host-ip>:11434/v1`
   - API Key: `ollama` (placeholder)
   - Model: `qwen2.5-coder:7b`
   - Save

2. **Settings → Connectors**
   - Click **Add Connector**
   - Name: `robot-fleet`
   - Transport: **HTTP/SSE**
   - URL: `http://localhost:8080/mcp`
   - Save

## 5. MCP Server Setup

The MCP server runs via `mcp-proxy` which exposes the stdio server as HTTP for TrueForge.

### Start mcp-proxy

In a new WSL terminal:

```bash
cd ~/roboops_agent
npx mcp-proxy --port 8080 -- python mcp_server/robot_fleet_mcp.py
```

You should see:

```
starting server on port 8080
```

### Verify Connection

In TrueForge, go to **Settings → Connectors**. The `robot-fleet` connector should show **Connected** with 6 tools listed:

- `get_fleet_telemetry`
- `get_incident_log_file`
- `execute_robot_action`
- `get_current_datetime`
- `safety_invariant_check`
- `restart_planner`

## 6. Create the Agent

In TrueForge UI:

1. Click **"Save Agent"** (top-right of chat)
2. Name: `RoboOps-Incident-Commander`
3. Model: `Ollama Local` (or your configured model)
4. Connector: `robot-fleet`
5. Instructions, paste this:

```
You are the RoboOps Incident Commander for a ROS 2 AMR fleet.

AVAILABLE MCP TOOLS (use these exact names):
- get_fleet_telemetry(robot_id)
- get_incident_log_file(robot_id)
- execute_robot_action(robot_id, action, operator_approval)
- get_current_datetime()
- safety_invariant_check(robot_id)
- restart_planner(robot_id, zone)

RULES:
1. Always call get_fleet_telemetry(robot_id) first when an alert arrives.
2. Call get_current_datetime() for timestamp.
3. Call safety_invariant_check(robot_id) to verify safety.
4. Propose recovery with specific tool calls from the list above.
5. NEVER call execute_robot_action or restart_planner without human approval.
6. NEVER invent tool names not listed above.
```

6. Save

## 7. Test

In TrueForge chat, type:

```
AMR-04 in Warehouse Zone 2 has NAV2_PLANNER_RECOVERY_EXHAUSTED. Diagnose and recover.
```

The agent should:

1. Call `get_fleet_telemetry("AMR-04")`
2. Call `get_current_datetime()`
3. Call `safety_invariant_check("AMR-04")`
4. Propose a recovery plan
5. Wait for your approval

## Troubleshooting

### Ollama: "Connection refused" from WSL

- Verify Ollama is running: `Get-Process ollama` in PowerShell
- Verify binding: `netstat -ano | findstr :11434` should show `0.0.0.0:11434`
- Check firewall: `New-NetFirewallRule -DisplayName "Ollama WSL" -Direction Inbound -LocalPort 11434 -Protocol TCP -Action Allow`
- Try gateway IP: `curl http://$(ip route | grep default | awk '{print $3}')/api/tags`

### TrueForge: "Cannot connect to API"

- The model base URL must use the Windows host IP, not `localhost`
- Get the IP: `cat /etc/resolv.conf | grep nameserver`
- Update in TrueForge Settings → Models

### MCP Server: Tools not showing

- Restart mcp-proxy after code changes:
  ```bash
  pkill -f mcp-proxy
  npx mcp-proxy --port 8080 -- python mcp_server/robot_fleet_mcp.py
  ```
- Verify connector shows **Connected** in TrueForge Settings → Connectors

### Agent: Hallucinating tool names

- Ensure agent instructions list all 6 tools explicitly
- Ensure model supports tool calling (7B+ recommended)
- Verify tools are visible in connector settings (Tools: 6)

### Agent: Not calling tools at all

- Check that the MCP server is running and connected
- Try a forced tool call: `Call get_fleet_telemetry for AMR-04 and return raw JSON`
- If still failing, upgrade to a larger model (qwen2.5-coder:7b or gpt-4o)

## Running Tests

```bash
cd ~/roboops_agent
source .venv/bin/activate

# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=mcp_server --cov-report=term-missing --cov-fail-under=85
```

## Architecture Overview

```
Windows Host                    WSL
┌─────────────────┐    ┌──────────────────────────────────────┐
│   Ollama        │    │                                      │
│   :11434        │◄───│  mcp-proxy :8080                     │
│   (0.0.0.0)     │    │      │                               │
└─────────────────┘    │      ▼                               │
                       │  robot_fleet_mcp.py (stdio)          │
                       │      │                               │
                       │      ▼                               │
                       │  TrueForge :8790                     │
                       │  (Agent Runtime + UI)                │
                       └──────────────────────────────────────┘
```

## Port Reference

| Service   | Port  | Binding                    |
| --------- | ----- | -------------------------- |
| Ollama    | 11434 | `0.0.0.0` (all interfaces) |
| mcp-proxy | 8080  | `localhost`                |
| TrueForge | 8790  | `localhost`                |
