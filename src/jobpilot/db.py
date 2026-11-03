"""SQLite storage for job applications.

One table, no server, no migrations framework: the schema is created on first
use and additive columns are handled with ``ALTER TABLE`` when needed.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_DB = Path("jobpilot.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company      TEXT NOT NULL DEFAULT '',
    role         TEXT NOT NULL DEFAULT '',
    location     TEXT NOT NULL DEFAULT '',
    seniority    TEXT NOT NULL DEFAULT '',
    work_mode    TEXT NOT NULL DEFAULT '',
    salary_low   INTEGER,
    salary_high  INTEGER,
    currency     TEXT NOT NULL DEFAULT '',
    deadline     TEXT,
    url          TEXT NOT NULL DEFAULT '',
    contact      TEXT NOT NULL DEFAULT '',
    skills       TEXT NOT NULL DEFAULT '[]',
    source       TEXT NOT NULL DEFAULT 'manual',
    notes        TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'applied',
    created_on   TEXT NOT NULL,
    fingerprint  TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_created ON applications(created_on);
"""

STATUSES = ("applied", "screening", "interview", "offer", "rejected", "ghosted")


def connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def fingerprint(company: str, role: str, url: str) -> str:
    """Stable key so re-importing the same posting does not duplicate it."""
    basis = (url or f"{company.strip().lower()}|{role.strip().lower()}").rstrip("/")
    return basis


def add(conn: sqlite3.Connection, record: dict[str, Any]) -> int | None:
    """Insert one record. Returns the new id, or None if it already existed."""
    fp = fingerprint(record.get("company", ""), record.get("role", ""), record.get("url", ""))
    try:
        cur = conn.execute(
            """INSERT INTO applications
               (company, role, location, seniority, work_mode, salary_low, salary_high,
                currency, deadline, url, contact, skills, source, notes, status, created_on,
                fingerprint)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record.get("company", ""), record.get("role", ""), record.get("location", ""),
                record.get("seniority", ""), record.get("work_mode", ""),
                record.get("salary_low"), record.get("salary_high"), record.get("currency", ""),
                record.get("deadline"), record.get("url", ""), record.get("contact", ""),
                json.dumps(record.get("skills") or []), record.get("source", "manual"),
                record.get("notes", ""), record.get("status", "applied"),
                record.get("created_on") or date.today().isoformat(), fp,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    except sqlite3.IntegrityError:
        return None


def add_many(conn: sqlite3.Connection, records: Iterable[dict[str, Any]]) -> tuple[int, int]:
    added = skipped = 0
    for record in records:
        if add(conn, record) is None:
            skipped += 1
        else:
            added += 1
    return added, skipped


def list_applications(conn: sqlite3.Connection, status: str | None = None,
                      limit: int = 100) -> list[dict[str, Any]]:
    query = "SELECT * FROM applications"
    params: list[Any] = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_on DESC, id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["skills"] = json.loads(item.get("skills") or "[]")
        out.append(item)
    return out


def update_status(conn: sqlite3.Connection, app_id: int, status: str) -> bool:
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")
    cur = conn.execute("UPDATE applications SET status = ? WHERE id = ?", (status, app_id))
    conn.commit()
    return cur.rowcount > 0


def summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Counts per status, plus the busiest skill and the nearest deadline."""
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM applications GROUP BY status ORDER BY n DESC"
    ).fetchall()
    by_status = {row["status"]: row["n"] for row in rows}
    total = sum(by_status.values())

    skills: dict[str, int] = {}
    for item in list_applications(conn, limit=1000):
        for skill in item["skills"]:
            skills[skill] = skills.get(skill, 0) + 1
    top_skills = sorted(skills.items(), key=lambda kv: kv[1], reverse=True)[:5]

    upcoming = conn.execute(
        "SELECT company, role, deadline FROM applications "
        "WHERE deadline IS NOT NULL AND deadline >= date('now') "
        "ORDER BY deadline ASC LIMIT 1"
    ).fetchone()

    answered = sum(by_status.get(s, 0) for s in ("screening", "interview", "offer", "rejected"))
    return {
        "total": total,
        "by_status": by_status,
        "response_rate": round(100 * answered / total, 1) if total else 0.0,
        "top_skills": top_skills,
        "next_deadline": dict(upcoming) if upcoming else None,
    }
