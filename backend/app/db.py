"""SQLite persistence for ArchIntel AI. No MongoDB required."""
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

# backend/app/db.py -> backend/archintel.db
BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "archintel.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def save(project_id: str, name: str, state: dict[str, Any]) -> None:
    """Insert or update a project; compatible with existing main.py calls."""
    if not project_id:
        raise ValueError("project_id cannot be empty")
    if not isinstance(state, dict):
        raise TypeError("state must be a dictionary")

    payload = json.dumps(state, ensure_ascii=False, default=str)
    with _connect() as conn:
        conn.execute("""
            INSERT INTO projects (project_id, name, state_json)
            VALUES (?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                name = excluded.name,
                state_json = excluded.state_json,
                updated_at = CURRENT_TIMESTAMP
        """, (project_id, name, payload))
        conn.commit()


def get(project_id: str) -> Optional[dict[str, Any]]:
    """Return the {'name': ..., 'state': ...} shape expected by main.py."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT name, state_json FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()

    if row is None:
        return None
    return {"name": row["name"], "state": json.loads(row["state_json"])}


def delete(project_id: str) -> bool:
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM projects WHERE project_id = ?", (project_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
