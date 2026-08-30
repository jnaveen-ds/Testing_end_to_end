# Runbook — Running & Verifying the Feedback Analyzer

Everything needed to run the application, check every component, and verify the
pipeline works end to end. Companion docs: [ARCHITECTURE.md](ARCHITECTURE.md)
(what the system is), [INTERVIEW_NOTES.md](INTERVIEW_NOTES.md) (why it's designed this way).

---

## 0. Prerequisites

| Requirement | Check | Notes |
|---|---|---|
| Docker with compose plugin | `docker compose version` | The only hard requirement for the main path |
| ~2 GB free RAM, ~2 GB disk | — | Postgres + 2 Python containers + nginx + Redis |
| Ports free | 8080, 8000 | Frontend and API |

Default configuration is fully local: `LLM_PROVIDER=fake` (no network, no cost).

---

## 1. Full stack — one command (the default path)

```bash
git clone https://github.com/jnaveen-ds/Testing_end2end && cd Testing_end2end
docker compose up --build          # add -d to background it
```

First build takes a few minutes (installs Python deps, compiles the frontend).

| Container | Role | Reachable at |
|---|---|---|
| `frontend` | nginx serving the React SPA | http://localhost:8080 |
| `api` | FastAPI (docs UI) | http://localhost:8000/docs |
| `api` health probe | raw JSON | http://localhost:8000/health |
| `worker` | Celery consumer (no port) | see logs (below) |
| `db` | Postgres (no port exposed) | via other containers / `docker compose exec` |
| `redis` | queue broker (no port exposed) | via `docker compose exec` |

Stop: `docker compose down` (add `-v` to also wipe the database volume).

### First test through the UI

1. Open http://localhost:8080
2. Type feedback, e.g. `The app keeps crashing but support was helpful`
3. Click **Analyze** → status badge shows `pending` → flips to `completed` in ~1–2 s
4. Card shows summary, sentiment, themes, token usage, latency

---

## 2. Checking every component individually

Run these while the stack is up. Each includes what a healthy result looks like.

### 2.1 API (backend)

```bash
curl -s localhost:8000/health
# → {"status":"ok","provider":"fake"}          ← healthy; provider=fake = no Azure calls

curl -s localhost:8000/stats
# → {"provider":"FakeLLMProvider","jobs_by_status":{"completed":3,...}}
#   counts by status: pending/running = work in flight; completed = pipeline works
```

Interactive API docs: http://localhost:8000/docs — every endpoint can be tried from the browser.

### 2.2 Frontend

```bash
curl -sI localhost:8080        # HTTP 200, content-type text/html
```
Or open http://localhost:8080 and check: page renders, form accepts text, submitting shows a job id. If the UI loads but submit fails, the problem is API-side (→ 2.1), not frontend.

### 3. Worker (the most important check)

```bash
docker compose logs -f worker
```
Healthy cycle for one job:
```
[2026-...] INFO Received task: tasks.run_analysis[<task-id>]
[INFO] MainProcess ... Task tasks.run_analysis[...] succeeded in 0.05s
```
- `Received` with no `succeeded` → task is stuck (see Troubleshooting #4).
- `succeeded` but job still `pending` → worker↔DB write failed (see #5).

### 2.4 Redis (queue/cache)

```bash
docker compose exec redis redis-cli ping                    # → PONG (alive)
docker compose exec redis redis-cli llen celery             # messages waiting
```
`celery` queue length should return to **0** shortly after jobs are submitted. A constantly growing queue with an idle worker means the worker can't consume (wrong `REDIS_URL`, worker crashed).

### 2.5 Postgres (database)

```bash
docker compose exec db psql -U app -d feedback -c "SELECT 1;"   # alive
# Job table — the real output of the pipeline:
docker compose exec db psql -U app -d feedback \
  -c "SELECT id, status, sentiment, prompt_tokens, latency_ms FROM analysis_jobs ORDER BY created_at DESC LIMIT 5;"
```
Healthy: newest jobs `completed`, sentiment in (positive/neutral/negative), tokens > 0. `failed` rows: check their `error` column:
```bash
... -c "SELECT id, error FROM analysis_jobs WHERE status='failed' LIMIT 5;"
```

### 2.6 The full pipeline trace (do this once after every change)

Submit and watch it propagate through every hop:

```bash
# 1. Submit
JOB=$(curl -s -X POST localhost:8000/analyses -H 'Content-Type: application/json' \
      -d '{"text":"onboarding was confusing but docs helped"}' | jq -r .id)

# 2. Immediately check: row exists, pending → running
docker compose exec db psql -U app -d feedback -c "SELECT status FROM analysis_jobs WHERE id='$JOB'"

# 3. Worker received it?  (docker compose logs -f worker → "Received task")

# 4. Result written?
sleep 2 && curl -s localhost:8000/analyses/$JOB | jq

# 5. Queue drained? redis-cli llen celery → 0
# 6. UI shows completed card at localhost:8080
```

All six passing = every hop (API→DB, API→Redis, Redis→worker, worker→LLM, worker→DB, DB→UI) is verified.

---

## 3. Running on a server (stage 5 pattern: one Linux VM)

Same stack, same command — only the host changes.

```bash
# on the VM (Ubuntu):
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
git clone https://github.com/jnaveen-ds/Testing_end2end && cd Testing_end2end
docker compose up -d --build
```

Open firewall (Azure NSG / cloud console) for ports 80 and 8000 — better: only 80, and put the API behind the frontend's nginx.

Check from your laptop:

```bash
curl http://<SERVER_IP>/health        # via a proxy/ingress on the VM
```

On the server itself, everything from section 2 works identically (`docker compose logs`, `exec`...). To keep it running across reboots: `sudo systemctl enable docker` (compose restart policies handle the containers).

Production-style hardening to practice here (stage 5 of the roadmap): TLS via nginx/certbot, only port 443 public, `.env` with real `LLM_PROVIDER=azure` values owned by root, and `docker compose pull && up -d` as the update path.

---

## 4. Running without Docker (development with hot reload)

For iterating on code — edit a file, see the change without rebuilding images.

```bash
# infra only in Docker (or native Postgres/Redis if installed)
docker compose up -d db redis

# backend (terminal 1) — SQLite keeps this dependency-free
export DATABASE_URL="sqlite:///./local.db"        # Windows: set DATABASE_URL=...
export REDIS_URL="redis://localhost:6379/0"
cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000
#  API: http://localhost:8000/docs  (hot reload on save)

# worker (terminal 2)
cd backend && celery -A app.celery_app.celery_app worker --loglevel=info

# frontend (terminal 3) — dev server with hot reload + /api proxy to :8000
cd frontend && npm install && npm run dev          # UI on http://localhost:5173
```

Note: without Docker the API/worker use SQLite + localhost Redis; the frontend dev server proxies `/api` → `:8000` (see `vite.config.ts`).

---

## 5. Tests (no services needed at all)

```bash
cd backend && ../.venv/bin/python -m pytest tests -v      # 12 tests, SQLite + fake LLM
cd frontend && npm ci && npx tsc --noEmit && npm run build
```

If tests fail after a change: they run with the fake provider and stubbed queue, so a failure is in application logic — not in infra.

---

## Troubleshooting

| # | Symptom | Likely cause | Check / fix |
|---|---|---|---|
| 1 | `docker compose up` fails on port | 8000/8080 already bound | `lsof -i :8000` or change the host port mapping |
| 2 | Frontend loads, submit 5xx | API down or DB not ready | `curl localhost:8000/health`; `docker compose logs api` |
| 3 | Job stays `pending` forever | Worker not consuming | `docker compose logs worker`; `redis-cli llen celery` growing = worker dead/wrong REDIS_URL |
| 4 | Worker logs show `Received` but no `succeeded` | Task hung (provider timeout) | worker log tail; with `LLM_PROVIDER=azure` check endpoint/key env vars |
| 5 | Worker `succeeded` but job still pending | DB write failed | `docker compose logs worker | grep -i error`, check `DATABASE_URL` |
| 6 | `failed` jobs with provider errors | Azure config / quota / key | `SELECT error FROM analysis_jobs WHERE status='failed'`; switch to `LLM_PROVIDER=fake` to isolate |
| 7 | API can't reach `db` / `redis` | Started before healthchecks passed or wrong hostnames | compose `depends_on` conditions; hostnames are service names (`db`, `redis`), never `localhost` |
| 8 | Works locally, fails on server | Stale image or missing env | `docker compose build --no-cache api worker`; diff env vars between environments |

---

## One-paragraph summary (for explaining to a colleague)

> `docker compose up --build` runs five containers: Postgres (source of truth), Redis (queue), API (FastAPI), worker (Celery), frontend (nginx/React). Submit feedback at localhost:8080 → API writes a `pending` row and enqueues the id on Redis → worker logs the task, calls the LLM, writes results → UI polls until `completed`. Verify each hop: `/health` + `/stats` for the API, `logs -f worker` for the consumer, `redis-cli llen celery` for the queue (should drain to 0), `SELECT ... FROM analysis_jobs` for the data, and the six-step trace in §2.6 for the full pipeline.
