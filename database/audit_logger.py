import json
import sqlite3
import time

DB_PATH = "roboops_audit.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS incident_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                robot_id TEXT,
                error_code TEXT,
                agent_diagnosis TEXT,
                remediation_action TEXT,
                operator_approval TEXT,
                execution_result TEXT
            )
        """)
    print("✅ [Database] roboops_audit.db initialized successfully.")

def log_incident_event(robot_id: str, error: str, diagnosis: dict, action: str, approved_by: str, result: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO incident_audit_log 
            (timestamp, robot_id, error_code, agent_diagnosis, remediation_action, operator_approval, execution_result)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (time.time(), robot_id, error, json.dumps(diagnosis), action, approved_by, result))

if __name__ == "__main__":
    init_db()