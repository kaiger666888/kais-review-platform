# Milestones

## v1.1 Integration Tests & Tech Debt (Shipped: 2026-05-07)

**Phases completed:** 3 phases, 6 plans, 9 tasks

**Key accomplishments:**

- POST /api/v1/reviews/{id}/token endpoint generating one-time review tokens with JWT auth, plus verification that audit log UPDATE/DELETE protection works correctly
- Login page with API key form, httpOnly JWT cookie, and dashboard redirect for unauthenticated users (DEBT-02)
- 14 integration tests via httpx.AsyncClient covering full review lifecycle: submit with AUTO/HUMAN/BLOCK disposition, approve/reject transitions, audit trail, 401/404/409 status codes, and concurrent submission independence
- 7 SSE integration tests via event_manager queue pipeline plus production fix: SSE endpoints migrated to FastAPI 0.136 async generator pattern with response_class=EventSourceResponse
- 9 integration tests verifying HMAC-SHA256 webhook signatures, exponential backoff retry (1s/5s/30s), failure after max retries, and source_system filtering via HTTP CRUD + direct deliver_webhook testing
- Standalone bash test script verifying Docker Compose stack end-to-end through Nginx with 7 black-box tests covering health, Redis integration, SSE, memory limits, and container security

---
