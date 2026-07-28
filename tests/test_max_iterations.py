"""The review loop terminates deterministically at MAX_REVIEW_ITERATIONS."""

from __future__ import annotations

from src.config import settings
from src.constants import Decision


def _run(graph):
    state = {
        "ticket_id": "t1",
        "ticket": "please help with my order",
        "order_id": None,
        "facts": [],
        "tool_calls": [],
        "iterations": 0,
    }
    return graph.invoke(state, config={"configurable": {"thread_id": "t1"}})


def test_loop_escalates_after_max_iterations(make_graph, monkeypatch):
    from tests.conftest import FakeLLM

    monkeypatch.setattr(settings, "max_review_iterations", 2)
    # Reviewer always rejects → loop must bottom out at ESCALATE.
    llm = FakeLLM(approve=False, feedback="not grounded enough")
    graph = make_graph(llm)

    out = _run(graph)

    assert out["decision"] == Decision.ESCALATE.value
    assert out["iterations"] == 2  # exactly MAX_REVIEW_ITERATIONS
    assert "not grounded enough" in (out["escalation_reason"] or "")
    # responder ran once initially + once per retry before the final rejection
    assert llm.calls.count("draft") == 2
    assert llm.calls.count("review") == 2


def test_single_iteration_setting_is_respected(make_graph, monkeypatch):
    from tests.conftest import FakeLLM

    monkeypatch.setattr(settings, "max_review_iterations", 1)
    llm = FakeLLM(approve=False)
    graph = make_graph(llm)

    out = _run(graph)

    assert out["decision"] == Decision.ESCALATE.value
    assert out["iterations"] == 1


def test_approved_draft_resolves_without_escalation(make_graph):
    from tests.conftest import FakeLLM

    llm = FakeLLM(approve=True)
    graph = make_graph(llm)

    out = _run(graph)

    assert out["decision"] == Decision.RESOLVED.value
    assert out["iterations"] == 1
    assert llm.calls.count("review") == 1


def test_out_of_scope_category_escalates_immediately(make_graph):
    """Out-of-scope tickets are escalated after the classifier, before the pipeline."""
    from tests.conftest import FakeLLM

    llm = FakeLLM(category="other")
    graph = make_graph(llm)

    out = _run(graph)

    assert out["decision"] == Decision.ESCALATE.value
    assert out["category"] == "other"
    assert "out of scope" in (out["escalation_reason"] or "").lower()
    assert out["iterations"] == 0
    # Only the classifier ran; no research/respond/review work was done.
    assert llm.calls == ["classify"]
