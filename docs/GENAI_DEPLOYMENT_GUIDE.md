# GenAI Applications — Build, Deploy, Operate, and Destroy

This is the detailed implementation and learning guide for the accelerated three-app
Azure sprint. The [visual companion](GENAI_DEPLOYMENT_GUIDE.html) is optimized for quick
navigation; this Markdown file is the source of truth for concepts, commands, portal
paths, verification, troubleshooting, CI/CD, cost, and cleanup.

Readers with basic Python/LLM knowledge should first read the plain-language
[Azure GenAI Deployment Handbook for Beginners](AZURE_GENAI_BEGINNER_HANDBOOK.md),
available as [visual HTML](AZURE_GENAI_BEGINNER_HANDBOOK.html) and a
[Word document](AZURE_GENAI_BEGINNER_HANDBOOK.docx). The handbook explains what each
flowchart arrow and YES/NO path means; this guide is the practical execution reference.

> **Documentation rule:** a service is not “done” because the portal says deployment
> succeeded. It is done only when its application flow is verified, logs and cost are
> inspected, failure/recovery is exercised, evidence is captured, and the lab resource is
> destroyed. Whenever implementation changes, update this file and its HTML companion.

## 1. Delivery status and scope

| Item | Status | Source of truth |
|---|---|---|
| Existing Feedback Analyzer React/FastAPI/Celery app | Implemented and locally verified | `frontend/`, `backend/app/`, `docker-compose.yml` |
| Existing PR checks | Implemented | `.github/workflows/ci.yml` |
| Existing GHCR image publication | Implemented | `.github/workflows/publish.yml` |
| Shared three-page React learning SPA | **Planned; not implemented yet** | Will evolve `frontend/src/` |
| Chat, RAG, and Agent FastAPI entry points | **Planned; not implemented yet** | Will be added under `backend/app/` |
| Azure deployment workflow | **Planned; not implemented yet** | Will be added under `.github/workflows/` |
| Azure resources | Not created for this sprint yet | Azure Portal/CLI during the guided blocks |

Planned behavior is deliberately labelled. Do not run a command that references a future
file until that file exists in the repository and its local tests pass.

### How every app/service section must be read

This guide is not a command collection. For every concept, service, and deployment step,
record and review:

1. problem solved and architecture ownership;
2. when to use and when a simpler/different option is better;
3. application code/configuration and portal/CLI/IaC implementation;
4. cost meter, free-allowance dependency, and cost controls;
5. latency added/removed, including cold start and queue wait;
6. security defaults, identity, encryption, public exposure, and tenant boundary;
7. scaling signal, quota, and maximum bound;
8. failure modes, timeout/retry/idempotency, and recovery;
9. verification evidence and destruction step.

Prices change by region/date/offer. Use this guide to understand the meter and tradeoff,
then use the portal estimate and Cost Management as the authoritative amount.

## 2. The simple application shape

One React SPA provides three pages. Three small FastAPI applications expose public APIs.
The backend image is built once and deployed three times with different entry commands;
this avoids three dependency trees while keeping independent API boundaries.

```text
React SPA (Azure Static Web Apps)
  ├─ /chat       → APIM → chat FastAPI  → Redis → Foundry chat model
  ├─ /documents  → APIM → RAG FastAPI   → AI Search → Blob → Foundry
  └─ /agent      → APIM → agent FastAPI → Durable Functions approval timer
                                             └→ Service Bus → worker → Cosmos DB

Shared: ACR, managed identities/RBAC, Key Vault, Application Insights, Log Analytics
```

### Planned repository layout

```text
frontend/src/
  App.tsx                   # shared shell and three simple page routes/tabs
  api.ts                    # one typed client; browser calls APIM only
  pages/ChatPage.tsx
  pages/DocumentsPage.tsx
  pages/AgentPage.tsx

backend/app/
  chat_api.py               # FastAPI /health and /chat
  rag_api.py                # FastAPI /health, /documents, /questions
  agent_api.py              # FastAPI /health, /runs, /runs/{id}, approval
  cache.py                  # cache key, TTL, lock, hit/miss metadata
  providers/                # fake and Azure model/search adapters
  workflows/                # Durable Functions orchestration/activities
  config.py                 # environment-only configuration

.github/workflows/
  ci.yml                    # existing required PR checks
  publish.yml               # existing immutable image publication
  deploy-azure.yml          # planned OIDC deployment and verification
```

## 3. What each application teaches

### App 1 — Chat: Azure's Fargate-style container exercise

**User flow:** enter a prompt in React → FastAPI checks cache → cache miss calls Foundry →
response and usage appear → repeat prompt returns a cache hit without model tokens.

**Why these services**

- **Container Apps:** closest practical Azure match for an ECS/Fargate HTTP service. It
  adds ingress, revisions, KEDA autoscaling, logs, scale-to-zero, and rollback without
  managing Kubernetes nodes.
- **ACR:** private, Azure-local image registry; analogous to Amazon ECR.
- **Azure Managed Redis:** low-latency cache-aside store. It is not the database.
- **APIM:** stable API boundary for HTTPS, rate limits, routing, and policy.

**Use this pattern when:** the response normally completes in seconds and the client can
wait; identical safe requests are common; horizontal scaling is useful.

**Do not use it when:** a request can take minutes, requires human approval, or has side
effects that must survive restarts. Use App 3's asynchronous workflow instead.

**Cache correctness contract**

```text
key = SHA256(tenant + normalized input + model deployment
             + prompt version + temperature + output schema version)
GET key
  HIT  → return cached result with cache_status=HIT and model_tokens=0
  MISS → acquire short SET-NX lock → call model once → SET result EX <ttl>
```

- Never share personalized results across tenant/user authorization scopes.
- Do not cache errors, approval decisions, or side-effecting tool results.
- Use TTL for freshness, not as a substitute for explicit invalidation after prompt/model
  changes.
- A distributed lock prevents a cache stampede when many users send the same miss.

### App 2 — Document Q&A: basic RAG

**User flow:** upload/select two harmless documents in React → FastAPI stores/indexes them
→ ask a question → retrieve relevant chunks → send only those chunks to Foundry → render
the answer with source citations. An unknown question must return “not found in supplied
documents,” not an invented answer.

**Why these services**

- **Blob Storage:** cheap durable source-of-truth objects, analogous to S3.
- **Azure AI Search:** lexical/vector retrieval and metadata filters.
- **Foundry embeddings/chat:** convert chunks to vectors and synthesize a grounded answer.
- **Content Safety:** demonstrate input/output safety outside the model itself.

**Use this pattern when:** answers must be grounded in private or frequently updated
documents and citations matter.

**Do not use it when:** the model already knows stable public information, exact SQL-style
answers are required, or the source corpus is tiny enough for deterministic lookup.

**RAG concepts to observe:** chunk size/overlap, embedding model compatibility, lexical
versus vector search, top-k, metadata filters, prompt grounding, citations, and evaluation
for answer relevance versus retrieval relevance.

### App 3 — Approval-gated long-running agent

**User flow:** submit a task in React → FastAPI returns HTTP `202` and a run ID → UI polls
status → proposed plan appears → user approves/rejects → approved work enters Service Bus
→ worker runs controlled steps → result/audit appears. No decision within ten minutes
expires without executing tools.

**Why these services**

- **FastAPI:** the only public backend contract used by React.
- **Durable Functions:** checkpoints workflow state and waits for an external event or
  durable timer without keeping a request/thread alive.
- **Service Bus:** absorbs bursts, applies controlled worker concurrency, retries transient
  failures, and isolates poison/expired messages in the dead-letter queue.
- **Cosmos DB:** application-facing status/result/audit record; item TTL removes old lab
  data automatically.

**Use this pattern when:** work takes longer than an HTTP request, requires approval,
needs retries/checkpoints, or calls rate-limited models/tools.

**Do not use a queue merely because there are multiple users.** Short requests scale with
Container Apps replicas. Queue when the work itself must be buffered and decoupled.

### Four different TTL/deadline controls

| Control | Purpose | Lab value | What happens at expiry |
|---|---|---:|---|
| Redis TTL | Cached response freshness | 15 min | Next request is a miss and recomputes |
| Service Bus message TTL | Maximum wait before a queued command becomes stale | 15 min | Dead-letter for inspection |
| Approval TTL | Maximum human decision window | 10 min | Workflow becomes `expired`; no action runs |
| Cosmos item TTL | Retention of old lab run/audit records | 1 day | Cosmos removes the item asynchronously |

A worker execution timeout and Service Bus lock renewal are separate. Message TTL must
not be treated as a mechanism for killing code already running. Agent steps must be
idempotent and checkpointed so retries cannot repeat side effects.

## 4. Shared prerequisites and safety gate

### Existing GitHub prerequisites — completed

- Public repository.
- Protected `main` requiring a pull request, up-to-date branch,
  `backend-tests`, and `frontend-build`.
- Public GHCR backend/frontend packages.
- Entra app `github-actions-testing-e2e`, GitHub OIDC federated credential, Contributor
  role, and repository secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and
  `AZURE_SUBSCRIPTION_ID`.

Never create `AZURE_CLIENT_SECRET`; OIDC exchanges short-lived identity tokens.

### Session variables

Use Cloud Shell Bash on the managed laptop. Choose `LOCATION` only after checking model
and service availability; not every Foundry model is available in every Azure region.

```bash
export SUBSCRIPTION_ID="<select without pasting it into documentation>"
export LOCATION="<one region supporting the chosen model and required services>"
export SUFFIX="<4-6 lowercase letters/numbers>"
export RG="learn-genai-20260927"
export EXPIRES="2026-09-27T20:00:00+05:30"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query '{name:name,id:id,tenantId:tenantId}' -o table
```

Do not publish the subscription/tenant/client IDs in screenshots. They are identifiers,
not passwords, but there is no learning benefit in exposing account metadata.

### Before creating anything

Portal:

1. **Cost Management + Billing → Free services** — record eligible SKU quantities.
2. **Cost Management → Budgets** — confirm warning alerts; budgets do not stop spend.
3. **Microsoft Foundry → Model catalog** — check chosen chat/embedding model region and
   quota; use pay-as-you-go, never provisioned throughput.
4. For any paid service, inspect **Review + create → estimated cost**. Redis is paid.

Create the lifecycle boundary:

```bash
az group create --name "$RG" --location "$LOCATION" \
  --tags purpose=genai-sprint owner=learning expires="$EXPIRES"
az group show --name "$RG" -o table
```

Why: one group makes RBAC, cost filtering, activity history, tagging, and final deletion a
single boundary. AWS has no exact mandatory equivalent; it combines ideas from a stack,
resource group/tags, and IAM scope.

## 5. Enable Azure resource providers

Provider registration enables a subscription to create a resource type; it does not
create or bill a service. Register only the providers used by this sprint.

```bash
for provider in \
  Microsoft.App Microsoft.ContainerRegistry Microsoft.CognitiveServices \
  Microsoft.Search Microsoft.Storage Microsoft.KeyVault Microsoft.ApiManagement \
  Microsoft.Insights Microsoft.OperationalInsights Microsoft.Web \
  Microsoft.ServiceBus Microsoft.DocumentDB Microsoft.Cache; do
  az provider register --namespace "$provider"
done

az provider list --query \
  "[?namespace=='Microsoft.App' || namespace=='Microsoft.CognitiveServices' || namespace=='Microsoft.Cache'].{Provider:namespace,State:registrationState}" \
  -o table
```

Portal equivalent: **Subscriptions → learning subscription → Resource providers → search
provider → Register**. Registration can take several minutes. `Registering` is not
`Registered`; verify before diagnosing a later create failure.

## 6. Local development before Azure

### Existing baseline

The current stack already proves React → FastAPI → database/Redis queue → worker → fake
LLM. Use it as the known-good foundation:

```bash
docker compose up -d --no-build
docker compose ps
curl http://localhost:8000/health
# Browser: http://localhost:8080
```

If corporate TLS interception blocks `pip install` during Docker build, use the public
CI-built images as documented in [RUNBOOK.md](RUNBOOK.md). Do not disable TLS validation
or use pip `--trusted-host`.

### Development contract for the new pages/APIs

Every FastAPI service must have:

- `GET /health`: liveness only; no expensive dependency calls.
- `GET /ready`: verifies required configured dependencies for deployment readiness.
- typed request/response Pydantic schemas.
- bounded inputs and model output token limit.
- correlation/run ID in response and logs.
- OpenAPI documentation generated by FastAPI.
- fake provider path used by tests; CI never requires Azure/network/Redis.

React pages must provide loading, success, validation, and error states; poll only while a
run is non-terminal; stop timers on unmount; never contain Azure credentials.

### Local verification matrix

| App | Happy path | Important negative path |
|---|---|---|
| Chat | first request MISS, second HIT | different prompt version is a MISS; failed call is not cached |
| Document Q&A | answer cites uploaded source | unknown question refuses to invent |
| Agent | approve reaches completed | reject, timeout, duplicate approval, changed plan hash |

Run before any cloud deployment:

```bash
cd backend && pytest -v
cd ../frontend && npm ci && npx tsc --noEmit && npm run build
docker compose config --services
```

## 7. App-by-app build and deployment

Execute one application completely before moving to the next. Shared foundations are
created during App 1 and reused; they are not three separate setup exercises.

### App 1 execution record — Real-time Chat

| Phase | Work | Cost/latency/security questions | Evidence before moving on |
|---|---|---|---|
| Develop | React Chat page, FastAPI `/chat`, fake provider, cache abstraction | Is tenant/model/prompt version in key? Are input/output tokens bounded? | local MISS→HIT tests and frontend build |
| Package | Build one backend image and immutable tag in ACR | What registry storage/build meter applies? Is admin access disabled? | digest and `sha-<commit>` tag |
| Platform | Foundry chat model, Log Analytics, Container Apps environment, managed identity | Does region support model? What is cold-start versus min-replica cost? What roles are actually needed? | playground call, identity ID, environment ready |
| Deploy | Chat Container App min 0/max 3, readiness/liveness, APIM route, React Chat page | Does scale-to-zero latency meet need? Is APIM-to-backend HTTPS? | public HTTPS health and chat response |
| Cache | Managed Redis only after estimate; local fallback | Does saved token/model latency justify provisioned cache cost? Is TLS/Entra enabled? | MISS→HIT, TTL expiry, hit token count 0 |
| Stress/fail | 20 duplicates, wrong config, Redis unavailable | Is stampede lock effective? Is fallback bounded and secure? | one model call, logs, safe error/degradation |
| Deliver | New immutable revision and rollback | Which deployment strategy and stop threshold? | previous revision restored |
| Destroy | Delete Managed Redis immediately | Did hourly billing stop? Any instance in another RG? | Redis absent and cost note recorded |

Detailed service mechanics: §§8.1–8.5 and 8.8–8.9.

### App 2 execution record — Document Q&A

| Phase | Work | Cost/latency/security questions | Evidence before moving on |
|---|---|---|---|
| Develop | React Documents page, RAG FastAPI, fake Blob/Search/model adapters | Are uploads bounded/type-checked? Does unknown evidence refuse? | known citation + unknown-answer tests |
| Data | Private Blob container and two harmless documents | Are capacity/operation/egress meters understood? Is public access off? | private container and object list |
| Retrieve | Search Free index, metadata, lexical then vector query | Is Free eligible? What top-k balances latency/tokens/relevance? Are tenant ACL filters present? | expected chunks in Search Explorer |
| Generate | Foundry embedding + grounded chat prompt | What embedding/token cost applies? Is source metadata authoritative? | cited answer and measured usage |
| Deploy | Independent RAG Container App, APIM route, React page | Can RAG scale without affecting Chat? Are data roles least privilege? | end-to-end HTTPS UI flow |
| Fail/evaluate | unknown question, removed chunk, Search unavailable | Does the system fail honestly rather than generate ungrounded text? | refusal/dependency error and traces |
| Deliver | SHA revision and smoke check | Are index/schema changes backward compatible with old revision? | good revision active; rollback path recorded |

Detailed service mechanics: §§8.1–8.4, 8.6, and 8.8–8.9.

### App 3 execution record — Approval-gated Agent

| Phase | Work | Cost/latency/security questions | Evidence before moving on |
|---|---|---|---|
| Develop | React Agent page, FastAPI run/status/approval, fake durable/queue/state adapters | Is request returned as `202` quickly? Is approver authenticated and plan hash immutable? | approve/reject/timeout unit flows |
| Orchestrate | Durable Functions storage, external event, ten-minute timer | What Functions/storage operations occur while waiting? Is orchestration deterministic? | restart-safe awaiting state |
| Queue | Service Bus Standard queue, TTL, lock, retry, DLQ | Is queue delay acceptable? Are TTL/lock/worker timeout distinct? Is payload minimal? | queue properties and burst depth |
| Persist | Eligible Cosmos free-tier/serverless account, `/tenant_id`, item TTL | Do point reads avoid cross-partition RU cost? Does audit retention meet policy? | status/audit record and TTL setting |
| Deploy | Agent FastAPI, internal orchestrator/worker, APIM route, React page | Are internal endpoints private/protected? Can worker scale without exceeding model quota? | end-to-end approved completion |
| Fail/recover | reject, expiry, duplicate/changed approval, stopped worker, retry, poison message | Can any path execute without valid approval? Are side effects idempotent? | no-action proofs, DLQ, replay evidence |
| Deliver | SHA revision, smoke and rollback | Can an old API coexist with in-flight workflow state? | compatibility note and rollback drill |
| Destroy | Final RG deletion after evidence/cost | Are messages, records, and soft-deleted resources understood? | RG false, subscription sweep, cost note |

Detailed service mechanics: §§8.1–8.4 and 8.7–8.9.

## 8. Azure service implementation reference

Manual-first means: create in the portal once, inspect the generated resource and CLI
representation, verify it, then automate it. It does not mean keeping hand-created
resources forever.

### 8.1 Foundry model deployments

**Concept:** Foundry governs model selection/deployment and inference endpoints. The
platform/project is not the expensive part; model tokens and provisioned capacity are.

Portal:

1. **Microsoft Foundry → Create project/resource** in `$RG` and `$LOCATION`.
2. **Model catalog → choose a small pay-as-you-go chat model → Deploy**.
3. Set a low token/rate quota appropriate for the lab.
4. Repeat for a compatible embedding model used by RAG.
5. Playground: send one short prompt; record model/deployment names and token usage.

Use when model governance, evaluation, deployment names, quota, and safety controls matter.
For local/CI tests, use the deterministic fake provider instead.

### 8.2 ACR and backend image

```bash
export ACR="genai${SUFFIX}"
az acr create --resource-group "$RG" --name "$ACR" --sku Standard
az acr show --name "$ACR" --query '{loginServer:loginServer,sku:sku.name}' -o table
az acr build --registry "$ACR" --image genai-backend:manual-1 backend
az acr repository show-tags --name "$ACR" --repository genai-backend -o table
```

`az acr build` builds in Azure, avoiding the managed laptop's Docker certificate chain.
Never deploy `latest` as evidence: deploy `sha-<commit>` or another immutable tag so a
revision can be reproduced and rolled back.

### 8.3 Log Analytics, Application Insights, and Container Apps environment

```bash
export LAW="law-genai-${SUFFIX}"
export ENV="cae-genai-${SUFFIX}"
az monitor log-analytics workspace create -g "$RG" -n "$LAW" -l "$LOCATION"
az containerapp env create -g "$RG" -n "$ENV" -l "$LOCATION" \
  --logs-workspace-id "$(az monitor log-analytics workspace show -g "$RG" -n "$LAW" --query customerId -o tsv)" \
  --logs-workspace-key "$(az monitor log-analytics workspace get-shared-keys -g "$RG" -n "$LAW" --query primarySharedKey -o tsv)"
```

The workspace centralizes logs. Container Apps provides the Fargate-style runtime. Use
min replicas `0`, a small maximum, readiness/liveness probes, and external HTTPS ingress.

### 8.4 Deploy the three FastAPI services

These commands become executable after the three entry modules exist:

```bash
export LOGIN_SERVER="$(az acr show -n "$ACR" --query loginServer -o tsv)"
export IMAGE="$LOGIN_SERVER/genai-backend:sha-<commit>"

# Repeat for chat-api, rag-api, and agent-api with the corresponding uvicorn module.
az containerapp create -g "$RG" -n chat-api --environment "$ENV" \
  --image "$IMAGE" --target-port 8000 --ingress external \
  --min-replicas 0 --max-replicas 3 \
  --command uvicorn --args app.chat_api:app --host 0.0.0.0 --port 8000
```

After creation:

```bash
az containerapp identity assign -g "$RG" -n chat-api --system-assigned
az containerapp show -g "$RG" -n chat-api \
  --query '{fqdn:properties.configuration.ingress.fqdn,revision:properties.latestRevisionName}' -o table
az containerapp logs show -g "$RG" -n chat-api --follow
```

Assign RBAC to the managed identity at the narrowest resource scope. Contributor is for
infrastructure deployment, not application data access. Exact data-plane roles are added
only after the target resource exists and are recorded beside the implementation.

### 8.5 Azure Managed Redis

**Important current-state decision:** do not create legacy Azure Cache for Redis from an
old tutorial. New public-cloud customers have been blocked since April 1, 2026 and the
service is retiring. Use Azure Managed Redis.

Portal:

1. **Create a resource → Azure Managed Redis → Create**.
2. Select `$RG`, same supported region, **In-memory**, and the smallest available size.
3. Disable high availability only for this disposable dev/test lab after reading the data
   loss warning.
4. Keep Microsoft Entra authentication and TLS enabled; do not enable non-TLS access.
5. Before **Create**, inspect hourly/monthly estimate. If it threatens the cap, cancel and
   use local Redis for the code exercise.
6. After use, delete Redis immediately rather than waiting for final sprint cleanup.

Azure Managed Redis uses port `10000`, TLS 1.2/1.3, and supports Entra/managed-identity
authentication. The Python client should use `DefaultAzureCredential`, TLS, and the Redis
scope rather than a committed access key.

Verify behavior, not just connectivity: MISS → model call → SET with TTL → HIT with zero
model tokens; then 20 concurrent identical misses must produce one model call.

### 8.6 Blob Storage and Azure AI Search

```bash
export STORAGE="genai${SUFFIX}docs"
export SEARCH="genai-${SUFFIX}-search"
az storage account create -g "$RG" -n "$STORAGE" -l "$LOCATION" \
  --sku Standard_LRS --kind StorageV2 --allow-blob-public-access false
az storage container create --account-name "$STORAGE" --name documents --auth-mode login
az search service create -g "$RG" -n "$SEARCH" -l "$LOCATION" --sku free
```

Portal inspection:

- **Storage account → Containers → documents**: source files remain private.
- **Search service → Indexes/Search explorer**: inspect chunk text, source metadata, and
  lexical results before adding vectors.
- **Metrics**: tiny query/document count; no unexplained indexing loop.

The index must store source ID/title/chunk and vector fields. Verify a known question and
an unknown question. Citations come from retrieved metadata, not model-generated URLs.

### 8.7 Durable Functions, Service Bus, and Cosmos DB

```bash
export FUNC_STORAGE="genai${SUFFIX}func"
export SB="genai-${SUFFIX}-sb"
export COSMOS="genai-${SUFFIX}-cosmos"

az storage account create -g "$RG" -n "$FUNC_STORAGE" -l "$LOCATION" \
  --sku Standard_LRS --kind StorageV2
az servicebus namespace create -g "$RG" -n "$SB" -l "$LOCATION" --sku Standard
az servicebus queue create -g "$RG" --namespace-name "$SB" -n agent-work \
  --default-message-time-to-live PT15M --enable-dead-lettering-on-message-expiration true \
  --max-delivery-count 3 --lock-duration PT1M
```

Create Cosmos through the portal only after checking whether this subscription is still
eligible for its one free-tier account:

1. **Create a resource → Azure Cosmos DB for NoSQL**.
2. Select `$RG`; enable **Free Tier Discount** only if shown as eligible.
3. Choose serverless/free-eligible capacity as shown by the portal; no multi-region write.
4. Create database `genai` and container `runs`, partition key `/tenant_id`.
5. Enable default item TTL `86400` seconds for the lab.

Durable Functions uses its Storage account for internal checkpoints; Cosmos stores the
application-facing run/audit view. Do not manually edit Durable runtime tables/queues.

State machine:

```text
planning → awaiting_approval → queued → running → completed
                         ├────────────→ rejected
                         └────────────→ expired
running ──retry──→ running ──max attempts──→ failed/dead-lettered
```

Approval API requirements:

- verify approver authorization;
- include expected `plan_hash` in the decision;
- use an idempotency key/conditional state transition;
- only `awaiting_approval` can become `queued`, `rejected`, or `expired`;
- append audit data; never overwrite history silently.

### 8.8 APIM and HTTPS/TLS

Portal:

1. **Create a resource → API Management → Consumption** in `$RG`.
2. **APIs → Add API → OpenAPI**; import each FastAPI `/openapi.json`.
3. Give routes stable prefixes: `/chat`, `/documents`, `/agent`.
4. Set each backend URL to its Container Apps `https://...` FQDN.
5. Add a small inbound rate-limit policy and correlation ID.
6. Do not allow a client to bypass approval by calling internal Functions/Service Bus.

Managed Azure hostnames already have publicly trusted certificates. Verify real TLS:

```bash
export HOST="<APIM generated hostname without https://>"
curl -sS -I "https://$HOST/chat/health"
openssl s_client -connect "$HOST:443" -servername "$HOST" </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```

Expected: trusted issuer, current validity dates, HTTPS response, and an APIM backend URL
that also begins with `https://`. The certificate belongs at APIM/Container Apps ingress,
not inside the FastAPI image. Attach a custom domain only if one is already owned: prove
DNS ownership, add CNAME/TXT records, then select a managed certificate. No domain purchase
is needed for the sprint.

### 8.9 Shared React SPA on Static Web Apps

Build once:

```bash
cd frontend
npm ci
npx tsc --noEmit
npm run build
```

Portal manual-first path: **Create a resource → Static Web App → Free → Other deployment
source** (or GitHub after the manual exercise), select `$RG`, and deploy `frontend/dist`.
Set only the APIM base URL as public frontend configuration. No Azure service key belongs
in Vite variables because `VITE_*` values are compiled into public JavaScript.

Verification:

- Chat page shows cache MISS then HIT.
- Documents page shows citations and unknown-answer behavior.
- Agent page shows planning, awaiting approval, approve/reject buttons, and terminal state.
- Browser network requests target APIM only; no Redis/Search/Cosmos credentials or direct
  endpoints appear in the bundle/network panel.

## 9. CI/CD — existing workflows and target deployment

### 9.1 `.github/workflows/ci.yml` — required PR quality gate

| YAML section | Meaning |
|---|---|
| `on.push.branches: [main]` | Rechecks code after merge |
| `on.pull_request` | Runs on every PR update; branch protection waits for it |
| `permissions.contents: read` | Least privilege: CI only reads the repository |
| `backend-tests` | Required check name; case-sensitive branch rule dependency |
| `defaults.run.working-directory: backend` | Backend commands run from the Python project |
| `setup-python`, `cache: pip` | Reproducible Python 3.12 and faster dependency installs |
| `LLM_PROVIDER: fake` | Tests never call Azure or bill tokens |
| `pytest -v` | Unit/integration behavior gate |
| `frontend-build` | Second required check name |
| `npm ci` | Exact lockfile install; unlike `npm install`, CI fails on drift |
| `npx tsc --noEmit` | Type-check without producing output |
| `npm run build` | Proves Vite can generate deployable static files |

Do not rename `backend-tests` or `frontend-build` without updating branch protection in
GitHub Settings; otherwise merging can be permanently blocked waiting for a nonexistent
check.

### 9.2 `.github/workflows/publish.yml` — immutable artifacts

- Runs only after a push reaches protected `main`; PR code cannot publish packages.
- `packages: write` is scoped to this workflow's `GITHUB_TOKEN`.
- A matrix builds backend and frontend from their own Docker contexts.
- Buildx and GitHub Actions cache reduce rebuild time.
- `latest` is convenient for humans, but `sha-<commit>` is the deploy/rollback identity.
- GHCR login uses the temporary `GITHUB_TOKEN`, not a personal access token.

The sprint may simplify publication to one reusable backend image plus one frontend build.
Any change must preserve immutable SHA tags.

### 9.3 Planned `.github/workflows/deploy-azure.yml`

The actual YAML will be committed and then documented line-by-line. Its required design:

1. Trigger only after CI succeeds on protected `main`, with optional manual dispatch.
2. Use `permissions: id-token: write, contents: read, packages: read`.
3. Run `azure/login` with `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and
   `AZURE_SUBSCRIPTION_ID`; no client secret.
4. Resolve the immutable `sha-<commit>` image tag.
5. Update each Container App, creating a new revision rather than mutating an old image.
6. Deploy the React build to Static Web Apps.
7. Wait for `/health` and `/ready`; run one tiny smoke flow per app.
8. On smoke failure, stop and preserve the previous revision/traffic.
9. Record deployed commit, revision names, and URLs in the job summary.
10. Never run `az group delete` automatically from an untrusted pull request.

Conceptual YAML skeleton—**not executable until resource names and files exist**:

```yaml
name: Deploy Azure
on:
  workflow_dispatch:
  push:
    branches: [main]
permissions:
  contents: read
  id-token: write
jobs:
  deploy:
    environment: learning
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - name: Deploy immutable backend revision
        run: echo "Replaced by tested az containerapp update commands"
      - name: Smoke test through APIM
        run: echo "Replaced by health and three tiny scenario checks"
```

`id-token: write` lets GitHub mint an OIDC token. `azure/login` exchanges it according to
the federated credential's exact repository/branch subject. The `environment` is the
place to add deployment approval later; it is not the application human-approval flow.

## 10. End-to-end verification and failure drills

| Concern | Verify | Deliberate failure |
|---|---|---|
| Fargate-style hosting | replicas 0→1, HTTPS, revision name | wrong env var; restore and rollback |
| Cache | MISS→HIT; hit uses 0 model tokens | expire TTL; concurrent identical misses |
| RAG | citation matches source chunk | unknown question; deleted index document |
| Queue | depth rises then drains; max concurrency respected | stop worker; inspect backlog |
| Approval | approve, reject, timeout, duplicate decision | changed plan hash rejected |
| Retry/DLQ | transient retry completes | exceed max delivery; inspect/replay DLQ |
| Cosmos TTL | run/audit readable before retention | short test TTL removes disposable record |
| TLS | trusted chain, expiry, HTTPS backend | HTTP request redirects/rejects |
| CI/CD | SHA revision passes smoke test | bad revision receives no traffic/rollback |

Capture screenshots only after sensitive identifiers and document content are reviewed.
Evidence should include architecture, resource list, successful UI state, cache/queue
metrics, approval state transitions, logs, revision rollback, cost, and deletion proof.

## 11. Cost and destroy procedure

- Target under ₹500; hard learning cap ₹1,500.
- Redis and model inference are paid; check estimates/token usage.
- Search Free, Static Web Apps Free, consumption grants, and 12-month grants apply only
  when this subscription and exact SKU are eligible.
- Budgets alert; they do not stop charges.

Destroy Redis as soon as its block ends. At final cleanup:

```bash
az resource list -g "$RG" -o table
az group delete -n "$RG" --yes
az group exists -n "$RG"             # must eventually print false
az resource list -o table             # inspect anything outside the group
```

Then inspect:

1. **Cost Management → Cost analysis** filtered to `$RG` (billing data can lag).
2. **Resource groups** — group absent.
3. Service-specific soft-delete/recovery views for Key Vault and other supported services;
   soft-deleted names may remain recoverable even though billing stopped.
4. ACR/Redis/APIM/Search/Cosmos lists — no accidental resource in another group.

Do not purge recoverable resources merely for tidiness unless name reuse is required;
purge is irreversible and requires separate consideration.

## 12. Documentation update checklist

At the end of every implementation/deployment block:

- update actual file/function references in this guide;
- update [GENAI_DEPLOYMENT_GUIDE.html](GENAI_DEPLOYMENT_GUIDE.html);
- update [LEARNING_JOURNAL.md](LEARNING_JOURNAL.md) and
  [LEARNING_JOURNAL.html](LEARNING_JOURNAL.html);
- regenerate `docs/Learning_Tracker.xlsx` with `scripts/make_tracker.py`;
- record actual cost, evidence, incident/correction, and destroyed state;
- if application behavior changed, update `ARCHITECTURE.md` and `INTERVIEW_NOTES.md` as
  required by repository policy.

## 13. Authoritative references

- [Azure Container Apps overview](https://learn.microsoft.com/azure/container-apps/overview)
- [Azure Managed Redis overview](https://learn.microsoft.com/azure/redis/overview)
- [Azure Managed Redis TLS](https://learn.microsoft.com/azure/redis/tls-configuration)
- [Azure Cache for Redis retirement](https://learn.microsoft.com/azure/azure-cache-for-redis/retirement-faq)
- [Durable Functions human interaction](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-human-interaction)
- [Service Bus queues/topics/subscriptions](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-queues-topics-subscriptions)
- [Cosmos DB time to live](https://learn.microsoft.com/azure/cosmos-db/time-to-live)
- [Static Web Apps overview](https://learn.microsoft.com/azure/static-web-apps/overview)
- [GitHub Actions OIDC with Azure](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect)

Azure documentation and SKU availability change. The subscription's portal eligibility,
regional availability, quota, and estimate displayed at creation time override this lab's
planning assumptions.
