# Architecture — Feedback Analyzer and App 1 Chat

This document explains every component, every request flow, and how each file maps
to a real production concept. Written for a backend engineer learning the full stack.

The original queued Feedback Analyzer remains implemented. App 1 adds a second,
synchronous learning path: React calls `POST /chat`, FastAPI checks a scoped TTL cache,
and only a cache miss invokes the configured fake/Azure provider. The same FastAPI image
can run the combined local API (`app.main:app`) or the dedicated future Container App
entry point (`app.chat_api:app`).

---

## 1. The 30,000-foot view

```
                         ┌─────────────────────────────── YOUR BROWSER ─────────────────────────┐
                         │                                                                      │
                         │   React SPA (static JS loaded once from nginx)                       │
                         │   - renders a form, calls fetch("/api/...")                          │
                         └──────────────────────────────┬───────────────────────────────────────┘
                                        HTTP JSON       │
                         ┌──────────────────────────────▼───────────────────────────────────┐
                         │  nginx (frontend container)          FastAPI (api container)      │
                         │  serves static files              ① POST /analyses  → create job  │
                         │  proxies /api → api:8000          ② GET /analyses/{id} → poll     │
                         │                                   ③ GET  /stats                   │
                         └──────────────────────────────┬─────────────────────────────────────┘
                                                │                    │
                              INSERT job (pending)               ENQUEUE task id
                                                │                    │
                     ┌──────────────────────────▼───┐    ┌───────────▼──────────┐
                     │ PostgreSQL                    │    │ Redis                │
                     │ the system of record:         │    │ message broker only  │
                     │ analysis_jobs table:          │    │ (no business data)   │
                     │  id, input_text, status,      │    └───────────┬──────────┘
                     │  summary, sentiment, themes,  │                │ consume
                     │  tokens, latency, error       │                │
                     └────────────────▲──────────────┘        ┌─────────┴─────────┐
                                      │  UPDATE row when done │ Celery worker     │
                                      │                       │ (same image as    │
                                      │                       │ the API, different│
                                      │                       │ entrypoint)       │
                                      │                       └─────────┬─────────┘
                                      │                                 │ call
                                      │                    ┌────────────▼────────────┐
                                      └────────────────────┤ LLM provider            │
                                           write results   │ fake (default, free)   │
                                           + status=completed          │ or azure openai │
                                                       └───────────────────┘
```

**The one-sentence version:** the API never calls the LLM inside the web request — it
writes a `pending` job row, drops the job id on a Redis queue, and a separate worker
process does the slow LLM call and updates the row. The UI polls the row until status
changes. That split (web tier / queue / worker / database) is the shape of most
production backend systems at any scale.

---

## 2. The components and why each one exists

| Component | Container | What it does | Production equivalent |
|---|---|---|---|
| **SPA** (Single Page App) | `frontend` (nginx) | Static JS/HTML loaded once; afterwards it only exchanges JSON with the API. It holds no business logic or state. | The product UI, served from a CDN or ingress in real deployments |
| **REST API** | `api` | Stateless request handler: validates input, writes rows, enqueues work, answers polls. Knows nothing about LLMs. | Ingress to any microservice tier; must stay stateless so it can scale horizontally |
| **Relational DB** | `db` (Postgres) | The single source of truth. One row per job = an append-friendly audit of input, result, usage, and errors. | Postgres/MySQL everywhere; "job table" is the async-task pattern |
| **Queue** | `redis` | Hand-off buffer between "request time" and "processing time". Decouples them so a slow LLM can't hold an HTTP connection or crash the API. | SQS / Service Bus / Kafka — same role, different guarantees |
| **Worker** | `worker` | Long-running process that consumes the queue, does the slow work (LLM), writes results. Can crash/restart without losing accepted jobs — the row + queue message are the durable hand-off. | Celery workers, Sidekiq, K8s Jobs, Container Apps "worker" apps |
| **LLM provider** | inside worker | External inference. Behind an interface so a fake can stand in locally. | Any paid external dependency — always behind an interface + fake |

**Why a queue at all?** An LLM call takes 1–30 s. Holding an HTTP request open for that
wastes connections, times out through load balancers, and loses the work on retry.
Queue + job-row = accepted-quickly, processed-later, status-checkable. This is the
single most transferable pattern in backend engineering.

---

## 3. The lifecycle of one request (trace it in the code)

**Submit** — `frontend/src/App.tsx#submit` → `POST /api/analyses`
1. React calls `createAnalysis(text)` (`frontend/src/api.ts`) — plain JSON over HTTP.
2. nginx (`frontend/Dockerfile` → `frontend/nginx.conf`) strips the `/api` prefix and
   proxies the request to the `api` container on port 8000.
3. FastAPI validates the body against `AnalysisCreate` (`app/schemas.py`). Bad input never reaches your code — this is why `test_rejects_blank_text` expects 422.
4. `create_analysis` (`app/main.py`) inserts `AnalysisJob(status=pending)` (`app/models.py`) and calls `run_analysis_task.delay(id)` — that **serializes the job id onto Redis** and returns instantly. Response: `201 {id, status: "pending"}`.

**Process** — Celery worker, `app/tasks.py`
5. The worker's event loop receives the message and calls `process_job`.
6. Status guard: only `pending` jobs are processed (idempotency — a redelivered message can't overwrite a finished result).
7. `get_provider()` (`app/llm.py`) returns `FakeLLMProvider` or `AzureOpenAIProvider`. The worker calls `.analyze(text)` and gets the same `AnalysisResult` shape either way.
8. One `UPDATE` persists summary, sentiment, themes, token counts, latency — and `status=completed`. Any exception → `status=failed` + `error` text; Celery retries the message 3× for transient infra errors.

**Read** — React polls `GET /analyses/{id}` every 1.5 s
9. `get_analysis` reads the row. UI renders a status badge, then the result + usage when `status === "completed"`.

> **Key mental model:** the queue carries only *"do job X"*. The database carries the
> work itself. Queues are for delivery, not storage. Workers are stateless too —
> crash one mid-task and the message redelivers; the row guard makes the retry safe.

---

## 4. File map — every file to its concept

```
backend/
├── requirements.txt          # pinned Python deps (fastapi, celery, sqlalchemy, redis, pytest)
├── Dockerfile                # ONE image, two roles: CMD=API, compose overrides command → worker
└── app/
    ├── config.py             # all config from env vars (12-factor) — .env locally, Key Vault later
    ├── db.py                 # engine + session factory; get_db() = one session per request
    ├── models.py             # SQLAlchemy ORM: the analysis_jobs table (the source of truth)
    ├── schemas.py            # Pydantic request/response contracts = the API's typed boundary
    ├── llm.py                # provider interface + fake + azure — the seam for external deps
    ├── celery_app.py         # broker/backend wiring (Redis URLs)
    ├── tasks.py              # worker logic: plain function (testable) + thin Celery wrapper
    └── main.py               # FastAPI routes + CORS + create_all on startup
backend/tests/
    ├── test_llm.py           # unit tests: pure logic, no services
    ├── test_api.py           # API integration: real routes, stubbed enqueue
    └── test_tasks.py         # worker tests: real DB, no broker (calls process_job directly)
frontend/
├── package.json / vite.config.ts / tsconfig.json
├── Dockerfile                # multi-stage: node build → nginx serve
├── nginx.conf                # same-origin /api proxy + SPA route fallback
└── src/
    ├── main.tsx / styles.css # app bootstrap + styling
    ├── api.ts                # typed API client — the ONLY file that knows HTTP details
    └── App.tsx               # the one screen: form + poller + result card
root:
├── docker-compose.yml        # the whole stack for local dev (the "production topology, free")
├── .github/workflows/ci.yml  # CI: tests + typecheck on every push/PR
├── .github/workflows/publish.yml  # builds & pushes both images to GHCR on main
├── .env.example              # documents every env var, no real secrets ever
└── .gitignore                # keeps .env, node_modules, venvs, tfstate out of git
```

---

## 5. Configuration & secrets (12-factor style)

Everything is environment-driven (`app/config.py`); nothing is hardcoded:

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | SQLite (local) | Postgres inside compose, Azure PostgreSQL later |
| `REDIS_URL` | localhost | Redis inside compose |
| `LLM_PROVIDER` | `fake` | `fake` = free/offline; `azure` = real Azure OpenAI |
| `AZURE_OPENAI_*` | empty | endpoint/auth/deployment; API keys stay in `.env`/Key Vault, while Azure runtime uses managed identity |

The same image + different env vars = different behavior per environment (dev → staging → prod). That is the 12-factor principle, and it is what makes the later Terraform stages simple.

---

## 6. How this maps to the Azure deployment (stages 5–6)

The local Docker topology **is** the production topology — only the hosting changes:

| Local (Docker Compose) | Stage 5: Azure VM | Stage 6: Azure Container Apps |
|---|---|---|
| container = one compose service | docker containers on 1 VM | one Container App per role |
| Postgres container | same VM, volume | Azure Database for PostgreSQL |
| Redis container | same VM | Azure Redis (briefly) / containerized |
| port mapping | VM + NSG + nginx + TLS | managed ingress + revisions |
| restart: always | systemd / compose restart | scale rules, scale-to-zero |
| docker logs | CloudWatch-equivalent (Azure Monitor) | App Insights + Log Analytics |
| .env file | VM env / Key Vault | Key Vault + managed identity |

Concepts you are practicing now that transfer directly: stateless API tier, durable job rows, queue decoupling, provider seam, env-per-environment config, health endpoints (`/health` for probes), `/stats` for observability.

---

## 7. Running it

```bash
docker compose up --build     # everything: UI :8080, API docs :8000, worker logs in compose
```

Tests (no Docker needed — fake LLM + SQLite, stubbed broker):

```bash
cd backend && python -m pytest tests -v
cd frontend && npm ci && npx tsc --noEmit && npm run build
```

Smoke the flow manually:

```bash
curl -X POST localhost:8000/analyses -H 'Content-Type: application/json' \
     -d '{"text":"app is slow but support was great"}'
# {"id":"...","status":"pending",...}   ← then GET /analyses/{id} until "completed"
```

---

## 8. App 1 real-time Chat — implemented local architecture

```text
React Chat page (`frontend/src/pages/ChatPage.tsx`)
        │ POST /api/chat
        ▼
nginx/Vite removes /api → FastAPI `/chat` (`backend/app/chat.py`)
        │ validate 1..2000 characters
        │ build SHA-256 key from tenant + prompt + provider/model + prompt version
        ▼
ChatCache (`backend/app/chat_cache.py`)
        ├─ HIT  → answer + zero new model tokens
        └─ MISS → per-key lock → check cache again → provider.chat(prompt)
                                              │
                                              ▼
                              Fake provider locally/CI, Azure provider when opted in
                                              │
                                              ▼
                              cache successful answer for 900 seconds → response
```

### Request lifecycle

1. React trims the prompt, enforces a 2,000-character browser limit, and posts JSON through
   the same-origin `/api` path. FastAPI independently rejects blank or oversized input.
2. `cache_key()` includes the fixed learning tenant scope, normalized whitespace,
   provider/model, prompt version, and temperature. This prevents reuse across boundaries
   that can change answer meaning or authorization.
3. On a HIT, FastAPI returns the cached answer with zero prompt/completion tokens and zero
   model latency. Each HTTP response still receives its own correlation ID.
4. On a MISS, a per-key lock prevents concurrent identical requests from all invoking the
   provider. The cache is checked again after lock acquisition because another request may
   have produced the value while this request waited.
5. Only a successful answer is cached. The in-memory cache is the free test/default path;
   Compose selects Redis so different API replicas can share values and locks.
6. Redis read/write/lock failures degrade to a cache miss. This preserves availability,
   but future gateway rate limits and maximum replicas must bound model cost during an
   outage.

### File map

| File | Responsibility |
|---|---|
| `backend/app/chat_api.py` | Dedicated App 1 FastAPI application with `/health`, `/ready`, and `/chat` |
| `backend/app/chat.py` | Cache-key contract, synchronous cache-aside service, and route |
| `backend/app/chat_cache.py` | In-memory TTL cache for tests and Redis cache/distributed lock for shared runtime |
| `backend/app/llm.py` | Common `.chat()` provider seam; deterministic fake and Azure implementation |
| `backend/tests/test_chat.py` | MISS/HIT, zero hit tokens, input boundaries, key scope, TTL, and stampede tests |
| `frontend/src/pages/ChatPage.tsx` | Prompt form, loading/error states, cache badge, token/latency metrics, correlation ID |
| `frontend/src/App.tsx` | Shared shell and tabs for App 1 and the existing Feedback Analyzer |

### Configuration

| Variable | Default | Local/Compose meaning | Azure mapping |
|---|---|---|---|
| `CHAT_CACHE_BACKEND` | `memory` | Tests need no service; Compose sets `redis` | Azure Managed Redis after estimate approval |
| `CHAT_CACHE_TTL_SECONDS` | `900` | 15-minute response freshness exercise | Environment setting; measured per use case |
| `CHAT_PROMPT_VERSION` | `v1` | Changing prompt behavior creates new cache keys | Revision configuration |
| `CHAT_TENANT_SCOPE` | `public-learning-demo` | One fixed non-authenticated lab scope | Replace with authenticated tenant/user scope before multi-tenant production |
| `REDIS_URL` | localhost | Compose uses `redis://redis:6379/0` | Managed Redis TLS/Entra configuration later |
| `LLM_PROVIDER` | `fake` | Free deterministic development/CI | `azure` only for controlled Foundry calls |
| `AZURE_OPENAI_AUTH` | `api_key` | Optional local real-provider experiment | `managed_identity`; no model API key in the app |
| `AZURE_MANAGED_IDENTITY_CLIENT_ID` | empty | Not needed for fake/API-key mode | User-assigned identity client ID; empty uses the default Azure credential chain |

### Local-to-Azure mapping

| Local implementation | Azure target | Why the contract stays the same |
|---|---|---|
| Vite/nginx same-origin `/api` | Static Web Apps → APIM | Browser still knows only one public API base |
| `app.chat_api:app` under uvicorn | Azure Container Apps revision | Same image/entry point, managed ingress and scaling |
| `MemoryChatCache` / Redis container | Azure Managed Redis | `ChatCache` contract keeps service logic unchanged |
| `FakeLLMProvider` | Foundry/Azure OpenAI provider | `.chat()` returns the same typed result |
| process-local logs | Application Insights/Log Analytics | Correlation ID and metrics become cloud traces |

### Verification completed locally

- Full backend suite: 18 tests passed.
- Frontend: TypeScript check and production build passed.
- Live request: first identical prompt returned MISS with tokens; second returned HIT with
  zero prompt and completion tokens.
- Twenty concurrent identical requests produced one provider invocation in the asymmetric
  stampede test.
- Desktop and narrow React states were rendered and inspected.

Azure verification remains pending: ACR image, Container Apps scale-to-zero, managed
identity, Foundry tokens, APIM HTTPS/rate limit, Managed Redis, telemetry, revision, and
rollback.
