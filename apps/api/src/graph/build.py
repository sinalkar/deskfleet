"""Compile the DeskFleet StateGraph.

``compile_graph`` accepts an optional :class:`LLMClient` — the dependency
injection seam. Production passes nothing and gets the configured OpenAI client;
tests pass a scripted fake.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.graph.edges import route_after_review
from src.graph.llm import LLMClient, build_llm_client
from src.graph.nodes import (
    make_classifier,
    make_researcher,
    make_responder,
    make_reviewer,
)
from src.graph.state import TicketState
from src.observability.tracing import configure_tracing


def compile_graph(llm: LLMClient | None = None):
    """Build and compile the classifier→researcher→responder→reviewer graph."""
    # Idempotent, and a no-op when tracing is off. Repeated here so graphs built
    # outside the FastAPI lifespan (scripts, notebooks, tests) are traced too.
    configure_tracing()

    client = llm or build_llm_client()

    graph = StateGraph(TicketState)
    # Plain callables returning partial-state dicts are the documented LangGraph
    # node form and work at runtime, but langgraph 1.x's add_node overloads
    # don't admit them under mypy — hence the targeted ignores.
    graph.add_node("classifier", make_classifier(client))  # type: ignore[call-overload]
    graph.add_node("researcher", make_researcher(client))  # type: ignore[call-overload]
    graph.add_node("responder", make_responder(client))  # type: ignore[call-overload]
    graph.add_node("reviewer", make_reviewer(client))  # type: ignore[call-overload]

    graph.add_edge(START, "classifier")
    graph.add_edge("classifier", "researcher")
    graph.add_edge("researcher", "responder")
    graph.add_edge("responder", "reviewer")
    graph.add_conditional_edges(
        "reviewer",
        route_after_review,
        {"responder": "responder", END: END},
    )

    return graph.compile()
