# Daily Playbook — exact steps for every day (Aug 31 → Sep 27)

Companion to [LEARNING_PLAN.md](LEARNING_PLAN.md) (the *why* and schedule) — this file
is the *how*: services, portal clicks, CLI commands, verification, and destruction
for each day. Dates assume start Mon Aug 31.

**Conventions used every day:**

```bash
# Run once at session start
az login
az account set --subscription <YOUR_SUBSCRIPTION_ID>   # find via: az account list -o table
az configure --defaults location=southindia            # your confirmed region
```

- **Resource group naming:** `learn-<stage>-<date>` (e.g. `learn-kv-0903`)
- **Destroy ritual (end of every session):** see §Destroy — the last command block below
- Where a day needs Terraform files, I will have committed them under `infra/<day>/`
  before the session; your job is: `terraform plan` → **read it** → `terraform apply`
- Time flags: ⏱90m / ⏱2h mean budget more than the usual hour that day

---

## Day 1 — Mon Aug 31 · GitHub setup (no Azure)
**Services:** GitHub only.
**Portal:** ① Branch protection: Settings → Branches → Add classic rule → pattern `main`
→ require status checks `backend-tests` + `frontend-build` (strict) + include admins.
② Packages (your profile → Packages → each package → settings): visibility → Public.
**Verify:** a new commit shows "checks required" on PRs; package pages show "public".
**Destroy:** nothing (no cloud resources).

## Day 2 — Tue Sep 1 · Azure CLI onboarding
**Services:** CLI only. Nothing deployed.
**Portal:** Sign in at portal.azure.com; note your Subscription ID (Subscriptions blade).
**CLI:**
```bash
az login                                    # opens browser
az account list -o table                    # confirm the right subscription
az account set --subscription <SUB_ID>
az group list -o table                      # see what exists (likely nothing new)
az provider register --namespace Microsoft.ContainerRegistry   # pre-warm providers
```
**Learn:** everything in Azure hangs off a **resource group**; note your subscription id
privately. **Destroy:** nothing created.

## Day 3 — Tue Sep 2 · Key Vault, manually in the portal
**Services:** Key Vault.
**Portal steps:** Create resource → Key Vault → RG `learn-kv-0902`, region South India →
RBAC authorization (not access policies) → create. Then Secrets → + Generate/Import →
name `LLM-PROVIDER`, value `fake`. Then your user: IAM → add role `Key Vault Secrets User`.
**CLI (the same thing, second pass):**
```bash
az keyvault create -g learn-kv-0902 -n kv-learn-0902 --enable-rbac-authorization
az role assignment create --role "Key Vault Secrets User" \
  --assignee $(az ad signed-in-user show --query id -o tsv) \
  --scope $(az keyvault show -g learn-kv-0902 -n kv-learn-0902 --query id -o tsv)
az keyvault secret set --vault-name kv-learn-0902 --name LLM-PROVIDER --value fake
az keyvault secret show --vault-name kv-learn-0902 --name LLM-PROVIDER --query value -o tsv
```
**Verify:** secret reads back `fake` in CLI *and* portal. **Destroy:** delete RG
(keep if you prefer — vaults cost ~nothing; your call, say it out loud either way).

## Day 4 — Thu Sep 4 · Terraform fundamentals ⏱90m
**Services:** Terraform state (local), Resource Groups.
**Portal:** nothing (this is the lesson: TF replaces the portal).
**CLI:** `az ad signed-in-user show --query id -o tsv` (note it), then:
```bash
mkdir -p infra/day4 && cd infra/day4
# files: main.tf (below), then:
terraform init
terraform plan -out=tfplan          # READ the plan: it should create exactly 1 RG
terraform apply tfplan
```
**Verify:** `az group list -o table` shows `learn-tf-0904`. Look at `terraform state list`.
**Destroy (learn state):** `terraform destroy` — read the plan shows 1 destroy.

## Day 5 — Fri Sep 5 · Terraform: Key Vault as code
**Services:** Key Vault via TF, GitHub secrets.
**CLI:** TF: `azurerm_resource_group` + `azurerm_key_vault` (RBAC) +
`azurerm_key_vault_secret` (`LLM-PROVIDER=fake`). `terraform plan` → read → apply.
Then: `az ad app create --display-name github-actions-e2e` + federated credential
(`repo:jnaveen-ds/Testing_end_to_end:ref:refs/heads/main`) + Contributor role on the
subscription (portal: App → IAM, or `az role assignment create`).
**Portal:** App registrations → verify the federated credential exists.
**GitHub:** Settings → Secrets → `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`.
**Destroy:** `terraform destroy` (keep the Entra app — it's free and reused all month).

## Day 6 — Sat Sep 6 · App reads secrets from Key Vault
**Services:** Key Vault + your app (local compose for now).
**Steps:** locally set `AZURE_KEY_VAULT_NAME`, run a small script (I'll provide
`backend/scripts/fetch_secrets.py`) that pulls `LLM-PROVIDER` from the vault into env
before `uvicorn` starts; verify `/health` reflects the vault value; then flip the secret
in the vault and watch it change on next run — config without redeploy.
**Destroy:** nothing cloud-side except test secrets you created.

## Day 7 — Sun Sep 7 · Buffer + cost review (30m)
`az consumption usage list --top 5 -o table`; portal → Cost Management. Confirm week
spend ≈ $0–1. Destroy any orphaned RGs: `az group list -o table`.

---

## Day 8 — Mon Sep 8 · Terraform: VM + networking ⏱90m
**Services:** VM, VNet, subnet, NSG, public IP, disk — all via TF under `infra/day8/`.
**CLI:** `terraform plan` (read: 1 VNet, 1 subnet, 1 NSG, 1 IP, 1 VM) → apply →
`ssh azureuser@<IP> "uname -a"`.
**Portal:** confirm every NSG rule you created exists and nothing more (least privilege).
**Destroy:** `terraform destroy` — yes, even tonight; rebuild tomorrow is 10 minutes.

## Day 9 — Tue Sep 8 · Deploy the app to the VM ⏱90m
**Services:** VM (TF from Day 8, redeployed) + docker compose on it.
**CLI:** recreate TF stack, then:
```bash
scp -r backend frontend docker-compose.yml azureuser@<IP>:~/app/
ssh azureuser@<IP> "curl -fsSL https://get.docker.com | sh && usermod -aG docker azureuser"
ssh -t azureuser@<IP> "cd ~/app && docker compose up -d --build"
curl http://<IP>:8080          # app live on the internet
```
**Portal:** open the VM blade — find boot diagnostics, serial log, and the cost estimate;
open NSG rules and prove 8080 is the only app port open.
**Verify:** RUNBOOK §2.6 trace against the public IP. **Keep tonight** (tomorrow needs
it — that's the one planned exception this week).

## Day 10 — Wed Sep 9 · TLS + custom domain (or honest alternative)
**Services:** nginx, certbot (Let's Encrypt if you have any domain; else self-signed +
explicit curl `-k` understanding).
**Verify:** `curl https://<domain-or-ip> -k` → app UI. **Destroy:** end of day or keep
one extra day max.

## Day 11 — Thu Sep 11 · CI/CD to the VM
**Services:** GitHub Actions deploy job + the VM.
**Steps:** add a deploy job (I'll write it) that SSHes (key stored as a repo secret,
never in git), pulls `ghcr.io/...:sha-<commit>`, restarts compose. Watch a PR deploy
itself. **Portal:** none. **Keep** the VM for tomorrow's chaos day, then destroy.

## Day 12 — Fri Sep 12 · Break it on purpose ⏱90m
Kill the worker mid-traffic, set a wrong env var, fill the disk (dd), kill docker
daemon — recover each using RUNBOOK §8. **Then destroy the whole RG.** Cost review.

## Day 13–14 · Weekend — buffer / catch-up. Nothing running.

---

## Day 15 — Mon Sep 15 · Container Apps environment ⏱90m
**Services:** Log Analytics, Container Apps environment, Managed Environment networking.
**CLI:** TF `azurerm_log_analytics_workspace` + `azurerm_container_managed_environment`
→ plan/apply/verify: `az containerapp env list -g ... -o table`. **Portal:** find the
environment; read its "Apps" tab (empty). Keep this env all week (~free while empty).

## Day 16 — Tue Sep 16 · Deploy the API to Container Apps
**Services:** Container Apps (Consumption), GHCR pull.
**CLI:** TF `azurerm_container_app` (image `ghcr.io/jnaveen-ds/feedback-analyzer-backend:latest`,
ingress external, target port 8000, env `DATABASE_URL`→sqlite placeholder first) →
`az containerapp show -g ... -n api -o table`; curl the FQDN `/health`.
**Portal:** the Container App blade — find Revisions, Log stream, Scale tab (look,
don't touch yet). **Destroy:** the app only (env stays for tomorrow).

## Day 17 — Wed Sep 17 · Worker app + scale-to-zero
**Services:** second Container App (worker), KEDA scale rule on `--min-replicas 0`.
**Verify:** scale tab shows 0 when idle; submit a job, watch it scale 0→1 in the
Log stream. This is scale-to-zero you can *see*. **Destroy:** both apps (env stays).

## Day 18 — Thu Sep 18 · Managed PostgreSQL + real wiring ⏱90m
**Services:** Azure Database for PostgreSQL Flexible (B1ms, free-tier size), Key Vault
secret for its connection string, app env var update.
**CLI:** TF `azurerm_postgresql_flexible_server` (B1ms) + firewall allow-Azure + secret
stored to Key Vault → update the Container App env from the vault → deploy both images →
RUNBOOK §2.6 against the public URL.
**Portal:** find the DB's "Server parameters", "Metrics", "Connection strings" blades.
**Keep the DB** (within free allowance) until Sep 26; destroy the apps.

## Day 18b/19 — Fri Sep 19 · Load test + watch autoscaling ⏱90m
**Services:** Container Apps scale rules, Log Analytics, (optional) Application Insights.
**CLI:** `apt install hey; hey -c 20 -z 2m https://<app-url>/health` while watching
`az containerapp replica list` / the Metrics blade. Note replica count over time.
**Destroy:** app but keep env+DB.

## Day 20 — Sat Sep 20 · Revisions, rollback, blue/green
**CLI:**
```bash
az containerapp revision list -g RG -n api -o table
# deploy an image tagged with a deliberate fake break, then:
az containerapp revision activate   / az containerapp ingress traffic set --revision-weight old=100
```
**Learn:** revisions are your rollback primitive; traffic-weight = blue/green.
**Destroy:** all app resources; keep only the DB.

## Day 21 — Sun Sep 21 · Buffer / rest / cost check. RG sweep: keep only Postgres.

---

## Day 22 — Mon Sep 22 · AKS evening ⏱2h (the only long day — or skip)
**Services:** AKS (free tier), kubectl.
**CLI:**
```bash
az aks create -g learn-aks-0922 -n learn-aks --node-count 1 \
  --node-vm-size Standard_B2s --generate-ssh-keys --tier free
az aks get-credentials -g learn-aks-0902 -n learn-aks
kubectl get nodes; kubectl apply -f k8s/   # I'll provide a minimal API+worker manifest
kubectl get pods -w
```
**Portal:** Workloads / Services / Logs tabs — see the same app in k8s terms.
**Destroy same night:** `az aks delete -g learn-aks-0902 -n learn-aks` + delete RG +
`az config` check. AKS left running is the #1 budget killer.

## Day 23 — Wed Sep 24 · App Configuration + feature flag
**Services:** App Configuration.
**CLI/TF:** `az appconfig create` + a `UI_SHOW_USAGE=true` flag; wire the frontend/API to
read it; flip the flag in the portal and watch the UI change without a deploy.
**Destroy:** appconfig (or keep — it's pennies).

## Day 24 — Thu Sep 24 · Failure day + monitoring
**Services:** Application Insights, Log Analytics queries, Azure Monitor alerts.
**CLI/portal:** enable App Insights on the API app; kill the DB; watch health probes +
retries; write an alert rule (failed-request rate); fix; note alert email.
**Destroy:** whatever was created.

## Day 25 — Fri Sep 26 · The full pipeline ⏱90m
**Deliverable:** PR → CI → publish → deploy to Container Apps → verify → rollback, all
via Actions (OIDC from Day 4, environment approval on GitHub). Green pipeline = the
goal of the whole month.

## Day 26 — Sat Sep 26 · FinOps sweep ⏱90m
`az group list -o table` → for every RG that isn't deliberately kept: `az group delete`.
Check Cost Management actuals vs plan. Confirm budget alerts fired at least once.

## Day 27 — Sat Sep 27 · Write-up
Before destroying the last RG: screenshots (App Insights, Container Apps revisions,
scale graphs, CI runs) → `docs/PORTFOLIO.md`. Then destroy everything. Total spent:
expect **$20–60 of $200**.

---

## THE DESTROY RITUAL (every session, no exceptions)

```bash
# 1. What exists?
az group list -o table
# 2. Destroy this session's RG (this deletes everything inside it — VMs, vaults, apps)
az group delete -n learn-<today>-<date> --yes --no-wait
# 3. Terraform-managed resources additionally:
cd infra/<day> && terraform destroy      # review the plan: should list exactly today's resources
# 4. Anything left? (disks, NICs, public IPs are RG members too — RG delete catches them)
az resource list -o table | grep -i <today>
# 5. Cost check
az consumption usage list --top 5 -o table
# 6. Screenshot the dashboards BEFORE step 1 (portfolio evidence)
```

Deletions are soft (recoverable ~48h) — but treat every destroy as final and check
`az group list` shows nothing unexpected the next day.
