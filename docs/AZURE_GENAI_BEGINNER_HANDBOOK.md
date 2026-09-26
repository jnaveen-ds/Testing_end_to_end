# Azure GenAI Deployment Handbook for Beginners

**Audience:** a learner with basic Python and LLM knowledge who has not deployed a
production-style application before.

**Companion formats:**
[visual HTML](AZURE_GENAI_BEGINNER_HANDBOOK.html) ·
[Word document](AZURE_GENAI_BEGINNER_HANDBOOK.docx)

This handbook explains the ideas before giving instructions. It does not assume that a
reader already knows words such as API gateway, cache, queue, managed identity, TTL,
revision, or orchestration. The purpose is not to memorize Azure product names. The
purpose is to understand a problem well enough to choose a suitable service, predict its
cost and failure modes, deploy it safely, and explain the decision to another person.

> **Current delivery status:** the existing Feedback Analyzer, local Docker stack, CI
> checks, and GHCR images are implemented. App 1 now has a working React Chat page,
> dedicated FastAPI entry point, fake/Azure provider seam, scoped cache key, TTL cache,
> Redis-compatible distributed lock, managed-identity model authentication path, and
> local tests. Its Azure resources are not yet deployed. Apps 2 and 3 remain planned.
> Local behavior must not be mistaken for a cloud deployment.

## 1. How to read and use this handbook

Read the handbook in this order:

1. Learn the basic vocabulary in §2.
2. Follow one request through the whole platform in §3.
3. Study App 1, App 2, and App 3 in §§4–6. Each solves a different problem.
4. Learn why the shared Azure services exist in §7.
5. Learn manual deployment, CI/CD, security, cost, and cleanup in §§8–12.
6. Use the detailed [app-by-app deployment guide](GENAI_DEPLOYMENT_GUIDE.md) while doing
   the practical work.

For each service, ask the same questions:

- What problem exists before this service is added?
- What exactly does the service do in our application?
- What happens when the normal path succeeds?
- What “no,” empty, timeout, duplicate, or failure path can occur?
- When is this service unnecessary or the wrong choice?
- How does it affect cost, latency, scaling, and security?
- How will we prove it works, and how will we remove it?

This question pattern is reusable. It applies to future deployments on Azure, AWS, or
another cloud even when the product names change.

## 2. Basic vocabulary, explained without assuming cloud experience

### 2.1 Frontend, backend, and API

The **frontend** is the page the user sees. In our project it is written with React and
TypeScript. It displays forms, loading indicators, results, and errors. Frontend code is
downloaded into the user's browser, so anything placed in that code can be inspected by
the user. For that reason, an Azure password, storage key, Redis key, or model credential
must never be placed in a React environment variable or JavaScript bundle.

The **backend** is code running on a server. In our project it is written with FastAPI.
The backend validates requests, checks authorization, calls Azure services, and decides
what response is safe to return. The browser does not need to know how Redis, Search,
Service Bus, or Cosmos DB work. It only needs a stable FastAPI contract.

An **API** is that contract. For example, `POST /chat` means “send a chat request,” while
`GET /runs/123` means “tell me the current state of run 123.” A contract specifies the
request fields, response fields, possible errors, and authentication requirements. This
separation lets the backend change its internal Azure services without forcing the user
interface to understand those changes.

### 2.2 Container and image

A **container image** is a packaged, read-only copy of the application, Python runtime,
and dependencies. It is similar to a sealed application installer. A **container** is a
running instance of that image. Azure Container Registry stores images; Azure Container
Apps runs containers. Storing an image does not mean an application is running, just as
keeping an installer file does not mean the program is open.

We tag images with the Git commit, such as `sha-abc123`, rather than deploying only a tag
called `latest`. An immutable tag lets us answer, “Which exact code is running?” and lets
us return to a known version when a deployment fails.

### 2.3 Model deployment and inference

An LLM is not copied into our FastAPI container. Azure hosts the selected model behind a
managed endpoint. A **model deployment** is a named configuration that makes a model
available with a quota and pricing mode. **Inference** is one request to that model.
Inference normally costs according to input and output tokens and usually takes much
longer than a cache lookup or database point read.

This distinction matters for cost. Creating a project in Microsoft Foundry may not be
the expensive action; repeatedly sending large prompts or selecting provisioned model
capacity can be expensive. We therefore limit prompt size, output tokens, request rate,
and test traffic.

### 2.4 Cache

A **cache** keeps a temporary copy of a result that is expensive to produce. Imagine a
restaurant keeping popular ingredients ready instead of preparing them from the beginning
for every identical order. In App 1, Redis can store a safe model answer for a short time.

A cache is not the source of truth. It may be deleted, unavailable, or contain an old
value. The application must know how to recompute a result. A cache key must include the
tenant or authorization scope, model, prompt version, and generation settings. Otherwise,
one user's private result could be returned to another user or an answer from an old
prompt could be mistaken for a current answer.

### 2.5 Queue

A **queue** is a waiting line for work. The API places a message in the line, workers take
messages when they have capacity, and the user checks status separately. A queue is useful
when work is slow, bursty, retryable, or limited by an external quota.

Multiple users do not automatically require a queue. If each request finishes quickly,
Container Apps can run more FastAPI replicas. A queue becomes useful when accepting work
quickly and processing it later is better than keeping every HTTP connection open.

### 2.6 Managed identity and RBAC

A **managed identity** is an Azure-provided identity for an application. Instead of saving
a permanent password in configuration, FastAPI asks Azure for a short-lived access token.
**Role-based access control (RBAC)** determines what that identity may do. For example,
the Chat API may read and write only its Redis data, while the RAG API may read one Blob
container and query one Search service.

“Contributor” is an infrastructure-management role and is usually too broad for an
application at runtime. Least privilege means granting the narrowest data role at the
narrowest resource scope that still permits the required operation.

### 2.7 HTTPS and TLS

HTTPS is HTTP protected by **TLS**. TLS encrypts traffic and uses a certificate to help
the client verify which server it reached. Azure-generated APIM, Container Apps, and
Static Web Apps hostnames have Microsoft-managed certificates. We do not copy certificate
files into the FastAPI image for this design.

TLS protects data while it travels, but it does not decide whether a user is allowed to
perform an action. Authentication, authorization, validation, and tenant isolation are
still required. “The page uses HTTPS” does not mean “the application is secure.”

### 2.8 TTL, timeout, and retention

**TTL** means time to live, but different TTLs solve different problems:

- Redis TTL controls how long a cached answer is considered reusable.
- Service Bus message TTL controls how long queued work remains meaningful before it is
  processed.
- An approval deadline controls how long a human may approve a proposed action.
- Cosmos item TTL controls how long an old status or lab record is retained.

A **timeout** limits how long an active operation may run. A queue-message TTL does not
safely stop code that has already started. A **lock duration** controls how long a worker
owns a message before another worker may receive it. These controls must not be treated as
interchangeable merely because they all involve time.

### 2.9 Revision and rollback

A Container Apps **revision** is an immutable version of an application configuration and
image. A new image or environment change creates a new revision. We test the new revision
and preserve the previous known-good revision until verification succeeds.

**Rollback** means returning traffic to the previous working revision. Rollback is not a
substitute for tests; it is the recovery path when tests cannot predict a real deployment
problem such as a missing role, wrong environment value, or incompatible dependency.

## 3. The complete platform, followed one step at a time

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ React website: Chat page · Document Q&A page · Agent page                 │
└─────────────────────────────────┬──────────────────────────────────────────┘
                                  │ HTTPS API request
                                  ▼
                         ┌──────────────────┐
                         │ API Management   │
                         │ TLS, routes,     │
                         │ limits, policy   │
                         └───┬──────┬───────┘
                             │      │
              ┌──────────────┘      └──────────────────┐
              ▼                                        ▼
      FastAPI services                         approval workflow
      on Container Apps                       and queued worker
              │                                        │
              ├─ Foundry models                        ├─ Service Bus
              ├─ Managed Redis                         └─ Cosmos DB
              ├─ Blob Storage
              └─ AI Search

Shared operations: ACR · managed identity/RBAC · Key Vault · App Insights · Logs
Shared delivery: GitHub PR checks → immutable image → OIDC login → revision → verification
```

### 3.1 What happens before the user clicks anything

The browser downloads the React website from Azure Static Web Apps. Static Web Apps sends
HTML, JavaScript, and CSS; it does not contain Azure service passwords. The only cloud
address the browser needs is the public APIM base URL.

Separately, backend images have already been built, stored in ACR, and deployed as
Container Apps. Each backend receives a managed identity and environment configuration.
The deployment process—not the user request—creates those running services.

### 3.2 What happens when a request enters APIM

The browser sends HTTPS to API Management. APIM first terminates the client TLS connection.
It then applies gateway rules such as route selection, a small rate limit, and correlation
ID. `/chat` is routed to Chat FastAPI, `/documents` to RAG FastAPI, and `/agent` to Agent
FastAPI.

APIM is not the business application. It should not contain the full chat, retrieval, or
approval logic. Its job is to provide a controlled front door. APIM sends another HTTPS
request to the selected backend, so traffic is encrypted on both network legs.

### 3.3 Why three APIs instead of one large process

The APIs use one reusable image to keep development simple, but Azure can run them as
separate services. Chat traffic can scale without consuming the worker capacity needed
for an agent. A broken RAG deployment can be rolled back without changing Chat. Each API
also receives only the permissions it needs.

For a tiny hobby application, one FastAPI process could be simpler. We separate the
runtimes here because independent scaling, failure isolation, and least-privilege identity
are exactly the deployment lessons we want to practise.

## 4. App 1 — Real-time Chat, explained from click to response

**Implementation checkpoint:** the local fake-provider version of this flow is now
implemented in `frontend/src/pages/ChatPage.tsx`, `backend/app/chat_api.py`,
`backend/app/chat.py`, and `backend/app/chat_cache.py`. The test suite proves MISS→HIT,
zero hit tokens, TTL expiry, cache-key boundaries, and one provider call for 20 concurrent
identical misses. The next checkpoint is manual Azure service creation and deployment.

### 4.1 The problem in ordinary language

A user writes a prompt and expects an answer within seconds. During a burst, many users
may send requests at once. Some may send exactly the same safe question. Calling the LLM
for every duplicate wastes tokens and makes users wait for work that has already been
done. We need a fast API, bounded scaling, temporary result reuse, trusted HTTPS, logs,
and a way to reverse a bad deployment.

### 4.2 The request flow

```text
User clicks Send
      │
      ▼
React validates text and calls POST /chat
      │
      ▼
APIM accepts HTTPS, applies route/rate policy, forwards over HTTPS
      │
      ▼
FastAPI validates size and authorization, then calculates a cache key
      │
      ▼
Redis lookup ── YES, value exists ──▶ return cached answer
      │
      NO
      ▼
acquire short distributed lock → call Foundry model → validate result
      │
      ▼
store successful safe result with TTL → return answer → React renders it
```

### 4.3 Step-by-step explanation

**Step 1 — React validates the obvious errors.** The page prevents an empty prompt and
shows a useful message before using network or model resources. This improves user
experience, but the backend repeats validation because browser validation can be bypassed.

**Step 2 — APIM controls the public entrance.** It can reject excessive traffic before
the request reaches the application. Rate limiting is useful protection against accidents
and basic abuse, but it must be sized for legitimate usage and is not a replacement for
authentication.

**Step 3 — FastAPI validates the real contract.** It checks request type, maximum length,
allowed model options, user/tenant scope, and output-token limit. An oversized prompt is
rejected rather than silently creating unexpected token cost.

**Step 4 — FastAPI constructs a cache key.** The key is a SHA-256 digest of normalized
input plus tenant scope, model deployment, prompt version, temperature, and output schema
version. A key based only on prompt text would be unsafe because two tenants might ask the
same text under different private context.

**Step 5 — Redis answers YES or NO.** “YES” means a non-expired value exists for the exact
key. FastAPI returns it, records `cache_status=HIT`, and reports zero new model tokens.
“NO” is not an error. It normally means this is the first request, the TTL expired, or a
model/prompt setting changed. FastAPI must compute a fresh result.

**Step 6 — A lock prevents a stampede.** Imagine twenty users submit the same uncached
prompt at the same moment. Without coordination, all twenty see NO and all twenty call the
model. A short Redis `SET NX` lock lets one request become the producer. Others wait briefly
and read the produced value. The lock itself needs an expiry so a crashed producer cannot
block the key forever.

**Step 7 — Foundry performs inference.** FastAPI obtains a short-lived identity token,
sends the bounded prompt, and waits within an application timeout. A transient throttling
response may receive a small bounded retry with jitter. Authentication errors, invalid
requests, and exhausted quota are not retried blindly.

**Step 8 — Only a valid success enters the cache.** Errors, partial streams, unsafe
outputs, and side-effecting tool results are not cached. The successful result is stored
with a 15-minute lab TTL. This duration is a learning choice, not a universal production
value.

**Step 9 — The response returns through APIM.** The response includes the answer,
correlation ID, latency, cache HIT/MISS, and usage fields safe for the user. Internal keys,
access tokens, raw prompts from other users, and exception traces remain server-side.

### 4.4 Why a YES path and NO path both matter

The YES path proves reuse: lower latency and no second model charge. The NO path proves
fresh computation. A correct system needs both. If the application treats every NO as an
error, a new prompt can never work. If it treats every similar prompt as YES, it may return
incorrect or unauthorized data.

A cache should be skipped when requests are nearly always unique, when results must always
reflect immediate data, when the answer contains user-specific secrets that cannot be
scoped safely, or when the cache's provisioned cost is greater than the model work it
saves. For this short lab, Managed Redis is created only after checking its estimate and
is deleted immediately after the cache exercise. Local Redis remains the fallback.

### 4.5 Multiple users: replicas first, queue only when needed

FastAPI requests that complete in seconds can be handled by multiple Container Apps
replicas. Azure observes HTTP demand and creates replicas up to a configured maximum.
Maximum replicas protect cost and downstream model quota. Minimum zero avoids idle compute
but creates cold-start latency for the first request after inactivity.

Adding a queue to synchronous chat would change the product contract: instead of receiving
an answer in one request, the user would receive a job ID and poll. That extra complexity
is justified for long work, not merely because twenty users exist. App 3 demonstrates the
case where a queue is appropriate.

### 4.6 Failures we deliberately test

- Redis unavailable: treat it as a bounded cache miss and call the model only if rate and
  cost controls permit; do not pretend a cache failure is a model answer.
- Model throttled: retry a small number of transient failures with backoff; return a clear
  temporary error when the limit is reached.
- Twenty identical misses: one model call should occur, proving stampede protection.
- Wrong environment value: readiness or smoke test fails; logs identify the configuration;
  traffic returns to the previous revision.
- Expired TTL: next request is a MISS and recomputes; this is expected freshness behavior.

## 5. App 2 — Document Q&A, including the “answer not found” path

### 5.1 Why an ordinary chat model is not enough

An LLM may not know a company's private documents, and its training knowledge may be old.
Asking it to answer anyway can produce fluent but unsupported text. Retrieval-augmented
generation, or RAG, first retrieves relevant source text and then asks the model to answer
from that evidence.

RAG does not guarantee truth. It can retrieve the wrong chunk or fail to retrieve a right
one. We therefore inspect retrieval separately, preserve source metadata, test known and
unknown questions, and instruct the model to refuse when evidence is insufficient.

### 5.2 Ingestion flow: how documents become searchable

```text
Content owner uploads a harmless file through React
      ▼
FastAPI validates identity, file type, and size
      ▼
private Blob Storage keeps the original source
      ▼
backend extracts text → splits it into overlapping chunks
      ▼
embedding model converts each chunk into a vector
      ▼
AI Search stores chunk text + vector + source/title/position + access metadata
```

The Blob object is the durable source of truth. AI Search is a serving index that can be
rebuilt. A **chunk** is a smaller passage because sending every document with every
question would be slow and token-expensive. Some overlap prevents an important sentence
at a boundary from losing its surrounding context.

An **embedding** is a numeric representation used to compare meaning. The vector does not
replace the source text. The Search record keeps both the vector and source metadata so
the final citation can be taken from controlled metadata rather than invented by the LLM.

Files remain private. React uploads through FastAPI; it does not receive a permanent Blob
key. FastAPI checks content type and size, but production systems also need malware
scanning and document-level authorization.

### 5.3 Question flow: known answer and unknown answer

```text
User asks a question
      ▼
FastAPI validates question and user scope
      ▼
AI Search applies access filters and returns top relevant chunks
      │
      ├─ NO useful evidence ─▶ “The supplied documents do not contain the answer”
      │
      └─ useful evidence exists
                 ▼
        FastAPI builds a bounded prompt with those chunks
                 ▼
        Foundry generates an answer constrained to evidence
                 ▼
        FastAPI returns answer + citations from stored metadata
```

The NO-evidence path can happen because the documents truly do not contain the answer,
the wording differs too much, chunking lost useful context, access filters correctly hide
the document, or indexing failed. These causes require different responses. The user gets
an honest refusal, while operators use retrieval logs and Search Explorer to diagnose why.

The YES-evidence path still requires evaluation. A chunk can contain matching words but
not answer the question. We test retrieval relevance separately from answer quality. We
start with lexical search because it is easier to inspect, then add vector retrieval for
semantic similarity.

### 5.4 Cost, latency, and security reasoning

Indexing pays the embedding cost once per chunk rather than on every question. At query
time, Search adds a network hop but usually reduces model tokens by sending only top
chunks. Increasing top-k can improve recall but also adds irrelevant text, model latency,
and token cost. The correct number is measured with an evaluation set, not guessed.

Search filters must include tenant/document access rules. “The chunk exists in the index”
does not mean “every user may see it.” Prompt-injection text inside a document is treated
as untrusted data, not as system instructions. Content Safety can moderate input/output,
but it does not replace authorization or grounding evaluation.

### 5.5 Failures we deliberately test

- Ask a known question and verify the cited title/chunk actually supports the answer.
- Ask an unknown question and verify the system refuses instead of inventing a citation.
- Remove or misconfigure an index document and observe retrieval diagnostics.
- Make Search unavailable and verify FastAPI returns a dependency error, not an ungrounded
  model answer presented as RAG.
- Inspect the browser bundle/network panel and prove no Blob or Search credential exists.

## 6. App 3 — Long-running agent with human approval

### 6.1 Why holding one HTTP request open is the wrong design

An agent may plan, wait for a human, call slow tools, retry, or continue for minutes. A
normal web request can time out, a container can restart, and a human may answer hours
later. Keeping a FastAPI process waiting wastes capacity and loses state after restart.

Instead, FastAPI accepts the task quickly and returns HTTP `202 Accepted`. This means “the
request was accepted for processing,” not “the work is finished.” The response contains
a run ID and status URL. React polls that status only while the run is non-terminal.

### 6.2 Detailed state flow

```text
POST /runs
   ▼
planning → awaiting_approval
                 │
                 ├─ YES, approved before deadline ─▶ queued → running → completed
                 │
                 ├─ NO, explicitly rejected ───────▶ rejected; execute nothing
                 │
                 └─ NO response before deadline ──▶ expired; execute nothing

running ─ transient failure ─▶ retry safely
running ─ repeated/poison failure ─▶ failed or dead-lettered for inspection
```

### 6.3 What each stage means

**Planning:** the system creates a proposed plan but does not execute side effects. It
stores an immutable hash of the exact plan. This prevents an approval for “send a draft
email” from being reused after the plan silently changes to “delete a record.”

**Awaiting approval:** Durable Functions checkpoints workflow state and waits for either
an external approval event or a durable timer. No FastAPI request and no dedicated worker
needs to remain open. If the Function host restarts, the orchestration can reconstruct its
state from checkpoints.

**YES — approved:** FastAPI verifies the approver, run state, deadline, and expected plan
hash. A conditional transition changes only `awaiting_approval` to `queued`. The approved
command is sent to Service Bus. Repeated clicks return the existing decision rather than
enqueueing duplicate side effects.

**NO — rejected:** rejection is a valid business outcome, not a system error. The run
records approver, time, decision, and plan hash, becomes terminal, and no command enters
the queue.

**NO RESPONSE — expired:** a durable timer wins the race when no decision arrives within
ten lab minutes. A late approval is rejected because old screens must not authorize work
indefinitely. Expiry differs from rejection: rejection is a human decision; expiry means
the decision window ended.

**Queued and running:** Service Bus absorbs bursts so FastAPI can accept requests without
starting unlimited model/tool calls. Workers use controlled concurrency. Queue depth shows
how much work is waiting and can become an autoscaling signal.

**Completed or failed:** successful output and audit state are written to Cosmos DB. A
transient dependency failure may be retried. A poison message that repeatedly fails moves
to the dead-letter queue instead of looping forever.

### 6.4 Why idempotency is essential

Message systems normally provide at-least-once delivery: under failure, a worker may see
the same message again. A user may also double-click Approve. Therefore each action needs
an idempotency key and a state check. “Charge invoice 123” must either happen once or
detect that it already happened. Relying only on the queue lock is unsafe because locks
can expire while slow work is still running.

For side effects that cannot be made naturally idempotent, use a durable operation record,
conditional write, or provider idempotency key before calling the external tool. Retrying
without this design can repeat emails, payments, or destructive actions.

### 6.5 How the time controls differ in this app

- The approval timer answers, “How long may a person decide?”
- Message TTL answers, “How long may approved work wait before it is no longer useful?”
- Lock duration/renewal answers, “How long does this worker own the message?”
- Worker timeout answers, “How long may this attempt actively run?”
- Cosmos item TTL answers, “How long should old lab records remain?”

Setting all five to the same number would not make the design simpler; it would mix
different business and technical meanings. In production, each value is chosen from user
expectations, dependency latency, retry policy, legal retention, and recovery needs.

### 6.6 Failures we deliberately test

- Approve one run, reject one, and let one expire; only the approved run executes.
- Submit a duplicate approval and prove no duplicate queue message or action occurs.
- Submit an approval with the wrong plan hash and prove it is rejected.
- Stop the worker, observe queue depth grow, restart it, and observe controlled draining.
- Force a transient failure and prove a retry succeeds without repeating side effects.
- Force repeated failure, inspect the DLQ, repair the cause, and replay deliberately.

## 7. Why each shared Azure service exists

### 7.1 Resource Group — the lifecycle boundary

A Resource Group is a logical container for Azure resources that share a lifecycle. Our
website, APIs, registry, gateway, logs, and data services are tagged and grouped so they
can be listed, cost-filtered, permission-scoped, and deleted together.

AWS does not have one exact mandatory equivalent. The idea resembles using one
CloudFormation stack plus consistent tags and IAM scope. A Resource Group does not isolate
network traffic and does not automatically make every contained resource secure. Its main
value here is ownership and cleanup.

Use a shared group when resources are created and destroyed together. Use separate groups
when teams, permissions, billing ownership, or lifecycles differ. Deleting the learning
group is our final proof that hourly resources are not forgotten.

### 7.2 Azure Container Registry and Container Apps

ACR stores private images. Container Apps pulls an exact image and runs it with HTTPS,
revisions, logs, managed identity, and autoscaling. This is the closest practical Azure
exercise to an ECS/Fargate HTTP service: we manage the container configuration, not
Kubernetes nodes.

Container Instances is simpler for “run this raw container,” while Container Apps Jobs is
better for scheduled or one-off tasks. AKS is appropriate when Kubernetes-level control
and ecosystem features justify operating clusters. None is universally superior; the
workload and operational responsibility determine the choice.

Scale-to-zero reduces idle compute cost but adds cold-start latency. A production API with
strict latency requirements may keep one warm replica and accept the cost. Maximum
replicas prevent a burst from creating unbounded compute or overwhelming model quota.

### 7.3 API Management

APIM creates one public API front door even when several backends exist. It owns stable
routes, TLS termination, rate limits, and gateway policy. The React application does not
need a different base URL for every backend.

For a small private API, direct Container Apps ingress may be cheaper and simpler. APIM is
useful when central policy, multiple consumers, versioning, or independent backend routes
justify another network hop. It can add latency and must not become a place where all
business logic is hidden in difficult gateway policies.

### 7.4 Key Vault versus managed identity

Managed identity is preferred for Azure-to-Azure access because there is no stored secret
to rotate. Key Vault stores secrets that still must exist, such as a third-party API key.
Key Vault does not magically remove secrets; it controls access, auditing, and rotation.

An application identity receives permission to read only the required secret. The secret
value is never printed in CI output or placed in React. Configuration that is not secret,
such as a deployment name or timeout, remains an environment variable rather than being
put into Key Vault merely because the service exists.

### 7.5 Application Insights and Log Analytics

Observability answers what happened after deployment. We record correlation IDs, request
duration, dependency duration, cache status, token counts, queue depth, state transitions,
and failures. These signals let us separate “the model is slow” from “the queue is waiting”
or “the cache is unavailable.”

Logs are metered by ingestion and retention. More logs are not always better. Prompt and
document content can contain private data, so we log metadata and redacted diagnostics,
not credentials or complete user content. Sampling and retention limits control cost.

### 7.6 Static Web Apps

Static Web Apps hosts the built React files and provides a trusted HTTPS hostname. It is a
good fit because React runs in the browser and does not require a Node server after build.
If the website later requires server-side rendering, long-lived server logic, or special
runtime control, a container-based frontend may be more appropriate.

All `VITE_*` build values are public. The APIM URL may be public; a service credential may
not. This is a security property of browser applications, not an Azure-specific rule.

## 8. Manual first, then automation

We create and inspect each service manually once because the portal shows available SKUs,
regional limitations, identity options, networking defaults, and estimated cost. The goal
is not to become dependent on clicking. The goal is to understand the resource we later
automate.

After manual verification, we inspect the resource with Azure CLI. CLI output exposes the
actual resource name, ID, SKU, identity, endpoint, and configuration. Finally, Terraform
or a deployment workflow makes creation reproducible. If automation fails, manual
experience helps identify whether the problem is code, permissions, region, quota, or
service configuration.

For every resource, follow this learning loop:

1. State the problem and expected behavior before opening the portal.
2. Check eligibility, region, quota, and estimated cost.
3. Create the smallest suitable configuration manually.
4. Inspect it in the portal and CLI; write down what each important setting means.
5. Connect one application path and verify a real result.
6. Cause one controlled failure and recover.
7. Repeat through automation using the same understood settings.
8. Capture non-sensitive evidence and delete the resource.

## 9. CI/CD explained as a story, not only YAML keywords

### 9.1 Continuous Integration (CI)

A developer creates a feature branch and pull request. GitHub starts two required jobs:
`backend-tests` installs Python dependencies and runs tests with the fake provider;
`frontend-build` installs exact npm lockfile dependencies, type-checks TypeScript, and
builds React.

The fake provider matters because CI must be deterministic, fast, and free from Azure
availability and token charges. A passing CI run means the tested code met those checks;
it does not prove that Azure roles, quota, or networking are correct. Cloud smoke tests
belong after deployment in a controlled environment.

Branch protection waits for both exact job names and requires the feature branch to be up
to date. If a job is renamed in YAML but the branch rule still expects the old name, the
pull request can remain blocked forever. This is why workflow names are part of the
delivery contract.

### 9.2 Packaging

After protected code reaches `main`, the publish workflow builds container images and
stores them in a registry. The image receives an immutable commit tag. Building once and
promoting the same image avoids the risk that staging and production were built from
slightly different dependencies.

`latest` is convenient for humans but ambiguous for rollback. The deployment records the
exact SHA tag and resulting revision. If verification fails, we know both the failed and
previous versions.

### 9.3 Secretless Azure login with OIDC

GitHub requests a short-lived identity token for the workflow. Azure trusts only the
configured repository, branch, and audience through a federated credential. The workflow
exchanges that token with Azure and receives temporary access according to its service
principal roles.

There is no `AZURE_CLIENT_SECRET`. Repository values for client, tenant, and subscription
IDs identify where to log in; the federated trust and short-lived token prove identity.
OIDC reduces secret rotation and leakage risk, but the Azure role must still be narrow.

### 9.4 Deployment and verification

CD updates Container Apps with the immutable image, creating a new revision. It waits for
liveness and readiness, then runs one tiny scenario per app. A healthy process is not
enough: Chat must answer, RAG must cite known evidence, and Agent must create a run without
executing before approval.

Only after smoke tests pass should traffic remain on the new revision. On failure, the
workflow stops and preserves or restores the prior revision. Deployment approval in
GitHub authorizes releasing code; it is different from the Agent application's human
approval, which authorizes one runtime plan.

## 10. Choosing a deployment strategy

**Recreate** stops the old instance and starts the new one. It is cheap and acceptable for
a disposable lab, but it creates downtime and offers a weaker rollback window.

**Rolling update** gradually replaces replicas. It keeps service available but old and
new versions coexist. API and database changes must remain compatible during that period.

**Container Apps revisions** are our default. We create an immutable revision, verify it,
and keep the previous known-good revision until confidence is established. This provides
fast rollback without building a duplicate data platform.

**Blue-green** runs two complete application versions and switches traffic. It reduces
cutover downtime but temporarily doubles application capacity and can accidentally run
side effects from both environments.

**Canary** sends a small traffic percentage to the new revision. It is useful when real
traffic is needed to reveal risk, but it requires strong metrics and stop conditions. For
LLMs it can also duplicate evaluation/token cost.

Choose a strategy from acceptable downtime, rollback speed, backward compatibility,
side-effect risk, monitoring quality, and temporary cost—not because one strategy sounds
more advanced.

## 11. Cost, latency, and security: how to reason instead of memorize

### 11.1 Cost

First identify the meter. Model inference meters tokens. Redis generally meters
provisioned capacity over time. Container Apps meters compute and requests. Blob meters
stored data, operations, and egress. Search paid SKUs may meter provisioned service time.
Logs meter ingestion and retention.

A “free tier” is a usage allowance with conditions, not a guarantee that every related
SKU is free. The subscription's **Cost Management + Billing → Free services** grid and the
portal estimate at creation time are authoritative. Budgets send alerts but do not stop
resources or charges.

The lab target is under ₹500 with a hard learning stop at ₹1,500. Azure Managed Redis and
model tokens are treated as paid. Redis exists for one short block only. Everything is
deleted by September 27 at 8:00 PM IST, regardless of a later PAYG conversion.

### 11.2 Latency

Break total time into parts: browser-to-APIM network time, gateway policy, FastAPI work,
cache lookup, Search query, model inference, queue wait, worker execution, and response
travel. The slowest part differs by app.

Chat aims for one synchronous response, so cold start and model latency are visible to the
user. A Redis hit can remove most model latency. RAG adds retrieval but can reduce prompt
size. Agent work intentionally adds queue wait and human wait; its API latency stays low
because it returns `202` rather than pretending the whole task is synchronous.

### 11.3 Security

Draw trust boundaries. The browser is untrusted and receives no service credential. APIM
is the public gateway. FastAPI validates the user and business contract. Managed identity
authenticates FastAPI to Azure services. Each data service remains private or permissioned
as far as the lab configuration permits.

Security questions include: Can one tenant read another tenant's cache or Search result?
Can a late or duplicate approval execute work? Can a pull request obtain production
credentials? Are prompts or documents copied into broad logs? Does the worker have more
roles than its task requires? TLS is one answer in this larger model, not the entire model.

## 12. Destruction is part of deployment

Cloud resources continue to exist after a learning session unless they are explicitly
removed. Closing the browser, stopping a local container, or deleting source code does not
delete Azure services. A forgotten provisioned cache, gateway, database, or VM can keep
billing.

Before deletion, record non-sensitive evidence, actual cost, and the resource list. Delete
Managed Redis as soon as its exercise ends. At final cleanup, delete the sprint Resource
Group, wait until `az group exists` reports `false`, list subscription resources, and check
service-specific lists for anything accidentally created outside the group.

Soft-deleted resources may remain recoverable after billing resources are removed. Do not
purge them merely for tidiness because purge is irreversible. Confirm whether name reuse
or policy actually requires it.

## 13. What “complete” means for each application

App 1 is complete when the learner can explain and demonstrate request validation, cache
MISS and HIT, key scoping, TTL expiry, stampede prevention, autoscaling bounds, HTTPS,
logs, a failed revision, rollback, actual cost, and Redis deletion.

App 2 is complete when the learner can explain and demonstrate private source storage,
chunking, embeddings, lexical and vector retrieval, metadata citations, known and unknown
questions, tenant filtering, a Search failure, token/latency observations, and cleanup.

App 3 is complete when the learner can explain and demonstrate `202` plus status polling,
checkpointed planning, approval YES, rejection NO, no-response expiry, plan-hash binding,
queue bursts, controlled worker concurrency, safe retry, dead-letter inspection/replay,
idempotency, record TTL, and cleanup.

The project is complete only when CI checks, immutable packaging, OIDC deployment, smoke
verification, revision rollback, cost evidence, and verified resource deletion have also
been performed. Creating resources or seeing a green portal notification alone is not
completion.

## 14. Teach-back questions

If a learner can answer these in their own words, they understand the architecture rather
than only following commands:

1. Why can React safely know the APIM URL but not a Redis or Storage key?
2. Why is a cache MISS normal, and why must tenant and prompt version be in the key?
3. Why do twenty short users need replicas, while long approved jobs benefit from a queue?
4. Why does RAG need a “not found in supplied documents” path?
5. Why are Blob and AI Search not both systems of record?
6. Why does the Agent return `202` rather than keep the request open?
7. What is the difference between rejection, approval timeout, message TTL, lock expiry,
   worker timeout, and record retention?
8. Why must approval bind to an immutable plan hash?
9. Why can the same Service Bus message be processed more than once, and how does
   idempotency prevent duplicate side effects?
10. Why does passing CI not prove the Azure deployment is healthy?
11. Why is an immutable image tag necessary for rollback?
12. Why is destroying the Resource Group part of the deployment exercise?

## 15. Where the exact practical steps live

- [GENAI_SOLUTION_OVERVIEW.md](GENAI_SOLUTION_OVERVIEW.md): concise architecture and
  engineering decision reference.
- [GENAI_DEPLOYMENT_GUIDE.md](GENAI_DEPLOYMENT_GUIDE.md): app-by-app portal paths, CLI,
  local development contracts, CI/CD design, failure drills, and destruction commands.
- [LEARNING_JOURNAL.md](LEARNING_JOURNAL.md): actual actions, incidents, evidence, cost,
  and destroyed state as work is performed.
- [Learning_Tracker.xlsx](Learning_Tracker.xlsx): block status, service eligibility,
  deployment evidence, actual cost, and cleanup confirmation.

The Markdown file is the editable source for this handbook. Run
`python scripts/make_beginner_handbook.py` after changing it to regenerate the HTML and
Word versions. Markdown, HTML, and Word must always describe the same architecture and
status.
