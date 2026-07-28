# 🚀 DeskFleet — Multi-Agent Support Ticket Resolver

![Python](https://img.shields.io/badge/python-3.11-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-1C3C3C)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Prometheus](https://img.shields.io/badge/Metrics-Prometheus-E6522C?logo=prometheus&logoColor=white)
![Grafana](https://img.shields.io/badge/Dashboards-Grafana-F46800?logo=grafana&logoColor=white)
[![CI](https://github.com/sinalkar/deskfleet/actions/workflows/ci.yml/badge.svg)](https://github.com/sinalkar/deskfleet/actions/workflows/ci.yml)

**LangGraph + FastAPI + Streamlit · monorepo · Docker Compose · GitHub Actions → GHCR**

> 🎓 **Capstone project by [Sanjay Sinalkar](https://github.com/sinalkar)** — built for the
> **iHub DivyaSampark @ IIT Roorkee × Masai** program (Multi-Agent Systems track, project C·04).
> A LangGraph crew resolves real support tickets end-to-end against an external order API,
> with every tool call, decision, and per-node latency traceable in LangSmith.

DeskFleet is a small, self-contained reference implementation of a **production-shaped
multi-agent system**: it takes a raw support ticket, runs it through a four-node
LangGraph `StateGraph`, and returns a fully-audited decision — with prompt-injection
defense, PII redaction, a hard security allowlist on tool calls, tracing, cost
accounting, and a live dashboard, all wired together end-to-end rather than sketched
as a notebook demo.

Every ticket that enters the system ends in exactly one terminal decision:

| Decision | Emoji | Meaning |
|---|---|---|
| `RESOLVED` | ✅ | An auto-reply was drafted, grounded in real data, and approved by the reviewer agent |
| `ESCALATE` | ⚠️ | Handed to a human, with a concrete reason (unfixable draft, or the review loop ran out) |
| `REFUSE` | ⛔ | Prompt injection or an out-of-scope request — refused **before the LLM is ever called** |

---

## 📸 See it in action

**Support console — chat home.** Example tickets covering every terminal decision,
live API status, and per-session decision stats:

![DeskFleet chat console home](docs/screenshots/chat-console-home.png)

**Prompt injection refused before any LLM call.** The guardrail short-circuits and
the matched pattern is surfaced as the refusal reason — note `0 ms` latency and
`$0.000000` cost, because the model was never invoked:

![Injection attempt refused](docs/screenshots/injection-refused.png)

**Multi-turn console flow.** Each message is an independent ticket resolution with
its own decision pill, metric chips, and audit trail (in demo mode without an LLM
key, live tickets degrade gracefully to `ESCALATE`):

![Conversation flow](docs/screenshots/conversation-flow.png)

---

## ⚡ Quick start

**Prerequisites:** Python 3.11+, Docker + Compose (for the full stack). An LLM API
key is **optional** — the whole test suite and the `REFUSE` path work with none.

```bash
# 1. Clone and install
git clone https://github.com/sinalkar/deskfleet.git
cd deskfleet
python -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements-dev.txt      # API + dev/test deps
python -m pip install -r apps/ui/requirements.txt  # Streamlit UI deps

# 2. Configure (optional — everything else defaults safely)
cp .env.example .env
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-...

# 3. Verify — 100+ tests, all green with zero API keys
make test
make lint
```

**Run it** — local processes, or the full stack:

```bash
# Option A — local processes
make api    # FastAPI  → http://localhost:8080  (/health, /docs, /metrics)
make ui     # Streamlit → http://localhost:8501  (second shell)

# Option B — Docker Compose (adds Prometheus + Grafana)
docker compose up --build
```

| Service | URL | What you'll see |
|---|---|---|
| 🚪 API | http://localhost:8080 | `/docs` (OpenAPI), `/health`, `/metrics` |
| 🖥️ Streamlit UI | http://localhost:8501 | The chat support console |
| 📈 Prometheus | http://localhost:9090 | Raw metrics + query explorer |
| 📊 Grafana (`admin`/`admin`) | http://localhost:3000 | Auto-provisioned **DeskFleet Overview** dashboard |

**Try it** — click an example ticket chip in the UI, or hit the API directly:

```bash
curl -X POST localhost:8080/resolve -H 'content-type: application/json' \
  -d '{"ticket":"Where is my order 3?","order_id":"3"}'
```

Without a configured LLM key, `/health` reports `llm_configured: false`; injection
tickets still `REFUSE` (the guardrail needs no model) and live tickets degrade
gracefully to `ESCALATE` with a clear reason — the service never 500s.

---

## 📚 Table of contents

- [Why this exists](#-why-this-exists)
- [How a ticket flows through the system](#-how-a-ticket-flows-through-the-system)
- [The agent graph, node by node](#-the-agent-graph-node-by-node)
- [Request lifecycle, step by step](#-request-lifecycle-step-by-step)
- [Security: prompt-hijack defense in depth](#-security-prompt-hijack-defense-in-depth)
- [The FakeStore mapping](#-the-fakestore-mapping)
- [Repository layout](#-repository-layout)
- [Configuration](#-configuration)
- [Multi-provider LLM support](#-multi-provider-llm-support)
- [API reference](#-api-reference)
- [Testing](#-testing)
- [Coding standards](#-coding-standards)
- [Observability](#-observability)
- [CI/CD pipeline](#-cicd-pipeline)
- [Seed & smoke test](#-seed--smoke-test)
- [Credits](#-credits)

---

## 💡 Why this exists

Customer support triage is a good stress test for agentic systems: it needs
**real tool use** (order/product lookups), **grounded generation** (replies must be
based on facts, not invented), **a self-check loop** (a second agent reviews the
first agent's draft), and **hard safety boundaries** (never call an arbitrary tool,
never leak PII, never take instructions embedded inside user content). DeskFleet
implements all of that as actual, tested code rather than prompt-only guardrails —
the security-critical decisions (tool allowlisting, loop bounds, injection
short-circuiting) all live in plain Python, not in something an LLM could be talked
out of.

The service is traced end-to-end in LangSmith, exports Prometheus metrics, persists a
full audit trail to SQLite, and ships with the Streamlit console shown above so a
human can see exactly what the agents did and why.

---

## 🧭 How a ticket flows through the system

```mermaid
flowchart TD
    Client(["👤 Client / Support Agent"]) -->|"POST /resolve"| API["🚪 FastAPI /resolve"]
    API --> PII1["🕵️ Redact PII — inbound"]
    PII1 --> INJ{"🛡️ Injection Guardrail"}
    INJ -- "pattern match" --> REFUSE["⛔ REFUSE\n(no LLM call made)"]
    INJ -- "clean" --> GRAPH["🧠 LangGraph StateGraph\nClassifier → Researcher → Responder → Reviewer"]
    GRAPH --> PII2["🕵️ Redact PII — outbound"]
    REFUSE --> DB
    PII2 --> DB[("🗄️ SQLite\ntickets + tool_calls audit")]
    DB --> METRICS["📊 Prometheus metrics\n+ tiktoken cost accounting"]
    METRICS --> RESP(["📬 JSON response:\ndecision · reply · tool_calls · trace_url"])
    GRAPH -.->|"every node + tool call traced"| LANGSMITH["🔭 LangSmith"]

    style REFUSE fill:#cf222e,color:#fff
    style GRAPH fill:#1C3C3C,color:#fff
    style DB fill:#2496ED,color:#fff
```

**The two guardrails run outside the agent graph entirely.** PII redaction and
injection detection are plain regex layers that execute *before* the graph is ever
invoked — a malicious or leaky ticket is neutralized by ordinary code, not by asking
an LLM nicely.

---

## 🤖 The agent graph, node by node

```mermaid
flowchart LR
    START(["▶️ START"]) --> C["🏷️ Classifier\nLLM: order | product | refund | other"]
    C --> R["🔍 Researcher\nplans + runs allowlisted tools"]
    R -- "get_order_status\nget_product\nsearch_products" --> FS[("🛒 FakeStoreAPI")]
    FS --> R
    R -- "off-registry tool?" --> BLOCK["🚫 blocked + audited\n(never executed)"]
    R --> RESP["✍️ Responder\ndrafts reply grounded ONLY in facts"]
    RESP --> REV{"✅ Reviewer\ngrounded? policy-ok?"}
    REV -- "approved" --> RESOLVED(["🟢 RESOLVED"])
    REV -- "needs_fix &\niterations < MAX" --> RESP
    REV -- "iterations ≥ MAX" --> ESCALATE(["🟠 ESCALATE + reason"])

    style RESOLVED fill:#1a7f37,color:#fff
    style ESCALATE fill:#9a6700,color:#fff
    style BLOCK fill:#cf222e,color:#fff
```

| # | Node | What it does | Writes to state |
|---|---|---|---|
| 1 | **🏷️ Classifier** | One LLM call buckets the ticket into a category | `category` |
| 2 | **🔍 Researcher** | Plans and dispatches tool calls — but *only* tools present in `tools/registry.py::ALLOWLIST`; anything else is logged as `status="blocked"` and never runs | `facts`, `tool_calls` |
| 3 | **✍️ Responder** | Drafts a reply grounded *only* in the accumulated `facts` — on a retry it also incorporates the reviewer's `review_feedback` | `draft` |
| 4 | **✅ Reviewer** | Grades the draft for grounding and policy compliance; returns a structured `{approved, feedback}` verdict and increments the iteration counter | `decision` or `review_feedback` |

The loop-back edge from Reviewer → Responder is the graph's one piece of real
branching, and its exit condition (`iterations >= MAX_REVIEW_ITERATIONS`) is enforced
in `graph/edges.py` — **plain routing code, never trusted to the model** — so a
model that keeps rejecting its own drafts cannot spin forever; it deterministically
becomes `ESCALATE` with the last feedback attached as the reason.

---

## 🔁 Request lifecycle, step by step

```mermaid
sequenceDiagram
    participant U as 👤 Client
    participant API as 🚪 FastAPI /resolve
    participant G as 🛡️ Guardrails
    participant SG as 🧠 StateGraph
    participant T as 🛒 FakeStoreAPI
    participant DB as 🗄️ SQLite
    participant P as 📊 Prometheus

    U->>API: POST /resolve {ticket, order_id}
    API->>G: redact PII, then scan for injection
    alt injection detected
        G-->>API: REFUSE + matched pattern
        API->>DB: persist ticket (decision=REFUSE)
        API-->>U: 200 {decision: "REFUSE", reply: null}
    else clean ticket
        API->>SG: invoke(state, thread_id=ticket_id)
        SG->>SG: classifier → category
        SG->>T: researcher: allowlisted tool calls
        T-->>SG: order/product facts
        SG->>SG: responder drafts reply from facts
        SG->>SG: reviewer grades the draft
        opt not approved & iterations < MAX
            SG->>SG: retry responder with feedback
        end
        SG-->>API: final state (RESOLVED or ESCALATE)
        API->>G: redact PII from the outbound reply
        API->>DB: persist ticket + full tool_calls audit
        API->>P: record decision, latency, tokens, cost
        API-->>U: 200 {decision, reply, tool_calls, trace_url, cost_usd}
    end
```

---

## 🔐 Security: prompt-hijack defense in depth

Every layer below is **plain, deterministic Python** — bounded, testable with zero
API keys, and impossible for a model to be "talked out of". The layers stack, so a
payload has to defeat all of them:

| # | Layer | Where | What it stops |
|---|---|---|---|
| 1 | **Request-size cap** | `schemas.py` (`max_length=8000`) | Prompt-stuffing / flooding and unbounded token spend, rejected with `422` at the API boundary |
| 2 | **Unicode normalization** | `guardrails/injection.py::normalize` | Obfuscated payloads — NFKC folds fullwidth forms (`ｉｇｎｏｒｅ`), and zero-width/bidi/invisible characters are stripped, so `i​g​n​o​r​e` can't slip past the patterns |
| 3 | **Inbound injection scan** | `guardrails/injection.py` | 27 pattern families: system-override, role-hijack, prompt-exfiltration, chat-template/special-token smuggling (`</system>`, `<|im_start|>`), encoded payloads, tool coercion. A match → `REFUSE` **before any LLM call** — tests assert zero model invocations |
| 4 | **PII redaction (in 3 places)** | `guardrails/pii.py` | Emails/phones/SSNs/cards scrubbed from the inbound ticket, the outbound draft, and everything persisted — while order/invoice/tracking references are preserved for lookups |
| 5 | **Prompt spotlighting** | `graph/llm.py` | Untrusted ticket text is fenced in `<<<TICKET>>> … <<<END_TICKET>>>` delimiters, and every node's system prompt has standing orders to treat fenced content as DATA, never instructions |
| 6 | **Tool allowlist** | `tools/registry.py::ALLOWLIST` | Any model-requested tool outside the registry is recorded with `status="blocked"` and dispatched to nothing — the allowlist *is* the security boundary |
| 7 | **Tool-output quarantine** | `graph/nodes.py` researcher | *Indirect* injection: payloads planted in external API data (e.g. a poisoned product title) are quarantined before they reach the responder's prompt, and the audit trail marks the call `sanitized` |
| 8 | **Bounded review loop** | `graph/edges.py` | Infinite loops / token burn: `MAX_REVIEW_ITERATIONS` is enforced in routing code — exhaustion deterministically becomes `ESCALATE` |
| 9 | **Outbound leak gate** | `service.py` + `detect_prompt_leak` | A drafted reply that narrates its instructions, echoes role tags, or contains credential-shaped strings is never sent — the ticket escalates with the reply withheld |

Two structural principles underpin the layers:

- **The LLM is dependency-injected.** Every node depends on the `LLMClient`
  protocol (`graph/llm.py`); the test suite injects a scripted fake, so the entire
  safety suite runs deterministically with **zero API keys**.
- **Nothing security-critical is delegated to the model.** Allowlisting, loop
  bounds, injection short-circuiting, and the leak gate all live in ordinary code
  paths covered by `tests/test_hijack_hardening.py`, `test_injection.py`,
  `test_allowlist.py`, `test_max_iterations.py`, and `test_pii.py`.

---

## 🛒 The FakeStore mapping

FakeStore has no real order-status/fulfillment endpoint, so DeskFleet maps the
domain concept of an **order** onto FakeStore's `/carts` resource (the closest
analogue: it links a user to purchased products with a date).

- `get_order_status` fetches `/carts/{id}` and derives a **deterministic synthetic
  status** — `processing → shipped → in_transit → delivered`, chosen by
  `cart_id % 4` — and documents this mapping in a `note` field on the response.
- `search_products` filters the catalog client-side, since FakeStore has no native
  search endpoint.

---

## 🗂️ Repository layout

```
deskfleet/
├── apps/
│   ├── api/            🚪 FastAPI service — the deployable unit
│   │   └── src/
│   │       ├── graph/          🧠 state.py · nodes.py · edges.py · build.py · llm.py
│   │       ├── tools/          🛒 registry.py (allowlist) · fakestore.py
│   │       ├── guardrails/     🛡️ injection.py · pii.py
│   │       ├── storage/        🗄️ db.py · repo.py (SQLite)
│   │       ├── observability/  📊 metrics.py · costing.py · usage.py · tracing.py
│   │       ├── schemas.py      📋 Pydantic request/response models
│   │       ├── service.py      🔁 orchestration: guardrails → graph → persist → metrics
│   │       └── main.py         🌐 FastAPI app factory + routes
│   └── ui/              🖥️ Streamlit support console
├── packages/shared/     📦 shared constants (decision enum, categories)
├── infra/               📈 Prometheus scrape config + provisioned Grafana dashboard
├── tests/               ✅ deterministic safety + contract suite — no API keys needed
├── scripts/             🌱 seed_tickets.py · smoke_test.sh
├── docs/screenshots/    📸 README screenshots
└── .github/workflows/   ⚙️ ci · code-quality · security · publish-image
                            · release-please · release-image · deploy-cloudrun
```

---

## ⚙️ Configuration

All configuration flows through `apps/api/src/config.py` (pydantic-settings) — no
module reads `os.environ` directly. See `.env.example` for every variable; the
notable ones:

| Var | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai` \| `groq` \| `gemini` \| `nvidia` \| `anthropic` \| `ollama` |
| `LLM_MODEL` | `gpt-4o-mini` | provider-specific chat model id |
| `OPENAI_API_KEY` … | — | per-provider credential (only the selected provider's key is required) |
| `LLM_BASE_URL` | — | optional endpoint override for OpenAI-compatible providers |
| `MAX_REVIEW_ITERATIONS` | `2` | review-loop bound (enforced in code, see above) |
| `MAX_TOOL_ROUNDS` | `3` | researcher tool-call cap per ticket |
| `SQLITE_PATH` | `./deskfleet.db` | audit database path |
| `LANGCHAIN_TRACING_V2` | `false` | enable LangSmith tracing (also needs a real `LANGCHAIN_API_KEY`) |
| `LANGCHAIN_API_KEY` | — | LangSmith credential; the `lsv2_...` placeholder counts as unset |
| `LANGCHAIN_PROJECT` | `deskfleet` | LangSmith project the traces land in |

---

## 🔀 Multi-provider LLM support

Switching providers is a two-line edit in `.env` — no code changes. Graph nodes
receive the model through `build_chat_model()` (`apps/api/src/graph/llm.py`) and
never know which provider is active.

| `LLM_PROVIDER` | Example `LLM_MODEL` | Key var | Extra install |
|---|---|---|---|
| `openai` | `gpt-4o-mini` | `OPENAI_API_KEY` | — |
| `groq` | `llama-3.3-70b-versatile` | `GROQ_API_KEY` | — |
| `nvidia` | `meta/llama-3.1-70b-instruct` | `NVIDIA_API_KEY` | — |
| `ollama` | `llama3.1:8b` | none (`OLLAMA_BASE_URL`) | [Ollama](https://ollama.com) + `ollama pull llama3.1:8b` |
| `anthropic` | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` | `pip install -r apps/api/requirements-providers.txt` |
| `gemini` | `gemini-2.0-flash` | `GOOGLE_API_KEY` | `pip install -r apps/api/requirements-providers.txt` |

Groq, NVIDIA NIM, and Ollama ride the OpenAI-compatible lane (`langchain-openai`
with a `base_url` swap) — zero new dependencies. Anthropic and Gemini use their
native LangChain integrations for the most reliable tool-calling and structured
output. Boot fails fast with a clear message if the selected provider's key is
missing. Costing resolves a `(provider, model)` price table; Ollama and NVIDIA NIM
report `$0`. Caveat: small local models (<8B) can be unreliable at the
structured-output steps (Classifier/Reviewer) — prefer ≥8B instruct models.

---

## 🌐 API reference

| Endpoint | Behavior |
|---|---|
| `POST /resolve` | `{ticket, order_id?}` → `{decision, reply, category, tool_calls, escalation_reason, iterations, langsmith_trace_url, latency_ms, cost_usd}` |
| `GET /health` | liveness probe; also reports `llm_configured` |
| `GET /metrics` | Prometheus scrape endpoint |
| `GET /tickets?limit=N` | last N resolved tickets from SQLite (demo/audit aid) |

```bash
curl -X POST localhost:8080/resolve -H 'content-type: application/json' \
  -d '{"ticket":"Where is my order 3?","order_id":"3"}'
```

---

## ✅ Testing

```bash
make test         # pytest tests/ -v   — NO API key required
make lint         # ruff check .
```

| Test | Guarantees |
|---|---|
| `test_allowlist` | Off-registry tool call is blocked, logged, **never executed** |
| `test_max_iterations` | Loop ends at `ESCALATE` after exactly `MAX_REVIEW_ITERATIONS` |
| `test_injection` | Injected ticket ⇒ `REFUSE` with **zero** LLM invocations |
| `test_hijack_hardening` | Obfuscation (zero-width/fullwidth) detected, poisoned tool output quarantined, leaky drafts escalated with reply withheld, oversized tickets rejected |
| `test_pii` | Email/phone/SSN/card redacted in the API response **and** in the DB |
| `test_api` | `/resolve` schema, `422` on empty ticket, `/health` 200, `/metrics` |
| `test_fakestore` | Tool semantics verified against stubbed HTTP |
| `test_llm_provider` | Provider routing, missing-key errors, and per-provider costing |

---

## 📏 Coding standards

Standards are enforced both locally and in CI (`code-quality.yml`):

| Gate | Tool | Command |
|---|---|---|
| Lint (bug patterns, imports, modern idioms) | ruff | `ruff check .` |
| Canonical formatting | ruff format | `ruff format --check .` |
| Static typing | mypy | `mypy` (config in `pyproject.toml`) |
| Test coverage floor (80%) | pytest-cov | `pytest tests/ --cov --cov-fail-under=80` |
| Python SAST | Bandit | `bandit -r apps/api/src apps/ui packages scripts -ll` |
| Dependency vulnerabilities | pip-audit | runs in `security.yml` |

For local enforcement before every commit:

```bash
pip install pre-commit
pre-commit install        # hooks: ruff, ruff-format, yaml checks, private-key detection
```

---

## 📊 Observability

- **Prometheus** — `deskfleet_tickets_total{decision}`,
  `deskfleet_ticket_latency_seconds` (histogram), `deskfleet_tokens_total`,
  `deskfleet_cost_usd_total`, `deskfleet_llm_calls_total`,
  `deskfleet_token_source_total{source}`, tool-call counters.
- **Grafana** — provisioned **DeskFleet Overview** dashboard: throughput, P50/P99
  latency, decision breakdown, cumulative spend, escalation rate.
- **LangSmith** — every node, tool call, and retry is traced, and the root run's
  URL is returned in the `/resolve` response as `langsmith_trace_url`.

### Token accounting

Cost is computed from the **provider's own reported token counts**, accumulated
across *every* LLM call the graph makes — classify, research, and one
draft/review pair per review iteration. A `UsageCollector` callback is passed in
the graph config and LangGraph propagates it to each nested call, so structured
-output calls (whose return value hides token counts) are captured too.

When a provider reports no usage, the service falls back to a tiktoken estimate
over the ticket and reply. `deskfleet_token_source_total{source="estimated"}`
tracks how often that happens — the fallback is far less accurate, since it
cannot see system prompts, tool schemas, accumulated facts, or retries.

### Enabling tracing

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_...      # a real key; the `lsv2_...` placeholder is ignored
LANGCHAIN_PROJECT=deskfleet
```

`configure_tracing()` runs at startup and exports these into `os.environ`, which
is where the LangChain SDK reads them from — setting them only in `.env` reaches
the `settings` object but **not** the SDK. Real environment variables (Cloud Run
secrets, Compose) always win over `.env`. Confirm with `GET /health`, which
reports `tracing_enabled`.

---

## ⚙️ CI/CD pipeline

```mermaid
flowchart LR
    PUSH["📝 git push / PR"] --> CI["✅ ci.yml\nruff · pytest · docker build ×2"]
    PUSH --> CQ["📏 code-quality.yml\nlint · format · mypy · coverage ≥80%"]
    PUSH --> SEC["🔐 security.yml\nCodeQL · Gitleaks · Trivy · Dep Review\nBandit · pip-audit"]
    CI --> MAIN{"branch == main?"}
    MAIN -- yes --> PUB["📦 publish-image.yml\npytest gate → SHA image → ghcr.io"]
    MAIN -- yes --> RP["🏷️ release-please.yml\nmaintains the release PR + CHANGELOG"]
    MAIN -- "opt-in only" --> DEP["🚀 deploy-cloudrun.yml\npytest gate → gcloud run deploy → /health"]
    RP -- "release PR merged" --> REL["🚀 GitHub Release tagged"]
    REL --> RI["📦 release-image.yml\nsemver + latest tags → ghcr.io"]

    style CI fill:#1a7f37,color:#fff
    style CQ fill:#6f42c1,color:#fff
    style SEC fill:#9a6700,color:#fff
    style PUB fill:#2496ED,color:#fff
    style RI fill:#2496ED,color:#fff
    style DEP fill:#4285F4,color:#fff
```

| Workflow | Trigger | Purpose |
|---|---|---|
| **`ci.yml`** | every push/PR | `ruff check` → `pytest` → `docker build` of both images |
| **`code-quality.yml`** | every push/PR | coding standards: lint, `ruff format --check`, mypy type check, coverage floor (80%) |
| **`security.yml`** | PRs + push to `main` | CodeQL, dependency review, Gitleaks, Trivy, **Bandit** (Python SAST), **pip-audit** (dependency CVEs) |
| **`publish-image.yml`** | push to `main` | re-run tests → publish immutable per-commit SHA image to `ghcr.io` |
| **`release-please.yml`** | push to `main` | maintains the release PR, `CHANGELOG.md`, version tag, GitHub Release |
| **`release-image.yml`** | GitHub Release *published* | build & push the API image to GHCR with semver + `latest` tags |
| **`deploy-cloudrun.yml`** | **opt-in**: manual dispatch, or push to `main` with `DEPLOY_TO_CLOUDRUN=true` | pytest gate → `gcloud run deploy` → `/health` smoke test |

Apart from the optional GCP deploy secrets below, the only secret these workflows
use is `GITHUB_TOKEN`, provided automatically by GitHub — no additional
repository secrets are required for CI/CD to pass.

Releases follow [Conventional Commits](https://www.conventionalcommits.org/):
`feat:` → minor bump, `fix:` → patch bump, `feat!:`/`BREAKING CHANGE` → major bump,
`docs:`/`chore:` → no release. Merging the standing release PR tags the commit,
publishes the GitHub Release, and triggers `release-image.yml`.

<details>
<summary><strong>🚀 Cloud Run deployment (optional, opt-in)</strong> — click to expand</summary>

GCP deployment is **fully optional** — the repo stays green with no GCP account.
`deploy-cloudrun.yml` runs only when *both* are true: the three GCP secrets are
configured, **and** deployment was requested (repo variable
`DEPLOY_TO_CLOUDRUN=true` for auto-deploy on `main`, or a manual
*Run workflow* dispatch). Otherwise the guard job skips everything with a neutral
notice.

When enabled, it completes the deployment spine —
**pytest → docker build → `gcloud run deploy`**:

| Step | Detail |
|---|---|
| **Gate** | The agent-safety suite (allowlist, max-iteration, injection REFUSE) must pass |
| **Auth** | Workload Identity Federation — no long-lived service-account JSON in the repo |
| **Build** | `gcloud run deploy --source apps/api`; Cloud Build reads `apps/api/Dockerfile` |
| **Secrets** | `--set-secrets` from Secret Manager — never `--set-env-vars`, which would land keys in the revision config and logs |
| **Verify** | Polls `<URL>/health` with retries; a deploy that returns 503 fails the job |

To enable it, add:

```bash
# Secret Manager (once per project)
echo -n "$OPENAI_API_KEY"    | gcloud secrets create openai-api-key --data-file=-
echo -n "$LANGCHAIN_API_KEY" | gcloud secrets create langchain-api-key --data-file=-

# Let the Cloud Run runtime SA read them, or the revision fails to start
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/secretmanager.secretAccessor"
```

then set repository **secrets** `GCP_PROJECT_ID`,
`GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, set the repository
**variable** `DEPLOY_TO_CLOUDRUN=true` (or use manual dispatch), and optionally
the **variables** `GCP_REGION`, `CLOUD_RUN_SERVICE`, `LLM_PROVIDER`, `LLM_MODEL`.

The container binds `0.0.0.0:$PORT` as Cloud Run requires — the single most
common cause of a green deploy that serves 503s.

The immutable SHA image published to `ghcr.io` remains the portable artifact if
you'd rather roll out to ECS, Kubernetes, or a plain VM instead.

</details>

<details>
<summary><strong>Required GitHub repository settings</strong> — click to expand</summary>

- **Settings → Actions → General → Workflow permissions:** *Read and write
  permissions*, plus *Allow GitHub Actions to create and approve pull requests*
  (needed by release-please).
- **Settings → Code security:** enable *Code scanning* to receive CodeQL/Trivy
  SARIF uploads.
- **Branch protection on `main`:** require `CodeQL (Python)`, `Dependency Review`,
  `Gitleaks Secret Scan`, `Trivy Filesystem Scan`, and the CI `test` job as status
  checks.

</details>

---

## 🌱 Seed & smoke test

```bash
make api                       # in one shell
python scripts/seed_tickets.py # 5 sample tickets vs. expected decisions
bash scripts/smoke_test.sh     # curl /health + /resolve + /tickets
```

The seed tickets cover the full decision space: an order-status query →
`RESOLVED`, a refund per policy → `RESOLVED`, a prompt-injection attempt →
`REFUSE`, an out-of-scope rant → `ESCALATE`, and a product question →
`RESOLVED`.

---

## 🎓 Credits

**DeskFleet** is the capstone project of **Sanjay Sinalkar**, built for the
**iHub DivyaSampark @ IIT Roorkee × Masai** program — Multi-Agent Systems track
(project brief C·04). The brief called for a LangGraph crew
(Classifier → Researcher → Responder → Reviewer) that resolves real tickets
end-to-end against an external order API, with bounded tools, injection and PII
guardrails, full LangSmith traceability, Prometheus/Grafana observability, and a
CI/CD pipeline gated by agent-safety tests.

Built with: [LangGraph](https://langchain-ai.github.io/langgraph/) ·
[FastAPI](https://fastapi.tiangolo.com/) · [Streamlit](https://streamlit.io/) ·
[Prometheus](https://prometheus.io/) · [Grafana](https://grafana.com/) ·
[LangSmith](https://smith.langchain.com/) ·
[FakeStoreAPI](https://fakestoreapi.com/) (external order/product data).
