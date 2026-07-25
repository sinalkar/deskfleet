"""Graph nodes: classifier, researcher, responder, reviewer.

Each node is created as a closure over an injected :class:`LLMClient` so the same
node code runs identically in production and under test. Nodes are pure state
transformers: they read from and return partial ``TicketState`` updates.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.config import settings
from src.constants import Category, Decision, ToolStatus
from src.graph.llm import LLMClient
from src.graph.state import TicketState
from src.guardrails.injection import scan_tool_result
from src.guardrails.pii import redact_pii
from src.tools.registry import dispatch_tool


def make_classifier(llm: LLMClient) -> Callable[[TicketState], dict[str, Any]]:
    def classifier(state: TicketState) -> dict:
        category = llm.classify(state["ticket"])
        if category not in {c.value for c in Category}:
            category = Category.OTHER.value
        return {"category": category}

    return classifier


def make_researcher(llm: LLMClient) -> Callable[[TicketState], dict[str, Any]]:
    """Tool-calling loop, allowlisted tools only, bounded by MAX_TOOL_ROUNDS.

    The allowlist is enforced by :func:`dispatch_tool`; a model request for an
    off-registry tool is recorded with ``status="blocked"`` and never executed.
    """

    def researcher(state: TicketState) -> dict:
        facts = list(state.get("facts") or [])
        tool_calls = list(state.get("tool_calls") or [])

        requests = llm.plan_research(
            ticket=state["ticket"],
            category=state.get("category") or Category.OTHER.value,
            order_id=state.get("order_id"),
        )

        for req in requests[: settings.max_tool_rounds]:
            name = req.get("name", "")
            args = req.get("args", {}) or {}
            record = dispatch_tool(name, args)
            tool_calls.append(record)
            if record["status"] == "ok":
                # Indirect-injection defense: external API responses are
                # untrusted. Strings carrying injection payloads are quarantined
                # before they can reach the responder's prompt, and the record
                # is marked so the audit trail shows what happened.
                flagged, sanitized = scan_tool_result(record["result"])
                if flagged:
                    record["status"] = ToolStatus.SANITIZED.value
                    record["result"] = sanitized
                facts.append({"tool": name, "args": args, "data": sanitized})

        return {"facts": facts, "tool_calls": tool_calls}

    return researcher


def make_responder(llm: LLMClient) -> Callable[[TicketState], dict[str, Any]]:
    def responder(state: TicketState) -> dict:
        draft = llm.draft(
            ticket=state["ticket"],
            category=state.get("category") or Category.OTHER.value,
            facts=state.get("facts") or [],
            feedback=state.get("review_feedback"),
        )
        # PII redaction on the outbound draft (defense in depth: also redacted
        # again at the API boundary before returning/persisting).
        return {"draft": redact_pii(draft)}

    return responder


def make_reviewer(llm: LLMClient) -> Callable[[TicketState], dict[str, Any]]:
    """Grade the draft and set the terminal decision or request a revision.

    The max-iteration guard lives in the routing layer (edges.py); the reviewer
    only increments the counter and reports approval/feedback. When the loop is
    exhausted, routing converts the last feedback into an ESCALATE reason.
    """

    def reviewer(state: TicketState) -> dict:
        iterations = state.get("iterations", 0) + 1
        verdict = llm.review(
            ticket=state["ticket"],
            draft=state.get("draft") or "",
            facts=state.get("facts") or [],
        )

        if verdict.get("approved"):
            return {
                "iterations": iterations,
                "decision": Decision.RESOLVED.value,
                "review_feedback": None,
            }

        feedback = verdict.get("feedback") or "Draft not approved by reviewer."
        update: dict = {"iterations": iterations, "review_feedback": feedback}

        # If the loop is exhausted, finalize as ESCALATE here so state carries a
        # concrete reason; edges.py routes to END either way.
        if iterations >= settings.max_review_iterations:
            update["decision"] = Decision.ESCALATE.value
            update["escalation_reason"] = (
                f"Reviewer did not approve after {iterations} iteration(s): {feedback}"
            )
        return update

    return reviewer
