# Learning Plan — Azure DevOps in 28 days (to Sep 27)

~1 hr/day. One small app, many deployments, everything destroyed when done.
Companion docs: [DAILY_PLAYBOOK.md](DAILY_PLAYBOOK.md) for planned steps,
[LEARNING_JOURNAL.md](LEARNING_JOURNAL.md) for the work actually performed,
[RUNBOOK.md](RUNBOOK.md), [ARCHITECTURE.md](ARCHITECTURE.md), and
[INTERVIEW_NOTES.md](INTERVIEW_NOTES.md).

## Accelerated GenAI sprint — Sep 26–27, 2026

The original 28-day sequence is preserved below as the long-term curriculum, but the
active plan changed when the Azure portal reported **₹19,109.25 credit remaining with an
expiry date of September 28, 2026**. The portal date is not treated as a promise of access
through local midnight. Finish and destroy by **8:00 PM IST on September 27**; September
28 is contingency only.

**Goal:** spend 16 focused hours deploying three intentionally small applications that
cover the three GenAI production patterns a developer is most likely to meet: synchronous
inference, retrieval-augmented generation (RAG), and asynchronous inference. The apps
share one disposable platform so the time goes into deployment and operations rather
than repeatedly creating the same registry, model, identity, and monitoring resources.

```text
Client → shared React SPA ─→ API Management
                                    ├→ App 1 FastAPI → Redis cache → Foundry chat
                                    ├→ App 2 FastAPI → AI Search → Blob
                                    └→ App 3 FastAPI → Durable Functions waits for approval/TTL
                                                         └→ Service Bus → agent worker → Cosmos DB
GitHub OIDC → ACR → immutable images/revisions
Managed identity + RBAC → Foundry, Key Vault, Redis, Search, Storage, Service Bus, Cosmos DB
Application Insights + Log Analytics ← all three applications
```

All three scenarios use **React in the browser and FastAPI as their public backend**.
To keep the build simple, one shared React SPA supplies three pages—Chat, Document Q&A,
and Agent Approval—and reuses one layout, API client, status component, and basic styling.
Each page calls its own small FastAPI API through APIM. Durable Functions, Service Bus,
Redis, Search, and Cosmos DB are internal implementation services and are never called
directly by browser code.

### The three applications

| App | User scenario | Deployment style | Azure lessons | Approximate AWS equivalents |
|---|---|---|---|---|
| **1. Chat — Fargate-equivalent exercise** | React chat form calls FastAPI `POST /chat`; repeated safe requests use a cache | FastAPI container on Container Apps behind APIM, with Azure Managed Redis cache-aside | Foundry model deployment, ACR, managed identity, revisions, autoscaling, scale-to-zero, token-saving cache, TLS, rollback, gateway policy | Bedrock + ElastiCache + ECR + ECS/Fargate + API Gateway |
| **2. Document Q&A** | React upload/question page calls FastAPI and displays a cited answer | FastAPI container plus Blob and AI Search | ingestion, embeddings, vector/lexical search, grounded answers, Content Safety | S3 + Textract/OpenSearch + Bedrock Guardrails |
| **3. Approval-gated agent** | React run page calls FastAPI, displays the plan/status, and provides Approve/Reject; unanswered approvals expire | FastAPI facade → Durable Functions external event/timer → Service Bus → agent worker → Cosmos DB | durable orchestration, human-in-the-loop, queue load leveling, retries, TTLs, idempotency, audit/status persistence | Step Functions + API Gateway/Lambda + SQS + Lambda + DynamoDB |

Each application is complete only after it has been deployed, called successfully,
observed in logs, deliberately failed and recovered, redeployed, and removed. App 1 is
also deployed a second time from the learner's own commands as the repetition exercise.

### ECS Fargate and Azure: the practical mapping

There is no exact one-to-one service name. **Azure Container Apps** is the best match for
this sprint's long-running HTTP container: it supplies managed serverless container
compute plus ingress, revisions, KEDA-based autoscaling, logs, and scale-to-zero without
the learner managing Kubernetes nodes. ECS performs scheduling while Fargate supplies
serverless compute; Container Apps presents those concerns as one opinionated platform.

**Azure Container Instances (ACI)** is closer to “run this container directly,” but it
lacks the richer application lifecycle needed by the Chat API. **Container Apps Jobs**
is the closer Azure choice for one-off, scheduled, or event-driven Fargate-style tasks.
App 1 therefore uses Container Apps and explicitly exercises image deployment, a
long-running service, revision creation, autoscaling/scale-to-zero, and rollback.

### Multiple users, queueing, and model-response caching

Multiple simultaneous HTTP users do not automatically require a queue. Container Apps
handles short synchronous requests through concurrent replicas and autoscaling. App 3
uses Service Bus because long inference jobs need load leveling: the API accepts work
quickly, the queue absorbs bursts, and worker concurrency is capped to protect Foundry
rate limits. Queue depth becomes the scaling and operational signal.

App 1 uses **Azure Managed Redis** as a cache-aside layer. The application checks a
SHA-256 key derived from normalized input, tenant/auth scope, model deployment, prompt
version, and generation parameters. A hit returns the prior safe result without spending
model tokens; a miss calls or queues inference and stores the result with a short TTL.
A distributed `SET NX` lock prevents many identical misses from creating a cache
stampede. Personalized or sensitive responses are not shared across users, failures are
never cached, and Redis remains disposable—not the system of record.

Azure Cache for Redis Basic/Standard/Premium is retiring and creation has been blocked
for new public-cloud customers since April 1, 2026. Use **Azure Managed Redis**, which
supports TLS 1.2/1.3, rather than following an older tutorial. It has no verified free
allowance in this subscription plan: create the smallest dev/test configuration with
high availability disabled only if the portal estimate fits the cap, use it for the
cache block, and delete it that day. If the estimate does not fit, run open-source Redis
locally to learn the application pattern and record the managed-service portal review.

### HTTPS and certificates

Container Apps and APIM provide publicly trusted Microsoft-managed HTTPS certificates
on their generated domains. The exercise proves HTTP-to-HTTPS behavior, inspects the
certificate chain/expiry, terminates client TLS at APIM, and keeps APIM-to-Container Apps
traffic on HTTPS. The certificate is attached at the ingress/gateway, not copied into the
FastAPI image. If the learner already owns a domain, add its DNS verification and a
managed Container Apps or APIM custom-domain certificate. Do not buy a domain solely for
this sprint; the generated Azure hostname already demonstrates real SSL/TLS.

### Long-running agents, human approval, and TTLs

App 3's FastAPI endpoint never keeps an HTTP request open while an agent works or waits
for a person. It returns `202 Accepted` with a run ID and status URL, then starts the
internal Durable Functions workflow. A Durable Functions
orchestrator checkpoints the proposed plan, records `awaiting_approval`, and races an
external `Approval` event against a durable timer. An authorized approve event continues
to Service Bus; reject or timeout ends the run without executing the proposed action.
The approval records actor, time, decision, and the immutable plan hash so a changed plan
cannot reuse an earlier approval. Duplicate decisions are idempotent.

The exercise distinguishes four controls that are often all called “TTL”:

1. **Redis TTL** controls cached response freshness and token reuse.
2. **Service Bus message TTL** limits how long approved work may wait in the queue; expired
   messages are dead-lettered for diagnosis.
3. **Approval TTL** is a durable workflow timer (10 minutes in the lab), after which the
   status becomes `expired` and no tool/action runs.
4. **Cosmos DB item TTL** removes old lab status/audit records after the chosen retention.

Worker execution has a separate application deadline and lock renewal. Message TTL is
not treated as a safe way to terminate code already running. Long work is split into
idempotent steps with checkpoints so retries do not repeat side effects.

### Services in scope and why

| Service | GenAI purpose | Selection |
|---|---|---|
| Resource Group + tags | Lifecycle, cost, RBAC, one-command cleanup | One shared disposable sprint boundary |
| Microsoft Foundry | Project/model governance and playground | Platform is free; consumed model/features bill normally |
| Foundry model deployment | Real chat completion | Small pay-as-you-go model; no general free token grant |
| Azure AI Search | Retrieval and vector search for RAG | Always-free SKU: 50 MB, 10,000 documents, 3 indexes |
| Blob Storage | Source documents for grounding | 12-month grant: 5 GB Hot LRS plus operation quotas |
| Azure Container Registry | Private application image supply chain | 12-month grant: one Standard registry, 100 GB, 10 webhooks |
| Azure Container Apps | HTTPS, revisions, managed identity, scale-to-zero | Minimal FastAPI container; no VM or AKS |
| Azure Static Web Apps | Host the shared React SPA and its three pages | Free tier; one deliberately simple website |
| Managed Identity + RBAC | Passwordless service-to-service authentication | Model and data access without stored cloud keys |
| Key Vault | Learn secret governance and fallback key handling | 12-month grant: 10,000 Standard secret/key operations |
| API Management | Gateway, rate limit, API contract, central policy | Consumption: first 1 million API operations/month included |
| Content Safety | Prompt shields and text/image moderation | F0: 5,000 text records and 5,000 images/month; stops at limit |
| Application Insights + Log Analytics | Traces, failures, latency, model-call visibility | Low-volume lab telemetry |
| Azure Monitor + Cost Management | Alerting and spend control | Budget/alert plus final cost evidence |
| GitHub Actions OIDC | Secretless build/deploy and revision creation | Reuse the Day 1 federated identity |
| Azure Managed Redis | Cache-aside responses, token savings, stampede protection | Smallest dev/test configuration for one short block; paid and destroyed same day |
| Azure Functions + Durable Functions | HTTP ingress and checkpointed approval-gated orchestration | Consumption plan; external event plus durable timer without holding a request/thread |
| Storage account | Durable Functions runtime state | Standard LRS; runtime-managed checkpoints, not application results |
| Service Bus | Durable job handoff, retries, and dead lettering | Standard tier; one short-lived queue |
| Cosmos DB | Job status and result lookup | One free-tier account if the subscription remains eligible |

The sprint deliberately skips VMs, AKS, managed PostgreSQL, private endpoints, and
provisioned model throughput. Those add cost and setup time without improving these
three GenAI deployment patterns.

### Day A — shared platform, synchronous API, and RAG (8 hours)

| Block | Outcome |
|---:|---|
| 1 | Verify credit/expiry, budget guard, subscription context, regions, quotas, and providers |
| 2 | Draw all three request/identity/data flows; run the shared React SPA plus three FastAPI contracts locally; create the tagged group, Foundry deployments, ACR, Key Vault, monitoring, and only an approved-cost Managed Redis instance |
| 3 | Build/push App 1 FastAPI, create its Container App, and deploy the React SPA Chat page to Static Web Apps |
| 4 | Give App 1 managed identity least-privilege access; test cache MISS then HIT through APIM; inspect token usage and the managed HTTPS certificate |
| 5 | Send concurrent duplicate requests, observe autoscaling and cache-stampede protection; break configuration, diagnose/restore, deploy a revision, and roll back |
| 6 | Repeat App 1 deployment from the learner's own saved CLI commands without copying the walkthrough line by line |
| 7 | Create Blob Storage, AI Search Free, and Content Safety; upload two harmless documents and inspect lexical/vector retrieval |
| 8 | Deploy App 2 FastAPI and React Document Q&A page; verify a cited grounded answer and unknown-answer case, safety behavior, and traces |

### Day B — asynchronous app, automation, operations, and destruction (8 hours)

| Block | Outcome |
|---:|---|
| 9 | Create Functions Consumption/Durable Functions storage, Service Bus with TTL/dead-lettering, and one eligible Cosmos DB free-tier account with item TTL |
| 10 | Deploy App 3's FastAPI start/status/approval endpoints, React Agent page, internal orchestrator, and queue worker with managed identity and least-privilege RBAC |
| 11 | Submit concurrent agent runs, inspect plans, approve one, reject one, let one approval expire, and observe queue depth, controlled concurrency, and status/audit records |
| 12 | Test duplicate approval, changed-plan rejection, worker retry, message expiry/dead letter, repair/replay, lock renewal, and idempotent side effects |
| 13 | Add all three application routes to APIM, enforce HTTPS/rate limits, inspect TLS termination and certificate expiry, and compare synchronous/asynchronous contracts |
| 14 | Use GitHub OIDC to build/publish/deploy immutable versions; no Azure client secret in the workflow |
| 15 | Query cross-app logs, inspect latency/failures, run tiny tests, and repeat one deployment without the walkthrough |
| 16 | Capture architecture/cost evidence, delete the sprint group, check soft-deleted services, and prove no billable resources remain |

### Cost guardrails

- **Expected two-day spend:** under ₹500 for tiny traffic when free tiers are available.
- **Hard learning cap:** ₹1,500; stop before creating anything whose portal estimate could
  exceed it. Prices and tax vary, so the portal cost view is authoritative.
- Use pay-as-you-go token deployments only, low token limits, scale-to-zero compute,
  Standard LRS storage, the eligible ACR Standard grant, APIM Consumption, Functions
  Consumption, one Service Bus queue, and one eligible Cosmos DB free-tier account.
- If AI Search Free is unavailable, create Basic only during the RAG block and delete it
  immediately afterward.
- If Cosmos DB free tier is unavailable, use Table Storage for job state rather than
  creating paid provisioned throughput; if Service Bus Standard is not shown as eligible,
  create it only for the async block and delete it immediately afterward.
- Azure Managed Redis is paid, not assumed free. Review the portal estimate first, disable
  high availability only for this disposable dev/test exercise, keep it for one block,
  and use local Redis instead if its estimate threatens the ₹1,500 cap.
- Never select provisioned throughput, GPU compute, AKS, premium gateways, or private
  endpoints during this sprint.
- All planned charges consume Azure credit. Outside-credit spend remains ₹0 unless the
  owner explicitly upgrades to pay-as-you-go or buys a custom domain; neither is needed.

### What happens after the promotional credit expires

Pay-As-You-Go is an explicit upgrade, not the automatic next state. Without an upgrade,
Microsoft disables the free-trial subscription and its services when the credit is used
or the 30-day period ends. If the owner upgrades:

- eligible 12-month service grants continue only until 12 months from the **original
  signup date**, not 12 months from the upgrade;
- always-free monthly grants continue within their current service-specific limits;
- the promotional credit still expires on its original date;
- non-free services, non-free SKUs, and usage above each grant bill the payment method;
- Cost Management budgets alert but do not enforce a hard spending cap.

Foundry model tokens, ACR, AI Search Basic when Free is unavailable, Key Vault operations,
storage, network egress, and telemetry beyond included grants can all bill on PAYG. The
sprint therefore ends with deletion regardless of whether the account is later upgraded.
No upgrade is required or authorized by this plan.

### Free-quota map relevant to a GenAI developer

Free allowances are quantities, not additional currency. They reset monthly, unused
amounts do not roll over, and the exact SKU matters. The subscription's
**Cost Management + Billing → Free services** grid is authoritative for eligibility and
usage; the public list can change.

| Service | Period | Current included amount | Sprint decision |
|---|---|---|---|
| Azure AI Search | Always | 50 MB, 10,000 hosted documents, 3 indexes per service | **Use Free** for RAG |
| Container Apps Consumption | Always | 180,000 vCPU-s, 360,000 GiB-s, 2 million requests/subscription/month | **Use** with scale-to-zero |
| Static Web Apps Free | Free tier | Hosting quota shown by the selected plan | **Use** for the shared React SPA |
| API Management Consumption | Included monthly | First 1 million API operations/subscription/month | **Use** for gateway/rate limit |
| Content Safety F0 | Free tier | 5,000 text records and 5,000 images/month; service stops at limit | **Use** for prompt shields/moderation |
| ACR Standard | First 12 months | One registry, 100 GB storage, 10 webhooks | **Use Standard**, not Basic |
| Blob Storage Hot LRS | First 12 months | 5 GB, 20,000 reads, 10,000 writes | **Use** for grounding files |
| Key Vault Standard | First 12 months | 10,000 RSA-2048 key or secret operations | **Use** for secret governance |
| Document Intelligence S0 | First 12 months | 500 pages | **Stretch:** parse one sample PDF |
| Azure Language | Always | 5,000 text records | **Stretch:** compare key phrases/sentiment |
| Functions Consumption | Monthly grant | 1 million executions and 400,000 GB-s | **Use** for durable orchestration/workers |
| Event Grid | Always | 100,000 operations/month | **Stretch:** Blob upload event |
| Service Bus Standard | First 12 months | 750 hours and 13 million operations | **Use** for approved agent work |
| Cosmos DB free tier | Always | 1,000 RU/s and 25 GB when the free-tier account option is selected | **Use** for agent status/audit with item TTL |
| Azure Managed Redis | Paid | No verified free-account allowance; hourly SKU charge | **Use briefly** only after portal estimate; local fallback |
| PostgreSQL Flexible | First 12 months | 750 B1ms hours, 32 GB data, 32 GB backup | Skip; FastAPI remains stateless |
| Linux/Windows VMs | First 12 months | 750 hours each of eligible B1s/B2pts v2/B2ats v2 SKUs | Skip; Container Apps teaches the target path |
| Microsoft Foundry platform | Platform | Portal/project exploration is free; consumed capabilities bill normally | **Use**, but meter model calls |
| Foundry/OpenAI model inference | No general grant | Token/model/deployment-specific pay-as-you-go pricing | **Paid from credit**, strict token limits |
| Azure Monitor logs | No general free ingestion grant shown | Standard metrics/activity logs have free units; Log Analytics ingestion is metered | **Use minimally**, sampling/cap enabled |

This changes the likely sprint cost toward model tokens plus a very small telemetry bill.
It does not justify adding every free service: a service belongs in the architecture only
when it teaches a coherent GenAI concern.

---

## The rhythm for every deployment exercise

> create (Terraform plan → **you** review → apply) → deploy → verify (RUNBOOK §2) →
> break something on purpose → fix → `terraform destroy` same day → note the cost.

**Manual first, automate second.** Every stage: do it once by hand in the portal
or with `az` CLI (so you know what exists and how it composes), then encode it in
Terraform + CI so the pipeline can repeat it.

## Standing rules for every session

1. One resource group per experiment: `learn-<stage>-<date>`.
2. Expiry tag on everything (`expires=+3d`).
3. You review every `terraform plan` before apply.
4. Overrunning the hour? Destroy and resume tomorrow — infra is cheap to recreate; that's the point.
5. Screenshot dashboards before destroying (portfolio evidence).
6. Check Cost Management after each session.

---

## Week 1 (Aug 31 – Sep 6) — Foundations, secrets, IaC basics

| Day | Goal | Azure services | Output |
|---|---|---|---|
| Mon 31 | Your 4 setup items (branch protection, package visibility, OIDC app registration, first local compose run) | — | Governance in place |
| Tue 1 | Install `az` CLI, `az login`, explore: RGs, `az resource list` | CLI, Resource Groups | Azure organized in your head |
| Wed 2 | **Manual:** create RG + Key Vault in portal; add a secret; read via CLI; compare access policies vs RBAC | **Key Vault, RBAC** | Vault kept (~$0/mo) |
| Thu 3 | Terraform 101: `init/plan/apply` a resource group; read the state file | Terraform state | First TF apply |
| Fri 4 | TF: Key Vault + secret; import what you made manually | IaC vs manual | tf files in repo |
| Sat 5 | Wire the app to read config from Key Vault (SPN/env locally); `/health` proves it | App↔Vault integration | Stack uses vault |
| Sun 6 | Review week. **Destroy all TF resources except the vault** | Cost discipline | ~$0 remaining |

## Week 2 (Sep 7–13) — Deploy to a VM (stage 5)

| Day | Goal | You learn | Output |
|---|---|---|---|
| Mon 7 | TF: Linux VM (B2s), VNet, NSG, public IP | Compute + network primitives | VM reachable |
| Tue 8 | Docker on VM, `compose up` the stack, open only 80/443 | Remote deploy, firewall rules | App on a public VM |
| Wed 9 | nginx reverse proxy + TLS (certbot) | Ingress, certificates | HTTPS URL |
| Thu 10 | Deploy pipeline v1: Actions SSHes in, pulls new `sha-` image tags, `up -d` | Continuous delivery | push = deploy |
| Fri 11 | Chaos hour: kill worker, fill disk, wrong env → recover with RUNBOOK §8 | Debugging under failure | Incident notes |
| Sat 12 / Sun 13 | Buffer. **Destroy the VM's RG.** Check the bill | Cost discipline | RG gone |

## Week 3 (Sep 14–20) — Azure-native (stage 6): the "modern" deployment

| Day | Goal | You learn | Output |
|---|---|---|---|
| Mon 14 | TF: Log Analytics workspace + Container Apps environment | Hosting primitive, log wiring | Env created |
| Tue 15 | Deploy API as a Container App from GHCR image; custom domain optional | Ingress, revisions | Public URL |
| Wed 16 | Add worker app (same image, different command); scale rule 0→3 on queue length | Scale-to-zero, KEDA | Idle = $0 |
| Thu 17 | Azure PostgreSQL Flexible (B1ms, free tier) + swap in; secrets from Key Vault | Managed data services | E2E on managed stack |
| Fri 18 | Load test (`hey -c 50 -z 60s`); watch replicas scale in the portal | Autoscaling behavior | Numbers to quote |
| Sat 19 | **WEBSITE deployment**: React UI to Azure Static Web Apps (free tier), wired to the API; optional custom domain | Static hosting, SWA CI | Live public website |
| Sun 20 | Rollback drill: deploy a bad revision, revert it; traffic split; then destroy all but the DB | Blue/green, canary basics | Drill done |

## Week 4 (Sep 21–27) — Production behaviors + Kubernetes taste

| Day | Goal | You learn | Output |
|---|---|---|---|
| Mon 21 | Full CI/CD: PR → tests → publish → deploy **staging** → manual approval → prod | Environments + approvals | 2-env pipeline |
| Tue 22 | AKS evening (may take 2h): TF a 1-node free-tier cluster, deploy the API, walk pods/services/ingress, **destroy tonight** | Kubernetes vocabulary | AKS literacy |
| Wed 23 | App Configuration + a feature flag the app reads; flip it without redeploying | Remote config, flags | Config externalized |
| Thu 24 | Break the DB mid-traffic; watch retries, health probes, alert on failure rate | Resilience + **App Insights / Monitor** | Alert rule active |
| Fri 25 | Full pipeline tour end-to-end, then deliberate rollback via revisions | The complete lifecycle | Green + revert demo |
| Sat 26 | `az resource list` sweep → destroy every remaining RG; cost review | FinOps | Near-zero balance |
| Sun 27 | Write the story: what you built, every screenshot, costs, incidents — your portfolio doc | Consolidation | Notes doc |

## Deliverables: 9 distinct deployments by Sep 27

1. Local compose stack (you run it)  2. VM + compose + TLS  3. Container Apps API
4. Container Apps worker with scale-to-zero 5. Managed Postgres behind Key Vault
6. **Website: React UI on Azure Static Web Apps** 7. AKS (one evening, destroyed same day)
8. Automated deploy with approval + rollback 9. Load-tested + alerting deployment

## Why this fits $200

- Only the VM week and the AKS evening cost ~$2–5/day — they exist for days.
- Container Apps idle at scale-0 ≈ $0; PostgreSQL B1ms inside the free allowance;
  Key Vault ≈ cents; Log Analytics capped by short retention.
- Destroy same-day = the big burn risks (forgotten VM/AKS) can't accumulate.
- Expected spend: **~$8–15 of $200** (per-day model in `docs/Learning_Tracker.xlsx` → Day Cost Plan; the $20–60 earlier figure was the pre-refinement buffer).

## What we deliberately skip (and why that's OK)

- AKS beyond one evening (k8s is a course of its own; Container Apps covers the patterns).
- Service Bus vs Storage Queue deep dive — we use one, note the tradeoffs, move on.
- Multi-region, Front Door, private endpoints — flag them as "next quarter" topics.
- AKS persisting beyond its evening; provisioned OpenAI throughput (fixed hourly burn).
