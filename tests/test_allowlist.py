"""Off-registry tool calls must be blocked, logged, and never executed."""

from __future__ import annotations

from src.constants import ToolStatus
from src.tools import registry
from src.tools.registry import ALLOWLIST, dispatch_tool


def test_off_allowlist_tool_is_blocked_and_never_dispatched(monkeypatch):
    executed: list[str] = []

    # Wrap every allowlisted callable to prove none of them run for a bad name.
    for name, func in list(ALLOWLIST.items()):
        def _spy(*a, _n=name, _f=func, **k):
            executed.append(_n)
            return _f(*a, **k)

        monkeypatch.setitem(ALLOWLIST, name, _spy)

    record = dispatch_tool("delete_order", {"order_id": "1"})

    assert record["status"] == ToolStatus.BLOCKED.value
    assert record["tool_name"] == "delete_order"
    assert executed == []  # no allowlisted tool was invoked


def test_allowlisted_tool_dispatches(monkeypatch):
    def fake_get_product(product_id):
        return {"id": product_id, "title": "Test"}

    monkeypatch.setitem(registry.ALLOWLIST, "get_product", fake_get_product)
    record = dispatch_tool("get_product", {"product_id": "1"})
    assert record["status"] == ToolStatus.OK.value
    assert record["result"]["title"] == "Test"


def test_researcher_blocks_off_allowlist_request_in_graph(make_graph):
    """A model that 'requests' delete_order gets it blocked + audited in state."""
    from tests.conftest import FakeLLM

    llm = FakeLLM(
        tool_requests=[
            {"name": "delete_order", "args": {"order_id": "1"}},
        ]
    )
    graph = make_graph(llm)
    state = {
        "ticket_id": "t1",
        "ticket": "cancel and delete my order",
        "order_id": "1",
        "facts": [],
        "tool_calls": [],
        "iterations": 0,
    }
    out = graph.invoke(state, config={"configurable": {"thread_id": "t1"}})

    blocked = [c for c in out["tool_calls"] if c["tool_name"] == "delete_order"]
    assert blocked and blocked[0]["status"] == ToolStatus.BLOCKED.value
    # blocked results never become grounding facts
    assert all(f.get("tool") != "delete_order" for f in out.get("facts", []))
