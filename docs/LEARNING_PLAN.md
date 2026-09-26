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

**Goal:** spend 16 focused hours deploying one intentionally small synchronous FastAPI
API in the same production-shaped path used by a GenAI application. Maximize coherent
learning, not the number of unrelated services.

```text
Client → API Management → Container Apps / FastAPI → Microsoft Foundry model
                                  │                └→ Azure AI Search → Blob documents
GitHub OIDC → ACR → revision ─────┤
Managed identity + RBAC ──────────┤
Key Vault ────────────────────────┤
Application Insights + Logs ◀─────┘
```

### Services in scope and why

| Service | GenAI purpose | Selection |
|---|---|---|
| Resource Group + tags | Lifecycle, cost, RBAC, one-command cleanup | One disposable sprint boundary |
| Microsoft Foundry | Project/model governance and playground | Platform is free; consumed model/features bill normally |
| Foundry model deployment | Real chat completion | Small pay-as-you-go model; no general free token grant |
| Azure AI Search | Retrieval and vector search for RAG | Always-free SKU: 50 MB, 10,000 documents, 3 indexes |
| Blob Storage | Source documents for grounding | 12-month grant: 5 GB Hot LRS plus operation quotas |
| Azure Container Registry | Private application image supply chain | 12-month grant: one Standard registry, 100 GB, 10 webhooks |
| Azure Container Apps | HTTPS, revisions, managed identity, scale-to-zero | Minimal FastAPI container; no VM or AKS |
| Managed Identity + RBAC | Passwordless service-to-service authentication | Model and data access without stored cloud keys |
| Key Vault | Learn secret governance and fallback key handling | 12-month grant: 10,000 Standard secret/key operations |
| API Management | Gateway, rate limit, API contract, central policy | Consumption: first 1 million API operations/month included |
| Content Safety | Prompt shields and text/image moderation | F0: 5,000 text records and 5,000 images/month; stops at limit |
| Application Insights + Log Analytics | Traces, failures, latency, model-call visibility | Low-volume lab telemetry |
| Azure Monitor + Cost Management | Alerting and spend control | Budget/alert plus final cost evidence |
| GitHub Actions OIDC | Secretless build/deploy and revision creation | Reuse the Day 1 federated identity |

The sprint deliberately skips VMs, AKS, managed PostgreSQL, Redis, private endpoints, and
provisioned model throughput. Those add cost and setup time without improving this
two-day GenAI learning path.

### Day A — model-to-API deployment (8 hours)

| Block | Outcome |
|---:|---|
| 1 | Verify credit/expiry, budget guard, subscription context, regions, quotas, and providers |
| 2 | Draw the request/identity/data flow; create one tagged sprint resource group |
| 3 | Create a Foundry resource/project manually and understand its governance boundary |
| 4 | Deploy a small chat model, test it in the playground, inspect tokens and safety behavior |
| 5 | Run the minimal synchronous FastAPI `/health` and `/chat` contract locally with provider seam |
| 6 | Create Basic ACR; build/tag/push the container; understand registry versus running container |
| 7 | Create Log Analytics, Application Insights, Container Apps environment, and scale-to-zero API |
| 8 | Enable managed identity, assign least-privilege model access, connect Key Vault, and test HTTPS `/chat` |

### Day B — RAG, operations, delivery, and destruction (8 hours)

| Block | Outcome |
|---:|---|
| 9 | Create Standard LRS Blob Storage and upload two harmless sample documents |
| 10 | Create AI Search, an index, and retrieval fields; inspect lexical results first |
| 11 | Add embeddings/vector retrieval and prove a grounded RAG response cites the sample data |
| 12 | Import the OpenAPI contract into APIM Consumption and add a small rate-limit policy |
| 13 | Exercise model content filters, prompt-injection handling, and one small evaluation set |
| 14 | Use GitHub OIDC to build/publish/deploy a new immutable revision; no client secret |
| 15 | Query logs, inspect latency/failures, run a tiny load test, and perform revision rollback |
| 16 | Capture evidence, review actual cost, delete the sprint group, and prove no billable resources remain |

### Cost guardrails

- **Expected two-day spend:** under ₹500 for tiny traffic when free tiers are available.
- **Hard learning cap:** ₹1,500; stop before creating anything whose portal estimate could
  exceed it. Prices and tax vary, so the portal cost view is authoritative.
- Use pay-as-you-go token deployments only, low token limits, scale-to-zero compute,
  Standard LRS storage, the eligible ACR Standard grant, and APIM Consumption.
- If AI Search Free is unavailable, create Basic only during the RAG block and delete it
  immediately afterward.
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
| API Management Consumption | Included monthly | First 1 million API operations/subscription/month | **Use** for gateway/rate limit |
| Content Safety F0 | Free tier | 5,000 text records and 5,000 images/month; service stops at limit | **Use** for prompt shields/moderation |
| ACR Standard | First 12 months | One registry, 100 GB storage, 10 webhooks | **Use Standard**, not Basic |
| Blob Storage Hot LRS | First 12 months | 5 GB, 20,000 reads, 10,000 writes | **Use** for grounding files |
| Key Vault Standard | First 12 months | 10,000 RSA-2048 key or secret operations | **Use** for secret governance |
| Document Intelligence S0 | First 12 months | 500 pages | **Stretch:** parse one sample PDF |
| Azure Language | Always | 5,000 text records | **Stretch:** compare key phrases/sentiment |
| Functions Consumption | Monthly grant | 1 million executions and 400,000 GB-s | **Stretch:** event-driven ingestion |
| Event Grid | Always | 100,000 operations/month | **Stretch:** Blob upload event |
| Service Bus Standard | First 12 months | 750 hours and 13 million operations | Skip unless core sprint finishes early |
| Cosmos DB free tier | Always | 1,000 RU/s and 25 GB when the free-tier account option is selected | Skip; no conversation database needed |
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
