# Phase 1: Core Engine - Context

**Gathered:** 2026-05-05
**Status:** Ready for planning

<domain>
## Phase Boundary

External systems can submit review items, have them evaluated against YAML policy rules, routed to the correct disposition, and all state transitions are recorded in an immutable audit trail -- all via REST API.

This phase delivers: REST API (submit/query/approve/reject), YAML policy engine with risk-tier routing, 4-state checkpoint state machine, JWT auth + one-time tokens, and append-only audit trail.

</domain>

<decisions>
## Implementation Decisions

### Data Model & API Design
- Flexible JSON metadata field + typed columns for core fields (id, type, status, source, priority) — balances query performance with extensibility
- Consistent `{data, meta, error}` envelope with snake_case fields — standard FastAPI pattern
- Cursor-based pagination (id-based) — consistent performance, works with real-time updates
- Single schema.py module with version tracking table — lightweight, no Alembic overhead for single-DB app

### Policy Engine & State Machine
- YAML condition blocks with AND/OR logic + risk_score threshold — handles real scenarios like "if source=movie-agent AND risk>0.7 then HUMAN"
- Default to HUMAN review when no rules match — safe conservative default
- Hardcoded Python enum + transition validation function for state machine — 4 states are well-defined, no dynamic graph needed
- arq scheduled task with Redis TTL for auto-escalation — natural fit with existing stack

### Auth & Project Structure
- Static API key in env var for machine-to-machine auth (kais-movie-agent calls with API key, gets JWT) — LAN-only, no user accounts needed
- Redis with TTL for one-time review tokens — auto-expiry, atomic check-and-delete
- Follow RESEARCH-REPORT layout: `app/core/`, `app/api/v1/`, `app/models/`, `app/templates/` — clear separation by concern
- `.env` file + Pydantic Settings — standard FastAPI pattern, type-safe

### Claude's Discretion
Specific library choices (aiosqlite, PyJWT version, Pydantic version), error message wording, internal function signatures, test structure.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- No existing code — greenfield project
- Research docs provide detailed architecture guidance (RESEARCH-REPORT.md, DEPLOYMENT-FEASIBILITY.md)
- Research STACK.md specifies: FastAPI 0.136+, SQLAlchemy 2.0.49 (async via aiosqlite), redis-py asyncio module, arq 0.28.0, PyJWT >=2.11.0

### Established Patterns
- Python async patterns (FastAPI + aiosqlite + redis.asyncio)
- SQLite WAL mode with busy_timeout=5000ms from day one (critical pitfall from research)
- Optimistic locking with version column for state transitions (prevents race conditions)

### Integration Points
- External systems (kais-movie-agent, kais-gold-team) will POST to /api/v1/reviews
- Redis shared between FastAPI and arq worker (same event loop)
- Audit trail writes on every state transition (2 writes per transition: state update + audit log)

</code_context>

<specifics>
## Specific Ideas

- State machine follows 4-state directed graph: PENDING → POLICY_EVAL → APPROVING → COMPLETE
- Reject/escalate/expire transitions available at each state
- Policy CRUD via API with version tracking
- Audit log is strictly append-only (no update/delete)
- One-time tokens: 32-char, unguessable, TTL-based, atomic single-use

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>
