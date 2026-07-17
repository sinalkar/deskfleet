"""Shared graph state."""

from __future__ import annotations

from typing import TypedDict


class TicketState(TypedDict, total=False):
    ticket_id: str
    ticket: str  # PII-redacted input
    order_id: str | None
    category: str | None  # order | product | refund | other
    facts: list[dict]  # tool results accumulated by the researcher
    draft: str | None
    review_feedback: str | None
    decision: str | None  # RESOLVED | ESCALATE | REFUSE
    escalation_reason: str | None
    iterations: int
    tool_calls: list[dict]  # audit trail (includes blocked attempts)
