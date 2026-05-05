# Feature Research

**Domain:** AI Production Pipeline Review/Governance Platform
**Researched:** 2026-05-05
**Confidence:** MEDIUM-HIGH (based on direct analysis of Cordum, Temporal, OPA, DeepEval, LangGraph documentation and broader governance market research)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist in any review/governance platform. Missing these = product feels incomplete or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **REST API: Submit/Approve/Reject/Query** | The core contract between AI pipelines and the governance layer. Every reference platform (Cordum, Temporal, LangGraph) exposes this. Without it, no integration is possible. | LOW | FastAPI auto-generates OpenAPI docs. Simple CRUD endpoints. |
| **Policy-driven routing (AUTO/HUMAN/BLOCK)** | The entire point of the platform. Cordum calls this "Safety Kernel" with ALLOW/DENY/REQUIRE_APPROVAL/ALLOW_WITH_CONSTRAINTS. Without automatic routing, users must manually triage every task. | MEDIUM | YAML-based rules evaluating risk metadata to determine disposition. |
| **Human approval gates** | Every governance platform supports pausing execution for human review. Temporal does this via Signals. LangGraph via `interrupt()`. Cordum via built-in approval nodes. Without this, the platform is just a pass-through. | MEDIUM | Review state persists, approval resumes the workflow. One-click approve/reject UX is critical. |
| **Immutable audit trail** | Non-negotiable for governance. Cordum: "append-only execution records." Temporal: "deterministic run history." Industry standard: tamper-evident, queryable log of every decision, action, and state transition. | MEDIUM | SQLite WAL append-only. Consider Merkle root anchoring for tamper evidence (from PROJECT.md). |
| **Real-time status notifications** | Reviewers need to know when items await their action. Submitting systems need to know when decisions are made. SSE + Webhook is the standard pattern. | LOW | FastAPI built-in SSE for live updates. httpx for outbound Webhook callbacks. |
| **Authentication & authorization** | No governance platform works without identity. Even single-user systems need API key + JWT to prevent unauthorized pipeline submissions. | LOW | JWT short-lived tokens (15min). One-time review tokens for approval links. |
| **Review item detail view** | Reviewers must see what they are approving: context, risk metadata, originating pipeline, payload preview. Without this, approval is blind. | MEDIUM | HTMX server-rendered cards. Image thumbnail support for kais-movie-agent scenes. |
| **Policy version management** | Policies change. When auditing past decisions, you must know which policy version was active. Cordum: "snapshot-based decisions with replayable reasoning." | MEDIUM | Git-synced YAML files. Policy hash stored with each audit record. |
| **Docker Compose deployment** | The target environment (low-spec machine 192.168.71.140) demands containerized, resource-bounded deployment. Total memory under 400MB. | LOW | 3-4 containers: API + Redis + Nginx + optional Dozzle. Well-understood pattern. |
| **Query/filter audit history** | "What happened last week?" is the first question after any incident. Audit logs are useless without search. | MEDIUM | SQLite queries with date range, pipeline source, decision type, status filters. HTMX paginated results. |

### Differentiators (Competitive Advantage)

Features that set this platform apart. Not all governance platforms have these, but they create significant value for the specific use case (personal AI production pipeline governance on constrained hardware).

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Mobile-first review UX (PWA)** | Cordum has a React dashboard. Temporal has a web UI. Neither is mobile-first. For the personal/small-team use case, approval from a phone during daily life is a major quality-of-life advantage. HTMX + Alpine.js + Tailwind keeps this lightweight. | MEDIUM | PWA installable on mobile. Touch-friendly approve/reject cards. Push notification via Webhook to Telegram/WeChat. |
| **Risk-tier auto-routing with escalation** | Not just static routing: low-risk items auto-pass, medium-risk get AI scoring, high-risk require human review. If human does not respond within timeout, auto-escalate. Cordum has risk-aware routing but not timeout escalation. Temporal has timers but requires explicit coding. | HIGH | YAML policies define risk tiers. Timeout ladder: AI 5min -> human 24h -> auto-escalate. State machine handles transitions. |
| **AI scoring plugin bus** | DeepEval's core innovation: pluggable evaluation metrics with configurable weights and thresholds. Reserve the interface in v1, ship CLIP/aesthetic model scoring in v1.x. This turns the platform from passive approval gate into active quality filter. | HIGH | Abstract `Metric` interface: `score(payload) -> float`. Plugin registry. Threshold config in policy. Ship with no-op default. |
| **Directed-graph state machine with checkpoint** | LangGraph's proven pattern: model review flow as a directed graph where each node is a processing step and edges are transitions. State is checkpointed at every node, enabling pause/resume/replay. More flexible than linear state machines. | HIGH | StateGraph with nodes (submit, evaluate_policy, human_review, complete). Edges define transitions. SQLite-backed checkpoint store. |
| **One-time approval tokens** | Generate a unique, unguessable URL that grants approval rights for a single review item without login. Share via Telegram/WeChat. No other platform offers this frictionless approval pattern for small teams. | LOW | 32-character random token. Stored in Redis with TTL. One use then invalidated. Hashed in DB. |
| **Git-synced policy-as-code** | Policies live in a Git repo. Platform periodically pulls changes. Full history, diffing, rollback via git. OPA uses Rego (steep learning curve). YAML policies with git versioning is simpler and more accessible for the target user. | MEDIUM | `git pull` cron job or webhook-triggered. Policy reload without restart. Hash-based version tracking. |
| **Lightweight resource footprint** | Cordum requires Go + NATS + Redis (4GB+ RAM recommended). Temporal is a full platform (8GB+). This platform targets <400MB total. That constraint IS the differentiator for homelab/personal infrastructure. | LOW | Architectural constraint, not a feature per se. Every design decision feeds this. SQLite not PostgreSQL. arq not Celery. |
| **Integration-first API design** | Built specifically for kais-movie-agent and kais-gold-team integration patterns. Pre-built webhook contracts, pipeline-specific metadata schemas, preview image support. Cordum is framework-agnostic (generic). This is purpose-built. | MEDIUM | Pipeline-specific API schemas. Movie agent: scene/storyboard previews. Gold team: GPU job parameters. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem appealing but create complexity, maintenance burden, or scope creep that undermines the core value.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **OPA/Rego policy engine** | OPA is the CNCF standard for policy-as-code. Rego is powerful and expressive. | Reggo has a steep learning curve for a single-developer project. OPA adds another service container (~50MB RAM, separate process). YAML policies cover 95% of use cases for this domain. The power user pattern (nested conditions, set operations) is not needed for risk-tier routing. | YAML policies with clear schema. Git-versioned. If complexity outgrows YAML in v2, evaluate OPA embed (WASM) then. |
| **WebSocket bidirectional communication** | Real-time bidirectional feels more modern. Some platforms offer it. | SSE is sufficient for server-to-client push. Client-to-server actions use REST POST. WebSocket adds connection management complexity (reconnect, heartbeat, multiplexing) for zero marginal benefit in this review/approve flow. Cordum offers WebSocket but it serves their multi-agent fleet scenario. | SSE for push + REST for actions. Simple, proven, FastAPI native. |
| **Prometheus/Grafana monitoring stack** | Production systems need observability. Standard practice. | Prometheus + Grafana adds 200-500MB RAM and 2 more containers. The platform itself has <400MB budget. For a single-user/personal platform, this is overkill. | Docker logs + Dozzle for log viewing. Simple health endpoint (`/healthz`). Shell script for basic metrics. Add structured logging for future log aggregation. |
| **Multi-tenant support** | "What if we need to support multiple teams later?" | Multi-tenancy touches every layer: database schema, auth, policy isolation, audit segregation. It adds 3-5x complexity to data modeling and API design. The stated use case is single-user/single-team. Premature multi-tenancy is a classic architecture astronaut pattern. | Single-tenant schema. If multi-tenancy becomes real, add a `tenant_id` column and API key scoping. Design the API to not prevent it, but do not build it. |
| **React/Vue SPA frontend** | Modern web apps use SPA frameworks. Rich interactivity. | SPA requires build tooling (webpack/vite), node_modules, CI build step, separate deployment. HTMX provides the same interactivity for CRUD review flows without any build step. The review UX is approve/reject/query -- not a complex interactive application. | HTMX + Alpine.js + Tailwind CSS. Zero build. 14KB total. Server-rendered. |
| **OAuth/SSO integration** | Enterprise governance requires enterprise identity. | OAuth adds external dependency, token management complexity, provider-specific configuration. The platform runs on a private LAN (192.168.71.x). JWT + API keys are sufficient for this trust boundary. | JWT short-lived tokens. API keys for pipeline integration. One-time approval tokens for ad-hoc reviewers. |
| **Video streaming review** | kais-movie-agent produces video. Reviewers should stream it. | Video streaming requires transcoding, CDN, progressive loading, bandwidth management. The low-spec machine cannot handle video transcoding. Thumbnail/preview image review covers the quality-check use case. | Thumbnail extraction during submit. Preview images in review cards. Link to full video on NAS/storage for detailed review outside the platform. |
| **Generic workflow builder (visual drag-and-drop)** | Cordum has a visual workflow engine. Temporal has workflow-as-code. Visual builders are impressive demos. | Visual workflow builders are months of development for an edge case. The review flow is fixed: submit -> evaluate -> route -> approve/reject -> complete. There are 4-5 states. A hardcoded state machine handles this. If flows become variable later, YAML-defined graphs (not visual builders) are the right abstraction level. | Hardcoded directed graph state machine. Transitions defined in code. If flexibility is needed later, add YAML graph definition support (like LangGraph's `StateGraph`). |
| **Celery task queue** | Celery is the standard Python task queue. Battle-tested. | Celery is 10x heavier than arq. Requires a broker (RabbitMQ or Redis), separate worker processes, does not share the async event loop. arq is pure async, shares FastAPI's event loop, uses Redis (already in the stack), and handles the task patterns needed (async approval timeout, webhook delivery). | arq with Redis. Same event loop as FastAPI. Zero additional infrastructure. |

## Feature Dependencies

```
[Policy-driven routing (AUTO/HUMAN/BLOCK)]
    +--requires--> [REST API: Submit/Approve/Reject/Query]
    +--requires--> [YAML Policy Engine]
    |
    +--enhances--> [Risk-tier auto-routing with escalation]
                       +--requires--> [Timeout/Timer system (arq)]
                       +--requires--> [State machine with checkpoint]

[Human approval gates]
    +--requires--> [State machine with checkpoint]
    +--requires--> [Authentication (JWT + approval tokens)]
    +--requires--> [Review item detail view]
    |
    +--enhances--> [One-time approval tokens]
    +--enhances--> [Mobile-first review UX (PWA)]

[Immutable audit trail]
    +--requires--> [SQLite WAL storage]
    +--enhances--> [Policy version management (hash stored with audit record)]
    +--enhances--> [Query/filter audit history]

[AI scoring plugin bus]
    +--requires--> [Policy-driven routing (to trigger AI scoring tier)]
    +--requires--> [Abstract Metric interface definition]
    |
    +--conflicts--> [Low resource footprint] (AI models consume GPU/RAM)

[Real-time status notifications (SSE + Webhook)]
    +--requires--> [arq task queue for async Webhook delivery]
    +--enhances--> [Mobile-first review UX (push via Telegram/WeChat)]

[Git-synced policy-as-code]
    +--requires--> [YAML Policy Engine]
    +--enhances--> [Policy version management]
    +--enhances--> [Immutable audit trail (policy hash tracking)]

[Docker Compose deployment]
    +--requires--> [All components containerized]
    +--requires--> [Resource limits configured]
    +--conflicts--> [Heavy dependencies (OPA, Prometheus, Celery)]
```

### Dependency Notes

- **Policy-driven routing requires REST API:** Routing decisions happen at submit time. The API must accept review submissions with enough metadata for policy evaluation.
- **Human approval gates require state machine with checkpoint:** Approval pauses the workflow. State must persist across the pause (could be hours/days). Checkpoint recovery must work after server restart.
- **AI scoring plugin bus conflicts with low resource footprint:** Running CLIP or aesthetic models requires GPU/RAM. The interface should be designed in v1 but implementations should run on the high-spec machine (192.168.71.38), not the low-spec review platform host. The plugin bus calls out to an external scoring service.
- **One-time approval tokens enhance human approval gates:** Tokens reduce friction for ad-hoc reviewers (share a link via chat, they approve without logging in). But tokens are built on top of the approval gate infrastructure -- cannot exist without it.
- **Git-synced policy-as-code enhances audit trail:** When auditing why a decision was made, you can trace to the exact policy version (git commit hash). This creates a complete chain: policy version -> routing decision -> approval/rejection -> outcome.

## MVP Definition

### Launch With (v1)

Minimum viable product -- what is needed to validate that the governance layer actually works end-to-end with kais-movie-agent.

- [ ] **REST API: Submit/Approve/Reject/Query** -- Without this, no pipeline integration. The primary contract.
- [ ] **YAML policy-driven routing (AUTO/HUMAN/BLOCK)** -- The core value proposition. Must demonstrate that policies automatically route tasks.
- [ ] **State machine with checkpoint (4 states: PENDING/POLICY_EVAL/APPROVING/COMPLETE)** -- Minimal directed graph. Enough to prove pause/resume works.
- [ ] **Human approval gate (approve/reject via API + simple web page)** -- Proves human-in-the-loop works. Does not need to be mobile-optimized yet.
- [ ] **Immutable audit log (SQLite append-only)** -- Proves every decision is recorded. Queryable via API.
- [ ] **JWT authentication + API keys** -- Prevents unauthorized submissions. Basic but essential.
- [ ] **SSE status push** -- Proves real-time notification works for status changes.
- [ ] **Docker Compose deployment (3 containers, <400MB)** -- Proves the resource constraint is achievable.

### Add After Validation (v1.x)

Features to add once the core governance loop is validated with real pipeline traffic.

- [ ] **Mobile-first review UX (PWA with HTMX)** -- Trigger: reviewer needs to approve from phone during daily life. Without mobile UX, approval latency is high.
- [ ] **One-time approval tokens** -- Trigger: sharing approval links via Telegram/WeChat instead of requiring login.
- [ ] **Webhook callbacks to pipelines** -- Trigger: kais-movie-agent needs to know review results without polling.
- [ ] **Git-synced policies** -- Trigger: policies change often enough that manual updates are error-prone.
- [ ] **Risk-tier escalation with timeouts** -- Trigger: review items getting stuck because reviewer is unavailable.
- [ ] **Query/filter audit history UI** -- Trigger: need to investigate what happened to a specific task.
- [ ] **Policy version tracking in audit records** -- Trigger: need to explain why a decision was made after policy changed.

### Future Consideration (v2+)

Features to defer until the platform is proven and usage patterns emerge.

- [ ] **AI scoring plugin bus (CLIP/aesthetic model integration)** -- Requires GPU resources on high-spec machine. Design the interface in v1, implement plugins later.
- [ ] **Telegram/WeChat bot integration** -- Push notifications + inline approve/reject. Requires bot API setup.
- [ ] **Merkle root audit anchoring** -- Tamper-evidence beyond append-only logs. Only needed if audit integrity becomes a real concern.
- [ ] **Policy simulation/testing** -- Cordum offers this. Test policies against historical data before rollout. Useful when policies get complex.
- [ ] **Multi-reviewer workflows** -- Require N-of-M approvals for high-risk items. Only needed if team grows.
- [ ] **YAML-defined graph workflows** -- Let users define custom review flows (not hardcoded 4-state graph). Only if review patterns diversify beyond the current model.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| REST API (Submit/Approve/Reject/Query) | HIGH | LOW | P1 |
| YAML policy-driven routing | HIGH | MEDIUM | P1 |
| State machine with checkpoint | HIGH | MEDIUM | P1 |
| Human approval gate | HIGH | MEDIUM | P1 |
| Immutable audit log (SQLite) | HIGH | MEDIUM | P1 |
| JWT auth + API keys | HIGH | LOW | P1 |
| Docker Compose deployment | HIGH | LOW | P1 |
| SSE real-time push | MEDIUM | LOW | P1 |
| Review item detail view (web) | MEDIUM | MEDIUM | P1 |
| Mobile-first PWA review UX | HIGH | MEDIUM | P2 |
| One-time approval tokens | MEDIUM | LOW | P2 |
| Webhook callbacks | MEDIUM | LOW | P2 |
| Git-synced policies | MEDIUM | MEDIUM | P2 |
| Risk-tier escalation + timeouts | MEDIUM | MEDIUM | P2 |
| Audit history query UI | MEDIUM | MEDIUM | P2 |
| Policy version in audit records | MEDIUM | LOW | P2 |
| AI scoring plugin bus interface | HIGH | HIGH | P3 |
| Telegram/WeChat bot | MEDIUM | MEDIUM | P3 |
| Merkle root anchoring | LOW | MEDIUM | P3 |
| Policy simulation | LOW | HIGH | P3 |
| Multi-reviewer workflows | LOW | HIGH | P3 |
| YAML-defined custom graphs | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch (v1 MVP)
- P2: Should have, add when core is working (v1.x)
- P3: Nice to have, future consideration (v2+)

## Competitor Feature Analysis

| Feature | Cordum (Agent Control Plane) | Temporal (Workflow Engine) | LangGraph (State Machine) | Our Approach |
|---------|------------------------------|----------------------------|---------------------------|--------------|
| **Policy engine** | Safety Kernel: ALLOW/DENY/REQUIRE_APPROVAL/ALLOW_WITH_CONSTRAINTS. Declarative YAML. Snapshot-based. | No native policy engine. Policy logic must be coded into workflow activities. | No native policy engine. Graph structure itself is the "policy." | YAML policies with risk-tier routing. Simpler than Cordum's Safety Kernel but covers the same surface. Git-versioned. |
| **Human approval** | Built-in approval gates. Risk-aware routing. Decision binding to job hash + policy snapshot. | Signals + Queries. Workflows wait indefinitely for human signal. Zero compute while waiting. | `interrupt()` function pauses graph. Checkpointer saves state. Resume with `Command(resume=...)`. | State machine checkpoint at APPROVING state. arq timer handles timeout escalation. One-time tokens for frictionless approval. |
| **Audit trail** | Append-only execution records. Searchable decision context. SIEM-friendly export. | Full workflow history. Event streaming. Replay capability. | Checkpoint history at every super-step. Time-travel debugging. | SQLite WAL append-only. Queryable via API. Policy hash + decision recorded per entry. Merkle anchoring in v2. |
| **State machine** | DAG execution model with retries, dependency handling, parallel steps. | Full workflow-as-code with durable execution, retries, compensation. | Directed cyclic graph. Nodes + edges + state schema. Checkpoint per step. | Hardcoded 4-state directed graph (PENDING/POLICY_EVAL/APPROVING/COMPLETE). SQLite-backed checkpoints. Extensible to YAML-defined graphs later. |
| **Resource footprint** | Go services + NATS + Redis. 4GB+ RAM recommended. Multi-container microservices. | Java/Go services + persistence layer. 8GB+ RAM for production. Heavyweight. | Python library (no standalone service). Checkpointer depends on backend (SQLite/Postgres). | Python (FastAPI) + SQLite + Redis. <400MB total. 3 containers. Deliberately minimal. |
| **Integration model** | CAP protocol. SDKs in Go/Python/Node. Plugin packs for 30+ services. MCP bridge. | gRPC + HTTP APIs. SDKs in Go/Java/Python/TS. Activity-based integration. | Python library. Integrates into LangChain ecosystem. `StateGraph` API. | REST API + Webhook. Direct integration with kais-movie-agent and kais-gold-team. Purpose-built, not generic. |
| **Mobile UX** | React dashboard (desktop). No mobile-first design. | Web UI (desktop). No mobile focus. | LangGraph Studio (desktop IDE). No review UI. | Mobile-first PWA with HTMX. Touch-friendly approve/reject cards. Optimized for phone approval. |
| **AI evaluation** | No native AI scoring. Policy-only governance. | No AI evaluation. General-purpose workflow. | No AI evaluation. Graph state machine only. | Plugin bus interface reserved in v1. CLIP/aesthetic model integration planned. Inspired by DeepEval's metric architecture. |

## Key Design Patterns from Competitors

These patterns emerged consistently across the researched platforms and should inform implementation.

### 1. Safety Kernel / Pre-execution Gate (from Cordum)
Every action is evaluated against policy BEFORE execution. The policy decision is recorded with a snapshot of the active policy version. This enables post-hoc reasoning about why a decision was made.

**Adoption:** Core to our routing engine. YAML policy evaluates risk metadata before determining AUTO/HUMAN/BLOCK disposition.

### 2. Durable Waiting (from Temporal)
Workflows can wait for human approval for hours/days without consuming compute resources. The state is persisted to storage, and the process is rehydrated when the signal arrives.

**Adoption:** arq task handles timeout tracking. State persists in SQLite. API endpoint resumes workflow on approval.

### 3. Checkpoint + Interrupt (from LangGraph)
State is saved at every graph node transition. Execution can be interrupted at specific nodes and resumed later with new input. This enables "time-travel" debugging.

**Adoption:** SQLite-backed checkpoint store. Every state transition writes a checkpoint. Enables audit trail and recovery.

### 4. Pluggable Metrics (from DeepEval)
Evaluation is abstracted into a metric interface. Each metric produces a score. Metrics can be combined with weights and thresholds. This decouples "what to evaluate" from "how to route."

**Adoption:** Define `Metric` protocol in v1. No-op default. CLIP scoring plugin in v1.x runs on high-spec machine.

### 5. Policy-as-Code (from OPA + Cordum)
Policies are declarative, version-controlled, and separate from application logic. Changes to policy do not require code changes or deployments.

**Adoption:** YAML policies in a Git repo. Platform pulls changes periodically. Policy hash recorded with each decision.

## Sources

- [Cordum -- Agent Control Plane](https://cordum.io/) -- Direct analysis of homepage and GitHub README. Closest competitor. Pre-execution policy enforcement, approval gates, audit trails. BUSL-1.1 license. Go + NATS + Redis stack.
- [Cordum GitHub Repository](https://github.com/cordum-io/cordum) -- Architecture details, CAP protocol, SDK, integration packs. Feature comparison table vs Guardrails AI and NeMo Guardrails.
- [Temporal -- Human-in-the-Loop Documentation](https://docs.temporal.io/ai-cookbook/human-in-the-loop-python) -- Signals + Queries pattern for durable human approval. Zero-compute waiting.
- [LangGraph Interrupts Documentation](https://docs.langchain.com/oss/python/langgraph/interrupts) -- `interrupt()` function, checkpoint/resume pattern. Directed graph state machine.
- [OPA -- Open Policy Agent](https://openpolicyagent.org/docs) -- Rego language, policy-as-code, JSON-based decisions. CNCF graduated project. Evaluated and deliberately excluded from v1.
- [DeepEval AI Evaluation Framework](https://github.com/confident-ai/deepeval) -- Pluggable metric design. Answer relevancy, faithfulness, hallucination detection metrics. Plugin bus inspiration.
- [AI Governance Tools: Practical Guide (OvalEdge)](https://www.ovaledge.com/blog/ai-governance-tools) -- Market overview of AI governance tooling landscape.
- [AI Governance Framework 2026 (Ethyca)](https://www.ethyca.com/guides/ai-governance) -- Enterprise governance patterns: approval, deployment, monitoring, retirement lifecycle.
- [Immutable Audit Trails for AI (Medium)](https://medium.com/source-of-truth/the-immutable-source-of-truth-fa54106a4ceb) -- Immutable pipeline design, content certification, audit integrity patterns.
- [Audit Trails in CI/CD for AI Agents (Prefactor)](https://prefactor.tech/blog/audit-trails-in-ci-cd-best-practices-for-ai-agents) -- Tamper-evident audit records, policy decision logging, approval event capture.

---
*Feature research for: AI Production Pipeline Review/Governance Platform*
*Researched: 2026-05-05*
