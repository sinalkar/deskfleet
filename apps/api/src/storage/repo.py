"""Persistence helpers for tickets and their tool-call audit trail."""

from __future__ import annotations

import json
from typing import Any

from src.storage.db import get_connection


def insert_ticket(
    *,
    ticket_id: str,
    body: str,
    category: str | None,
    decision: str | None,
    reply: str | None,
    escalation_reason: str | None,
    iterations: int,
    latency_ms: float,
    cost_usd: float,
    db_path: str | None = None,
) -> None:
    """Upsert a resolved ticket record.

    ``body`` and ``reply`` are expected to already be PII-redacted by the
    caller — persistence never stores raw PII.
    """
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO tickets
                (id, body, category, decision, reply, escalation_reason,
                 iterations, latency_ms, cost_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                body=excluded.body,
                category=excluded.category,
                decision=excluded.decision,
                reply=excluded.reply,
                escalation_reason=excluded.escalation_reason,
                iterations=excluded.iterations,
                latency_ms=excluded.latency_ms,
                cost_usd=excluded.cost_usd
            """,
            (
                ticket_id,
                body,
                category,
                decision,
                reply,
                escalation_reason,
                iterations,
                latency_ms,
                cost_usd,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def insert_tool_call(
    *,
    ticket_id: str,
    tool_name: str,
    args: dict[str, Any] | None,
    result: Any,
    status: str,
    db_path: str | None = None,
) -> None:
    """Append an entry to the tool-call audit trail."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO tool_calls (ticket_id, tool_name, args_json, result_json, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                tool_name,
                json.dumps(args or {}, default=str),
                json.dumps(result, default=str),
                status,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def recent_tickets(limit: int = 10, db_path: str | None = None) -> list[dict[str, Any]]:
    """Return the most recent tickets for the demo ``/tickets`` endpoint."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM tickets ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def tool_calls_for_ticket(ticket_id: str, db_path: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM tool_calls WHERE ticket_id = ? ORDER BY id ASC",
            (ticket_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
