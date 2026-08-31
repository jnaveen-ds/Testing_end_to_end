# Feedback Analyzer — a production-shaped GenAI CI/CD playground

A deliberately small GenAI application (feedback analyzer) used to learn a complete,
production-style engineering lifecycle end to end — with **$0 default cloud cost**.

**Docs:** [LEARNING_PLAN.md](docs/LEARNING_PLAN.md) — 28-day plan to Sep 27 · [DAILY_PLAYBOOK.md](docs/DAILY_PLAYBOOK.md) — per-day services, portal steps, CLI commands, destroy ritual · [RUNBOOK.md](docs/RUNBOOK.md) — running & verifying · [ARCHITECTURE.md](docs/ARCHITECTURE.md) — design · [INTERVIEW_NOTES.md](docs/INTERVIEW_NOTES.md) — decisions

## Architecture

```
┌────────────────────┐
│ React + TypeScript │  (frontend/, static SPA)
└─────────┬──────────┘
          │ /api
┌─────────▼─────────┐     enqueue job      ┌──────────────┐
│ FastAPI (REST API)│ ───────────────────▶ │ Redis queue  │
└─────────┬─────────┘                      └──────┬───────┘
          │ read/write jobs                 Celery worker
┌─────────▼─────────┐                      ┌─────▼──────┐
│    PostgreSQL     │                      │    LLM     │
└───────────────────┘                      └────────────┘
                                    (fake provider by default,
                                     Azure OpenAI when opted in)
```

Flow: user submits feedback text → API creates a `pending` job row and enqueues it on
Redis → the Celery worker calls the LLM provider and stores summary/sentiment/themes
plus token usage and latency → the UI polls the job until it completes.

The **fake LLM provider** is deterministic and free, so local development and CI never
touch Azure. `LLM_PROVIDER=azure` swaps in real Azure OpenAI calls with the same code
path — the same provider-abstraction pattern you would use in a real system.

## Learning roadmap

| Stage | Topic | Where |
|---|---|---|
| 1 ✅ | Application + local Docker Compose stack | `backend/`, `frontend/`, `docker-compose.yml` |
| 2 ✅ | CI: automated tests on every push | `.github/workflows/ci.yml` |
| 3 ✅ | Packaging: build & publish Docker images to GHCR | `.github/workflows/publish.yml` |
| 4 | Config & secrets management (env → Key Vault) | `app/config.py`, `.env.example` |
| 5 | Deploy to an Azure VM (same compose stack, TLS, networking) | Terraform, stage 5 |
| 6 | Deploy to Azure Container Apps (scale-to-zero) | Terraform, stage 6 |
| 7 | Observability: `/stats`, logs, App Insights | `app/main.py#stats` |
| 8 | Scaling: workers, autoscaling rules, load testing | Container Apps rules |
| 9 | Deployment strategies, rollback, failure handling | revisions, health probes |
| 10 | Live LLM cost control & cleanup (`terraform destroy`) | budgets + tags |

## Run locally

```bash
# Full stack (db, redis, api, worker, frontend)
docker compose up --build
# UI:    http://localhost:8080
# API:   http://localhost:8000/docs
```

Or without Docker (uses SQLite + needs a local Redis for the queue):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --app-dir backend          # API on :8000
celery -A app.celery_app:celery_app worker --loglevel=info  # from backend/
cd frontend && npm install && npm run dev                # UI on :5173
```

## Tests

```bash
cd backend && pytest -v          # unit + integration, fake LLM, no services needed
cd frontend && npx tsc --noEmit && npm run build
```

## Configuration

All configuration is environment-based (see `.env.example`; never commit `.env`):

- `LLM_PROVIDER=fake` (default, free) or `azure`
- Azure OpenAI settings only needed for `LLM_PROVIDER=azure` — real keys stay in
  `.env` locally and move to Key Vault in the deployment stages.

## Cost discipline

Default setup is **$0** (fake LLM, local containers, SQLite/Postgres in Docker).
Azure resources will be created with Terraform only when a stage needs them,
tagged with an expiry, and `terraform destroy`ed after each exercise — with a
plan review and estimated cost before every apply.
