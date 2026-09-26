# Interview / Colleague Explanation Notes — Feedback Analyzer

Everything here is defensible from the actual code. File/function references in
brackets so you can point to real lines, not hand-wave.

---

## 1. The 60-second pitch (memorize this shape)

> "It's a GenAI feedback analyzer built to learn production lifecycle practices.
> A React SPA submits feedback to a FastAPI API. The API never calls the LLM
> inline — it writes a `pending` job row to Postgres and enqueues the job id on
> Redis. A Celery worker consumes it, calls the LLM through a provider
> interface, and updates the row with summary, sentiment, themes, token usage,
> and latency. The UI polls the job until it completes. Everything runs in five
> containers via one compose file, configured entirely by environment
> variables, CI runs tests on every push, and the whole stack maps 1:1 onto an
> Azure deployment with Container Apps."

If the interviewer wants depth, they'll pick a thread — sections below cover each.

---

## Why questions (the ones interviewers actually ask)

### Why a queue instead of calling the LLM in the request handler?
- LLM calls take 1–30+ s. Holding HTTP that long wastes worker connections,
  hits proxy/LB timeouts, and loses the work if the client retries or disconnects.
- The queue gives: **quick acknowledgment** (201 + job id), **durability**
  (accepted work survives worker crashes — message redelivers), and
  **independent scaling** (API tier scales with user traffic, worker tier with
  LLM load — different bottlenecks).
- This is the async job pattern: same shape as video transcoding, emails,
  billing runs — any slow side effect.

### Why write a job row to Postgres at all? Isn't the queue message enough?
- The queue message carries only "do job X" — it is deleted on consumption.
  The row is the durable record: input, result, tokens, latency, error,
  timestamps. UI polls it; nobody scans a queue for results.
- Queues = delivery; DB = source of truth. Confusing the two is a classic
  design smell.

### Why is the API stateless? Why does that matter?
- Any replica can serve any request — no session affinity, no in-memory state.
  Scaling is then just adding replicas behind a load balancer. Job state lives
  in Postgres, not in any process. (In this codebase: nothing in `main.py`
  holds request-scoped state; all reads go back to the DB.)

### Why is the worker a separate process, not a thread in the API?
- Failure isolation: an OOM or hang in LLM handling can't take down the API
  accepting user traffic.
- Independent deploy/scale/restart cadence.
- Celery gives delivery semantics (ack, retry, redelivery) that ad-hoc
  threads don't.

### Why a provider interface around the LLM?
- The rest of the system (`tasks.py`) depends only on the `AnalysisResult`
  shape. `FakeLLMProvider` (deterministic, free, offline) and
  `AzureOpenAIProvider` are interchangeable behind it. That's why tests and CI
  run with zero cloud cost, and why swapping models later is a one-line change
  in `get_provider()`. General rule: never let an external paid dependency
  leak past a seam.

### Why does the UI poll instead of using websockets?
- Honest tradeoff answer: polling a simple `GET /analyses/{id}` every 1.5 s is
  stateless, trivially cacheable, and horizontally scalable; for a
  seconds-long job the UX cost is negligible. WebSockets/SSE buy push
  updates at the cost of stateful connections. Right-sized choice, not
  ignorance — say that.

### Why does nginx proxy `/api` instead of the browser calling port 8000 directly?
- The SPA and API share one browser origin, avoiding environment-specific API URLs and
  CORS dependence. `frontend/src/api.ts` consistently calls `/api`; Vite rewrites it in
  development and `frontend/nginx.conf` strips the prefix in the container.
- This boundary must be tested as part of the deployed artifact. The first local image
  exposed a useful failure: nginx served the SPA but its default configuration returned
  404 for `POST /api/analyses`. Installing the explicit config in `frontend/Dockerfile`
  aligned the production container with the documented request path.

### Why store tokens and latency per job?
- That's usage metering and observability data captured at the source. In a
  real system it feeds cost tracking per customer and SLO dashboards. Capturing
  it in the write path (rather than parsing logs later) is the cheap, reliable way.

## Correctness & failure questions

### What happens if the worker crashes mid-job?
- Celery acks the message only after the task returns; unacked messages are
  redelivered. The new delivery re-runs `process_job`, whose guard only
  processes `pending` jobs — a job already updated to `completed` is skipped.
  That guard is the idempotency key.

### What if the LLM call fails?
- The exception is caught in `process_job`: job → `failed` with the error text
  stored, so the user sees *why* it failed. Transient infra errors (DB/Redis
  down) raise out and Celery retries the task (3×, 10 s delay) — the
  distinction: business failure = terminal state on the row; infra failure =
  retry.

### What if two messages for the same job arrive?
- Status guard: second one sees non-`pending` and exits without touching the
  row. (In bigger systems this becomes per-row locking / unique constraints /
  exactly-once queues — the guard is the small-scale version.)

### Where do secrets live?
- Not in git: `.env` is gitignored, `.env.example` documents shape. Everything
  reaches the app via env vars (12-factor). Later stages move real values to
  Key Vault with managed identity; the app code doesn't change, only where env
  vars come from.

### How do you scale it?
- API replicas: behind LB, scale with request traffic.
- Workers: scale with queue depth — the production signal is
  "messages waiting × avg processing time"; Celery/Container Apps can
  autoscale on that. Concurrency knob here is `--concurrency` on the worker.
- DB: the shared bottleneck; vertical first, read replicas later.
- Postgres table is the write path — one INSERT on submit, one UPDATE per
  completion; small and indexed by status.

## Deployment / lifecycle talking points

- **One artifact, two roles**: backend image runs as API (uvicorn) and worker
  (celery) — compose overrides the command. Same digest deployed everywhere.
- **Same topology locally and in Azure** (compose ↔ Container Apps): db, queue,
  api, worker, static-frontend — only hosting changes, so prod surprises are low.
- **Config = env vars per environment**; images are immutable.
- **CI**: tests (fake LLM, no cloud) + typecheck/build on every push; later
  stages add image publish → deploy with manual approval for production.
- **Rollback story** (stage 9): container revisions roll back image+config
  atomically; DB schema is the compatibility constraint — hence additive
  changes.
- **Cost discipline**: fake provider in dev/CI, scale-to-zero on Container
  Apps, Terraform creates/expenses everything, `destroy` after exercises,
  budget alerts first.

## The numbers, if asked "what would this cost in prod?"
- Local/CI: $0 (fake LLM, containers only).
- Azure Container Apps with scale-to-zero: often ~$0 idle; PostgreSQL +
  registry + logs dominate the floor (~$15–30/mo beyond free tiers).
- LLM cost is per-token and known per job (we store it): ~$0.004 per analysis
  at gpt-5.4-mini rates (2k in / 500 out).

---

## App 1 real-time Chat decisions

### Why is Chat synchronous while Feedback Analyzer uses a queue?

The Chat user expects one answer within a normal interactive request window. Container
Apps replicas handle concurrent short requests, so adding a queue would force a job-ID and
polling contract without solving a current problem. The Feedback Analyzer demonstrates
the asynchronous pattern for slower work. If Chat grows into multi-minute agent work or
waits for a person, it should move to App 3's `202` + status + queue contract.

### Why cache model responses?

Model inference is slower and token-metered; a Redis lookup is much faster. A safe repeated
prompt can return the prior answer with zero new model tokens. Caching is skipped when
inputs are unique, answers must be immediately fresh, authorization cannot be represented
in the key, or provisioned cache cost exceeds saved model cost.

### What makes the cache key safe?

`backend/app/chat.py#cache_key` hashes the tenant scope, normalized prompt, provider/model,
prompt version, and temperature. Prompt-only keys are unsafe because they can leak results
between tenants and keep serving old behavior after a model or system-prompt change. The
current fixed tenant scope is deliberately a single-user learning constraint; authenticated
tenant/user scope is required before production multi-tenancy.

### How is a cache stampede prevented?

Two cache checks surround a per-key lock. The first request that misses acquires the lock
and calls the provider. Waiting requests acquire the lock later, check again, and see the
new value. `test_concurrent_identical_misses_call_provider_once` sends 20 concurrent calls
and proves one provider call, one MISS, and 19 HITs.

### What if Redis fails?

Redis is an optimization, not the source of truth. Read, write, or lock failure degrades
to an uncached model call. That keeps the API available but can increase token cost during
an outage, so production also needs gateway rate limits, bounded maximum replicas, model
quota, and an alert on cache failures/hit-rate collapse.

### Why show tokens, latency, cache status, and correlation ID in the lab UI?

They make architecture observable. The learner can see the first MISS consume tokens and
the second HIT consume none, distinguish model time from total request time, and match a
browser result to server logs. A production UI may hide operational metadata while still
recording it in telemetry.

### Why support both API-key and managed-identity model authentication?

Local development may use an API key stored only in an ignored `.env`, but the Container
App should use `AZURE_OPENAI_AUTH=managed_identity`. `AzureOpenAIProvider` then requests a
short-lived Entra token for the Cognitive Services scope through `azure-identity`; no
model API key is present in the image or environment. The identity still needs the narrow
Foundry/Azure OpenAI data-plane role. Authentication proves who the workload is; RBAC
separately decides what that identity may do.
