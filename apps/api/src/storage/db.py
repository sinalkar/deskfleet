"""SQLite connection management and schema initialization (stdlib only)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id                TEXT PRIMARY KEY,
    body              TEXT NOT NULL,
    category          TEXT,
    decision          TEXT,
    reply             TEXT,
    escalation_reason TEXT,
    iterations        INTEGER DEFAULT 0,
    latency_ms        REAL DEFAULT 0,
    cost_usd          REAL DEFAULT 0,
    created_at        TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   TEXT NOT NULL,
    tool_name   TEXT NOT NULL,
    args_json   TEXT,
    result_json TEXT,
    status      TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_ticket ON tool_calls(ticket_id);
CREATE INDEX IF NOT EXISTS idx_tickets_created ON tickets(created_at);
"""


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Return a SQLite connection with row access by column name.

    ``check_same_thread=False`` because FastAPI may serve requests from a
    thread pool; each call opens its own short-lived connection.
    """
    path = db_path or settings.sqlite_path
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(db_path: str | None = None) -> None:
    """Create tables and indexes if they do not already exist."""
    conn = get_connection(db_path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
