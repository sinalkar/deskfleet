"""PII redaction.

Applied to the inbound ticket (before it enters state/persistence) and to the
outbound draft (before it is returned or stored). Redaction is idempotent —
running it twice yields the same output.
"""

from __future__ import annotations

import re

_REDACTED = "[REDACTED]"

# Order matters: match the most specific / longest patterns first so a card
# number is not partially eaten by the phone matcher, etc.
_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    # 13-16 digit card numbers, optionally grouped by spaces or dashes.
    ("card", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    # Phone: US-style with optional country code / separators.
    (
        "phone",
        re.compile(
            r"(?<!\d)(?:\+?\d{1,2}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"
        ),
    ),
]


def redact_pii(text: str | None) -> str:
    """Replace detected PII spans with ``[REDACTED]``."""
    if not text:
        return text or ""
    redacted = text
    for _label, pattern in _PII_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    return redacted


def find_pii(text: str | None) -> dict[str, int]:
    """Return a count of PII spans by type — used for tests/diagnostics."""
    counts: dict[str, int] = {}
    if not text:
        return counts
    for label, pattern in _PII_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            counts[label] = len(matches)
    return counts
