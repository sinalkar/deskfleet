"""Test fixtures — NO API key required.

Puts ``apps/api`` on the import path so tests import the service exactly as it
ships, points storage at an isolated temp SQLite file, and provides scriptable
fake LLM clients + compiled graphs. The fakes implement the same ``LLMClient``
protocol the production node code depends on, so routing/guards/allowlist logic
is exercised deterministically.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── import path: make ``src`` importable like the deployed API ──
API_SRC_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(API_SRC_ROOT))


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Point every test at a fresh on-disk SQLite file and init the schema."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_file))

    # settings is a cached singleton; patch the live attribute so all modules
    # that already imported ``settings`` see the temp path.
    from src.config import settings

    monkeypatch.setattr(settings, "sqlite_path", str(db_file))

    from src.storage.db import init_db

    init_db(str(db_file))
    yield


@pytest.fixture(autouse=True)
def _disable_langsmith_for_tests(monkeypatch):
    """Keep tests isolated from any real LangSmith credentials in .env.

    The API startup probe is forced to report unreachable, and module-level
    tracing state is reset so tests that exercise the enable path can control
    the outcome explicitly.
    """
    from src.observability import tracing

    monkeypatch.setattr(tracing, "_configured", False)
    monkeypatch.setattr(tracing, "_tracing_active", False)
    monkeypatch.setattr(tracing, "_langsmith_reachable", lambda *_, **__: False)
    yield


class FakeLLM:
    """Scriptable stand-in for the production LLM client.

    Every model interaction is recorded in ``self.calls`` so tests can assert the
    model was (or was never) invoked — e.g. the injection test asserts zero calls.
    """

    def __init__(
        self,
        *,
        category: str = "order",
        tool_requests: list[dict] | None = None,
        draft_text: str = "Thanks for reaching out — your order is on its way.",
        approve: bool = True,
        feedback: str = "Please add more grounded detail.",
    ) -> None:
        self.category = category
        self.tool_requests = tool_requests or []
        self.draft_text = draft_text
        self.approve = approve
        self.feedback = feedback
        self.calls: list[str] = []

    def classify(self, ticket: str) -> str:
        self.calls.append("classify")
        return self.category

    def plan_research(self, ticket: str, category: str, order_id: str | None) -> list[dict]:
        self.calls.append("plan_research")
        return list(self.tool_requests)

    def draft(self, ticket, category, facts, feedback) -> str:
        self.calls.append("draft")
        return self.draft_text

    def review(self, ticket, draft, facts) -> dict:
        self.calls.append("review")
        return {"approved": self.approve, "feedback": self.feedback}


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def make_graph():
    """Return a factory that compiles the real graph around a given FakeLLM."""
    from src.graph.build import compile_graph

    def _factory(llm: FakeLLM):
        return compile_graph(llm)

    return _factory


@pytest.fixture
def client(make_graph, fake_llm):
    """FastAPI TestClient with the graph overridden to use the fake LLM."""
    from fastapi.testclient import TestClient
    from src.main import app

    app.state.graph = make_graph(fake_llm)
    with TestClient(app) as c:
        c.fake_llm = fake_llm  # expose for assertions
        yield c
    app.state.graph = None
