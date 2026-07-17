"""FastAPI application factory, routes, and middleware."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response

from src.config import settings
from src.observability import metrics
from src.schemas import (
    HealthResponse,
    ResolveRequest,
    ResolveResponse,
    TicketSummary,
)
from src.service import resolve_ticket
from src.storage import repo
from src.storage.db import init_db

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("deskfleet")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("DeskFleet API started (llm_configured=%s)", settings.has_llm_credentials)
    yield


def get_graph(request: Request) -> Any:
    """Lazily compile the production graph, caching it on ``app.state``.

    Tests override ``app.state.graph`` with a fake-LLM-backed graph, so this is
    never called with real credentials in CI.
    """
    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        from src.graph.build import compile_graph

        graph = compile_graph()
        request.app.state.graph = graph
    return graph


def create_app() -> FastAPI:
    app = FastAPI(
        title="DeskFleet",
        description="Multi-agent support ticket resolver (LangGraph + FastAPI).",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.graph = None

    @app.middleware("http")
    async def request_timing(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed:.2f}"
        return response

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", llm_configured=settings.has_llm_credentials)

    @app.get("/metrics")
    def prometheus_metrics() -> Response:
        body, content_type = metrics.metrics_payload()
        return Response(content=body, media_type=content_type)

    @app.post("/resolve", response_model=ResolveResponse)
    def resolve(req: ResolveRequest, graph: Any = Depends(get_graph)) -> ResolveResponse:
        try:
            return resolve_ticket(graph, req)
        except Exception as exc:  # noqa: BLE001
            logger.exception("resolve failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/tickets", response_model=list[TicketSummary])
    def tickets(limit: int = 10) -> list[TicketSummary]:
        limit = max(1, min(limit, 100))
        return [TicketSummary(**row) for row in repo.recent_tickets(limit)]

    return app


app = create_app()
