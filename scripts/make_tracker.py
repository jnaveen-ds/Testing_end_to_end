"""Generate docs/Learning_Tracker.xlsx — the day-by-day Azure learning tracker.

Run from repo root:  .venv/bin/python scripts/make_tracker.py
"""
import datetime as dt

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

HDR = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(bold=True, color="FFFFFF", size=10)
WRAP = Alignment(wrap_text=True, vertical="top")

# (day, date, phase, goal, azure services, portal steps, CLI commands, time)
DAYS = [
    (1, "2026-08-31", "Setup", "Repo governance + OIDC prep + first local run",
     "none",
     "Branch protection on main; GHCR packages public; Entra app + federated credential; Contributor role",
     "az login; az account list; docker compose up --build (local)", "1h"),
    (2, "2026-09-01", "Foundations", "Azure anatomy: subscription, RGs, providers",
     "Resource Groups",
     "Subscriptions, Resource groups, Cost Management blades",
     "az login; az account set; az group create/delete; az resource list", "1h"),
    (3, "2026-09-02", "Secrets", "Key Vault manually in the portal",
     "Key Vault, RBAC",
     "Create vault (RBAC); Secrets tab add LLM-PROVIDER; IAM role assignment",
     "az keyvault show; az keyvault secret set/show", "1h"),
    (4, "2026-09-03", "Secrets", "CLI-driven vault access with least privilege",
     "Key Vault, Entra ID",
     "Role assignments blade on the vault",
     "az ad sp create; az role assignment create; az keyvault secret show", "1h"),
    (5, "2026-09-04", "IaC", "Terraform 101: resource group via code; state concept",
     "Terraform (azurerm)",
     "Verify TF-created RG in portal; read the plan output line by line",
     "terraform init; plan -out; apply; state list; destroy", "1h"),
    (6, "2026-09-05", "IaC", "Key Vault + secret entirely in Terraform",
     "Key Vault via TF",
     "Compare portal form fields with TF resource attributes",
     "terraform apply; terraform destroy", "1h"),
    (7, "2026-09-05", "Integration", "App reads config from Key Vault; OIDC app ready for GitHub",
     "Key Vault, Entra federated credential",
     "Federated credential subject: repo:jnaveen-ds/Testing_end_to_end:ref:refs/heads/main",
     "az keyvault secret show; verify app /health uses vault config", "1h"),
    (8, "2026-09-06", "Cleanup", "Week 1 review + cost check",
     "Cost Management",
     "Cost analysis blade; budget review",
     "az group list; az consumption usage list", "30m"),
    (9, "2026-09-07", "Week 2 · VM", "Terraform: Linux VM + VNet + subnet + NSG + public IP",
     "Linux VM, VNet, NSG, disk, public IP",
     "VM blade: boot diagnostics, NSG rules, size/cost estimate",
     "terraform apply (infra/day9); az vm list; ssh", "1h"),
    (10, "2026-09-08", "VM", "Deploy the app stack onto the VM; open only needed ports",
     "VM, Docker Compose, NSG rules",
     "NSG inbound rules audit; boot diagnostics",
     "ssh; docker compose up -d --build; curl /health", "90m"),
    (11, "2026-09-09", "VM", "TLS + reverse proxy in front of the app",
     "nginx, TLS (certbot)",
     "Certificates; custom domain (if any)",
     "nginx config; certbot --nginx or openssl self-signed", "1h"),
    (12, "2026-09-11", "CD", "Actions deploys to the VM: SSH + pull sha-tagged image + restart",
     "GitHub Actions, VM",
     "GitHub environment secrets review (never in git)",
     "git push -> deploy job -> curl public /health", "1h"),
    (13, "2026-09-12", "Chaos", "Break things on purpose: kill worker, wrong env, full disk; recover",
     "ops skills",
     "Serial console; boot diagnostics",
     "systemctl; docker; df -h; journalctl", "90m"),
    (14, "2026-09-13", "Cleanup", "Destroy the VM resource group; review week-2 spend",
     "Cost Management",
     "Cost analysis", "az group delete; terraform destroy", "30m"),
    (15, "2026-09-14", "Week 3 · Containers", "Log Analytics + Container Apps environment + deploy API",
     "Log Analytics, Container Apps",
     "Container app blade: Revisions, Log stream, Scale",
     "az containerapp env create; TF apply (infra/day15)", "90m"),
    (16, "2026-09-15", "Containers", "Worker as second app; scale-to-zero via KEDA rule",
     "Container Apps scale rules (KEDA)",
     "Scale tab: min 0 / max 3; watch 0->1 on submit",
     "az containerapp update --min-replicas 0", "1h"),
    (17, "2026-09-16", "Data", "Azure PostgreSQL Flexible (B1ms) wired via Key Vault secret",
     "PostgreSQL Flexible, Key Vault",
     "Server networking + metrics blades; firewall rules",
     "TF apply; az keyvault secret set (connection string)", "90m"),
    (18, "2026-09-17", "Autoscaling", "Load test with hey; watch replicas scale in the Metrics blade",
     "Container Apps autoscale, Metrics",
     "Metrics blade: replica count vs request rate",
     "hey -c 20 -z 2m https://<app-url>", "1h"),
    (19, "2026-09-19", "Website", "WEBSITE DEPLOYMENT: React UI on Azure Static Web Apps (free tier), pointed at the API",
     "Static Web Apps (+ optional custom domain)",
     "SWA portal: environments, tokens, custom domain",
     "az staticwebapp create; swa deploy; verify site + API wiring", "90m"),
    (20, "2026-09-20", "Resilience", "Rollback drills: bad revision -> revert; traffic split blue/green",
     "Container Apps revisions",
     "Revision management + traffic weighting UI",
     "az containerapp revision list/activate; ingress traffic set", "1h"),
    (21, "2026-09-20", "Cleanup", "Destroy week-3 compute; keep only free-tier DB + images",
     "-", "Cost check", "az group delete (each learn RG)", "30m"),
    (22, "2026-09-22", "Kubernetes", "AKS evening: 1-node free-tier cluster; deploy API+worker; DESTROY tonight",
     "AKS, kubectl, Azure Load Balancer",
     "AKS blade: workloads, services, logs",
     "az aks create; get-credentials; kubectl apply/get; az aks delete", "2h"),
    (23, "2026-09-23", "Config", "App Configuration + feature flag; change behavior without redeploy",
     "App Configuration",
     "Feature manager UI",
     "az appconfig create; az appconfig kv set; wire app endpoint", "1h"),
    (24, "2026-09-24", "Resilience", "App Insights live; kill DB mid-traffic; alert on error rate",
     "Application Insights, Monitor alerts",
     "Live Metrics; Log Analytics queries; create alert rule",
     "az monitor metrics alert create", "90m"),
    (25, "2026-09-25", "Pipeline", "Full automated flow: PR -> CI -> publish -> deploy staging -> approval -> prod -> rollback",
     "OIDC deploys, environments, approvals",
     "GitHub environment protection rules",
     "watch the Actions run end to end", "90m"),
    (26, "2026-09-26", "FinOps", "Sweep + destroy everything not deliberately kept; review spend",
     "Cost Management",
     "Cost analysis vs budget; verify alerts fired",
     "az group list; az group delete per learn-* RG", "90m"),
    (27, "2026-09-27", "Portfolio", "Screenshot dashboards -> docs/PORTFOLIO.md -> destroy the rest",
     "-", "Screenshot everything first", "final az group delete", "1h"),
]

DAY_PROGRESS = {
    1: (
        "Done",
        "Yes",
        "GitHub governance, public GHCR, Entra OIDC/RBAC, and local five-container flow "
        "completed. Fixed missing nginx /api proxy. Containers and pgdata volume destroyed.",
    ),
    2: (
        "In progress",
        "",
        "Accelerated two-day GenAI sprint started after portal confirmed INR 19,109.25 credit "
        "expires Sep 28. Use ephemeral Cloud Shell; destroy by Sep 27 20:00 IST.",
    ),
}

SPRINT_BLOCKS = [
    (1, "Day A", "Expiry, budget, subscription, quotas, providers", "Cost Management, Resource Providers", "₹0"),
    (2, "Day A", "Three flows + local shared React SPA and FastAPI contracts + shared cloud platform", "React, FastAPI, RG, Foundry, ACR, Key Vault, Monitor", "<₹100 target"),
    (3, "Day A", "App 1 FastAPI on Fargate-equivalent hosting + React Chat page", "Container Apps, Static Web Apps, ACR", "free-quota target"),
    (4, "Day A", "Cache MISS→HIT, managed identity, APIM, trusted HTTPS certificate", "Azure Managed Redis, RBAC, APIM", "Redis estimate required"),
    (5, "Day A", "Concurrent users, autoscaling, stampede lock, break/fix, revision rollback", "Container Apps, Redis, App Insights", "<₹100 target"),
    (6, "Day A", "Repeat App 1 deployment from learner's saved commands", "ACR, Container Apps, APIM", "<₹50 target"),
    (7, "Day A", "Blob, AI Search, Content Safety, lexical/vector retrieval", "Storage, AI Search Free, Content Safety F0", "<₹100 target"),
    (8, "Day A", "App 2 FastAPI + React Document Q&A; grounded and unknown answers", "Container Apps, Static Web Apps, Foundry, AI Search", "<₹100 target"),
    (9, "Day B", "Durable runtime, queue TTL/dead letter, Cosmos item TTL", "Functions, Storage, Service Bus, Cosmos DB", "free-quota target"),
    (10, "Day B", "App 3 FastAPI + React Agent page + approval orchestrator + worker", "Container Apps, Static Web Apps, Durable Functions", "<₹100 target"),
    (11, "Day B", "Concurrent runs: approve, reject, approval timeout, queue depth", "Durable Functions, Service Bus, Cosmos DB", "<₹50 target"),
    (12, "Day B", "Duplicate/changed approval, message expiry, retry, dead letter, replay, lock renewal", "Service Bus, Durable Functions, App Insights", "<₹50 target"),
    (13, "Day B", "Three APIM routes, HTTPS-only, certificate inspection, rate limits", "APIM Consumption, managed TLS", "near ₹0"),
    (14, "Day B", "OIDC build/publish/deploy immutable revision", "GitHub Actions, ACR, Container Apps", "<₹50 target"),
    (15, "Day B", "Cross-app logs, tiny load tests, alert, independent repeat deployment", "Azure Monitor, Container Apps revisions", "<₹100 target"),
    (16, "Day B", "Evidence, actual cost, delete and prove absence", "Cost Management, Resource Group", "₹0"),
]

FREE_QUOTAS = [
    ("AI/RAG", "Azure AI Search", "Always", "50 MB; 10,000 documents; 3 indexes", "Core: Free SKU"),
    ("Hosting", "Container Apps Consumption", "Always", "180,000 vCPU-s; 360,000 GiB-s; 2M requests/month", "Core: scale to zero"),
    ("Hosting", "Static Web Apps Free", "Free tier", "Hosting quota shown by the selected plan", "Core shared React SPA"),
    ("Gateway", "API Management Consumption", "Monthly included", "First 1M API operations/subscription/month", "Core"),
    ("Safety", "Content Safety F0", "Free tier", "5,000 text records + 5,000 images/month; hard stop", "Core"),
    ("Registry", "Container Registry Standard", "12 months", "1 registry; 100 GB; 10 webhooks", "Core: exact Standard SKU"),
    ("Data", "Blob Storage Hot LRS", "12 months", "5 GB; 20,000 reads; 10,000 writes", "Core"),
    ("Security", "Key Vault Standard", "12 months", "10,000 RSA-2048 key or secret operations", "Core"),
    ("Document AI", "Document Intelligence S0", "12 months", "500 pages", "Stretch"),
    ("NLP", "Azure Language", "Always", "5,000 text records", "Stretch"),
    ("Compute", "Functions Consumption", "Monthly grant", "1M executions + 400,000 GB-s", "Core durable workflow"),
    ("Events", "Event Grid", "Always", "100,000 operations/month", "Stretch Blob trigger"),
    ("Messaging", "Service Bus Standard", "12 months", "750 hours + 13M operations", "Core async queue"),
    ("Database", "Cosmos DB free tier", "Always", "1,000 RU/s + 25 GB when free tier selected", "Core status/audit"),
    ("Cache", "Azure Managed Redis", "Paid", "No verified free-account grant; hourly SKU charge", "One block if estimate fits; local fallback"),
    ("Database", "PostgreSQL Flexible B1ms", "12 months", "750 hours + 32 GB data + 32 GB backup", "Defer"),
    ("Compute", "Eligible Linux/Windows VMs", "12 months", "750 hours each for listed B1s/B2pts v2/B2ats v2", "Defer"),
    ("AI platform", "Microsoft Foundry", "Platform free", "Consumed features bill at their own rates", "Core"),
    ("Model", "Foundry/OpenAI inference", "Paid", "No general free-token grant; model/token rates", "Core: strict limits"),
    ("Observability", "Azure Monitor / Log Analytics", "Paid ingestion", "Platform metrics/activity logs have free units; log ingestion metered", "Core: sample/cap"),
]

# Per-day cost model. Rates are approximate pay-as-you-go list prices (USD,
# ~East US; South India similar for these SKUs). Azure free-account allowances
# (12-month free services) make several of these $0 in practice — shown so you
# learn the real meter that WOULD bill you. Cumulative assumes strict destroys.
# (day, services billed, meter/rate note, usage, est $)
DAY_COSTS = [
    (1,  "none (local only)",                        "-",                                     "-",      0.00),
    (2,  "Resource groups (empty)",                  "RGs are free; only contents bill",      "-",      0.00),
    (3,  "Key Vault",                                "$0.03 per 10,000 operations",           "tiny",   0.01),
    (4,  "Key Vault",                                "$0.03 per 10,000 operations",           "tiny",   0.01),
    (5,  "Resource group via Terraform",             "state kept in local file, $0",          "-",      0.00),
    (6,  "Key Vault via Terraform",                  "$0.03 per 10,000 operations",           "tiny",   0.01),
    (7,  "Key Vault + Entra app",                    "app registration free",                 "-",      0.01),
    (8,  "cleanup day (nothing running)",            "-",                                     "-",      0.00),
    (9,  "VM B2s (24h) + public IP + 30GB disk",     "~$1.00 compute + $0.09 IP + $0.10 disk", "24h",   1.20),
    (10, "VM day 2 (compose stack + image build)",   "same meters",                           "24h",    1.20),
    (11, "VM day 3 (TLS / nginx)",                   "same meters",                           "24h",    1.20),
    (12, "VM day 4 (CI deploys hitting it)",         "compute + egress ~$0.05",               "24h",    1.30),
    (13, "VM day 5 (chaos tests)",                   "same meters",                           "24h",    1.20),
    (14, "VM destroyed the evening before",          "resource group deleted",                "0h",     0.00),
    (15, "Container Apps env + API app (mostly idle)", "~$0.000024/vCPU-s consumption",       "minutes", 0.05),
    (16, "API + worker, brief scale-up tests",       "consumption plan, 2M requests free",    "minutes", 0.05),
    (17, "PostgreSQL B1ms + apps",                   "free tier: 750 B1ms hours + 32GB/mo",   "hours",  0.00),
    (18, "Load test: replicas briefly at 2-3",       "consumption plan",                      "1-2 h",  0.50),
    (19, "Static Web Apps free tier + egress",       "free tier, ~100GB bandwidth/month free", "1 day", 0.00),
    (20, "Revision/rollback drills on existing apps", "no new meters",                        "-",      0.05),
    (21, "everything destroyed",                     "-",                                     "-",     0.00),
    (22, "AKS evening: 1 node B2ms ~8h + LB",        "~$0.083/hr node + ~$0.01/hr LB",        "8h",     1.00),
    (23, "App Configuration",                        "free tier: 1k requests/day",            "tiny",   0.01),
    (24, "App Insights + Log Analytics",             "log ingestion metered; platform metrics free", "tiny", 0.05),
    (25, "pipeline reruns on existing resources",    "no new meters",                         "-",      0.05),
    (26, "finops sweep (nothing new)",               "-",                                     "-",      0.00),
    (27, "write-up day (DB kept only if free tier)", "B1ms beyond allowance = ~$0.41/day",    "-",      0.41),
]

DEPLOYMENTS = [
    (1, "Local compose stack (5 containers)", "Docker Compose", "Day 1", "destroyed after verification"),
    (2, "Shared website: React SPA with Chat, Document Q&A, and Agent pages", "Azure Static Web Apps", "Sprint Day A", "destroy Sep 27"),
    (3, "Chat FastAPI: Fargate-equivalent service with cache and TLS", "Container Apps, ACR, Managed Redis, APIM", "Sprint Day A", "Redis same-block; rest Sep 27"),
    (4, "Document Q&A FastAPI: cited RAG", "Container Apps, Blob, AI Search, Foundry", "Sprint Day A", "destroy Sep 27"),
    (5, "Approval-gated Agent FastAPI: durable wait, queue, status", "Durable Functions, Service Bus, Cosmos DB", "Sprint Day B", "destroy Sep 27"),
    (6, "Immutable OIDC redeploy and rollback", "GitHub Actions, ACR, Container Apps", "Sprint Day B", "destroy Sep 27"),
]


def header(ws, cols):
    for i, name in enumerate(cols, 1):
        c = ws.cell(row=1, column=i, value=name)
        c.fill = HDR
        c.font = HDR_FONT


def set_widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w


def main():
    wb = Workbook()

    # ---------- Overview ----------
    ws = wb.active
    ws.title = "Overview"
    lines = [
        ("Azure / DevOps Learning Tracker", ""),
        ("Active apps", "One shared React SPA + three small FastAPI APIs: Chat, Document Q&A, approval-gated Agent"),
        ("Active window", "Sep 26-27 2026, 16-hour accelerated sprint; destroy by Sep 27 20:00 IST"),
        ("Credit evidence", "INR 19,109.25 remaining; portal displays Sep 28 expiry; do not rely on Sep 28"),
        ("Sprint budget", "Expected <INR 500; hard cap INR 1,500; see 'GenAI Sprint' tab"),
        ("Golden rule", "A day is Done only when Destroyed? = Yes (except keep-listed items)"),
        ("Your role", "Portal clicks, az commands, terraform plan review + apply, verification"),
        ("Agent's job", "TF files + exact commands prepared before each session; docs updated"),
        ("Docs", "Start: AZURE_GENAI_BEGINNER_HANDBOOK.md/html/docx · 1) solution overview · 2) deployment guide · 3) journal"),
        ("Paused curriculum", "The original 28-day plan remains for later; VM and AKS stages are paused"),
        ("Cost tabs", "'GenAI Sprint' tracks the active blocks; legacy Day Cost Plan is retained; Cost Log records actuals"),
    ]
    for i, (a, b) in enumerate(lines, 1):
        ws.cell(row=i, column=1, value=a).font = Font(bold=True, size=14 if i == 1 else 10)
        cb = ws.cell(row=i, column=2, value=b)
        cb.alignment = WRAP
        cb.font = Font(size=10)
    set_widths(ws, [26, 100])

    # ---------- Accelerated GenAI Sprint ----------
    ws = wb.create_sheet("GenAI Sprint")
    header(ws, ["Block", "Sprint day", "Outcome", "Azure services", "Cost guardrail", "Status", "Evidence", "Destroyed?"])
    for r, (block, sprint_day, outcome, services, cost) in enumerate(SPRINT_BLOCKS, 2):
        vals = [block, sprint_day, outcome, services, cost, "Not started", "", ""]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = Font(size=10)
            cell.alignment = WRAP
    dv = DataValidation(type="list", formula1='"Not started,In progress,Done,Skipped,Blocked"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"F2:F{len(SPRINT_BLOCKS) + 1}")
    dv2 = DataValidation(type="list", formula1='"Yes,No,-"', allow_blank=True)
    ws.add_data_validation(dv2)
    dv2.add(f"H2:H{len(SPRINT_BLOCKS) + 1}")
    ws.cell(row=len(SPRINT_BLOCKS) + 3, column=1, value="Deadline").font = Font(bold=True)
    ws.cell(row=len(SPRINT_BLOCKS) + 3, column=2, value="Delete sprint RG and verify absence by Sep 27 20:00 IST")
    ws.cell(row=len(SPRINT_BLOCKS) + 4, column=1, value="Hard cap").font = Font(bold=True)
    ws.cell(row=len(SPRINT_BLOCKS) + 4, column=2, value="INR 1,500; stop before any unexpected paid tier")
    set_widths(ws, [7, 12, 44, 38, 18, 14, 30, 12])
    ws.freeze_panes = "C2"

    # ---------- Free Quotas ----------
    ws = wb.create_sheet("Free Quotas")
    header(ws, ["Category", "Service", "Period", "Included amount", "Sprint decision"])
    for r, values in enumerate(FREE_QUOTAS, 2):
        for c, v in enumerate(values, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = Font(size=10)
            cell.alignment = WRAP
    note_row = len(FREE_QUOTAS) + 3
    ws.cell(row=note_row, column=1, value="Important").font = Font(bold=True, color="C00000")
    ws.cell(row=note_row, column=2,
            value="Quotas reset monthly and do not roll over. Exact SKU and the subscription's "
                  "Cost Management > Free services grid are authoritative. PAYG overages bill the card.")
    ws.cell(row=note_row + 1, column=1, value="Official list").font = Font(bold=True)
    ws.cell(row=note_row + 1, column=2,
            value="https://azure.microsoft.com/en-us/pricing/free-services/")
    set_widths(ws, [16, 32, 18, 56, 28])
    ws.freeze_panes = "A2"

    # ---------- Daily Plan ----------
    ws = wb.create_sheet("Daily Plan")
    header(ws, ["Day", "Date", "Dow", "Phase", "Goal", "Azure services",
                "Portal steps", "CLI commands (key)", "Time", "Status", "Cost est. $", "Destroyed?", "Notes"])
    cost_by_day = {dc[0]: dc[4] for dc in DAY_COSTS}
    for r, (day, date, phase, goal, services, portal, cli, t) in enumerate(DAYS, 2):
        d = dt.date.fromisoformat(date)
        status, destroyed, notes = DAY_PROGRESS.get(day, ("Not started", "", ""))
        vals = [day, date, d.strftime("%a"), phase, goal, services, portal, cli, t,
                status, cost_by_day.get(day, ""), destroyed, notes]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = Font(size=10)
            cell.alignment = WRAP
    dv = DataValidation(type="list", formula1='"Not started,In progress,Done,Skipped"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"J2:J{len(DAYS) + 1}")
    dv2 = DataValidation(type="list", formula1='"Yes,No,-"', allow_blank=True)
    ws.add_data_validation(dv2)
    dv2.add(f"L2:L{len(DAYS) + 1}")
    set_widths(ws, [5, 11, 6, 12, 34, 24, 38, 38, 6, 12, 9, 11, 22])
    ws.freeze_panes = "E2"

    # ---------- Day Cost Plan ----------
    ws = wb.create_sheet("Day Cost Plan")
    header(ws, ["Day", "Date", "Services billed that day", "Meter / rate (approx list price)",
                "Usage", "Est. cost $", "Cumulative $", "Free-tier status"])
    date_of = {d0[0]: d0[1] for d0 in DAYS}
    cumulative = 0.0
    free_status = [
        ("static web apps", "Free tier (no charge)"),
        ("postgresql b1ms", "12-month free allowance covers it"),
        ("app insights", "Log ingestion is metered; keep volume tiny"),
        ("app configuration", "Free tier"),
        ("key vault", "Operations meter only — effectively free"),
        ("aks blade", "-"),
        ("aks evening", "Control plane free; you pay the node"),
        ("aks", "Control plane free; you pay the node"),
    ]
    for r, (day, services, meter, usage, cost) in enumerate(DAY_COSTS, 2):
        cumulative += cost
        note = next((txt for key, txt in free_status if key in meter.lower() or key in services.lower()), "")
        vals = [day, date_of.get(day, ""), services, meter, usage, cost, round(cumulative, 2), note]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = Font(size=10)
            cell.alignment = WRAP
    total_row = len(DAY_COSTS) + 2
    tc = ws.cell(row=total_row, column=7, value=round(cumulative, 2))
    tc.font = Font(bold=True, color="C00000")
    ws.cell(row=total_row, column=6, value="PLANNED TOTAL").font = Font(bold=True)
    ws.cell(row=total_row + 1, column=1,
            value="Without free-account allowances the same month would cost roughly $40-70 "
                  "(Postgres ~$12/mo + SWA Standard + App Insights + more VM/AKS hours).")
    set_widths(ws, [5, 12, 42, 38, 10, 11, 12, 34])
    ws.freeze_panes = "A2"

    # ---------- Deployments ----------
    ws = wb.create_sheet("Deployments")
    header(ws, ["#", "Deployment", "Azure services", "Day", "End-state plan", "Status", "Evidence link"])
    for r, (n, what, services, day, plan) in enumerate(DEPLOYMENTS, 2):
        status = "Done" if n == 1 else "Not started"
        evidence = "docs/LEARNING_JOURNAL.md#day-1--github-governance-azure-oidc-and-first-local-run" if n == 1 else ""
        for c, v in enumerate([n, what, services, day, plan, status, evidence], 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = Font(size=10)
            cell.alignment = WRAP
    set_widths(ws, [4, 44, 28, 10, 30, 12, 30])

    # ---------- Cost Log ----------
    ws = wb.create_sheet("Cost Log")
    header(ws, ["Date", "Resource group", "Service", "Est. cost $", "Actual cost $", "Destroyed?", "Notes"])
    first_day_cost = [
        "2026-08-31", "local (no Azure RG)", "GitHub/Entra setup + Docker Compose",
        0.00, 0.00, "Yes", "Local stack and pgdata volume removed; reusable $0 identity/config retained",
    ]
    for c, v in enumerate(first_day_cost, 1):
        ws.cell(row=2, column=c, value=v).alignment = WRAP
    ws.cell(row=40, column=4, value="TOTAL:").font = Font(bold=True)
    ws.cell(row=40, column=5, value="=SUM(D2:D39)").font = Font(bold=True)
    ws.cell(row=40, column=6, value="=SUM(E2:E39)").font = Font(bold=True)
    set_widths(ws, [12, 26, 26, 12, 12, 11, 30])

    # ---------- Destroy Ritual ----------
    ws = wb.create_sheet("Destroy Ritual")
    steps = [
        "1. SCREENSHOT dashboards first (portfolio evidence)",
        "2. az group list -o table   -- know exactly what exists",
        "3. az group delete -n learn-<stage>-<date> --yes --no-wait",
        "4. Terraform days: cd infra/<day> && terraform destroy  -- review: must list only today's resources",
        "5. az resource list -o table | grep <date>   -- no orphaned disks/NICs/IPs",
        "6. az consumption usage list --top 5 -o table   -- know today's cost",
        "7. Next morning: az group list   -- nothing unexpected alive",
    ]
    ws.cell(row=1, column=1, value="Run at the END of EVERY session. No exceptions.").font = Font(bold=True, size=12)
    for i, s in enumerate(steps, 3):
        ws.cell(row=i, column=1, value=s).font = Font(size=10)
    set_widths(ws, [110])

    wb.save("docs/Learning_Tracker.xlsx")
    print("saved docs/Learning_Tracker.xlsx")


if __name__ == "__main__":
    main()
