"""LangSmith tracing activation and per-ticket trace URL capture.

Two things are needed for the trace theater to work, and previously neither was
done:

1. **Activation.** ``pydantic-settings`` reads ``.env`` into the ``settings``
   object, but the LangChain SDK reads ``os.environ`` directly. Config that
   never reaches the process environment traces nothing. :func:`configure_tracing`
   bridges the two, and must run *before* the graph is compiled.

2. **Run capture.** A trace is only useful to a reviewer if the response links
   to it. :func:`trace_run` collects the root run of a graph invocation so the
   service can hand back a clickable URL.

Both degrade to no-ops when tracing is disabled or the SDK is unavailable —
resolving a ticket must never fail because observability is misconfigured.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any

from src.config import settings

logger = logging.getLogger("deskfleet.tracing")

# Name given to the graph invocation, so the root run is identifiable both in
# the LangSmith UI and when picking it back out of the collector.
ROOT_RUN_NAME = "deskfleet.resolve"

_configured = False
_tracing_active = False


def _settings_want_tracing() -> bool:
    """True when settings ask for tracing *and* a real credential is present."""
    key = settings.langchain_api_key
    if not key or key.startswith("lsv2_..."):  # ignore the .env.example placeholder
        return False
    return bool(settings.langchain_tracing_v2)


def tracing_enabled() -> bool:
    """True when tracing is active.

    Before :func:`configure_tracing` runs this reflects the settings object;
    afterwards it reflects the result of the startup probe (or explicit env
    variables in a real deployment).
    """
    if _configured:
        return _tracing_active
    return _settings_want_tracing()


def _langsmith_reachable(endpoint: str, timeout: float = 2.0) -> bool:
    """Probe the LangSmith API endpoint without sending credentials.

    Returns ``False`` for any SSL, network, timeout, or DNS failure so the
    service can degrade tracing to a no-op instead of logging repeated
    warnings on every request.
    """
    import urllib.error
    import urllib.request

    url = endpoint.rstrip("/")
    try:
        req = urllib.request.Request(f"{url}/info", method="HEAD")
        # `endpoint` is operator-controlled config (LANGCHAIN_ENDPOINT / .env),
        # never derived from ticket or request input.
        with urllib.request.urlopen(req, timeout=timeout):  # nosec B310
            return True
    except urllib.error.HTTPError as exc:
        # Any HTTP response means TLS + TCP are functional.
        return exc.code < 500
    except Exception:
        logger.warning(
            "LangSmith endpoint %s is unreachable; disabling tracing to avoid SSL warnings",
            url,
            exc_info=True,
        )
        return False


def configure_tracing() -> bool:
    """Export LangSmith config into ``os.environ`` for the LangChain SDK.

    Idempotent. Returns whether tracing ended up enabled. Existing environment
    variables win — a real deployment env (Cloud Run secrets, docker-compose)
    should not be overridden by a stale ``.env``.

    When settings enable tracing but the LangSmith endpoint cannot be reached
    (e.g. behind a firewall or on a disconnected network), tracing is disabled
    so the SDK does not emit SSLEOF warnings on every request.
    """
    global _configured, _tracing_active

    if not _settings_want_tracing():
        _tracing_active = False
        # Explicitly off, so a stale env var can't silently enable billing.
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
        os.environ.setdefault("LANGSMITH_TRACING", "false")
        logger.info("LangSmith tracing disabled (no API key or LANGCHAIN_TRACING_V2=false)")
        _configured = True
        return False

    if not _langsmith_reachable(settings.langchain_endpoint):
        _tracing_active = False
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
        os.environ.setdefault("LANGSMITH_TRACING", "false")
        logger.warning("LangSmith tracing disabled (endpoint unreachable)")
        _configured = True
        return False

    _tracing_active = True
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", settings.langchain_api_key)
    os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)
    os.environ.setdefault("LANGCHAIN_ENDPOINT", settings.langchain_endpoint)
    # LangSmith SDK ≥0.2 prefers the LANGSMITH_* names; set both so either works.
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_API_KEY", settings.langchain_api_key)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langchain_project)
    os.environ.setdefault("LANGSMITH_ENDPOINT", settings.langchain_endpoint)

    logger.info("LangSmith tracing enabled (project=%s)", settings.langchain_project)
    _configured = True
    return True


def _select_root(traced: list[Any]) -> Any | None:
    """Pick the graph invocation out of the collected runs.

    The collector can hold several parentless runs, and they are appended in
    completion order — children finish first, so index 0 is typically an LLM
    call, not the graph. Selection is therefore by identity, not position:
    our named run, else the outermost chain, else the last-completed run.
    """
    if not traced:
        return None

    for run in traced:
        if getattr(run, "name", None) == ROOT_RUN_NAME:
            return run

    chains = [
        run
        for run in traced
        if getattr(run, "run_type", None) == "chain" and getattr(run, "parent_run_id", None) is None
    ]
    if chains:
        return chains[-1]

    return traced[-1]


def _url_for_run(run: Any) -> str | None:
    """Resolve a clickable LangSmith URL for a collected run.

    Preferred path asks the SDK, which resolves the tenant/org id correctly.
    The constructed fallback is best-effort only.
    """
    run_id = getattr(run, "id", None)
    if not run_id:
        return None

    try:
        from langsmith import Client

        return Client().get_run_url(run=run)
    except Exception:  # noqa: BLE001 - fall back rather than fail the request
        logger.debug("get_run_url failed; using constructed URL", exc_info=True)

    host = settings.langchain_endpoint.replace("api.smith", "smith").rstrip("/")
    host = host.removesuffix("/api")
    return f"{host}/o/-/projects/p/{settings.langchain_project}/r/{run_id}"


class TraceHandle:
    """Mutable holder populated when the traced block exits."""

    __slots__ = ("run_id", "url")

    def __init__(self) -> None:
        self.run_id: str | None = None
        self.url: str | None = None


@contextmanager
def trace_run():
    """Run a block with LangSmith run collection, yielding a :class:`TraceHandle`.

    When tracing is off (or the SDK is missing) this is a transparent no-op and
    the handle stays empty — the caller simply returns a ``None`` trace URL.
    """
    handle = TraceHandle()

    if not tracing_enabled():
        yield handle
        return

    try:
        from langchain_core.tracers.context import collect_runs

        collector = collect_runs()
    except Exception:  # noqa: BLE001 - pragma: no cover
        yield handle
        return

    # NOTE: the caller's body is deliberately *not* wrapped in try/except here —
    # swallowing its exceptions would hide real resolution failures behind an
    # observability concern. Only the URL-resolution step is guarded.
    with collector as run_collector:
        yield handle

        try:
            # collect_runs() yields a RunCollectorCallbackHandler, not a list —
            # the runs live on .traced_runs. (Indexing the handler directly
            # raises, which previously left the URL silently None.)
            traced = getattr(run_collector, "traced_runs", None) or []
            root = _select_root(list(traced))
            if root is not None:
                handle.run_id = str(getattr(root, "id", "") or "") or None
                handle.url = _url_for_run(root)
        except Exception:  # noqa: BLE001 - tracing must never break resolution
            logger.warning("trace collection failed", exc_info=True)
