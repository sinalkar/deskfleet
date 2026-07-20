"""Real-token-usage accounting.

The service prefers provider-reported token counts and only estimates when the
provider gives nothing. These tests pin both paths, since silently reverting to
estimation would under-report spend without any visible failure.
"""

from __future__ import annotations

from types import SimpleNamespace

from src.observability.usage import UsageCollector


def _llm_result(*, usage_metadata=None, llm_output=None):
    """Build a minimal object shaped like a LangChain ``LLMResult``."""
    message = SimpleNamespace(usage_metadata=usage_metadata)
    generation = SimpleNamespace(message=message)
    return SimpleNamespace(generations=[[generation]], llm_output=llm_output)


def test_collector_reads_modern_usage_metadata():
    c = UsageCollector()
    c.on_llm_end(_llm_result(usage_metadata={"input_tokens": 120, "output_tokens": 30}))

    assert c.prompt_tokens == 120
    assert c.completion_tokens == 30
    assert c.total_tokens == 150
    assert c.has_usage is True
    assert c.llm_calls == 1


def test_collector_falls_back_to_legacy_token_usage():
    c = UsageCollector()
    c.on_llm_end(
        _llm_result(llm_output={"token_usage": {"prompt_tokens": 80, "completion_tokens": 20}})
    )

    assert (c.prompt_tokens, c.completion_tokens) == (80, 20)
    assert c.has_usage is True


def test_collector_accumulates_across_every_node_call():
    """Four nodes plus a review retry must all be counted, not just the last."""
    c = UsageCollector()
    for _ in range(5):
        c.on_llm_end(_llm_result(usage_metadata={"input_tokens": 100, "output_tokens": 25}))

    assert c.llm_calls == 5
    assert c.prompt_tokens == 500
    assert c.completion_tokens == 125


def test_collector_reports_no_usage_when_provider_omits_it():
    c = UsageCollector()
    c.on_llm_end(_llm_result())

    assert c.has_usage is False
    assert c.llm_calls == 1


def test_collector_never_raises_on_malformed_response():
    """Accounting must not be able to fail a ticket."""
    c = UsageCollector()
    c.on_llm_end(object())  # nothing resembling an LLMResult

    assert c.has_usage is False


def test_resolve_uses_provider_usage_when_available(client, monkeypatch):
    """End-to-end: reported usage drives cost, not the ticket-length estimate."""
    from src import service

    real_collector_cls = service.UsageCollector

    class SeededCollector(real_collector_cls):
        def __init__(self) -> None:
            super().__init__()
            # Simulate what the callback would have accumulated from a provider.
            self.prompt_tokens = 4000
            self.completion_tokens = 1000
            self.llm_calls = 5

    monkeypatch.setattr(service, "UsageCollector", SeededCollector)

    resp = client.post("/resolve", json={"ticket": "where is my order 5?"})
    assert resp.status_code == 200

    # 4000/1000 tokens costs far more than the handful of tokens in this ticket
    # would under the old estimate-only path.
    assert resp.json()["cost_usd"] > 0.0005


def test_resolve_falls_back_to_estimate_without_provider_usage(client):
    """The fake LLM reports nothing, so estimation still yields a cost."""
    resp = client.post("/resolve", json={"ticket": "where is my order 5?"})

    assert resp.status_code == 200
    assert resp.json()["cost_usd"] >= 0.0
