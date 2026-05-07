# Phase 2: Real-Time Events - Context

**Gathered:** 2026-05-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Review status changes are pushed to browsers in real-time via SSE and delivered to registered external systems via webhooks with retry -- no polling required.

This phase delivers: SSE stream endpoint with heartbeat-based zombie cleanup, webhook delivery system with retry and exponential backoff, webhook configuration CRUD API, and event emission integrated into the state machine.

</domain>

<decisions>
## Implementation Decisions

### SSE Architecture
- SSE endpoint at `GET /api/v1/events/stream` — follows existing v1 REST pattern
- JSON event format with `event: review_status`, `data: {review_id, old_state, new_state, timestamp}` — matches audit trail structure
- SSE comment lines (`: heartbeat`) every 30s — lightweight, no client parsing needed
- In-memory set with asyncio.Queue per connection — sufficient for LAN single-server, Redis not needed for SSE fan-out

### Webhook System
- SQLite table `webhook_configs` for webhook configuration storage — consistent with existing DB, single source of truth
- arq task per webhook delivery with exponential backoff (1s → 5s → 30s), max 3 retries — leverages existing arq infrastructure
- Standard JSON payload: `{event, review_id, old_state, new_state, timestamp, source_system}` — mirrors SSE event structure
- HMAC-SHA256 signature in `X-Webhook-Signature` header — industry standard, verifiable by receivers

### Event Emission Pattern
- Emit events in `state_machine.transition_state()` — single emission point, all state changes flow through it
- Direct iteration over SSE connections + arq.enqueue for each webhook — simple for single-server LAN deployment
- `POST/GET/PUT/DELETE /api/v1/webhooks` CRUD API — standard CRUD, JWT-protected
- No hard connection limit — LAN deployment, < 10 concurrent reviewers expected. Log warning at > 50 connections

### Claude's Discretion
Internal implementation details, error message wording, test structure.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/core/state_machine.py` — `transition_state()` is the emission point for all events
- `app/core/database.py` — async SQLite engine, `get_db()` dependency
- `app/core/auth.py` — JWT auth dependency, `get_current_client()`
- `app/core/dependencies.py` — shared Redis/arq pool accessors
- `app/workers/tasks.py` — existing arq worker with `WorkerSettings` and cron jobs
- `app/models/schema.py` — SQLAlchemy models, can add WebhookConfig table
- `app/models/schemas.py` — Pydantic schemas, can add webhook request/response models
- `app/api/v1/` — existing router pattern for new endpoints

### Established Patterns
- FastAPI async with SQLAlchemy async sessions
- arq for background tasks (already in use for timeout escalation)
- Redis for state management (already connected)
- JWT auth on all protected endpoints
- Cursor-based pagination for list endpoints
- Audit trail logging on state changes

### Integration Points
- `state_machine.transition_state()` — hook event emission here
- `app/workers/tasks.py` — add webhook delivery tasks to arq worker
- `app/main.py` — register new SSE and webhook routers
- External systems (kais-movie-agent, kais-gold-team) — webhook receivers

</code_context>

<specifics>
## Specific Ideas

- SSE events mirror audit trail structure for consistency
- Webhook delivery is fire-and-forget from the state machine perspective (async via arq)
- HMAC signature allows receivers to verify payload authenticity
- Zombie cleanup prevents memory leaks from abandoned browser connections

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>
