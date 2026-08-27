"""Unit tests to verify MCP tools, safety guardrails, and sandbox diagnostics."""
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from database.audit_logger import init_db, log_incident_event
from mcp_server.robot_fleet_mcp import (
    FLEET_STATE,
    execute_robot_action,
    get_fleet_telemetry,
)
from mcp_server.safety_guard import ACTION_HISTORY, evaluate_safety_constraints
from sandbox.diagnose_logs import analyze_telemetry_logs

INITIAL_FLEET_STATE = {
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

@pytest.fixture(autouse=True)
def reset_state():
    FLEET_STATE.clear()
    FLEET_STATE.update({k: dict(v) for k, v in INITIAL_FLEET_STATE.items()})
    ACTION_HISTORY.clear()
    yield

# --- MCP Tools ---

def test_get_valid_telemetry():
    res = json.loads(get_fleet_telemetry("AMR-04"))
    assert res["status"] == "ERROR_NAVIGATION_STUCK"
    assert "battery_pct" in res

def test_get_invalid_robot():
    res = json.loads(get_fleet_telemetry("INVALID_BOT"))
    assert "error" in res

def test_get_incident_log():
    from mcp_server.robot_fleet_mcp import get_incident_log_file
    res = get_incident_log_file("AMR-04")
    assert res == "sandbox/amr_04_incident.json"

def test_get_incident_log_none():
    from mcp_server.robot_fleet_mcp import get_incident_log_file
    res = json.loads(get_incident_log_file("AMR-02"))
    assert "error" in res

def test_execute_safe_action():
    res = json.loads(execute_robot_action("AMR-04", "clear_costmap"))
    assert res["status"] == "SUCCESS"
    assert res["new_fleet_status"] == "ACTIVE_TRANSIT"

def test_execute_soft_reset():
    res = json.loads(execute_robot_action("AMR-04", "soft_reset_nav2"))
    assert res["status"] == "SUCCESS"
    assert res["new_fleet_status"] == "RECOVERING"

def test_execute_abort_mission():
    res = json.loads(execute_robot_action("AMR-04", "abort_mission"))
    assert res["status"] == "SUCCESS"
    assert res["new_fleet_status"] == "MANUAL_HOLD"

def test_execute_replan_path():
    res = json.loads(execute_robot_action("AMR-04", "replan_path"))
    assert res["status"] == "SUCCESS"
    assert res["new_fleet_status"] == "ACTIVE_TRANSIT"

def test_execute_invalid_action():
    res = json.loads(execute_robot_action("AMR-04", "unauthorized_command"))
    assert "error" in res

def test_execute_unknown_robot():
    res = json.loads(execute_robot_action("AMR-99", "clear_costmap"))
    assert "error" in res

# --- Safety Guard ---

def test_safety_guard_passes_normally():
    safe, reason = evaluate_safety_constraints("AMR-04", "clear_costmap", FLEET_STATE["AMR-04"])
    assert safe is True
    assert reason == "SAFE"

def test_safety_guard_rate_limit():
    for _ in range(3):
        evaluate_safety_constraints("AMR-04", "clear_costmap", FLEET_STATE["AMR-04"])
    safe, reason = evaluate_safety_constraints("AMR-04", "clear_costmap", FLEET_STATE["AMR-04"])
    assert safe is False
    assert "SAFETY LOCKOUT" in reason

def test_safety_guard_low_battery():
    low_battery_robot = {"battery_pct": 10.0}
    safe, reason = evaluate_safety_constraints("AMR-04", "clear_costmap", low_battery_robot)
    assert safe is False
    assert "Battery too low" in reason

def test_safety_guard_low_battery_not_clear_costmap():
    low_battery_robot = {"battery_pct": 10.0}
    safe, _reason = evaluate_safety_constraints("AMR-04", "replan_path", low_battery_robot)
    assert safe is True

# --- Audit Logger ---

def test_init_db():
    import sqlite3
    tmp = Path(tempfile.mktemp(suffix=".db"))
    import database.audit_logger as mod
    original = mod.DB_PATH
    mod.DB_PATH = tmp
    try:
        init_db()
        assert tmp.exists()
        with sqlite3.connect(tmp) as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            assert any("incident_audit_log" in t[0] for t in tables)
    finally:
        mod.DB_PATH = original

def test_log_incident_event():
    import sqlite3
    tmp = Path(tempfile.mktemp(suffix=".db"))
    import database.audit_logger as mod
    original = mod.DB_PATH
    mod.DB_PATH = tmp
    try:
        init_db()
        log_incident_event("AMR-04", "NAV2_PLANNER_RECOVERY_EXHAUSTED",
                           {"root_cause": "ghost costmap"}, "clear_costmap", "operator_1", "SUCCESS")
        with sqlite3.connect(tmp) as conn:
            rows = conn.execute("SELECT * FROM incident_audit_log").fetchall()
            assert len(rows) == 1
            assert rows[0][2] == "AMR-04"
    finally:
        mod.DB_PATH = original

# --- Sandbox Diagnostics ---

def test_analyze_telemetry_logs():
    result = analyze_telemetry_logs()
    assert result["robot_id"] == "AMR-04"
    assert result["requires_human_approval"] is True
    assert "suggested_actions" in result
    assert result["covariance_spike"] > 0

def test_analyze_telemetry_logs_main(capsys):
    result = subprocess.run(
        ["python", "-m", "sandbox.diagnose_logs"],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
        check=False
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["robot_id"] == "AMR-04"
