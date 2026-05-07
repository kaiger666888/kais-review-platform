# Phase 07: Docker Stack Integration Tests - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning
**Mode:** Auto-generated (testing phase — execution domain)

<domain>
## Phase Boundary

Full Docker Compose deployment verified as a black-box system through Nginx. Tests use httpx against the external Nginx port (8090) to verify the entire stack works together: Nginx → API → Redis → SQLite. Includes health checks, SSE through proxy, memory constraints, and security hardening verification.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — this is a Docker black-box testing phase with well-defined requirements (DOCK-01 through DOCK-07).

Key guidelines:
- Tests are NOT pytest — they are standalone scripts (bash or Python) that require Docker Compose to be running
- Tests hit http://localhost:8090 (or the configured external port) through Nginx
- Use docker stats for memory verification, docker exec for filesystem/user checks
- Tests should be runnable independently after `docker compose up -d`
- Test script should report pass/fail per requirement

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- docker-compose.yml — defines 4 services (api, nginx, redis, optional dozzle)
- docker/nginx/nginx.conf — reverse proxy config with SSE support
- Dockerfile — API container with read_only, cap_drop ALL, non-root user
- tests/integration/conftest.py — integration test patterns (but these use TestClient, not Docker)

### Established Patterns
- Health endpoint: GET /api/v1/health returns {status, dependencies}
- SSE endpoint: GET /events/stream through Nginx with 86400s timeout
- Container security: read_only filesystem, cap_drop ALL, user appuser (UID 1000)

### Integration Points
- Nginx proxy: localhost:8090 → api:8000
- Health check: /api/v1/health
- SSE: /events/stream (dedicated Nginx location bypassing rate limit)
- Docker stats: memory usage per container

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for Docker integration testing.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
