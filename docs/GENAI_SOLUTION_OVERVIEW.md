# Three GenAI Applications — Problem Statements and Solution Architecture

This is **Document 1** of the accelerated Azure GenAI learning project. It explains what
we are building, why each application exists, its architecture, and how the design solves
the problem. Read this before the app-by-app
[Build & Deployment Guide](GENAI_DEPLOYMENT_GUIDE.md).

Visual version: [GENAI_SOLUTION_OVERVIEW.html](GENAI_SOLUTION_OVERVIEW.html).

## 1. Goal and design rules

Build three deliberately small applications that expose three common production GenAI
patterns while reusing one platform:

1. **Real-time Chat** — synchronous inference, Fargate-style serverless containers,
   concurrent users, cache, token savings, scaling, TLS, and rollback.
2. **Document Q&A** — retrieval-augmented generation (RAG), private documents, vector
   search, grounding, citations, and safety.
3. **Approval-gated Agent** — long-running work, queue load leveling, durable wait for a
   human decision, TTLs, retries, idempotency, and audit history.

Every application follows the same simple product rule:

- **Frontend:** React + TypeScript.
- **Public backend:** FastAPI + typed OpenAPI contract.
- **Browser boundary:** React calls only FastAPI through API Management; it never receives
  Redis, Search, Storage, Service Bus, Cosmos DB, or model credentials.
- **Local/CI default:** deterministic fake providers, no Azure/network/token cost.
- **Azure authentication:** managed identity and least-privilege RBAC where supported.
- **Lifecycle:** deploy → verify → fail/recover → redeploy/rollback → capture evidence →
  destroy.

To avoid unnecessary code duplication, one React SPA supplies three pages and one backend
image contains three small FastAPI entry points. Azure runs the backend image as separate
services where isolation or scaling behavior matters.

### Reusable decision lens

This documentation is designed to remain useful beyond these three applications. Every
service, pattern, and deployment strategy is evaluated with the same questions:

| Question | Why it matters |
|---|---|
| What problem does it solve? | Prevents adding technology only because it is popular |
| When should and should not it be used? | Defines the decision boundary and simpler alternatives |
| How does it work and how is it configured? | Connects the concept to code, portal, CLI, and YAML |
| What is the cost model? | Identifies fixed/hourly, consumption, storage, operation, token, and egress meters |
| What latency does it add or remove? | Exposes network hops, cold starts, cache hits, queue wait, and processing time |
| How does it scale? | Separates request concurrency, queue depth, throughput, quota, and partition limits |
| Is it secure by default? | Identifies identity, encryption, public exposure, secrets, and tenant boundaries |
| How does it fail and recover? | Makes timeout, retry, dead letter, degradation, and rollback explicit |
| How is it verified? | Requires evidence of behavior—not merely successful resource creation |

Cost values vary by region, offer, date, and SKU. Therefore the documents explain the
**meter and relative cost behavior** and require the portal estimate/Cost Management view
before creation rather than presenting a stale fixed price as universal.

## 2. Whole-system architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ React SPA — Azure Static Web Apps                                          │
│ Chat page                 Documents page                 Agent page          │
└───────────────┬───────────────────┬───────────────────────────────┬─────────┘
                └───────────────────┴───────────────┬───────────────┘
                                                    │ HTTPS
                                           ┌────────▼────────┐
                                           │ API Management  │
                                           │ routes + limits │
                                           └───┬─────┬────┬──┘
                    ┌──────────────────────────┘     │    └─────────────────────┐
                    ▼                                ▼                          ▼
        ┌────────────────────┐          ┌────────────────────┐      ┌────────────────────┐
        │ Chat FastAPI       │          │ RAG FastAPI        │      │ Agent FastAPI      │
        │ Container Apps     │          │ Container Apps     │      │ Container Apps     │
        └──────┬─────────┬───┘          └──────┬─────────┬───┘      └─────────┬──────────┘
               │         │                     │         │                    │
        ┌──────▼───┐ ┌───▼───────┐      ┌──────▼───┐ ┌──▼─────────┐   ┌──────▼───────────┐
        │ Managed  │ │ Foundry   │      │ AI Search│ │ Blob       │   │ Durable Functions│
        │ Redis    │ │ chat model│      │ vectors  │ │ documents  │   │ approval + timer │
        └──────────┘ └───────────┘      └──────┬───┘ └────────────┘   └──────┬───────────┘
                                               │                              │ approved
                                        ┌──────▼──────┐                ┌──────▼──────┐
                                        │ Foundry     │                │ Service Bus │
                                        │ embed + chat│                │ work queue  │
                                        └─────────────┘                └──────┬──────┘
                                                                              ▼
                                                                    ┌────────────────┐
                                                                    │ Agent worker   │
                                                                    │ + Cosmos status│
                                                                    └────────────────┘

Shared platform: ACR · managed identity/RBAC · Key Vault · App Insights · Log Analytics
Delivery: GitHub PR checks → immutable images → GitHub OIDC → Azure revisions
```

### Why this is one platform, not one large application

The UI, dependencies, identity conventions, telemetry, and deployment pipeline are shared
because repeating them provides little learning value. Runtime boundaries remain distinct:

- Chat can scale independently from document retrieval.
- Agent work cannot consume all synchronous API capacity.
- A failure or bad revision can be isolated and rolled back per API.
- Each API demonstrates a different architecture without adding unrelated UI complexity.

## 3. App 1 — Real-time Chat

### Problem statement

Users need a simple chat page that returns an LLM response quickly. Multiple users may
ask the same or similar safe question. Calling the model for every identical request
increases latency and token cost. The API must scale during a burst, scale down while
idle, use real HTTPS, and support safe revision rollback.

### Actors and outcome

- **User:** submits a bounded prompt and sees response, token/latency, and cache status.
- **Operator:** sees replicas, cache hits/misses, failures, and revision health.
- **Expected result:** first request is a cache miss and invokes the model; an identical
  safe request is a hit and consumes no new model tokens.

### Architecture

```text
React Chat page
      │ POST /chat
      ▼
API Management ──rate limit/TLS──▶ Chat FastAPI on Container Apps
                                            │
                          cache key ─────────┴──────────┐
                                            │          │
                                            ▼          │ MISS
                                  Azure Managed Redis  │
                                            │ HIT      ▼
                                            └──── Foundry chat model
```

### How the design addresses the problem

1. **Container Apps handles concurrent HTTP traffic.** KEDA-based scaling adds replicas;
   minimum zero avoids idle compute. This is the practical Azure counterpart to an
   ECS/Fargate API service.
2. **Cache-aside reduces duplicate model work.** FastAPI derives a SHA-256 key from tenant
   scope, normalized input, model deployment, prompt version, and generation settings.
3. **A distributed lock prevents a cache stampede.** Concurrent identical misses do not
   create 20 identical model calls.
4. **TTL controls freshness.** A 15-minute lab TTL demonstrates expiry; prompt/model
   version changes naturally create a new key.
5. **APIM and Container Apps provide trusted HTTPS.** Certificates terminate at managed
   ingress, not inside the Python image.
6. **Immutable revisions enable rollback.** A bad environment value or image creates a
   new revision; traffic can return to the prior known-good revision.

### Use this architecture when

- responses usually complete within a normal HTTP window;
- workloads are stateless and horizontally scalable;
- repeated safe requests can reuse results;
- traffic is bursty and scale-to-zero is useful.

### Do not use it when

- work takes minutes or waits for a person;
- output has user-specific authorization but cache keys lack that scope;
- the request performs non-repeatable side effects;
- every prompt is unique, making cache infrastructure more expensive than saved tokens.

### Acceptance criteria

- React → APIM → FastAPI → Foundry succeeds over HTTPS.
- Cache MISS then HIT is visible; hit reports zero newly consumed model tokens.
- 20 concurrent identical requests produce one model call.
- Replicas scale and can return to zero.
- Wrong configuration is diagnosed from logs; previous revision is restored.

## 4. App 2 — Document Q&A (RAG)

### Problem statement

Users need answers based on a small private document set rather than only the model's
general training. Answers must cite retrieved source material and must not invent an
answer when the documents do not contain it.

### Actors and outcome

- **Content owner:** uploads two harmless sample documents.
- **User:** asks a question and sees an answer with source citations.
- **Operator:** inspects indexing status, retrieval results, safety decisions, latency,
  and token use.
- **Expected result:** known questions cite the correct chunk; unknown questions explicitly
  say the supplied documents do not provide the answer.

### Architecture

```text
Ingestion
React Documents page → RAG FastAPI → private Blob Storage
                                      │ chunk + embed
                                      ▼
                                Azure AI Search index

Question
React Documents page → APIM → RAG FastAPI → Content Safety
                                          → AI Search top-k chunks
                                          → Foundry grounded prompt
                                          → answer + source metadata
```

### How the design addresses the problem

1. **Blob is the durable source of truth.** Search is a rebuildable serving index, not the
   canonical document store.
2. **Chunking creates retrievable units.** Each chunk retains source ID/title and position
   so citations come from metadata rather than model-invented links.
3. **Lexical retrieval is tested before vectors.** This makes basic indexing errors easier
   to see. Vector retrieval is then added for semantic similarity.
4. **FastAPI constructs a bounded grounded prompt.** Only top relevant chunks are sent,
   reducing tokens and unrelated context.
5. **The prompt requires evidence-aware refusal.** If retrieval lacks sufficient evidence,
   the answer is “not found in supplied documents.”
6. **Content Safety is a separate control.** Input/output safety is observable and not
   confused with retrieval relevance or model correctness.

### Use this architecture when

- knowledge is private, domain-specific, or changes more often than a model;
- citations and traceable source context matter;
- documents are unstructured and semantic retrieval improves discovery.

### Do not use it when

- exact transactional answers should come from SQL/API queries;
- a deterministic lookup is enough;
- the corpus has no access-control metadata but different users have different rights;
- retrieval quality is not evaluated—RAG can still confidently ground on the wrong chunk.

### Acceptance criteria

- Uploaded files remain private in Blob.
- Search explorer returns expected lexical and vector chunks.
- A known question cites the correct source/title.
- An unknown question does not hallucinate.
- React calls only FastAPI/APIM; no Storage/Search key appears in the browser.

## 5. App 3 — Approval-gated Agent

### Problem statement

Some LLM/agent tasks take longer than a normal HTTP request and may propose an action that
must not run until a human approves it. The application must survive restarts while
waiting, handle bursts without overwhelming model/tool quotas, expire stale work, retry
transient failures without duplicating side effects, and preserve a decision audit trail.

### Actors and outcome

- **Requester:** submits a task and receives a run ID immediately.
- **Approver:** reviews the exact proposed plan and approves or rejects it.
- **Worker:** executes only an approved, non-expired plan.
- **Operator:** inspects workflow state, queue depth, retries, dead letters, and audit data.
- **Expected result:** approval continues; rejection and timeout execute nothing.

### Architecture

```text
React Agent page ─POST /runs─▶ APIM ─▶ Agent FastAPI ─▶ Durable orchestrator
       ▲                                             plan + plan_hash
       │ GET /runs/{id}                                    │
       │                                      awaiting_approval + durable timer
       │                                                    │
       └──── Approve/Reject ─▶ FastAPI ─external event──────┤
                                                            │ approved only
                                                            ▼
                                                     Service Bus queue
                                                            │
                                                     controlled worker
                                                            │
                                                     Cosmos result/audit
```

### How the design addresses the problem

1. **FastAPI returns `202 Accepted`.** The browser receives `run_id` and `status_url`; no
   request remains open for minutes.
2. **Durable Functions checkpoints state.** Waiting for approval consumes no dedicated
   web request or worker process and survives host restarts.
3. **External event races a durable timer.** Approve/reject within ten minutes transitions
   the run; timeout marks it expired and executes nothing.
4. **Approval binds to an immutable `plan_hash`.** A changed plan cannot reuse a previous
   approval. Actor, timestamp, decision, and hash are appended to audit history.
5. **Service Bus load-levels approved work.** Queue depth absorbs bursts; worker concurrency
   is capped to protect model/tool rate limits.
6. **Idempotent transitions prevent duplicate action.** Only `awaiting_approval` can move
   to `queued`; duplicate clicks/events return the existing decision.
7. **Retries and DLQ separate transient from poison work.** Maximum delivery attempts move
   repeatedly failing or expired messages to inspection instead of an infinite loop.
8. **Cosmos stores product status/audit.** Durable runtime storage remains an internal
   implementation detail. Cosmos item TTL cleans old lab records.

### The four lifetime controls

| Lifetime | Where/when to use | How it helps | Cost and latency | Security view | Expiry behavior |
|---|---|---|---|---|---|
| Redis cache TTL | Reusable, safe, non-side-effecting responses where freshness has a known bound | Reduces repeated model calls and token spend | Cache hit adds a small Redis network hop but removes much larger model latency/cost; longer TTL increases hit rate | Include tenant/auth scope and prompt/model version in key; never cache secrets/errors | Key disappears; next request recomputes |
| Service Bus message TTL | Commands that become invalid if they wait too long before processing | Prevents stale work from executing after business relevance has passed | No meaningful extra price by itself; expired/dead-letter operations and retained messages still use broker resources; queue wait increases end-to-end latency | Do not place secrets in message body; use identity/RBAC and encrypt transport; expiry is not authorization | Expired message is dead-lettered when configured |
| Approval durable timer | Human decision must happen within a policy window | Prevents an old approval screen from authorizing action indefinitely | Durable checkpoint/timer uses small Functions/storage operations; waiting consumes no dedicated worker, so cost is lower than holding compute | Bind decision to authenticated actor, exact plan hash, and deadline; reject late/replayed decisions | Run becomes `expired`; no action executes |
| Cosmos item TTL | Disposable status/audit/test records have a defined retention period | Controls storage growth and cleanup labor | Deletion consumes background capacity but avoids indefinite storage; no request latency in normal path | Do not use a short TTL where legal/audit retention is mandatory; deletion is asynchronous | Record is removed asynchronously |
| Service Bus lock duration/renewal | A worker needs exclusive processing ownership | Prevents another worker receiving the same message during valid processing | Renewal creates broker operations; too short causes duplicates, too long delays recovery | Not a security token; idempotency remains required | Lock expiry permits redelivery |
| Worker/application timeout | Code must not run forever after a dependency hangs | Bounds resource/token/tool consumption | Short timeout reduces runaway cost but can create retries; size it from measured operation latency | Cancellation must prevent or safely reconcile side effects | Attempt fails/cancels according to application policy |
| Identity/access-token lifetime | User/service authorization is temporary | Limits damage from stolen credentials and forces revalidation | Token refresh adds occasional identity latency/operations; do not cache beyond authorization validity | Validate issuer, audience, expiry, scopes/roles; never confuse cache TTL with auth expiry | Request must refresh/re-authenticate |

Worker execution timeout and message-lock renewal are different controls. Message TTL
does not safely kill code already executing. Long work is split into checkpointed,
idempotent steps.

### Use this architecture when

- work is long-running, bursty, or rate-limited;
- a person must approve a specific plan before side effects;
- process state must survive host restarts;
- retries, expiry, and auditability are product requirements.

### Do not use it when

- a simple short request is enough;
- the “approval” endpoint has no authentication/authorization;
- tools are not idempotent and retries can repeat side effects;
- queueing is added without a status/result contract for the user.

### Acceptance criteria

- React receives `202`, run ID, and status URL quickly.
- UI displays planning → awaiting approval → queued → running → completed.
- Approve, reject, ten-minute timeout, duplicate approval, and changed-plan rejection work.
- Concurrent submissions raise queue depth while worker concurrency remains controlled.
- Transient retry succeeds; max-delivery failure reaches DLQ and can be inspected/replayed.
- Cosmos status/audit records expire according to lab TTL.

## 6. Shared platform decisions

| Concern | Choice | Why | Important alternative |
|---|---|---|---|
| Website | Static Web Apps Free | simple React hosting and managed HTTPS | Container Apps frontend if SSR/server runtime is needed |
| Container runtime | Container Apps | Fargate-style managed service, scale-to-zero, revisions | ACI for one raw container; AKS for Kubernetes control |
| Image registry | ACR | private Azure-local supply chain | GHCR works, but ACR teaches native identity/deploy path |
| API gateway | APIM Consumption | stable routes, TLS, rate limits, policy | direct Container Apps ingress for simpler/internal APIs |
| Cache | Azure Managed Redis, briefly | shared low-latency cache and distributed lock | local Redis when paid estimate is too high |
| Retrieval | Blob + AI Search | durable objects plus rebuildable lexical/vector index | database vector extension for relational workloads |
| Long workflow | Durable Functions | external events and durable timers | explicit state machine/worker when platform neutrality matters |
| Queue | Service Bus Standard | TTL, lock, retry, DLQ, enterprise messaging | Storage Queue for simpler lower-feature work |
| Status/audit | Cosmos DB free tier if eligible | flexible keyed status with item TTL | Table Storage fallback for this tiny lab |
| Secrets/access | Managed identity + RBAC; Key Vault fallback | avoids stored cloud service credentials | access keys only where identity support is unavailable |
| Observability | App Insights + Log Analytics | correlated request/workflow/container logs | provider-neutral OpenTelemetry backend later |
| Delivery identity | GitHub OIDC | short-lived tokens; no client secret | long-lived service-principal secret is intentionally rejected |

### Cost, latency, and security tradeoffs by service

| Service/pattern | Cost behavior and control | Latency behavior | Security posture and required action |
|---|---|---|---|
| Static Web Apps | Free tier when eligible; static assets/egress limits | CDN-style static delivery is fast; API remains a separate hop | Public assets; never compile secrets into `VITE_*`; managed HTTPS |
| APIM Consumption | Per-operation consumption after included amount | Adds a gateway network/policy hop; usually small versus model inference | Central TLS, JWT/rate-limit policy; do not expose internal backends unnecessarily |
| Container Apps | Consumption by requests/vCPU/memory; min 0 controls idle cost, max replicas controls burn | Scale-to-zero can cold-start; warm replicas reduce latency at ongoing cost | Managed ingress/TLS; managed identity; narrow ingress and data roles |
| ACR | Registry storage and operations; one immutable image reused across APIs | Image pull affects revision startup, not steady request latency | Disable anonymous push/admin credentials; use identity and immutable SHA tags |
| Foundry inference | Token/model-specific usage; bound input/output tokens and traffic | Dominant synchronous latency; model/region/load affect response time | Managed identity where available, content controls, no prompt/secret logging |
| Azure Managed Redis | Paid provisioned capacity even when lightly used; create briefly or use local fallback | Cache hit is milliseconds and can remove seconds of model latency | TLS 1.2/1.3, Entra identity, scoped keys, no sensitive cross-tenant cache entries |
| Blob Storage | Capacity, transactions, and egress; tiny document lab is low cost | Object upload/read adds storage hop; index once instead of reading every question | Private container, RBAC, no public blob URLs for private corpus |
| AI Search | Free SKU if available; paid SKUs are provisioned hourly | Retrieval adds query latency but reduces prompt size and improves grounding | Filter by tenant/document ACL; do not assume index membership equals authorization |
| Durable Functions | Functions executions plus storage transactions; durable wait avoids idle compute | Start/checkpoint/event hops add latency but are appropriate for non-interactive work | Protect starter/event endpoints; deterministic orchestration; do not log approval secrets |
| Service Bus | Standard namespace may be hourly/included grant plus operations | Adds queue wait intentionally; protects downstream latency/quotas during bursts | Entra/RBAC, TLS, minimal payload, TTL/DLQ; queue is not an authorization boundary |
| Cosmos DB | RU/storage or serverless/free allowance; partition and query design control spend | Point read by partition key is low-latency; cross-partition scans cost more and are slower | RBAC/identity, tenant partitioning, retention policy; audit TTL must meet requirements |
| App Insights/Logs | Ingestion and retention can become costly; sample and cap | Telemetry export should be asynchronous but excessive instrumentation adds overhead | Redact prompts, documents, tokens, credentials, and personal data |

## 7. Data ownership and trust boundaries

| Data | System of record | Cache/index? | Browser access |
|---|---|---|---|
| Chat response | none for this lab | Redis with short TTL | only through FastAPI response |
| Source document | private Blob | AI Search is rebuildable | upload/query through FastAPI |
| Search chunks/vectors | AI Search serving index | rebuild from Blob | none |
| Agent workflow checkpoint | Durable Functions storage | internal runtime state | none |
| Agent status/result/audit | Cosmos DB | optional UI polling response | through Agent FastAPI only |
| Secrets | managed identity/RBAC or Key Vault | never frontend config | none |

The browser contains only public website assets and the APIM base URL. Vite `VITE_*`
variables are public at build time; they must never hold credentials.

## 8. Scaling, reliability, and failure boundaries

- **Chat/RAG:** scale replicas on HTTP concurrency. Bound request size, timeout, model
  tokens, and maximum replicas to control cost.
- **Agent:** API scales independently; queue depth and worker concurrency control long
  work. A busy agent cannot starve chat replicas.
- **Redis unavailable:** safe degradation is a cache miss/model call within rate limits;
  Redis data can be rebuilt.
- **Search unavailable:** RAG returns a dependency error, never an ungrounded fallback
  pretending to be grounded.
- **Model unavailable:** retry only transient errors with bounded backoff; do not cache
  failures.
- **Worker unavailable:** Service Bus retains approved work until TTL; UI remains honest
  about queued state.
- **Approval service restart:** Durable Functions resumes from checkpoint.
- **Bad deployment:** readiness/smoke test fails and traffic returns to prior revision.

## 9. Security and TLS model

```text
Browser ──trusted HTTPS──▶ Static Web Apps / APIM
APIM ──HTTPS──▶ Container Apps FastAPI
FastAPI managed identity ──RBAC/TLS──▶ Azure data/model services
```

- Microsoft-managed certificates on generated Azure hostnames provide real SSL/TLS; a
  custom domain is optional and requires owned DNS, not a requirement for learning TLS.
- APIM rate limits and routes public APIs; internal workflow/queue endpoints are not public.
- Managed identities receive narrow data-plane roles rather than subscription Contributor.
- Approval verifies the approver and immutable plan hash.
- Prompt/document content is not written to broad logs; credentials are never logged.
- Content Safety does not replace authorization, grounding evaluation, or prompt-injection
  defenses.

## 10. Delivery architecture

```text
feature branch
    │ pull request
    ▼
backend-tests + frontend-build (required)
    │ protected merge to main
    ▼
build immutable backend/frontend artifacts tagged sha-<commit>
    │ GitHub OIDC (no Azure client secret)
    ▼
deploy new Container Apps revisions + React site
    │
health/readiness + one tiny smoke flow per app
    ├─ pass → activate/retain revision and record evidence
    └─ fail → preserve/restore prior revision
```

The deployment pipeline and application approval are different:

- **GitHub environment approval** authorizes deploying code/infrastructure.
- **Agent human approval** authorizes one specific runtime plan/action.

### Deployment strategy selection

| Strategy | When to use | Cost | Latency/availability | Security and operational concerns |
|---|---|---|---|---|
| Recreate/replace | Disposable lab or noncritical single-instance app | Lowest temporary capacity | Has downtime/cold start | Simple, but no safe live rollback window |
| Rolling update | Many interchangeable replicas, backward-compatible change | Small overlap during rollout | Usually available; mixed versions briefly | APIs/schema must be compatible across versions |
| Container Apps revision swap | Default for this sprint; immutable app/config version and fast rollback | Old/new revisions overlap briefly; deactivate old after evidence | New revision warms before traffic; rollback is fast | Deploy exact SHA, smoke test new revision, preserve known-good revision |
| Blue-green | High-confidence cutover with complete parallel environment | Roughly doubles app capacity during overlap; duplicated data services can be expensive | Near-zero cutover downtime | Prevent both environments from performing duplicate side effects; manage schema compatibility |
| Canary/weighted traffic | Risky change needs production-like evidence from a small traffic percentage | Two revisions plus monitoring; model calls may increase | Small user subset may see new latency/errors | Strong metrics, correlation, stop conditions, and no security-policy mismatch |
| Feature flag | Behavior should change independently from deployment | Config service/complexity cost; avoids repeated deploys | Evaluation adds tiny latency, often cached | Authorization-critical checks must not rely on client-side flags; remove stale flags |
| Shadow/mirror | Compare new model/prompt without affecting user response | Can nearly double model token cost | User latency can remain unchanged if async | Redact data, never execute mirrored side effects, clearly isolate outputs |

For the lab, use **Container Apps revisions**: deploy an immutable SHA, verify health and
one scenario without moving all traffic where possible, activate it, then deliberately
restore the previous revision. Blue-green/canary are documented for future choices but
not added merely to consume services.

## 11. Cost and lifecycle architecture

- One tagged resource group is the deletion boundary.
- Search and Static Web Apps use free tiers when eligible.
- Container Apps/Functions/APIM use consumption allowances and tiny test traffic.
- ACR, Blob, Key Vault, and Service Bus use exact 12-month-eligible SKUs only if the
  subscription's Free Services grid confirms eligibility.
- Foundry model tokens and Azure Managed Redis are paid. Redis exists for one block only;
  use local Redis if the portal estimate threatens the cap.
- Expected target is under ₹500; stop before ₹1,500.
- Every resource is deleted by September 27, 8:00 PM IST. PAYG conversion later does not
  change this cleanup rule.

## 12. Definition of complete

The three-app solution is complete only when:

- all three React pages work through their FastAPI APIs and APIM;
- no browser bundle/request exposes service credentials or direct internal endpoints;
- Chat proves cache MISS/HIT, stampede prevention, scaling, TLS, and rollback;
- Document Q&A proves private ingestion, retrieval, citation, and unknown-answer refusal;
- Agent proves approve/reject/timeout/duplicate decision, queue burst handling, retry/DLQ,
  idempotency, and TTL cleanup;
- managed identity/RBAC and correlated logs are visible;
- CI uses fake providers and both required checks pass;
- CD uses immutable tags and OIDC, and a bad revision can roll back;
- actual cost and evidence are recorded;
- Redis is deleted after its block and the final resource group is verified absent.

## 13. Documentation sequence

1. **This document:** problem statements, architecture, and solution decisions.
2. **[GENAI_DEPLOYMENT_GUIDE.md](GENAI_DEPLOYMENT_GUIDE.md):** build and deploy App 1,
   then App 2, then App 3, including concepts, portal, CLI, code, tests, CI/CD, failure
   drills, cost, and destruction.
3. **[LEARNING_JOURNAL.md](LEARNING_JOURNAL.md):** actual daily actions, evidence,
   incidents, corrections, cost, and cleanup status.
4. **`Learning_Tracker.xlsx`:** sprint status, service quotas, deployments, cost, and
   destroyed confirmation.
