# DeskFleet — Multi-Agent Support Ticket Resolver

**LangGraph + FastAPI + Streamlit · monorepo · Docker Compose · GitHub Actions → GHCR**

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
.github/    workflows/ (ci, security, deploy, release-please, release-image)
            release-please-config.json + .release-please-manifest.json
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
| `LLM_PROVIDER` | `openai` | `openai` \| `groq` \| `gemini` \| `nvidia` \| `anthropic` \| `ollama` |
| `LLM_MODEL` | `gpt-4o-mini` | provider-specific chat model id |
| `OPENAI_API_KEY` … | — | per-provider credential (only the selected provider's key is required) |
| `LLM_BASE_URL` | — | optional endpoint override for OpenAI-compatible providers |
| `MAX_REVIEW_ITERATIONS` | `2` | review-loop bound |
| `MAX_TOOL_ROUNDS` | `3` | researcher tool-call cap |
| `SQLITE_PATH` | `./deskfleet.db` | audit DB |
| `LANGCHAIN_TRACING_V2` | `false` | enable LangSmith (env-only, no code change) |

### Multi-provider LLM support

Switching providers = editing two lines in `.env` — no code changes. The graph
nodes receive the model through `build_chat_model()` (`apps/api/src/graph/llm.py`)
and never know which provider is active.

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
missing. Costing resolves a `(provider, model)` price table; Ollama and NVIDIA
NIM report `$0`. Caveat: small local models (<8B) may be unreliable at the
structured-output steps (Classifier/Reviewer) — prefer ≥8B instruct models.

---

## API

| Endpoint | Behavior |
|---|---|
| `POST /resolve` | `{ticket, order_id?}` → decision, reply, tool_calls, trace URL, latency, cost |
| `GET /health` | liveness probe |
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

| Workflow | Trigger | Purpose |
|---|---|---|
| **`ci.yml`** | every push/PR | `ruff check` → `pytest` → `docker build` of both images |
| **`security.yml`** | PRs + push to `main` | CodeQL, dependency review, Gitleaks, Trivy (see below) |
| **`publish-image.yml`** | push to `main` | re-run tests → publish immutable per-commit SHA image to `ghcr.io` |
| **`release-please.yml`** | push to `main` | maintain the release PR, `CHANGELOG.md`, version tag, GitHub Release |
| **`release-image.yml`** | GitHub Release *published* | build & push the API image to GHCR with semver + `latest` tags |

The only secret used by these workflows is `GITHUB_TOKEN`, which GitHub provides
automatically (image push, security uploads, release-please, release-image). No
additional repository secrets are required for CI/CD to pass.

### Image publishing

`publish-image.yml` runs on every push to `main`: it runs `pytest` as the publish
gate, then builds and pushes the immutable per-commit SHA API image to `ghcr.io`.
It has a single job and no external cloud dependency, so a push to `main` cannot
fail on deployment configuration.

Runtime deployment is not part of the automated workflows — the SHA image published
to GHCR is the deployable artifact; roll it out with whatever mechanism your
environment uses.

### Security scanning versions

Trivy runs via `aquasecurity/trivy-action@v0.36.0` (pinned to a published release tag).

### Security scanning

`security.yml` runs on every pull request and on pushes to `main`. All jobs use
least-privilege permissions and workflow-level `concurrency` to cancel superseded runs.

- **CodeQL** — static analysis targeting Python; results upload to the **Security → Code
  scanning** tab (SARIF).
- **Dependency Review** — flags vulnerable/insecure dependency changes; **runs on pull
  requests only** (the action is unsupported on push) and fails on `high`+ severity.
- **Gitleaks** — secret scanning across full git history; uses the built-in
  `GITHUB_TOKEN`, so **no paid license is required** for public/personal repos.
- **Trivy** — filesystem scan for vulnerabilities, misconfigurations, and secrets.
  Runs twice: one pass uploads a full SARIF report to code scanning, a second pass
  **fails the build on HIGH/CRITICAL** (fixable) findings so PRs stay blocked.

### Releases (Release Please + Conventional Commits)

Releases are automated from [Conventional Commits](https://www.conventionalcommits.org/):

1. Merges to `main` update a standing **release PR** that accumulates the changelog and
   the next semantic version (a **`simple`** release component tracked in
   `.github/.release-please-manifest.json`).
2. Merging that release PR tags the commit (e.g. `v0.2.0`), publishes a **GitHub
   Release**, and updates `CHANGELOG.md`.
3. Publishing the release triggers **`release-image.yml`**, which builds `apps/api` and
   pushes to `ghcr.io/<owner>/<repo>/deskfleet-api` tagged with the full version
   (`0.2.0`), the `MAJOR.MINOR` alias (`0.2`), `latest`, and the bare `MAJOR` alias
   only once past `1.0.0` (a `0.x` major tag is intentionally skipped as unsafe).

**First-release bootstrap (automatic).** The manifest baseline is `0.0.0` and the
bootstrap commit carries a one-time `Release-As: 0.1.0` footer, so Release Please cuts
the **first** release as exactly **`v0.1.0`** — no manual label or post-merge edit is
required. `Release-As` only affects the release that contains that commit; once `v0.1.0`
is published the manifest advances to `0.1.0` and every later release resumes normal
Conventional-Commit bumping (`feat` → minor, `fix` → patch, `feat!`/`BREAKING CHANGE`
→ major). Do **not** re-use the footer afterward.

Commit message examples that drive the version bump:

```
feat: add /tickets pagination            # → minor bump (0.1.0 → 0.2.0)
fix: redact SSN in outbound draft        # → patch bump (0.2.0 → 0.2.1)
feat!: change /resolve response schema   # → major bump (0.x stays 0, 1.x → 2.0.0)
docs: clarify allowlist boundary         # → no release (changelog "Other" section)
```

### Required GitHub repository settings

- **Settings → Actions → General → Workflow permissions:** select **Read and write
  permissions** (release-please needs `contents: write` to tag/release, though each
  job also declares its own least-privilege scopes).
- Enable **Allow GitHub Actions to create and approve pull requests** so release-please
  can open its release PR.
- **Settings → Code security:** ensure **Code scanning** is enabled to receive the
  CodeQL and Trivy SARIF uploads.
- **Branch protection on `main`** — add these required status checks so security stays
  blocking: `CodeQL (Python)`, `Dependency Review`, `Gitleaks Secret Scan`,
  `Trivy Filesystem Scan`, and the CI `test` job.

---

## Seed & smoke

```bash
make api                       # in one shell
python scripts/seed_tickets.py # 5 sample tickets vs. expected decisions
bash scripts/smoke_test.sh     # curl /health + /resolve + /tickets
```
