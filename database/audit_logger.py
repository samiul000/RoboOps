import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta

DB_PATH = "roboops_audit.db"
_DB_LOCK = threading.Lock()
_INTEGRITY_KEY = os.getenv("ROBOOPS_AUDIT_INTEGRITY_KEY", "roboops-local-dev-key")


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _columns(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(incident_audit_log)").fetchall()}


def init_db():
    with _DB_LOCK, _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS incident_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                robot_id TEXT,
                error_code TEXT,
                agent_diagnosis TEXT,
                remediation_action TEXT,
                operator_approval TEXT,
                execution_result TEXT,
                integrity_hash TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_robot_time ON incident_audit_log(robot_id, timestamp)")
        if "integrity_hash" not in _columns(conn):
            conn.execute("ALTER TABLE incident_audit_log ADD COLUMN integrity_hash TEXT")
    print("✅ [Database] roboops_audit.db initialized successfully.")


def _hash_event(timestamp, robot_id, error_code, diagnosis, action, approved_by, result):
    payload = "|".join([
        str(timestamp), str(robot_id), str(error_code), json.dumps(diagnosis, sort_keys=True),
        str(action), str(approved_by), str(result), _INTEGRITY_KEY
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def log_incident_event(robot_id: str, error: str, diagnosis: dict, action: str, approved_by: str, result: str):
    init_db()
    timestamp = time.time()
    digest = _hash_event(timestamp, robot_id, error, diagnosis, action, approved_by, result)
    with _DB_LOCK, _connect() as conn:
        conn.execute("""
            INSERT INTO incident_audit_log
            (timestamp, robot_id, error_code, agent_diagnosis, remediation_action, operator_approval, execution_result, integrity_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, robot_id, error, json.dumps(diagnosis), action, approved_by, result, digest))


def purge_old_events(retention_days: int = 30):
    cutoff = time.time() - timedelta(days=retention_days).total_seconds()
    with _DB_LOCK, _connect() as conn:
        conn.execute("DELETE FROM incident_audit_log WHERE timestamp < ?", (cutoff,))


def backup_db(destination: str):
    init_db()
    destination_path = destination
    with _DB_LOCK:
        shutil.copy2(DB_PATH, destination_path)


def verify_integrity() -> list[dict]:
    init_db()
    failures = []
    with _DB_LOCK, _connect() as conn:
        rows = conn.execute("""
            SELECT timestamp, robot_id, error_code, agent_diagnosis, remediation_action,
                   operator_approval, execution_result, integrity_hash
            FROM incident_audit_log
        """).fetchall()
    for row in rows:
        timestamp, robot_id, error_code, diagnosis_json, action, approved_by, result, digest = row
        diagnosis = json.loads(diagnosis_json) if diagnosis_json else {}
        expected = _hash_event(timestamp, robot_id, error_code, diagnosis, action, approved_by, result)
        if expected != digest:
            failures.append({"robot_id": robot_id, "timestamp": timestamp})
    return failures


if __name__ == "__main__":
    init_db()