"""Prometheus metric definitions and helpers.

A single default registry is used so ``prometheus_client.generate_latest`` in the
``/metrics`` route exports everything. Metric objects are module-level singletons.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

TICKETS_TOTAL = Counter(
    "deskfleet_tickets_total",
    "Total tickets processed, labeled by terminal decision.",
    ["decision"],
)

TICKET_LATENCY = Histogram(
    "deskfleet_ticket_latency_seconds",
    "End-to-end ticket resolution latency in seconds.",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)

TOKENS_TOTAL = Counter(
    "deskfleet_tokens_total",
    "Total LLM tokens accounted, labeled by direction.",
    ["direction"],  # prompt | completion
)

COST_USD_TOTAL = Counter(
    "deskfleet_cost_usd_total",
    "Cumulative estimated LLM spend in USD.",
)

TOOL_CALLS_TOTAL = Counter(
    "deskfleet_tool_calls_total",
    "Total tool invocations, labeled by tool and status.",
    ["tool", "status"],
)

LLM_CALLS_TOTAL = Counter(
    "deskfleet_llm_calls_total",
    "Total LLM invocations made across all graph nodes.",
)

TOKEN_SOURCE_TOTAL = Counter(
    "deskfleet_token_source_total",
    "How token counts were obtained, for cost-accuracy monitoring.",
    ["source"],  # provider | estimated
)


def record_decision(decision: str) -> None:
    TICKETS_TOTAL.labels(decision=decision).inc()


def record_latency(seconds: float) -> None:
    TICKET_LATENCY.observe(seconds)


def record_tokens(prompt: int, completion: int) -> None:
    if prompt:
        TOKENS_TOTAL.labels(direction="prompt").inc(prompt)
    if completion:
        TOKENS_TOTAL.labels(direction="completion").inc(completion)


def record_cost(usd: float) -> None:
    if usd:
        COST_USD_TOTAL.inc(usd)


def record_tool_call(tool: str, status: str) -> None:
    TOOL_CALLS_TOTAL.labels(tool=tool, status=status).inc()


def record_llm_calls(count: int) -> None:
    if count:
        LLM_CALLS_TOTAL.inc(count)


def record_token_source(source: str) -> None:
    """``source`` is ``"provider"`` (real usage) or ``"estimated"`` (fallback)."""
    TOKEN_SOURCE_TOTAL.labels(source=source).inc()


def metrics_payload() -> tuple[bytes, str]:
    """Return ``(body, content_type)`` for the Prometheus scrape endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST
