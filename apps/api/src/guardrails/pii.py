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
# Business identifiers that must survive redaction. A 10-digit order number
# written inline ("order 1234567890") otherwise matches the phone pattern, and
# redacting it destroys the very fact the researcher needs to do a lookup.
# These spans are masked out before redaction and restored afterwards.
_PROTECTED_REF = re.compile(
    r"\b(order|invoice|tracking|ticket|reference|ref|awb)\b"
    r"\s*(?:id|no\.?|number|#)?\s*[:#]?\s*\d{3,}\b",
    re.I,
)

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


def _mask_protected(text: str) -> tuple[str, list[str]]:
    """Swap protected business refs for digit-free placeholders.

    The placeholder encodes its index as letters (0->a, 1->b, ...) and is wrapped
    in NUL bytes, so it cannot itself be matched by any digit-based PII pattern
    or appear in real ticket text.
    """
    saved: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        saved.append(match.group(0))
        token = "".join(chr(97 + int(d)) for d in str(len(saved) - 1))
        return f"\x00P{token}\x00"

    return _PROTECTED_REF.sub(_stash, text), saved


def _restore_protected(text: str, saved: list[str]) -> str:
    for index, original in enumerate(saved):
        token = "".join(chr(97 + int(d)) for d in str(index))
        text = text.replace(f"\x00P{token}\x00", original)
    return text


def redact_pii(text: str | None) -> str:
    """Replace detected PII spans with ``[REDACTED]``.

    Order/invoice/tracking references are preserved — they are business
    identifiers the agent needs, not personal data.
    """
    if not text:
        return text or ""

    redacted, saved = _mask_protected(text)
    for _label, pattern in _PII_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    return _restore_protected(redacted, saved)


def find_pii(text: str | None) -> dict[str, int]:
    """Return a count of PII spans by type — used for tests/diagnostics.

    Applies the same protected-reference masking as :func:`redact_pii` so the
    counts always describe what would actually be redacted.
    """
    counts: dict[str, int] = {}
    if not text:
        return counts

    masked, _ = _mask_protected(text)
    for label, pattern in _PII_PATTERNS:
        matches = pattern.findall(masked)
        if matches:
            counts[label] = len(matches)
    return counts
