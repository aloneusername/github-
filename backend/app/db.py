import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import get_settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    settings = get_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                repo_url TEXT NOT NULL UNIQUE,
                repo_name TEXT NOT NULL,
                local_path TEXT NOT NULL,
                status TEXT NOT NULL,
                report_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                event_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
            """
        )


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    conn = sqlite3.connect(settings.database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_project(project: dict[str, Any]) -> None:
    now = utc_now()
    with connect() as conn:
        existing = conn.execute("SELECT id FROM projects WHERE id = ?", (project["id"],)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE projects
                SET repo_url = ?, repo_name = ?, local_path = ?, status = ?,
                    report_json = ?, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    project["repo_url"],
                    project["repo_name"],
                    project["local_path"],
                    project["status"],
                    json.dumps(project.get("report"), ensure_ascii=False) if project.get("report") else None,
                    project.get("error"),
                    now,
                    project["id"],
                ),
            )
            return
        conn.execute(
            """
            INSERT INTO projects
                (id, repo_url, repo_name, local_path, status, report_json, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project["id"],
                project["repo_url"],
                project["repo_name"],
                project["local_path"],
                project["status"],
                json.dumps(project.get("report"), ensure_ascii=False) if project.get("report") else None,
                project.get("error"),
                now,
                now,
            ),
        )


def get_project(project_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _project_from_row(row) if row else None


def get_project_by_repo(repo_url: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE repo_url = ?", (repo_url,)).fetchone()
    return _project_from_row(row) if row else None


def list_projects() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
    return [_project_from_row(row) for row in rows]


def save_event(project_id: str, event: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events (project_id, event_json, created_at) VALUES (?, ?, ?)",
            (project_id, json.dumps(event, ensure_ascii=False), utc_now()),
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (utc_now(), project_id))


def clear_project_events(project_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM events WHERE project_id = ?", (project_id,))


def get_events_after(project_id: str, event_id: int = 0) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, event_json FROM events WHERE project_id = ? AND id > ? ORDER BY id ASC",
            (project_id, event_id),
        ).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        event = json.loads(row["event_json"])
        event["id"] = row["id"]
        events.append(event)
    return events


def _project_from_row(row: sqlite3.Row) -> dict[str, Any]:
    report = json.loads(row["report_json"]) if row["report_json"] else None
    return {
        "id": row["id"],
        "repo_url": row["repo_url"],
        "repo_name": row["repo_name"],
        "local_path": row["local_path"],
        "status": row["status"],
        "report": report,
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
