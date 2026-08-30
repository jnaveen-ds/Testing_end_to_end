# Architecture — Feedback Analyzer (end-to-end walkthrough)

This document explains every component, every request flow, and how each file maps
to a real production concept. Written for a backend engineer learning the full stack.

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
2. nginx (`frontend/Dockerfile` → nginx config) proxies `/api/*` to the `api` container.
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
| `AZURE_OPENAI_*` | empty | endpoint/key/deployment — real values only in `.env` (never committed) or Key Vault in later stages |

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
