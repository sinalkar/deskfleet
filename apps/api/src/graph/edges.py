"""Conditional routing with a deterministic max-iteration guard.

The review loop's termination is enforced here in code — never trusted to the
model. After the reviewer runs:

    approved                              -> END (decision=RESOLVED)
    not approved & iters <  MAX           -> responder (retry)
    not approved & iters >= MAX           -> END (decision=ESCALATE + reason)
"""

from __future__ import annotations

from langgraph.graph import END

from src.config import settings
from src.constants import Category, Decision
from src.graph.state import TicketState


def route_after_classifier(state: TicketState) -> str:
    """Return the next node name: ``"researcher"`` or ``END``.

    Tickets classified as ``other`` are out of scope for the supported
    categories (order, product, refund). They are escalated immediately
    without consuming LLM calls on the research/respond/review pipeline.
    """
    if state.get("category") == Category.OTHER.value:
        return END
    return "researcher"


def route_after_review(state: TicketState) -> str:
    """Return the next node name: ``"responder"`` or ``END``."""
    if state.get("decision") == Decision.RESOLVED.value:
        return END
    if state.get("iterations", 0) >= settings.max_review_iterations:
        return END  # reviewer already set decision=ESCALATE
    return "responder"
