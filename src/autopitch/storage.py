"""SQLite persistence for analysis jobs and their reports.

Only the finished report is stored, never the uploaded PDF. Each row belongs to an anonymous
owner id supplied by the browser, so one visitor cannot list or open another's reports.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    status TEXT NOT NULL,          -- queued | running | done | failed
    stage TEXT NOT NULL DEFAULT 'queued',
    filename TEXT NOT NULL,
    company TEXT,
    score REAL,
    error TEXT,
    report TEXT,                   -- Report as JSON, once done
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_owner ON jobs(owner, created_at DESC);
"""

_SUMMARY = "id, status, stage, filename, company, score, error, created_at, updated_at"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JobStore:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)

    def _run(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return cur

    def create(self, owner: str, filename: str) -> str:
        job_id = uuid.uuid4().hex  # 128 random bits: unguessable
        now = _now()
        self._run(
            "INSERT INTO jobs (id, owner, status, filename, created_at, updated_at)"
            " VALUES (?, ?, 'queued', ?, ?, ?)",
            (job_id, owner, filename[:200], now, now),
        )
        return job_id

    def set_stage(self, job_id: str, stage: str) -> None:
        self._run(
            "UPDATE jobs SET status='running', stage=?, updated_at=? WHERE id=?",
            (stage, _now(), job_id),
        )

    def complete(self, job_id: str, report_json: str, company: str, score: float) -> None:
        self._run(
            "UPDATE jobs SET status='done', stage='done', report=?, company=?, score=?,"
            " updated_at=? WHERE id=?",
            (report_json, company, score, _now(), job_id),
        )

    def fail(self, job_id: str, message: str) -> None:
        self._run(
            "UPDATE jobs SET status='failed', stage='failed', error=?, updated_at=? WHERE id=?",
            (message, _now(), job_id),
        )

    def get(self, job_id: str, owner: str) -> dict[str, Any] | None:
        row = self._run(
            f"SELECT {_SUMMARY}, report FROM jobs WHERE id=? AND owner=?", (job_id, owner)
        ).fetchone()
        return dict(row) if row else None

    def list(self, owner: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._run(
            f"SELECT {_SUMMARY} FROM jobs WHERE owner=? ORDER BY created_at DESC LIMIT ?",
            (owner, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, job_id: str, owner: str) -> bool:
        return self._run("DELETE FROM jobs WHERE id=? AND owner=?", (job_id, owner)).rowcount > 0

    def fail_interrupted(self) -> int:
        """Jobs still marked queued/running belong to a process that died; fail them."""
        return self._run(
            "UPDATE jobs SET status='failed', stage='failed', error=?, updated_at=?"
            " WHERE status IN ('queued', 'running')",
            ("The server restarted before this analysis finished. Please run it again.", _now()),
        ).rowcount

    def purge(self, older_than_days: int) -> int:
        if older_than_days <= 0:
            return 0
        cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
        return self._run("DELETE FROM jobs WHERE created_at < ?", (cutoff,)).rowcount
