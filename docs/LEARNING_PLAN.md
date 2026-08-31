# Learning Plan — Azure DevOps in 28 days (to Sep 27)

~1 hr/day. One small app, many deployments, everything destroyed when done.
Companion docs: [RUNBOOK.md](RUNBOOK.md), [ARCHITECTURE.md](ARCHITECTURE.md),
[INTERVIEW_NOTES.md](INTERVIEW_NOTES.md).

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
- Expected spend: **$20–60 of $200**.

## What we deliberately skip (and why that's OK)

- AKS beyond one evening (k8s is a course of its own; Container Apps covers the patterns).
- Service Bus vs Storage Queue deep dive — we use one, note the tradeoffs, move on.
- Multi-region, Front Door, private endpoints — flag them as "next quarter" topics.
- AKS persisting beyond its evening; provisioned OpenAI throughput (fixed hourly burn).
