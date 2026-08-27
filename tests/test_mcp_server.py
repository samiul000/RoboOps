"""Unit tests to verify MCP tools and safety constraints."""
import json
import pytest
from mcp_server.robot_fleet_mcp import get_fleet_telemetry, execute_robot_action

def test_get_valid_telemetry():
    res = json.loads(get_fleet_telemetry("AMR-04"))
    assert res["status"] == "ERROR_NAVIGATION_STUCK"
    assert "battery_pct" in res

def test_get_invalid_robot():
    res = json.loads(get_fleet_telemetry("INVALID_BOT"))
    assert "error" in res

def test_execute_safe_action():
    res = json.loads(execute_robot_action("AMR-04", "clear_costmap"))
    assert res["status"] == "SUCCESS"
    assert res["new_fleet_status"] == "ACTIVE_TRANSIT"

def test_execute_invalid_action():
    res = json.loads(execute_robot_action("AMR-04", "unauthorized_command"))
    assert "error" in res