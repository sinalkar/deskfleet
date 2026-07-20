"""PII is redacted on input and output, including in persistence."""

from __future__ import annotations

import pytest
from src.guardrails.pii import find_pii, redact_pii
from src.schemas import ResolveRequest
from src.service import resolve_ticket
from src.storage import repo


def test_redacts_common_pii_types():
    text = (
        "Reach me at jane.doe@example.com or 555-123-4567, "
        "SSN 123-45-6789, card 4111111111111111"
    )
    out = redact_pii(text)
    assert "jane.doe@example.com" not in out
    assert "555-123-4567" not in out
    assert "123-45-6789" not in out
    assert "4111111111111111" not in out
    assert out.count("[REDACTED]") >= 4


def test_redaction_is_idempotent():
    once = redact_pii("email me: a@b.com")
    twice = redact_pii(once)
    assert once == twice


def test_find_pii_counts():
    counts = find_pii("a@b.com and c@d.com, ssn 111-22-3333")
    assert counts.get("email") == 2
    assert counts.get("ssn") == 1


def test_inbound_and_outbound_redaction_in_response_and_db(make_graph):
    from tests.conftest import FakeLLM

    # Draft the model produces contains PII that must be scrubbed outbound.
    llm = FakeLLM(
        approve=True,
        draft_text="Sure! I'll email you at agent@corp.com and call 555-987-6543.",
    )
    graph = make_graph(llm)

    req = ResolveRequest(
        ticket="My email is customer@home.com and SSN 123-45-6789, where is order 2?"
    )
    resp = resolve_ticket(graph, req)

    # Outbound reply is redacted.
    assert "agent@corp.com" not in (resp.reply or "")
    assert "555-987-6543" not in (resp.reply or "")
    assert "[REDACTED]" in (resp.reply or "")

    # Persistence stores redacted body + reply (never raw PII).
    row = {r["id"]: r for r in repo.recent_tickets(5)}[resp.ticket_id]
    assert "customer@home.com" not in row["body"]
    assert "123-45-6789" not in row["body"]
    assert "agent@corp.com" not in (row["reply"] or "")


# ── protected business references ────────────────────────────────────────────
# A 10-digit order number matches the phone pattern. Redacting it destroys the
# exact fact the researcher needs to perform a lookup, so these spans are
# preserved while genuine PII around them is still removed.


@pytest.mark.parametrize(
    "text",
    [
        "Where is my order 1234567890?",
        "Order #1234567890 has not arrived",
        "tracking no: 9876543210 please update",
        "invoice number 1234567890 is wrong",
        "ref: 5551234567 needs review",
    ],
)
def test_order_style_references_survive_redaction(text):
    assert redact_pii(text) == text


def test_pii_still_redacted_alongside_protected_reference():
    text = "Order 1234567890 late. Call 555-123-4567 or a@b.com"
    out = redact_pii(text)

    assert "1234567890" in out  # business ref preserved
    assert "555-123-4567" not in out  # phone redacted
    assert "a@b.com" not in out  # email redacted


def test_bare_phone_number_is_still_redacted():
    """The protection must be scoped to labeled refs, not any 10-digit run."""
    assert "5551234567" not in redact_pii("call 5551234567 about invoice 1234567890")


def test_protected_reference_redaction_is_idempotent():
    text = "Order 1234567890 — reach me at a@b.com"
    assert redact_pii(redact_pii(text)) == redact_pii(text)
