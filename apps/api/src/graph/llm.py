"""LLM abstraction with a dependency-injection seam.

The graph nodes never talk to OpenAI directly — they call methods on an
:class:`LLMClient`. Production wires in :class:`OpenAILLMClient` (a configured
OpenAI-compatible chat model via langchain-openai). Tests inject a scripted fake
implementing the same protocol, so the graph's routing, guards, and allowlist
logic run deterministically with **zero API keys**.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.config import settings
from src.constants import Category


@runtime_checkable
class LLMClient(Protocol):
    """The four operations the graph needs from a language model."""

    def classify(self, ticket: str) -> str:
        """Return one of the Category values."""

    def plan_research(
        self, ticket: str, category: str, order_id: str | None
    ) -> list[dict[str, Any]]:
        """Return a list of ``{"name": str, "args": dict}`` tool requests."""

    def draft(
        self,
        ticket: str,
        category: str,
        facts: list[dict],
        feedback: str | None,
    ) -> str:
        """Return a customer-facing reply grounded only in ``facts``."""

    def review(self, ticket: str, draft: str, facts: list[dict]) -> dict[str, Any]:
        """Return ``{"approved": bool, "feedback": str}``."""


# ── Production implementation ─────────────────────────────────────────────────


class OpenAILLMClient:
    """Backed by an OpenAI-compatible chat model (configurable base URL/model)."""

    def __init__(self) -> None:
        # Imported lazily so the package (and the test suite) load without the
        # langchain-openai stack or any credentials present.
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": settings.llm_model,
            "temperature": settings.temperature,
            "api_key": settings.openai_api_key,
        }
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        self._chat = ChatOpenAI(**kwargs)

    def classify(self, ticket: str) -> str:
        from pydantic import BaseModel, Field

        class Classification(BaseModel):
            category: str = Field(description="one of: order, product, refund, other")

        model = self._chat.with_structured_output(Classification)
        result: Any = model.invoke(
            [
                (
                    "system",
                    "Classify the support ticket into exactly one category: "
                    "order, product, refund, or other.",
                ),
                ("human", ticket),
            ]
        )
        cat = str(result.category).strip().lower()
        return cat if cat in {c.value for c in Category} else Category.OTHER.value

    def plan_research(
        self, ticket: str, category: str, order_id: str | None
    ) -> list[dict[str, Any]]:
        from src.tools.registry import TOOL_SCHEMAS

        model = self._chat.bind_tools(TOOL_SCHEMAS)
        hint = f"\nKnown order_id: {order_id}" if order_id else ""
        msg: Any = model.invoke(
            [
                (
                    "system",
                    "You research support tickets. Call only the provided tools to "
                    "gather facts needed to answer. If no tool is needed, answer "
                    "without calling any.",
                ),
                ("human", f"Category: {category}\nTicket: {ticket}{hint}"),
            ]
        )
        calls = []
        for tc in getattr(msg, "tool_calls", []) or []:
            calls.append({"name": tc.get("name"), "args": tc.get("args", {})})
        return calls

    def draft(
        self,
        ticket: str,
        category: str,
        facts: list[dict],
        feedback: str | None,
    ) -> str:
        revise = f"\nReviewer feedback to address: {feedback}" if feedback else ""
        msg: Any = self._chat.invoke(
            [
                (
                    "system",
                    "Draft a concise, friendly support reply. Ground every claim ONLY "
                    "in the provided facts. Never invent order or product details.",
                ),
                (
                    "human",
                    f"Category: {category}\nTicket: {ticket}\nFacts: {facts}{revise}",
                ),
            ]
        )
        return str(getattr(msg, "content", "")).strip()

    def review(self, ticket: str, draft: str, facts: list[dict]) -> dict[str, Any]:
        from pydantic import BaseModel, Field

        class Verdict(BaseModel):
            approved: bool = Field(description="True if the reply is grounded and policy-ok")
            feedback: str = Field(default="", description="What to fix if not approved")

        model = self._chat.with_structured_output(Verdict)
        result: Any = model.invoke(
            [
                (
                    "system",
                    "Grade the drafted reply. Approve only if it is fully grounded in "
                    "the facts and follows support policy. Otherwise give concrete "
                    "feedback.",
                ),
                ("human", f"Ticket: {ticket}\nFacts: {facts}\nDraft: {draft}"),
            ]
        )
        return {"approved": bool(result.approved), "feedback": result.feedback or ""}


def build_llm_client() -> LLMClient:
    """Factory for the production client. Raises if no credentials are set."""
    if not settings.has_llm_credentials:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Set it in .env to run the live LLM flow, "
            "or inject a fake LLMClient (as the test suite does)."
        )
    return OpenAILLMClient()
