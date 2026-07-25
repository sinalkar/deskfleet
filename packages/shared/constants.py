"""Shared constants used across the API and UI.

Kept dependency-free so both the FastAPI service and the Streamlit UI can import
these values without pulling in heavy packages.
"""

from __future__ import annotations

from enum import Enum


class Decision(str, Enum):
    """Terminal decision for a resolved ticket."""

    RESOLVED = "RESOLVED"
    ESCALATE = "ESCALATE"
    REFUSE = "REFUSE"


class Category(str, Enum):
    """Ticket classification categories."""

    ORDER = "order"
    PRODUCT = "product"
    REFUND = "refund"
    OTHER = "other"


class ToolStatus(str, Enum):
    """Audit status for a tool invocation."""

    OK = "ok"
    ERROR = "error"
    BLOCKED = "blocked"
    SANITIZED = "sanitized"  # succeeded, but injection payload quarantined from result


DECISIONS = [d.value for d in Decision]
CATEGORIES = [c.value for c in Category]

# Color hints for the UI decision badge.
DECISION_COLORS = {
    Decision.RESOLVED.value: "#1a7f37",  # green
    Decision.ESCALATE.value: "#9a6700",  # amber
    Decision.REFUSE.value: "#cf222e",  # red
}
