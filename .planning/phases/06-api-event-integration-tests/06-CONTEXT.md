# Phase 06: API + Event Integration Tests - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning
**Mode:** Auto-generated (testing phase — execution domain)

<domain>
## Phase Boundary

All core workflows verified end-to-end through the HTTP layer using FastAPI TestClient. Covers API submission/approval/rejection/query flows, SSE real-time event streaming, and webhook delivery with retry. Tests go through actual HTTP routes, not direct module imports.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — this is a testing phase with well-defined requirements (TEST-01 through TEST-10, SSE-01 through SSE-06, HOOK-01 through HOOK-04). Use codebase conventions from existing test files (tests/conftest.py patterns, pytest-asyncio fixtures).

Key guidelines:
- Use FastAPI TestClient (httpx.AsyncClient with ASGI transport) for API tests
- Reuse existing conftest.py fixtures (db_session, db_engine, engine) where possible
- SSE tests should use httpx AsyncClient with streaming to consume text/event-stream
- Webhook tests should use httpx mock server or respx for delivery verification
- Follow TDD pattern from Phase 05 (test file first, then verify implementation passes)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- tests/conftest.py — existing fixtures for async DB session, test engine, mock Redis
- Phase 05 added: tests/test_token_endpoint.py, tests/test_audit_authorizer.py, tests/test_web_auth.py (patterns to follow)
- app/main.py — FastAPI app with router includes, the app instance for TestClient
- app/core/dependencies.py — get_redis, get_arq_pool for dependency injection overrides

### Established Patterns
- Pytest-asyncio with @pytest.mark.asyncio decorators
- SQLAlchemy async session fixtures with in-memory SQLite
- Mock Redis with custom MockScript for Lua support
- Tests use module-level imports (not HTTP) — integration tests should shift to TestClient

### Integration Points
- POST /api/v1/reviews — submit review
- POST /api/v1/reviews/{id}/approve — approve
- POST /api/v1/reviews/{id}/reject — reject
- GET /api/v1/reviews/{id} — query review
- GET /api/v1/audit/{review_id} — audit trail
- POST /api/v1/reviews/{id}/token — generate token (Phase 05)
- GET /events/stream — SSE endpoint
- POST /api/v1/webhooks — webhook config CRUD

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for integration testing FastAPI applications.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
