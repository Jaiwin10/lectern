"""SQLite storage. Every change to lesson text is also written to `versions`,
so no edit, AI draft or applied fix is ever lost."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from .config import settings

STEPS = ("research", "draft", "qc_facts", "qc_teaching")
JSON_FIELDS = ("research", "qc_facts", "qc_teaching", "steps")

SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    objective   TEXT NOT NULL,
    audience    TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    research    TEXT,
    qc_facts    TEXT,
    qc_teaching TEXT,
    steps       TEXT NOT NULL,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS versions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id  TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    content    TEXT NOT NULL,
    note       TEXT NOT NULL,
    author     TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS versions_lesson ON versions(lesson_id, id);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)


def _empty_steps() -> dict[str, dict[str, Any]]:
    return {s: {"status": "idle", "error": None, "started_at": None, "finished_at": None} for s in STEPS}


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for field in JSON_FIELDS:
        if field in out:
            out[field] = json.loads(out[field]) if out[field] else None
    return out


def create_lesson(title: str, objective: str, audience: str) -> dict[str, Any]:
    now = time.time()
    lesson_id = uuid.uuid4().hex[:12]
    with connect() as conn:
        conn.execute(
            "INSERT INTO lessons (id, title, objective, audience, steps, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (lesson_id, title, objective, audience, json.dumps(_empty_steps()), now, now),
        )
    return get_lesson(lesson_id)  # type: ignore[return-value]


def get_lesson(lesson_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        return _row(conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone())


def list_lessons() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, objective, steps, created_at, updated_at FROM lessons ORDER BY updated_at DESC"
        ).fetchall()
    return [_row(r) for r in rows]  # type: ignore[misc]


def update_lesson(lesson_id: str, **fields: Any) -> None:
    if not fields:
        return
    cols, values = [], []
    for key, value in fields.items():
        cols.append(f"{key} = ?")
        values.append(json.dumps(value) if key in JSON_FIELDS and value is not None else value)
    cols.append("updated_at = ?")
    values.append(time.time())
    values.append(lesson_id)
    with connect() as conn:
        conn.execute(f"UPDATE lessons SET {', '.join(cols)} WHERE id = ?", values)


def set_step(lesson_id: str, step: str, status: str, error: str | None = None) -> None:
    """Read-modify-write of one step inside a single transaction."""
    now = time.time()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT steps FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        if row is None:
            return
        steps = json.loads(row["steps"])
        entry = steps.setdefault(step, {})
        entry["status"] = status
        entry["error"] = error
        if status == "running":
            entry["started_at"] = now
            entry["finished_at"] = None
        elif status in ("done", "failed", "blocked"):
            entry["finished_at"] = now
        conn.execute("UPDATE lessons SET steps = ?, updated_at = ? WHERE id = ?", (json.dumps(steps), now, lesson_id))


def save_content(lesson_id: str, content: str, note: str, author: str) -> int:
    """Store new lesson text and a matching version row in one transaction."""
    now = time.time()
    with connect() as conn:
        conn.execute("UPDATE lessons SET content = ?, updated_at = ? WHERE id = ?", (content, now, lesson_id))
        cur = conn.execute(
            "INSERT INTO versions (lesson_id, content, note, author, created_at) VALUES (?, ?, ?, ?, ?)",
            (lesson_id, content, note, author, now),
        )
        return int(cur.lastrowid or 0)


def list_versions(lesson_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, note, author, created_at, length(content) AS size FROM versions"
            " WHERE lesson_id = ? ORDER BY id DESC",
            (lesson_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_version(lesson_id: str, version_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM versions WHERE lesson_id = ? AND id = ?", (lesson_id, version_id)
        ).fetchone()
    return dict(row) if row else None


def count_versions(lesson_id: str) -> int:
    with connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM versions WHERE lesson_id = ?", (lesson_id,)).fetchone()[0])


def delete_lesson(lesson_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))


def mark_interrupted() -> None:
    """If the server stopped mid-run, turn stuck steps into retryable failures."""
    with connect() as conn:
        rows = conn.execute("SELECT id, steps FROM lessons").fetchall()
        for row in rows:
            steps = json.loads(row["steps"])
            changed = False
            for entry in steps.values():
                if entry.get("status") in ("running", "pending"):
                    entry["status"] = "failed"
                    entry["error"] = "Interrupted because the server stopped. Retry this step."
                    changed = True
            if changed:
                conn.execute("UPDATE lessons SET steps = ? WHERE id = ?", (json.dumps(steps), row["id"]))
