"""LangSmith tracing activation.

Tracing was previously configured but never activated: settings never reached
``os.environ`` (where the LangChain SDK looks) and the trace URL was hardcoded
to ``None``. These tests pin the activation contract so it cannot silently
regress back to a dead feature.
"""

from __future__ import annotations

import pytest
from src.observability import tracing


@pytest.fixture
def clean_env(monkeypatch):
    for var in (
        "LANGCHAIN_TRACING_V2",
        "LANGCHAIN_API_KEY",
        "LANGCHAIN_PROJECT",
        "LANGCHAIN_ENDPOINT",
        "LANGSMITH_TRACING",
        "LANGSMITH_API_KEY",
        "LANGSMITH_PROJECT",
        "LANGSMITH_ENDPOINT",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def _enable(monkeypatch, *, key="lsv2_real_key_value", on=True):
    from src.config import settings

    monkeypatch.setattr(settings, "langchain_tracing_v2", on)
    monkeypatch.setattr(settings, "langchain_api_key", key)
    monkeypatch.setattr(settings, "langchain_project", "deskfleet-test")


def test_disabled_without_api_key(clean_env):
    _enable(clean_env, key="", on=True)
    assert tracing.tracing_enabled() is False
    assert tracing.configure_tracing() is False


def test_placeholder_key_does_not_enable_tracing(clean_env):
    """The .env.example placeholder must not count as a credential."""
    _enable(clean_env, key="lsv2_...")
    assert tracing.tracing_enabled() is False


def test_disabled_when_flag_off(clean_env):
    _enable(clean_env, on=False)
    assert tracing.tracing_enabled() is False


def test_configure_exports_settings_to_environ(clean_env):
    """The actual bug: config that never reaches os.environ traces nothing."""
    import os

    _enable(clean_env)

    assert tracing.configure_tracing() is True
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGCHAIN_API_KEY"] == "lsv2_real_key_value"
    assert os.environ["LANGCHAIN_PROJECT"] == "deskfleet-test"
    # Both naming schemes, so either SDK generation picks it up.
    assert os.environ["LANGSMITH_TRACING"] == "true"


def test_configure_does_not_override_real_environment(clean_env):
    """A deployment env (Cloud Run secrets) must win over a stale .env."""
    import os

    clean_env.setenv("LANGCHAIN_PROJECT", "from-cloud-run")
    _enable(clean_env)
    tracing.configure_tracing()

    assert os.environ["LANGCHAIN_PROJECT"] == "from-cloud-run"


def test_trace_run_is_a_noop_when_disabled(clean_env):
    _enable(clean_env, key="", on=False)

    with tracing.trace_run() as handle:
        pass

    assert handle.run_id is None
    assert handle.url is None


def test_trace_run_propagates_caller_exceptions(clean_env):
    """Observability must not swallow real failures."""
    _enable(clean_env, key="", on=False)

    with pytest.raises(ValueError, match="boom"):
        with tracing.trace_run():
            raise ValueError("boom")


def test_health_reports_tracing_state(client):
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert "tracing_enabled" in body


def test_resolve_returns_null_trace_url_when_tracing_off(client):
    """Field stays present and typed even with tracing disabled."""
    body = client.post("/resolve", json={"ticket": "where is my order 5?"}).json()

    assert "langsmith_trace_url" in body
    assert body["langsmith_trace_url"] is None


# ── root-run selection ───────────────────────────────────────────────────────
# The collector holds runs in completion order, and children complete before
# their parent — so the graph root is never reliably at index 0. Selecting the
# wrong run links reviewers to a single LLM call instead of the full trace.


class _Run:
    def __init__(self, name, run_type, parent_run_id=None, id="run-0"):
        self.name = name
        self.run_type = run_type
        self.parent_run_id = parent_run_id
        self.id = id


def test_selects_named_root_not_first_collected():
    traced = [
        _Run("ChatOpenAI", "llm"),
        _Run("ChatOpenAI", "llm"),
        _Run(tracing.ROOT_RUN_NAME, "chain", id="root-id"),
    ]
    assert tracing._select_root(traced).id == "root-id"


def test_falls_back_to_outermost_chain():
    traced = [_Run("ChatOpenAI", "llm"), _Run("LangGraph", "chain", id="chain-id")]
    assert tracing._select_root(traced).id == "chain-id"


def test_ignores_nested_chain_runs():
    traced = [
        _Run("inner", "chain", parent_run_id="p", id="nested"),
        _Run("outer", "chain", id="root"),
    ]
    assert tracing._select_root(traced).id == "root"


def test_falls_back_to_last_completed_run():
    traced = [_Run("a", "llm", id="first"), _Run("b", "llm", id="last")]
    assert tracing._select_root(traced).id == "last"


def test_empty_collection_selects_nothing():
    assert tracing._select_root([]) is None
