# DeskFleet — Multi-Agent Support Ticket Resolver

**LangGraph + FastAPI + Streamlit · monorepo · Docker Compose · GitHub Actions → Cloud Run**

DeskFleet resolves support tickets end-to-end with a four-node LangGraph
`StateGraph` — **Classifier → Researcher → Responder → Reviewer** — running
against the public FakeStore API. Every ticket ends in one terminal decision:

| Decision | Meaning |
|---|---|
| `RESOLVED` | An auto-reply was drafted and approved by the reviewer |
| `ESCALATE` | Handed to a human, with a reason (unfixable, or review loop exhausted) |
| `REFUSE`   | Prompt injection or out-of-scope — refused **before any LLM call** |

The service is traced in LangSmith, exports Prometheus metrics, persists an audit
trail to SQLite, and ships with a Streamlit support console.

---

## Architecture

```
POST /resolve
   │  redact PII (inbound)
   │  injection scan ──► match ──► REFUSE (no LLM call)  ─┐
   ▼                                                      │
 LangGraph StateGraph (thread_id = ticket_id)             │
   classifier ─► researcher ─► responder ─► reviewer      │
        │            │             ▲            │         │
        │       allowlisted        └── retry ◄──┤ needs_fix & iters < MAX
        │       tools only                      │
        │       (off-list = blocked+audited)    ▼
        │                                approved ─► RESOLVED
        │                                iters ≥ MAX ─► ESCALATE
   redact PII (outbound) ─► persist (SQLite) ─► metrics + cost ─┘
   ▼
{ decision, reply, category, tool_calls, langsmith_trace_url, latency_ms, cost_usd }
```

Key design points:

- **Injection short-circuits before the model.** `guardrails/injection.py` runs on
  the raw (already PII-redacted) ticket; a match returns `REFUSE` without ever
  constructing or invoking the LLM. Tests assert zero model calls.
- **PII redacted in three places:** inbound ticket, outbound draft, and everything
  written to SQLite. `[REDACTED]` replacement is idempotent.
- **The allowlist is the security boundary.** Only tools in
  `tools/registry.py::ALLOWLIST` can execute; any other model-requested tool is
  recorded with `status="blocked"` and never dispatched.
- **The review loop is bounded in code, not by the model.** `graph/edges.py`
  enforces `MAX_REVIEW_ITERATIONS`; when exhausted the ticket deterministically
  becomes `ESCALATE` with the reviewer's last feedback as the reason.
- **Dependency-injected LLM.** Nodes depend on the `LLMClient` protocol
  (`graph/llm.py`). Production wires in a configured OpenAI-compatible chat model;
  the test suite injects a scripted fake, so **the full safety suite runs with zero
  API keys.**

### FakeStore order-status assumption

FakeStore has no real order-status/fulfillment endpoint. DeskFleet maps the domain
concept of an **order** onto FakeStore's `/carts` resource (the closest analogue: it
links a user to purchased products with a date). `get_order_status` fetches
`/carts/{id}` and derives a **deterministic synthetic status**
(`processing → shipped → in_transit → delivered`, chosen by `cart_id % 4`). The
response includes a `note` field documenting this mapping. `search_products`
filters the catalog client-side because FakeStore has no search endpoint.

---

## Repository layout

```
apps/api    FastAPI service (the deployable unit; self-contained Docker context)
apps/ui     Streamlit support console
packages/   shared constants (mirrored into the API for isolated builds)
infra/      Prometheus scrape config + provisioned Grafana dashboard
tests/      deterministic safety + contract suite (no API keys)
scripts/    seed_tickets.py, smoke_test.sh
.github/    ci.yml (lint+test+docker), deploy.yml (ghcr.io + Cloud Run)
```

---

## Quick start

### 1. Local (Python)

```bash
cd deskfleet
python -m pip install -r requirements-dev.txt   # api + dev deps
python -m pip install -r apps/ui/requirements.txt

cp .env.example .env    # optional: add OPENAI_API_KEY for the live LLM flow

make api    # FastAPI on http://localhost:8080   (/health, /docs, /metrics)
make ui     # Streamlit on http://localhost:8501
```

Without an `OPENAI_API_KEY`, `/health` reports `llm_configured: false` and the live
graph will raise on `/resolve` for non-injection tickets (by design — no silent
fake in production). Injection tickets still `REFUSE` with no key, and the **entire
test suite passes with no key** via the injected fake.

### 2. Full stack (Docker Compose)

```bash
cp .env.example .env    # fill in keys
docker compose up --build
```

| Service | URL |
|---|---|
| API | http://localhost:8080 |
| Streamlit UI | http://localhost:8501 |
| Prometheus | http://localhost:9090 |
| Grafana (admin/admin) | http://localhost:3000 |

Grafana auto-provisions the Prometheus datasource and the **DeskFleet Overview**
dashboard (throughput, P50/P99 latency, decision breakdown, cumulative spend,
escalation rate, tokens, tool calls).

---

## Configuration

All configuration flows through `apps/api/src/config.py` (pydantic-settings) — no
module reads `os.environ` directly. See `.env.example` for every variable. Notable:

| Var | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | LLM credential (blank/`sk-...` ⇒ demo mode) |
| `LLM_MODEL` | `gpt-4o-mini` | chat model |
| `LLM_BASE_URL` | — | set for Groq / OpenAI-compatible swap |
| `MAX_REVIEW_ITERATIONS` | `2` | review-loop bound |
| `MAX_TOOL_ROUNDS` | `3` | researcher tool-call cap |
| `SQLITE_PATH` | `./deskfleet.db` | audit DB |
| `LANGCHAIN_TRACING_V2` | `false` | enable LangSmith (env-only, no code change) |

---

## API

| Endpoint | Behavior |
|---|---|
| `POST /resolve` | `{ticket, order_id?}` → decision, reply, tool_calls, trace URL, latency, cost |
| `GET /health` | liveness (Cloud Run) |
| `GET /metrics` | Prometheus scrape |
| `GET /tickets?limit=N` | last N resolved tickets from SQLite |

```bash
curl -X POST localhost:8080/resolve -H 'content-type: application/json' \
  -d '{"ticket":"Where is my order 3?","order_id":"3"}'
```

---

## Testing

```bash
make test         # pytest tests/ -v   — NO API key required
make lint         # ruff check .
```

The suite covers the spec's safety contracts:

- `test_allowlist` — off-registry tool call blocked, logged, never executed.
- `test_max_iterations` — loop ends at `ESCALATE` after exactly `MAX_REVIEW_ITERATIONS`.
- `test_injection` — injected ticket ⇒ `REFUSE` with **zero** LLM invocations.
- `test_pii` — email/phone/SSN/card redacted in response **and** in the DB.
- `test_api` — `/resolve` schema, `422` on empty ticket, `/health` 200, `/metrics`.
- `test_fakestore` — tool semantics with stubbed HTTP.

---

## CI/CD

- **`ci.yml`** (every push/PR): `ruff check` → `pytest` → `docker build` of both images.
- **`deploy.yml`** (main only): re-run tests → publish `deskfleet-api` to
  `ghcr.io` → deploy to Cloud Run, pulling `OPENAI_API_KEY` / `LANGCHAIN_API_KEY`
  from GCP Secret Manager.

Required repo secrets: `GCP_SA_KEY`, `GCP_REGION`, plus `OPENAI_API_KEY` /
`LANGCHAIN_API_KEY` in GCP Secret Manager. `GITHUB_TOKEN` is automatic.

---

## Seed & smoke

```bash
make api                       # in one shell
python scripts/seed_tickets.py # 5 sample tickets vs. expected decisions
bash scripts/smoke_test.sh     # curl /health + /resolve + /tickets
```
