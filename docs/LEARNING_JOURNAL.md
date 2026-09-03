# Azure DevOps Learning Journal

This is the day-by-day record of the work actually performed. It complements:

- [LEARNING_JOURNAL.html](LEARNING_JOURNAL.html): responsive visual/infographic view
- [LEARNING_PLAN.md](LEARNING_PLAN.md): schedule, goals, and budget
- [DAILY_PLAYBOOK.md](DAILY_PLAYBOOK.md): planned portal and CLI instructions
- [Learning_Tracker.xlsx](Learning_Tracker.xlsx): progress and cost tracker
- [RUNBOOK.md](RUNBOOK.md): application verification and troubleshooting

Update this journal at the end of every session with the exact portal path, commands,
verification evidence, actual cost, cleanup result, and any correction to the plan.
A day is complete only after its verification and destroy checklist passes.

> **Synchronization rule:** every confirmed step and daily update must change both this
> Markdown source and `LEARNING_JOURNAL.html` in the same change. Neither version may be
> updated alone.

## Progress

| Day | Topic | Status | Planned cost | Actual cost | Cleanup |
|---|---|---|---:|---:|---|
| 1 | GitHub governance, GHCR, Azure OIDC, local Compose | In progress | $0 | $0 so far | Pending local Compose cleanup |

## Day 1 — GitHub governance, Azure OIDC, and first local run

**Date:** 2026-08-31  
**Services:** GitHub repository, GitHub Actions, GHCR, Microsoft Entra ID, Azure RBAC,
and local Docker Compose  
**Goal:** Protect `main`, make deployment images publicly pullable, establish
passwordless GitHub-to-Azure authentication, and verify the five-container application.  
**Cost:** $0. GitHub public-repository features, GHCR public images, Entra app
registrations, federated credentials, and local containers do not consume the Azure
$200 credit.

### 1. Make the repository public — completed

GitHub path:

1. Repository **Settings → General**.
2. Scroll to **Danger Zone → Change repository visibility**.
3. Change visibility to **Public** and confirm the repository name.

Verified repository: `jnaveen-ds/Testing_end_to_end`; default branch: `main`.

Why this was necessary: GitHub Free does not enforce classic branch protection or
repository rulesets on a private repository. A public repository can use branch
protection for free. Public visibility also means the code, Git history, Actions logs,
issues, and pull requests are visible to everyone. Never commit `.env` files, cloud
credentials, private keys, or tokens. A scan of the current checkout found no obvious
tracked `.env`, private-key, or token files; GitHub secret scanning should remain enabled.

### 2. Protect `main` — completed

GitHub path: repository **Settings → Branches → Add classic branch protection rule**.

Configuration:

- Branch name pattern: `main`
- Require a pull request before merging
- Require status checks to pass before merging
- Require branches to be up to date before merging
- Required checks: `backend-tests` and `frontend-build` (names and case must match
  `.github/workflows/ci.yml`)
- Do not allow bypassing the above settings / include administrators
- No required approving review: the repository currently has one maintainer, who cannot
  approve their own pull request

Result: changes should go through a branch and pull request; failing or missing CI checks
block the merge to `main`.

**First-PR lesson:** PR
[#1](https://github.com/jnaveen-ds/Testing_end_to_end/pull/1) initially showed
“Review required” even though both CI checks passed. The branch rule accidentally required
one approving review, but GitHub does not allow an author to approve their own PR. For
this single-maintainer learning repository, **Require a pull request** remains enabled
while **Require approvals** is disabled (zero required approvals). After that correction,
PR #1 merged successfully with both required checks passing. In a team repository, keep
at least one independent approval instead.

### 3. Make GHCR packages public — completed and verified

Package settings:

- `https://github.com/users/jnaveen-ds/packages/container/feedback-analyzer-backend/settings`
- `https://github.com/users/jnaveen-ds/packages/container/feedback-analyzer-frontend/settings`

For each package: **Danger Zone → Change package visibility → Public**.

Anonymous token and `latest` manifest requests returned HTTP 200 for both:

- `ghcr.io/jnaveen-ds/feedback-analyzer-backend:latest`
- `ghcr.io/jnaveen-ds/feedback-analyzer-frontend:latest`

Public repository visibility does not automatically guarantee public package visibility;
the two package settings must be checked independently.

### 4. Register the GitHub Actions application in Entra — app created

Azure Portal path: **Microsoft Entra ID → App registrations → New registration**.

Configuration:

- Name: `github-actions-testing-e2e`
- Supported account type: **Single tenant only — Default Directory**
- Redirect URI: blank (GitHub OIDC does not use an application redirect URI)

Do not create a client secret. OIDC uses a short-lived token issued for each workflow run,
so there is no long-lived GitHub-to-Azure password to store or rotate.

### 5. Add the immutable GitHub federated credential — in progress

Azure Portal path: app registration **Certificates & secrets → Federated credentials →
Add credential → GitHub Actions deploying Azure resources**.

Configuration:

| Field | Value |
|---|---|
| Issuer | `https://token.actions.githubusercontent.com` |
| Organization/owner | `jnaveen-ds` |
| Organization/owner ID | `185759864` |
| Repository | `Testing_end_to_end` |
| Repository ID | `1350370641` |
| Entity type | Branch |
| Branch | `main` |
| Credential name | `github-main` |
| Audience | `api://AzureADTokenExchange` |

Expected immutable subject:

```text
repo:jnaveen-ds@185759864/Testing_end_to_end@1350370641:ref:refs/heads/main
```

GitHub owner and repository IDs are public, permanent identifiers—not secrets. They were
verified from GitHub's REST API:

```bash
gh api users/jnaveen-ds --jq '{login, id}'
gh api repos/jnaveen-ds/Testing_end_to_end \
  --jq '{full_name, id, owner_id: .owner.id}'
```

Equivalent browser endpoints:

- `https://api.github.com/users/jnaveen-ds`
- `https://api.github.com/repos/jnaveen-ds/Testing_end_to_end`

Azure labels the first value “Organization ID”; for a personally owned repository, it is
the GitHub **owner ID**. New GitHub repositories use the immutable subject format so a
rename, transfer, or recycled repository name cannot silently expand the credential's
trust boundary.

### 6. Grant Contributor access — not started

Azure Portal path: **Subscriptions → select the learning subscription → Access control
(IAM) → Add → Add role assignment**.

1. Select the **Contributor** role.
2. Select **User, group, or service principal**.
3. Choose `github-actions-testing-e2e`.
4. Review and assign.

Contributor lets the workflow create and manage learning resources but cannot grant
Azure roles to other identities. Subscription scope is used because later exercises must
create their own resource groups. This assignment costs $0 and remains in place during
the learning plan.

### 7. Add GitHub Actions configuration — not started

GitHub path: repository **Settings → Secrets and variables → Actions → New repository
secret**.

Create:

| Secret | Azure source |
|---|---|
| `AZURE_CLIENT_ID` | App registration: Application (client) ID |
| `AZURE_TENANT_ID` | App registration: Directory (tenant) ID |
| `AZURE_SUBSCRIPTION_ID` | Subscription: Subscription ID |

Do not record the values in this journal, commit them, or paste them into chat. No
`AZURE_CLIENT_SECRET` is needed.

### 8. Run and verify the local application — not started

On the learner's computer:

```bash
git clone https://github.com/jnaveen-ds/Testing_end_to_end
cd Testing_end_to_end
docker compose version
docker compose up --build -d
docker compose ps
```

Expected running services: `db`, `redis`, `api`, `worker`, and `frontend`.

Verify the API and SPA:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/stats
curl -I http://localhost:8080
docker compose logs --tail=30 worker
```

Open `http://localhost:8080`, submit feedback, confirm `pending → completed`, and inspect
the task execution:

```bash
docker compose logs --tail=100 worker
```

### Day 1 destroy and retention checklist

Delete the local containers, network, and test database volume:

```bash
docker compose down -v
docker compose ps
```

`docker compose ps` should show no running project services.

Keep these intentional $0 resources because later days reuse them:

- Entra app registration `github-actions-testing-e2e`
- GitHub federated credential `github-main`
- Contributor role assignment
- GitHub Actions repository configuration
- Public GHCR images

### Day 1 completion checklist

- [x] Repository is public
- [x] `main` requires a PR, an up-to-date branch, `backend-tests`, and
  `frontend-build`, with no administrator bypass
- [x] Backend and frontend GHCR packages are public and anonymously pullable
- [x] Entra application registration is created
- [ ] Immutable federated credential is added
- [ ] Contributor role is assigned
- [ ] Three GitHub Actions secrets are added
- [ ] Local five-container flow passes
- [ ] Local Compose resources and volume are destroyed
- [ ] Excel Day 1 row is marked `Done`, cost `$0`, and `Destroyed? = Yes`

## Daily update template

Copy this section for each new day:

```markdown
## Day N — Topic

**Date:** YYYY-MM-DD
**Services:**
**Goal:**
**Planned/actual cost:**

### Manual portal steps
### CLI steps
### What each command/resource does
### Verification evidence
### Problems, corrections, and lessons
### Destroy checklist
### Completion checklist
```
