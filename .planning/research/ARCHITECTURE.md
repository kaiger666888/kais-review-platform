# Architecture Research

**Domain:** AI Production Pipeline Review/Governance Platform
**Researched:** 2026-05-05
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
                        EXTERNAL SYSTEMS
                    (kais-movie-agent,
                     kais-gold-team)
                         |       ^
                 REST API |       | Webhook Callback
                         v       |
┌──────────────────────────────────────────────────────────────┐
│                        Nginx (:80)                           │
│  /api/* → proxy_pass api:8000                                │
│  /sse/*  → proxy_pass api:8000 (buffering off)               │
│  /*     → static HTML/HTMX templates                         │
└──────────────────┬───────────────────────────────────────────┘
                   │
┌──────────────────┴───────────────────────────────────────────┐
│                     FastAPI Application                       │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    Review API Layer                       │ │
│  │  /api/v1/review/*   /api/v1/approval/*                   │ │
│  │  /api/v1/policy/*   /api/v1/audit/*                      │ │
│  └───────────┬────────────────────────┬─────────────────────┘ │
│              │                        │                       │
│  ┌───────────▼──────────┐  ┌─────────▼──────────┐            │
│  │   Policy Engine      │  │  Event Bus          │            │
│  │   (YAML Rules)       │  │  (SSE + Webhook)    │            │
│  └───────────┬──────────┘  └─────────┬──────────┘            │
│              │                        │                       │
│  ┌───────────▼────────────────────────▼──────────────────┐   │
│  │           Checkpoint State Machine                     │   │
│  │  SUBMITTED → ROUTED → PENDING_REVIEW →               │   │
│  │  APPROVED / REJECTED / ESCALATED                      │   │
│  └───────────┬────────────────────────────────────────────┘   │
│              │                        │                       │
│  ┌───────────▼──────────┐  ┌─────────▼──────────┐            │
│  │   Audit Trail        │  │  Auth (JWT)         │            │
│  │   (Append-Only)      │  │  + Review Tokens    │            │
│  └───────────┬──────────┘  └────────────────────┘            │
│              │                                                │
└──────────────┼────────────────────────────────────────────────┘
               │
    ┌──────────▼──────────────────────┐
    │                                 │
    │    SQLite (WAL)     Redis 7     │
    │    Audit Log        State KV    │
    │    Review Records   Task Queue  │
    │    Policy Cache     arq Jobs    │
    │                                 │
    └─────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| **Review API** | REST endpoints for submit/approve/reject/query review items | FastAPI routers with Pydantic models |
| **Policy Engine** | Evaluate review items against YAML rules to determine routing (AUTO/HUMAN/AI_AUDIT/BLOCK) | Custom Python evaluator loading YAML policy files from disk |
| **Checkpoint State Machine** | Model review lifecycle as a directed graph with persistent checkpoints | Redis-backed state transitions with SQLite audit entries |
| **Event Bus** | Push real-time status updates to clients (SSE) and external systems (Webhook) | FastAPI `EventSourceResponse` + `httpx` async callbacks |
| **Audit Trail** | Immutable, append-only log of every action for traceability | SQLite INSERT-only table with hash chain |
| **Auth** | JWT authentication (15min short-lived) + one-time review tokens | PyJWT with Redis token blacklist |
| **HTMX Frontend** | Mobile-first review UI, zero JavaScript build step | Jinja2 templates + HTMX + Alpine.js + Tailwind CSS |

## Recommended Project Structure

```
app/
├── main.py                     # FastAPI app factory + lifespan
├── core/
│   ├── config.py               # Pydantic Settings (env-based)
│   ├── policy.py               # YAML policy engine + evaluator
│   ├── checkpoint.py           # State machine + Redis-backed checkpoints
│   ├── events.py               # Event bus (SSE fan-out + webhook dispatch)
│   ├── audit.py                # Immutable audit logger (SQLite append)
│   ├── auth.py                 # JWT + one-time review token logic
│   └── router.py               # Risk-tier routing decisions
├── api/
│   └── v1/
│       ├── review.py           # POST /review/submit, GET /review/{id}
│       ├── approval.py         # POST /approval/{id}/approve, /reject
│       ├── policy.py           # GET /policies, PUT /policies/{name}
│       ├── audit.py            # GET /audit/log, GET /audit/{review_id}
│       ├── stream.py           # GET /stream/events (SSE endpoint)
│       └── auth.py             # POST /auth/token, POST /auth/review-token
├── models/
│   ├── review.py               # ReviewItem, ReviewState SQLAlchemy models
│   ├── audit.py                # AuditEntry model (INSERT only)
│   ├── policy.py               # PolicyRule Pydantic models
│   └── events.py               # EventPayload Pydantic models
├── templates/                  # Jinja2 + HTMX templates
│   ├── base.html               # Layout: Tailwind + HTMX + Alpine.js CDN
│   ├── review/
│   │   ├── list.html           # Review queue (HTMX-powered)
│   │   ├── detail.html         # Single review with approve/reject
│   │   └── mobile_review.html  # Mobile-optimized review card
│   └── partials/
│       ├── review_card.html    # HTMX partial for review item
│       └── status_badge.html   # Status indicator partial
├── policies/                   # YAML policy files (Git-synced)
│   ├── default.yaml            # Default routing rules
│   └── movie_agent.yaml        # kais-movie-agent specific rules
├── static/                     # Minimal static assets
│   └── manifest.json           # PWA manifest
├── workers/
│   └── tasks.py                # arq task definitions (webhook dispatch, etc.)
└── db/
    ├── session.py              # SQLite + aiosqlite session factory
    └── migrations/             # Schema versioning scripts
```

### Structure Rationale

- **core/:** Business logic with zero HTTP dependency. Functions accept primitives/DTOs, not request objects. This makes the policy engine, state machine, and audit logger independently testable without FastAPI.
- **api/v1/:** Thin HTTP wrappers that call into core/. Each router file maps to one resource. Versioned under v1 for future API evolution.
- **models/:** Dual-purpose -- SQLAlchemy models for persistence, Pydantic models for API validation. Keep them separate; SQLAlchemy models are database-shaped, Pydantic models are API-shaped.
- **templates/:** Server-rendered HTML. HTMX fetches partials from the API layer via `hx-get`/`hx-post`. No client-side routing, no virtual DOM.
- **policies/:** Plain YAML files, Git-tracked. Loaded at startup with file-watcher for hot-reload. The policy engine reads from this directory.
- **workers/:** arq async task definitions. Runs in the same process as FastAPI (shared event loop), or as a separate worker process for heavier tasks.

## Architectural Patterns

### Pattern 1: Pre-Execution Gate (Safety Kernel)

**What:** Every review item must pass through the policy engine BEFORE any action is taken. The policy engine is the single source of truth for routing decisions.

**When to use:** Every `submit` and `escalate` operation. Never bypass the policy engine.

**Trade-offs:** Adds latency to the submit path (~5ms for YAML eval). Acceptable because submits are infrequent (not real-time) and correctness matters more than speed.

```
Client POST /review/submit
    |
    v
[Review API] --> [Policy Engine] --> routing decision
    |                |
    |                +-> AUTO:      directly to APPROVED
    |                +-> HUMAN:     to PENDING_REVIEW
    |                +-> AI_AUDIT:  to AI_SCORING (future)
    |                +-> BLOCK:     directly to REJECTED
    v
[Checkpoint State Machine] -- persist state --> Redis + SQLite
    |
    v
[Event Bus] -- emit event --> SSE clients + Webhook callbacks
    |
    v
[Audit Trail] -- append log --> SQLite (immutable)
```

### Pattern 2: Directed Graph State Machine with Checkpoints

**What:** The review lifecycle is modeled as a directed graph where each node is a checkpoint. Transitions are explicit, validated, and persisted. The current state lives in Redis for fast access; the full transition history lives in SQLite for durability.

**When to use:** Every state transition in the review pipeline.

**Trade-offs:** Two writes per transition (Redis + SQLite). Acceptable because transitions are low-frequency and correctness is critical. Redis provides fast reads for `GET /review/{id}` status checks; SQLite provides the authoritative audit trail.

**State Graph:**

```
                    ┌──────────────────────────┐
                    │                          v
  SUBMITTED ──> ROUTED ──> PENDING_REVIEW ──> APPROVED
                    |              |
                    |              +────> REJECTED
                    |              |
                    v              v
                 BLOCKED      ESCALATED ──> PENDING_REVIEW (re-enter)
                                  |
                                  v
                              AI_SCORING (future)
```

**Valid transitions (enforced by the state machine):**

| From State | Allowed To | Condition |
|------------|------------|-----------|
| SUBMITTED | ROUTED | Policy engine has evaluated |
| ROUTED | PENDING_REVIEW | Route = HUMAN |
| ROUTED | APPROVED | Route = AUTO |
| ROUTED | REJECTED | Route = BLOCK |
| ROUTED | AI_SCORING | Route = AI_AUDIT (future) |
| PENDING_REVIEW | APPROVED | Human approves |
| PENDING_REVIEW | REJECTED | Human rejects |
| PENDING_REVIEW | ESCALATED | Timeout or manual escalation |
| ESCALATED | PENDING_REVIEW | Re-assigned to another reviewer |
| APPROVED | (terminal) | |
| REJECTED | (terminal) | |
| BLOCKED | (terminal) | |

**Checkpoint persistence:**

```python
# Each checkpoint stores:
checkpoint = {
    "review_id": "rev_abc123",
    "state": "PENDING_REVIEW",
    "previous_state": "ROUTED",
    "transition_reason": "policy_route: HUMAN",
    "actor": "policy_engine",  # or user_id, or "timeout"
    "timestamp": "2026-05-05T10:30:00Z",
    "metadata": {"risk_tier": "high", "policy_version": "v1.2"}
}
# Redis: key=review_id, value=checkpoint (fast read)
# SQLite: append to audit_entries table (durable, immutable)
```

### Pattern 3: Event Bus with Dual Transport (SSE + Webhook)

**What:** A lightweight in-process event bus that distributes state change events to two transport layers simultaneously: SSE for browser clients and Webhook for external systems.

**When to use:** Every state transition triggers an event. Subscribers opt in by transport type.

**Trade-offs:** In-process event bus (asyncio.Queue-based) means events are lost if the process crashes before dispatch. Mitigated by the fact that the audit trail (SQLite) is the authoritative record and SSE is purely informational. Webhooks get retry logic via arq tasks.

**Implementation architecture:**

```python
# Event Bus core (in-process)
class EventBus:
    """Fan-out event distribution using asyncio.Queue"""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        # channel "review:{id}" for per-review SSE
        # channel "webhook:{system}" for outbound webhooks

    async def publish(self, channel: str, event: EventPayload):
        for queue in self._subscribers.get(channel, []):
            await queue.put(event)

    def subscribe(self, channel: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        self._subscribers.setdefault(channel, []).append(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue):
        self._subscribers.get(channel, []).remove(queue)

# SSE endpoint uses the event bus
@app.get("/api/v1/stream/events", response_class=EventSourceResponse)
async def sse_events(request: Request):
    queue = event_bus.subscribe("review:all")
    async def event_generator():
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                yield ServerSentEvent(data=event, event="review_update", id=event.id)
        except asyncio.TimeoutError:
            yield ServerSentEvent(comment="keep-alive")  # FastAPI does this automatically
        finally:
            event_bus.unsubscribe("review:all", queue)
    return event_generator()

# Webhook dispatch via arq background task
async def dispatch_webhook(ctx, target_url: str, payload: dict):
    """Retried by arq with exponential backoff"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(target_url, json=payload, timeout=10)
        resp.raise_for_status()
```

### Pattern 4: Immutable Audit Trail with Hash Chain

**What:** Every action in the system appends a row to a SQLite table that is INSERT-only. Each entry includes a SHA-256 hash of the previous entry, creating a tamper-evident chain.

**When to use:** Every mutation -- review submit, state transition, policy change, approval, rejection, escalation.

**Trade-offs:** Hash chain computation adds ~1ms per insert. No practical downside. Periodic Merkle root anchoring to Git is deferred to a later phase.

```sql
CREATE TABLE audit_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id TEXT NOT NULL,
    action TEXT NOT NULL,           -- "submit", "route", "approve", "reject", etc.
    actor TEXT NOT NULL,            -- "policy_engine", "user:kai", "timeout"
    from_state TEXT,
    to_state TEXT,
    payload JSON,                   -- arbitrary metadata
    prev_hash TEXT NOT NULL,         -- SHA-256 of previous row
    own_hash TEXT NOT NULL,          -- SHA-256 of this row (computed after insert)
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Enforce append-only: no UPDATE or DELETE
-- In Python: revoke UPDATE/DELETE via SQLite authorizer callback
```

### Pattern 5: HTMX Server-Rendered Review UI

**What:** The review frontend is entirely server-rendered HTML. HTMX handles partial page updates (approve/reject buttons, status changes) without a JavaScript framework. Alpine.js handles minimal client-side interactivity (form validation, confirmation dialogs).

**When to use:** All review CRUD operations. The review queue, review detail, and approval flow are all HTMX-driven.

**Trade-offs:** Less interactive than a SPA for complex workflows. Perfectly fine for this domain: reviewers see a queue, click items, approve/reject with a comment. No need for client-side state management.

```html
<!-- Review queue item (HTMX partial) -->
<div class="review-card" hx-get="/api/v1/review/{{ id }}/partial"
     hx-trigger="sse:review_update" hx-swap="outerHTML">
    <h3>{{ title }}</h3>
    <span class="badge">{{ state }}</span>
    <button hx-post="/api/v1/approval/{{ id }}/approve"
            hx-confirm="Confirm approval?"
            hx-target="#review-{{ id }}"
            class="btn-green">Approve</button>
    <button hx-post="/api/v1/approval/{{ id }}/reject"
            hx-target="#review-{{ id }}"
            class="btn-red">Reject</button>
</div>
```

HTMX SSE integration uses the `hx-ext="sse"` extension to listen for real-time updates:

```html
<div hx-ext="sse" sse-connect="/api/v1/stream/events">
    <div sse-swap="review_update" hx-swap="innerHTML">
        <!-- Reviews auto-update when SSE events arrive -->
    </div>
</div>
```

## Data Flow

### Primary Flow: Review Submission to Resolution

```
[kais-movie-agent]
    |
    | POST /api/v1/review/submit
    | { "type": "scene_image", "content_ref": "s3://...", "metadata": {...} }
    v
[FastAPI Review API]
    |
    | 1. Validate request (Pydantic)
    | 2. Create review record (SQLite: INSERT)
    | 3. Policy Engine evaluates → route decision
    | 4. State Machine: SUBMITTED → ROUTED → {next state}
    | 5. Persist checkpoint (Redis + SQLite)
    | 6. Audit Trail: append entry with hash chain
    | 7. Event Bus: publish "review:routed" event
    |
    +---> [SSE Transport] --> [Connected browsers see update]
    +---> [Webhook Transport via arq] --> [kais-movie-agent receives callback]
    |
    | Response: 202 Accepted { "review_id": "rev_abc", "state": "PENDING_REVIEW",
    |            "status_url": "/api/v1/review/rev_abc" }
    v

[Human Reviewer on Mobile]
    |
    | GET /review/rev_abc?token=one_time_token
    v
[HTMX renders review detail page]
    |
    | POST /api/v1/approval/rev_abc/approve
    | { "comment": "Scene quality good" }
    v
[State Machine: PENDING_REVIEW → APPROVED]
    |
    | 1. Persist checkpoint
    | 2. Audit Trail: append entry
    | 3. Event Bus: publish "review:approved"
    | 4. Webhook callback to kais-movie-agent: "APPROVED, proceed"
    |
    v
[kais-movie-agent receives callback, proceeds with pipeline]
```

### Secondary Flow: Timeout Escalation

```
[arq Background Worker: timeout_check]
    |
    | Runs every 60s: scan Redis for PENDING_REVIEW items older than threshold
    |
    | Found: review_id=rev_xyz, pending for 30min (threshold: 5min for AI, 24h for HUMAN)
    |
    v
[State Machine: PENDING_REVIEW → ESCALATED]
    |
    | Event Bus: publish "review:escalated"
    | Webhook: notify admin channel
    | SSE: update queue UI
    |
    v
[Admin receives notification, re-assigns review]
```

### State Storage Split

| Data | Primary Store | Why |
|------|--------------|-----|
| Review records | SQLite | Persistent, relational queries, durable |
| Current checkpoint state | Redis | Fast reads for status polling, TTL for timeout checks |
| Checkpoint history | SQLite (audit_entries) | Immutable audit trail, query for history |
| Policy cache | Redis (optional) | Cache parsed YAML to avoid disk reads |
| One-time review tokens | Redis | TTL-based expiry, fast lookup, atomic consume |
| Webhook retry queue | Redis (arq) | arq's native job queue, exponential backoff |
| SSE subscriber queues | In-process (asyncio.Queue) | Per-connection, ephemeral, lost on restart (acceptable) |

## Component Communication Map

```
                    ┌─────────────────────────────────────────────┐
                    │              EXTERNAL CLIENTS                │
                    │  kais-movie-agent, kais-gold-team, browsers │
                    └──────┬─────────────────────────┬────────────┘
                           | HTTP (REST + SSE)        | HTTP (callback)
                           v                         ^
┌──────────────────────────────────────────────────────────────────┐
│                         FastAPI Process                           │
│                                                                   │
│  ┌─────────┐    ┌──────────┐    ┌───────────┐    ┌───────────┐  │
│  │Review   │───>│Policy    │───>│Checkpoint │───>│Event Bus  │  │
│  │API      │    │Engine    │    │State Mach.│    │(SSE+Hook) │  │
│  └────┬────┘    └──────────┘    └─────┬─────┘    └─────┬─────┘  │
│       |                               |                 |         │
│       v                               v                 v         │
│  ┌─────────┐    ┌──────────┐    ┌───────────┐                   │
│  │Audit    │<───│Auth      │    │arq Tasks  │                   │
│  │Trail    │    │(JWT)     │    │(webhooks) │                   │
│  └─────────┘    └──────────┘    └───────────┘                   │
│       |                               |                           │
└───────┼───────────────────────────────┼───────────────────────────┘
        v                               v
   ┌─────────┐                    ┌───────────┐
   │ SQLite  │                    │  Redis 7  │
   │ (WAL)   │                    │           │
   └─────────┘                    └───────────┘
```

### Communication Rules

| From | To | Method | Reason |
|------|----|--------|--------|
| Review API | Policy Engine | Direct function call | Synchronous, same process, needs immediate result |
| Review API | Checkpoint SM | Direct function call | Synchronous state transition, needs confirmation |
| Checkpoint SM | Redis | async SET/GET | Fast state storage with TTL |
| Checkpoint SM | SQLite | async INSERT | Durable audit trail |
| Checkpoint SM | Event Bus | async publish | Fire-and-forget event distribution |
| Event Bus | SSE endpoint | asyncio.Queue | Per-connection fan-out |
| Event Bus | arq worker | arq.enqueue_job | Async webhook dispatch with retry |
| Policy Engine | YAML files | File I/O (cached) | Policy definition source |
| Policy Engine | Redis | Optional cache | Avoid re-parsing YAML on every request |
| Auth | Redis | GET/SET with TTL | Token validation and expiry |
| HTMX Frontend | Review API | HTTP (hx-get/hx-post) | Standard request/response |
| HTMX Frontend | SSE endpoint | EventSource | Real-time status updates |

## Build Order (Component Dependencies)

The components must be built in a specific order due to hard dependencies. Each phase builds on the previous.

```
Phase 1: Foundation (no dependencies)
├── SQLite schema + connection factory (db/session.py)
├── Redis connection factory (core/config.py)
├── Pydantic models (models/*.py)
└── FastAPI app skeleton (main.py)

Phase 2: Auth (depends on Phase 1)
├── JWT token generation/validation (core/auth.py)
├── One-time review token with Redis TTL
└── Auth middleware / dependency injection

Phase 3: Audit Trail (depends on Phase 1)
├── Append-only audit_entries table
├── Hash chain computation
└── audit_logger function (core/audit.py)

Phase 4: Policy Engine (depends on Phase 1, Phase 3)
├── YAML policy file parser
├── Rule evaluator (risk-tier routing)
├── Policy loading + caching
└── Every policy eval writes to audit trail

Phase 5: Checkpoint State Machine (depends on Phase 1, Phase 3)
├── State graph definition (valid transitions)
├── Redis-backed checkpoint persistence
├── SQLite audit entry on every transition
└── Timeout detection (arq periodic task)

Phase 6: Review API (depends on Phase 2, 3, 4, 5)
├── POST /review/submit (calls policy engine + state machine)
├── POST /approval/{id}/approve|reject
├── GET /review/{id} (reads from Redis + SQLite)
├── GET /review/ (queue listing)
└── All endpoints go through auth + audit

Phase 7: Event Bus (depends on Phase 5, Phase 6)
├── In-process asyncio.Queue fan-out
├── SSE endpoint (GET /stream/events)
├── Webhook dispatch via arq tasks
└── Nginx SSE proxy configuration

Phase 8: HTMX Frontend (depends on Phase 6, Phase 7)
├── Base template (Tailwind + HTMX + Alpine.js CDN)
├── Review queue page (HTMX-powered)
├── Review detail + approve/reject flow
├── Mobile-optimized review card
├── SSE integration for live updates
└── One-time review token deep-link page

Phase 9: Docker + Integration (depends on all above)
├── Dockerfile (multi-stage, non-root)
├── docker-compose.yml (api + redis + nginx + dozzle)
├── Nginx config (reverse proxy + SSE + static)
├── Health checks + resource limits
└── Integration tests with kais-movie-agent
```

### Critical Path Analysis

```
SQLite ──> Audit Trail ──> Policy Engine ──┐
                                            ├──> Review API ──> Event Bus ──> HTMX Frontend
Redis ──> Auth ──> Checkpoint SM ──────────┘
```

The longest dependency chain is: `SQLite → Audit Trail → Policy Engine → Review API → Event Bus → HTMX Frontend`. This is 6 steps and should be the focus of early development. Auth and Checkpoint SM can be developed in parallel with the Policy Engine since they share no direct dependencies (only SQLite and Redis as data stores).

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-100 reviews/day | Single FastAPI process + SQLite + Redis. This is the initial deployment. No changes needed. |
| 100-1K reviews/day | Add connection pooling for SQLite. Consider moving arq worker to a separate process. Add Redis-based rate limiting. |
| 1K-10K reviews/day | SQLite WAL mode handles this fine for single-writer. Add read replicas? No -- SQLite single file. Instead, consider PostgreSQL migration if concurrent writes become a bottleneck. |

### Scaling Priorities

1. **First bottleneck: SQLite write concurrency.** Single-writer means writes serialize. For review submissions at ~1/second this is fine. At ~100/second, consider batching audit writes or migrating to PostgreSQL.
2. **Second bottleneck: SSE connection count.** Each SSE connection holds an asyncio.Queue in memory. At 100+ concurrent SSE connections, memory usage grows. Solution: move to Redis Pub/Sub for event distribution so the process does not hold per-connection state.
3. **Not a concern for v1:** CPU (YAML eval is cheap), disk space (audit log grows ~1KB per entry), network (LAN deployment).

## Anti-Patterns

### Anti-Pattern 1: Bypassing the Policy Engine

**What people do:** Add a "quick approve" endpoint that skips policy evaluation.
**Why it is wrong:** Undermines the entire governance model. If any code path can bypass policy, the platform provides no real control.
**Do this instead:** The policy engine is the ONLY way to determine routing. The "AUTO" route is the fast path. If you want auto-approval, define a policy rule that routes to AUTO -- do not create a separate code path.

### Anti-Pattern 2: Mutable Audit Entries

**What people do:** Add an "undo" or "edit" feature that UPDATEs or DELETEs audit entries.
**Why it is wrong:** Destroys the tamper-evidence property of the hash chain and breaks regulatory compliance.
**Do this instead:** All corrections are new entries. If an approval was made in error, add a "revocation" entry. The audit trail tells the full story, including mistakes and corrections.

### Anti-Pattern 3: State Transitions Without Validation

**What people do:** Allow any state transition by directly updating the `state` field in the database.
**Why it is wrong:** Creates invalid states (e.g., APPROVED -> SUBMITTED) that break downstream logic and make the audit trail incoherent.
**Do this instead:** ALL state changes go through the Checkpoint State Machine, which validates transitions against the allowed graph. Direct database updates of the state field are prohibited.

### Anti-Pattern 4: Building a SPA for Review CRUD

**What people do:** Reach for React/Vue because "that is what modern apps use."
**Why it is wrong:** Adds build complexity, increases bundle size, requires API design for every UI interaction, and provides zero benefit for a review queue + approve/reject workflow.
**Do this instead:** HTMX + Jinja2 templates. The server already has all the data. Render HTML, swap fragments. The entire review flow is: see queue, click item, approve/reject with comment. This is a forms-over-data problem, not a rich-interaction problem.

### Anti-Pattern 5: Webhook in the Request Path

**What people do:** Make the review API wait for the webhook callback to succeed before returning 200 to the client.
**Why it is wrong:** Couples the review platform's response time to the external system's availability. If kais-movie-agent is down, review submissions hang.
**Do this instead:** Return 202 Accepted immediately. Dispatch webhooks via arq background tasks with retry logic. The client gets a fast response; webhooks deliver asynchronously.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| kais-movie-agent | REST API (inbound) + Webhook (outbound) | Agent POSTs to `/api/v1/review/submit`; platform calls back on resolution |
| kais-gold-team | REST API (inbound) + Webhook (outbound) | Same pattern as movie-agent |
| Telegram/WeChat | Webhook (outbound only) | Notification channel for review status changes |
| Git repository | Scheduled pull (policy files) | Cron or arq task to `git pull` policy YAML from remote |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Review API ↔ Policy Engine | Direct function call | Synchronous, must complete before responding |
| Review API ↔ Checkpoint SM | Direct function call | Synchronous, state must persist before event emission |
| Checkpoint SM ↔ Event Bus | async function call | Fire-and-forget after state is persisted |
| Event Bus ↔ SSE Transport | asyncio.Queue | Per-connection, ephemeral |
| Event Bus ↔ Webhook Transport | arq.enqueue_job | Async, retried on failure |
| HTMX Frontend ↔ Review API | HTTP (standard) | HTMX attributes drive all requests |
| HTMX Frontend ↔ SSE Endpoint | EventSource | Browser-native SSE client |

## FastAPI SSE Implementation Notes (from Official Docs)

FastAPI has built-in SSE support since version 0.135.0 with `EventSourceResponse` and `ServerSentEvent`:

- **Keep-alive:** FastAPI automatically sends a ping comment every 15 seconds when no messages are sent, preventing proxy connection drops.
- **Cache-Control:** Automatically sets `Cache-Control: no-cache` header.
- **Proxy buffering:** Automatically sets `X-Accel-Buffering: no` to prevent Nginx buffering.
- **Resume support:** `Last-Event-ID` header allows clients to reconnect and resume from the last received event.
- **Pydantic integration:** Yield Pydantic models directly; FastAPI serializes them via Rust-side Pydantic for high performance.

These features mean minimal custom code for SSE. The Nginx config still needs `proxy_buffering off` and `proxy_read_timeout 86400s` for long-lived connections.

## Sources

- [FastAPI Official SSE Documentation](https://fastapi.tiangolo.com/tutorial/server-sent-events/) -- Built-in EventSourceResponse and ServerSentEvent API (HIGH confidence)
- [Temporal Use Cases and Design Patterns](https://docs.temporal.io/evaluate/use-cases-design-patterns) -- State machine patterns for approval workflows (HIGH confidence)
- [Temporal: Human-in-the-Loop Tutorial](https://learn.temporal.io/tutorials/ai/building-durable-ai-applications/human-in-the-loop/) -- Signal-based approval patterns (HIGH confidence)
- [Microsoft Agent Governance Toolkit](https://techcommunity.microsoft.com/blog/linuxandopensourceblog/agent-governance-toolkit-architecture-deep-dive-policy-engines-trust-and-sre-for/4510105) -- Policy engine architecture for AI agents (MEDIUM confidence)
- [Checkpoint-Based Governance (CBG)](https://medium.com/@basilpuglisi/checkpoint-based-governance-a-constitution-for-human-ai-collaboration-7029ceeaf427) -- Formalized review gates as checkpoints (MEDIUM confidence)
- [Spiral Scout: AI Agent Governance](https://spiralscout.com/blog/ai-agent-governance-architecture) -- Runtime governance architectural capabilities (MEDIUM confidence)
- [LangGraph Patterns & Best Practices (2025)](https://sumanta9090.medium.com/langgraph-patterns-best-practices-guide-2025-38cc2abb8763) -- State machine + checkpoint + interrupt patterns (MEDIUM confidence)
- [FastAPI + HTMX Architecture Guide](https://blakecrosley.com/guides/fastapi-htmx) -- Production reference for no-build full-stack (MEDIUM confidence)
- [FastAPI ARQ Integration](https://davidmuraya.com/blog/fastapi-arq-retries/) -- Async task queue patterns with FastAPI (MEDIUM confidence)
- [chanx Tutorial: ARQ Background Jobs](https://chanx.readthedocs.io/en/stable/tutorial-fastapi/cp3-background-jobs.html) -- Step-by-step arq + FastAPI integration (MEDIUM confidence)
- Project context: `.planning/PROJECT.md`, `RESEARCH-REPORT.md`, `DEPLOYMENT-FEASIBILITY.md` (HIGH confidence)

---
*Architecture research for: AI Production Pipeline Review/Governance Platform*
*Researched: 2026-05-05*
