"""Canonical constants for the API service.

Vendored inside the API package so the Docker image (build context ``apps/api``)
is fully self-contained. The same values are mirrored in
``packages/shared/constants.py`` for tooling/UI that runs from the monorepo root.
"""

from __future__ import annotations

from enum import Enum


class Decision(str, Enum):
    RESOLVED = "RESOLVED"
    ESCALATE = "ESCALATE"
    REFUSE = "REFUSE"


class Category(str, Enum):
    ORDER = "order"
    PRODUCT = "product"
    REFUND = "refund"
    OTHER = "other"


class ToolStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    BLOCKED = "blocked"


DECISIONS = [d.value for d in Decision]
CATEGORIES = [c.value for c in Category]

DECISION_COLORS = {
    Decision.RESOLVED.value: "#1a7f37",
    Decision.ESCALATE.value: "#9a6700",
    Decision.REFUSE.value: "#cf222e",
}
