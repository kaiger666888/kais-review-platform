# Project Research Summary

**Project:** Kai's Review Platform (AI Production Pipeline Review/Governance Platform)
**Domain:** AI governance / review-gate platform for production pipelines
**Researched:** 2026-05-05
**Confidence:** HIGH

## Executive Summary

This is a policy-driven review/governance platform that sits between AI production pipelines (kais-movie-agent, kais-gold-team) and their execution. Every task must pass through a YAML policy engine before proceeding -- the platform either auto-approves, routes to a human reviewer, sends to AI scoring, or blocks it outright. The closest analogues are Cordum (agent control plane), Temporal (durable workflows), and LangGraph (checkpointed state machines), but this platform is purpose-built for a constrained homelab environment: a single machine with 8-16GB RAM, total container budget under 400MB, no public internet.

The recommended approach is a fully async Python stack (FastAPI + aiosqlite + redis.asyncio + arq) with a zero-build frontend (HTMX + Alpine.js + Tailwind CSS CDN). SQLite WAL mode handles the append-heavy audit workload. Redis handles ephemeral state (checkpoints, tokens, task queue). The architecture centers on five tightly integrated components: a policy engine (YAML rules), a directed-graph state machine with checkpoints, a dual-transport event bus (SSE + webhooks), an immutable audit trail with hash chain, and a server-rendered mobile-first review UI. Every design choice optimizes for minimal resource footprint and operational simplicity -- single uvicorn worker, single SQLite file, three core containers.

The key risks are SQLite write contention under concurrent access (mitigated by aiosqlite + WAL + busy_timeout + single worker), SSE zombie connections leaking memory (mitigated by heartbeat-based cleanup and connection limits), and state machine race conditions during concurrent approvals (mitigated by optimistic locking with version columns). The YAML policy engine is a risk for silent wrong routing -- it needs JSON Schema validation and a dry-run endpoint from day one. The platform must also handle HTMX SSE extension quirks (error handling gaps, reconnection thundering herds) and Docker volume configuration that preserves SQLite WAL files.

## Key Findings

### Recommended Stack

The stack is a deliberately minimal, fully async Python ecosystem designed for a single-machine Docker deployment under 400MB RAM. Every component was chosen to avoid infrastructure overhead -- SQLite instead of PostgreSQL, arq instead of Celery, HTMX instead of React, SSE instead of WebSocket. The entire frontend has zero build step and loads from CDNs.

**Core technologies:**
- **Python 3.12+ / FastAPI 0.136:** Runtime and web framework -- native async, built-in SSE, auto OpenAPI docs, Pydantic v2 integration
- **SQLite WAL + SQLAlchemy 2.0 + aiosqlite:** Persistent storage -- append-heavy audit log workload, single-writer matches review pattern, zero ops overhead
- **Redis 7 + redis-py 7.4 + arq 0.28:** State and task queue -- in-memory state machine checkpoints, TTL-based one-time tokens, async task queue sharing FastAPI event loop
- **PyJWT 2.12.1:** Authentication -- short-lived JWT (15min) + one-time review tokens (CVE-2025-45768 fixed in 2.11+)
- **HTMX 2.0.9 + Alpine.js 3.15.12 + Tailwind CSS 4.2.3:** Frontend -- zero-build, server-rendered HTML, 14KB gzipped, mobile-first review UI
- **httpx 0.28.1:** Async HTTP client -- outbound webhook delivery to kais-movie-agent and kais-gold-team
- **structlog 24.5.0:** Structured logging -- JSON logs for Docker ingestion, context binding for audit trail

**Critical version constraints:** PyJWT >= 2.11.0 (CVE fix), redis-py >= 5.0.0 (aioredis merged in), SQLAlchemy >= 2.0.0 (stable async API), FastAPI >= 0.100.0 (Pydantic v2 support), Python >= 3.12.

### Expected Features

Research across Cordum, Temporal, OPA, DeepEval, and LangGraph identified clear feature tiers. The MVP must prove the core governance loop: submit a review item, evaluate it against policy, route to the correct disposition, allow human approval, and record everything in an immutable audit trail.

**Must have (table stakes -- v1 MVP):**
- REST API: Submit/Approve/Reject/Query -- the primary contract between AI pipelines and governance layer
- YAML policy-driven routing (AUTO/HUMAN/BLOCK) -- the core value proposition, every task evaluated before execution
- Directed-graph state machine with checkpoint (SUBMITTED/ROUTED/PENDING_REVIEW/APPROVED/REJECTED/ESCALATED/BLOCKED) -- pause/resume review lifecycle
- Human approval gate with one-click approve/reject -- human-in-the-loop for high-risk items
- Immutable audit trail (SQLite append-only + hash chain) -- non-negotiable for governance
- JWT authentication + API keys + one-time review tokens -- identity and access control
- SSE real-time status push -- reviewers and pipelines need immediate notification
- Docker Compose deployment (3-4 containers, <400MB RAM) -- target environment constraint
- Review item detail view -- reviewers must see what they are approving

**Should have (competitive advantage -- v1.x):**
- Mobile-first PWA review UX (HTMX) -- approve from phone, major quality-of-life advantage over Cordum/Temporal desktop UIs
- One-time approval tokens -- frictionless approval via shareable links (Telegram/WeChat)
- Webhook callbacks to pipelines -- kais-movie-agent gets notified without polling
- Risk-tier escalation with timeouts -- auto-escalate stale reviews via arq timer
- Git-synced policy-as-code -- version-controlled policies with hash tracking in audit records
- Audit history query/filter UI -- investigate past decisions

**Defer (v2+):**
- AI scoring plugin bus (CLIP/aesthetic models) -- design the interface in v1, implement on high-spec machine later
- Telegram/WeChat bot integration -- push notifications + inline approve/reject
- Merkle root audit anchoring -- enhanced tamper-evidence beyond hash chain
- Policy simulation/testing, multi-reviewer workflows, YAML-defined custom graphs

### Architecture Approach

The architecture is a single FastAPI process with six internal components communicating via direct function calls and an in-process asyncio.Queue event bus. External communication uses REST (inbound from pipelines), SSE (outbound to browsers), and webhooks (outbound to pipelines). State is split: Redis holds ephemeral fast-access data (current checkpoint, tokens, task queue); SQLite holds durable data (review records, audit trail, policy cache). The policy engine is the single gate that every submission must pass through before any other action -- it is the "safety kernel" of the system.

**Major components:**
1. **Review API Layer** (FastAPI routers) -- thin HTTP wrappers for submit/approve/reject/query/policy/audit endpoints
2. **Policy Engine** (YAML evaluator) -- evaluates review items against declarative rules to determine routing; JSON Schema validated; dry-run capable
3. **Checkpoint State Machine** (directed graph) -- models review lifecycle with validated transitions; Redis-backed current state, SQLite-backed history
4. **Event Bus** (asyncio.Queue fan-out) -- dual-transport distribution: SSE to browsers, webhook to external systems via arq tasks
5. **Audit Trail** (append-only SQLite + hash chain) -- immutable log of every action, INSERT-only with tamper-evident SHA-256 chain
6. **Auth** (JWT + one-time tokens) -- short-lived JWT for API access, one-time tokens for frictionless review links, Redis token blacklist

**Key architectural patterns:** Pre-execution gate (policy evaluates before action), durable waiting (state persists across hours/days for human review), checkpoint recovery (full state reconstruction from SQLite), event-driven notification (state changes trigger SSE + webhooks simultaneously).

### Critical Pitfalls

1. **SQLite "database is locked" under concurrent writes** -- Use aiosqlite from day one, enable WAL mode + busy_timeout=5000, keep transactions short, run single uvicorn worker. Never use synchronous sqlite3 driver with async routes.
2. **SSE zombie connections leaking memory** -- Use sse-starlette library, implement 30-second heartbeat, periodically sweep stale connections (2h threshold), cap at ~200 concurrent connections. Configure Nginx with proxy_buffering off.
3. **State machine race conditions in concurrent approvals** -- Add version column for optimistic locking, perform state read-check-write in a single SQL transaction with BEGIN IMMEDIATE, make transitions idempotent, return 409 on conflict.
4. **YAML policy engine silent wrong routing** -- Define JSON Schema for policy YAML, validate at load time, build dry-run endpoint, implement deterministic rule precedence, add evaluation performance budget (50ms warning, 200ms reject), cap at 50 rules in v1.
5. **Docker read_only + SQLite WAL file mismatch** -- Mount the entire data directory (not just the .db file), use bind mount (not tmpfs) for SQLite data, verify PRAGMA journal_mode returns 'wal' after deployment.

## Implications for Roadmap

Based on the combined research, the dependency graph from ARCHITECTURE.md, and the pitfall-to-phase mapping from PITFALLS.md, the recommended structure is four phases. The build order is driven by one critical path: SQLite schema -> Audit Trail -> Policy Engine -> State Machine -> Review API -> Event Bus -> Frontend -> Docker. Phase 1 establishes the foundation with all the "never retrofit" components. Phase 2 builds the real-time layer. Phase 3 delivers the user-facing product. Phase 4 hardens for production.

### Phase 1: Foundation (Core Engine)

**Rationale:** The database layer, audit trail, state machine, and policy engine have hard interdependencies and must be correct from day one. PITFALLS.md is explicit: retrofitting async DB access, optimistic locking, and policy validation after the fact is extremely painful. This phase builds every component that cannot be safely modified later.

**Delivers:** Working policy engine, state machine, audit trail, and auth -- all testable via API endpoints but no UI yet.

**Addresses:** REST API (Submit/Approve/Reject/Query), YAML policy-driven routing, directed-graph state machine, immutable audit trail, JWT authentication.

**Avoids:** Pitfall 1 (SQLite locked -- aiosqlite from start), Pitfall 3 (race conditions -- version column in initial schema), Pitfall 5 (policy silent failures -- JSON Schema validation in first implementation).

**Components:** SQLite schema + connection factory, Redis connection factory, Pydantic/SQLAlchemy models, JWT auth + one-time tokens, audit trail with hash chain, policy engine with YAML parsing + validation + dry-run, checkpoint state machine with optimistic locking, Review API endpoints (CRUD), arq task skeleton.

### Phase 2: Real-Time Layer (Events + SSE)

**Rationale:** The event bus sits between the state machine (Phase 1) and the frontend (Phase 3). SSE and webhooks depend on the event bus, and SSE connection lifecycle management must be built into the implementation from the start (Pitfall 2). The HTMX SSE extension quirks (Pitfall 4) must be handled during SSE implementation, not bolted on after.

**Delivers:** Real-time status push to browsers via SSE, async webhook delivery to kais-movie-agent and kais-gold-team, event-driven architecture fully operational.

**Addresses:** SSE real-time push, webhook callbacks, event bus.

**Uses:** FastAPI EventSourceResponse, httpx for webhook delivery, arq for async webhook tasks with retry, asyncio.Queue for in-process event distribution.

**Avoids:** Pitfall 2 (SSE zombie connections -- sse-starlette + heartbeat + connection sweep), Pitfall 4 (HTMX SSE errors -- valid data always, reconnection throttling).

### Phase 3: Frontend + Mobile (User-Facing Product)

**Rationale:** With the API, state machine, and SSE layer working, the frontend becomes a pure consumer of existing endpoints. HTMX server-rendered HTML is straightforward once the API returns correct data. Mobile-first design is a differentiator but depends on having a working review queue and approval flow first.

**Delivers:** Complete mobile-first review UI -- queue view, review detail with approve/reject, SSE-powered live updates, one-time token deep-link page.

**Addresses:** Review item detail view, mobile-first PWA review UX, one-time approval tokens, HTMX frontend.

**Implements:** Jinja2 templates with HTMX + Alpine.js + Tailwind CSS, HTMX partial rendering via jinja2-fragments, SSE integration with hx-ext="sse", PWA manifest, responsive mobile layout.

**Avoids:** Anti-pattern 4 (building a SPA for review CRUD), UX pitfalls (no feedback during reconnection, no confirmation for destructive actions).

### Phase 4: Deployment + Integration Hardening

**Rationale:** Docker Compose deployment must be tested as a complete system. Nginx SSE proxy configuration is tricky and must be verified end-to-end (Pitfall 6). Integration testing with kais-movie-agent validates the entire governance loop. Resource limits must be tested under load.

**Delivers:** Production-ready Docker Compose deployment with Nginx reverse proxy, health checks, resource limits, backup strategy, and validated kais-movie-agent integration.

**Addresses:** Docker Compose deployment (<400MB), Nginx config (reverse proxy + SSE + static), kais-movie-agent integration, kais-gold-team integration.

**Avoids:** Pitfall 6 (Docker read_only + WAL mismatch), integration gotchas (synchronous webhooks, Nginx SSE buffering, no rate limiting), security mistakes (JWT secret in git, no SSE auth, CORS wildcard).

**Verifies:** PRAGMA journal_mode returns 'wal' in container, SSE events arrive individually via curl -N, backup and restore works, resource limits enforced under load.

### Phase Ordering Rationale

- **Phase 1 before everything:** The policy engine, state machine, and audit trail are the critical path. Every other component depends on them. The "never retrofit" pitfalls (async DB, optimistic locking, policy validation) all live here.
- **Phase 2 before Phase 3:** SSE must work before the frontend can show live updates. Building the frontend without SSE means building it twice.
- **Phase 3 before Phase 4:** Integration testing requires a complete UI. The kais-movie-agent integration test is more meaningful when it goes through the full flow: submit -> policy evaluate -> route -> approve on mobile -> webhook callback.
- **Phase 4 last:** Deployment hardening is iterative and requires a complete application to test against.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (Policy Engine):** YAML rule schema design is domain-specific. While JSON Schema validation is a known pattern, the specific rule conditions for kais-movie-agent scene quality and kais-gold-team GPU job parameters need domain research. Consider `/gsd:research-phase` for policy schema design.
- **Phase 3 (HTMX SSE Integration):** The HTMX SSE extension has documented bugs (Issue #134, #143). Testing the specific HTMX 2.0.9 + sse-starlette + Nginx proxy combination may uncover version-specific issues. Consider `/gsd:research-phase` for HTMX SSE configuration.
- **Phase 4 (kais-movie-agent Integration):** The webhook contract with kais-movie-agent needs concrete API specification. The current research assumes REST + Webhook but the exact payload schemas, authentication, and error handling need agreement with the kais-movie-agent team. Consider `/gsd:research-phase` for integration contract.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Database/Auth/Audit):** SQLAlchemy 2.0 async + SQLite WAL is well-documented. JWT auth is a solved problem. Hash chain audit trail follows standard patterns.
- **Phase 2 (Event Bus + Webhooks):** asyncio.Queue fan-out is straightforward. httpx async webhooks with arq retry is a well-documented pattern.
- **Phase 4 (Docker Compose):** Standard containerization. Nginx reverse proxy config for SSE is well-documented.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All technologies verified against PyPI, official docs, and Docker Hub. Version constraints confirmed (PyJWT CVE, redis-py merge, SQLAlchemy 2.0 stable). Alternatives thoroughly evaluated with clear rationale for each rejection. |
| Features | MEDIUM-HIGH | Feature tiers derived from direct competitor analysis (Cordum, Temporal, LangGraph, OPA, DeepEval). MVP definition is tight. Risk: kais-movie-agent integration requirements may shift feature priorities once real pipeline traffic flows. |
| Architecture | HIGH | Component responsibilities, data flow, and communication patterns are specific and detailed. Build order derived from dependency graph. Scaling path documented. Patterns sourced from Temporal, LangGraph, and Cordum architectures. |
| Pitfalls | HIGH | SQLite concurrency, SSE lifecycle, state machine race conditions, and HTMX SSE bugs are all verified against GitHub issues, Stack Overflow, and official docs. Prevention strategies are concrete and actionable. Recovery costs assessed. |

**Overall confidence:** HIGH

### Gaps to Address

- **kais-movie-agent webhook contract:** The exact payload schema, authentication mechanism, and callback behavior for kais-movie-agent integration is assumed but not specified. Must be defined during Phase 4 planning or validated with the kais-movie-agent codebase.
- **Policy schema for domain-specific rules:** YAML policy structure for risk-tier routing is designed generically. The specific conditions for kais-movie-agent (scene quality, storyboard metadata) and kais-gold-team (GPU job parameters, render cost) need domain-specific rule design during Phase 1 planning.
- **Tailwind CSS v4 CDN production readiness:** Tailwind v4's play CDN is described as suitable for development but its production performance and feature completeness for the review UI components need validation during Phase 3. If it proves inadequate, Tailwind CLI build or a pre-built CSS file would be needed.
- **sse-starlette vs FastAPI built-in EventSourceResponse:** ARCHITECTURE.md references FastAPI's built-in SSE (available since 0.135.0) while PITFALLS.md recommends sse-starlette. This discrepancy needs resolution during Phase 2 planning -- evaluate whether built-in SSE has sufficient disconnect detection or if sse-starlette is required.
- **AI scoring plugin bus interface shape:** The interface is deferred to v2 but needs a v1 placeholder design. The abstract `Metric` protocol from DeepEval patterns should be sketched during Phase 1 to avoid painting into a corner.

## Sources

### Primary (HIGH confidence)
- PyPI verified versions -- FastAPI 0.136, Pydantic 2.13.3, SQLAlchemy 2.0.49, redis-py 7.4.0, arq 0.28.0, PyJWT 2.12.1, httpx 0.28.1
- HTMX 2.0.9 release from htmx.org
- Alpine.js 3.15.12 from official CDN
- Tailwind v4 from tailwindcss.com
- FastAPI Official SSE Documentation -- built-in EventSourceResponse and ServerSentEvent API
- Temporal: Human-in-the-Loop Documentation -- signal-based approval patterns
- LangGraph Interrupts Documentation -- checkpoint/resume patterns
- SQLite WAL documentation -- official WAL mode behavior and limitations
- CVE-2025-45768 PyJWT vulnerability -- GitHub advisory
- PROJECT.md constraints (authoritative source)

### Secondary (MEDIUM confidence)
- Cordum (Agent Control Plane) -- closest competitor, pre-execution policy enforcement, approval gates, audit trails
- OPA -- evaluated and excluded from v1, policy-as-code patterns still informative
- DeepEval -- pluggable metric design, inspiration for AI scoring plugin bus
- Microsoft Agent Governance Toolkit -- policy engine architecture for AI agents
- FastAPI + HTMX Architecture Guide -- production reference for no-build full-stack
- FastAPI ARQ Integration guides -- async task queue patterns
- jinja2-fragments documentation -- partial template rendering
- Stack Overflow: SQLite concurrent writes with FastAPI + SQLAlchemy -- verified solutions
- HTMX SSE Extension GitHub Issues #134, #143 -- known bugs documented
- sse-starlette library -- production SSE implementation for FastAPI

### Tertiary (LOW confidence)
- Checkpoint-Based Governance (Medium article) -- formalized review gates, conceptual reference
- Spiral Scout: AI Agent Governance -- runtime governance patterns, general reference
- LangGraph Patterns & Best Practices (Medium) -- state machine patterns, supplemental
- YAML: The Silent Killer of DevOps Pipelines -- YAML validation strategies, general reference

---
*Research completed: 2026-05-05*
*Ready for roadmap: yes*
