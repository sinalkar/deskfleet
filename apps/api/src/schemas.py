"""Pydantic request/response models for the public API."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ResolveRequest(BaseModel):
    # max_length bounds prompt-stuffing / flooding attacks (and token spend) at
    # the API boundary; real support tickets fit comfortably within it.
    ticket: str = Field(..., min_length=1, max_length=8000, description="Raw support ticket text")
    order_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional order identifier referenced by the ticket",
    )

    @field_validator("ticket")
    @classmethod
    def _ticket_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ticket must not be empty")
        return v


class ToolCallRecord(BaseModel):
    tool_name: str
    args: dict = Field(default_factory=dict)
    result: dict | list | str | int | float | None = None
    status: str


class ResolveResponse(BaseModel):
    ticket_id: str
    decision: str
    reply: str | None = None
    category: str | None = None
    escalation_reason: str | None = None
    iterations: int = 0
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    langsmith_trace_url: str | None = None
    latency_ms: float = 0.0
    cost_usd: float = 0.0


class TicketSummary(BaseModel):
    id: str
    body: str
    category: str | None = None
    decision: str | None = None
    reply: str | None = None
    escalation_reason: str | None = None
    iterations: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    created_at: str


class HealthResponse(BaseModel):
    status: str = "ok"
    llm_configured: bool = False
    tracing_enabled: bool = False
