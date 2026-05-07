# Requirements: Kai's Review Platform

**Defined:** 2026-05-07
**Core Value:** 策略引擎驱动的审核路由 — 每个 AI 生产任务执行前必须通过策略评估

## v1 Requirements (Complete)

All v1 requirements shipped and verified in milestone v1.0. See archived requirements in `.planning/milestones/v1.0-REQUIREMENTS.md`.

## v1.1 Requirements

Requirements for integration tests and tech debt fixes. Each maps to roadmap phases.

### API Integration Tests (TEST)

- [x] **TEST-01**: TestClient can submit a review and receive correct disposition (AUTO/HUMAN/BLOCK) based on policy
- [x] **TEST-02**: TestClient can approve a review in APPROVING state, transitioning to COMPLETE with APPROVED disposition
- [x] **TEST-03**: TestClient can reject a review in APPROVING state, transitioning to COMPLETE with REJECTED disposition and reason
- [x] **TEST-04**: Every state transition through API creates an immutable audit log entry
- [x] **TEST-05**: TestClient can query review by ID and get full state with audit trail
- [x] **TEST-06**: API returns 401 for protected endpoints without valid JWT
- [x] **TEST-07**: API returns 409 on concurrent conflicting state transitions
- [x] **TEST-08**: API returns 422/400 for invalid state transition attempts (e.g., approve a PENDING review)
- [x] **TEST-09**: API returns 404 for non-existent review queries
- [x] **TEST-10**: Multiple reviews submitted concurrently maintain independent state machines

### SSE Integration Tests (SSE)

- [x] **SSE-01**: TestClient can connect to /events/stream and receive state change events
- [x] **SSE-02**: Approving a review triggers an SSE event pushed to connected clients
- [x] **SSE-03**: SSE connection receives heartbeat keep-alive messages
- [x] **SSE-04**: SSE connection cleanup works after client disconnect
- [x] **SSE-05**: Multiple SSE clients connected simultaneously all receive the same event
- [x] **SSE-06**: Slow SSE client (full queue) is dropped without affecting other clients

### Webhook Integration Tests (HOOK)

- [x] **HOOK-01**: Webhook delivers to configured URL with correct HMAC signature header
- [x] **HOOK-02**: Webhook retries on connection failure with exponential backoff
- [x] **HOOK-03**: Webhook marks delivery as failed after max retries exhausted
- [x] **HOOK-04**: Webhook only fires for matching source_system filter when configured

### Docker Integration Tests (DOCK)

- [x] **DOCK-01**: API responds to /api/v1/health through Nginx reverse proxy
- [x] **DOCK-02**: Health check returns 200 with all dependencies healthy, 503 with degraded status
- [x] **DOCK-03**: Redis connectivity confirmed through API (state transitions, token operations)
- [x] **DOCK-04**: SSE connections work through Nginx with long-lived connection support
- [x] **DOCK-05**: Total container memory usage stays under 400MB limit
- [x] **DOCK-06**: API container filesystem is read_only (write attempts fail)
- [x] **DOCK-07**: API process runs as non-root user

### Tech Debt Fixes (DEBT)

- [x] **DEBT-01**: Admin API endpoint exists to generate one-time review tokens for external systems
- [x] **DEBT-02**: Web template routes redirect unauthenticated users instead of silently serving data
- [x] **DEBT-03**: audit_protect_authorizer is registered on SQLite connection, blocking UPDATE/DELETE on audit_entries

## v2 Requirements

### Performance Testing

- **PERF-01**: Load test with 100 concurrent review submissions
- **PERF-02**: SSE connection scaling test (50+ concurrent connections)

### CI/CD

- **CICD-01**: Integration tests run in CI pipeline on every PR
- **CICD-02**: Docker integration tests run nightly against deployed environment

## Out of Scope

| Feature | Reason |
|---------|--------|
| OPA/Rego policy engine | YAML sufficient for risk-tier routing, OPA adds significant complexity |
| WebSocket bidirectional communication | SSE unidirectional push is adequate for review status updates |
| Celery task queue | arq is 10x lighter and shares FastAPI event loop |
| Prometheus/Grafana monitoring | Too heavy for 8GB machine, Docker native + scripts sufficient |
| OAuth/SSO/Third-party login | Single-team LAN deployment, JWT sufficient |
| Multi-tenancy | Single user/team scenario only |
| Native mobile app | PWA covers mobile use case |
| Video streaming review | v1 only handles preview images/thumbnails |
| Visual workflow builder | Hardcoded 4-state graph covers actual review flow |
| Frontend E2E (browser automation) | HTMX pages covered by API tests; browser tests fragile and overkill for SSR |
| Performance/load testing | v1.1 focuses on correctness; perf deferred to v2 |
| CI/CD pipeline integration | Infrastructure concern, separate from testing milestone |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEBT-01 | Phase 05 | Complete |
| DEBT-02 | Phase 05 | Complete |
| DEBT-03 | Phase 05 | Complete |
| TEST-01 | Phase 06 | Complete |
| TEST-02 | Phase 06 | Complete |
| TEST-03 | Phase 06 | Complete |
| TEST-04 | Phase 06 | Complete |
| TEST-05 | Phase 06 | Complete |
| TEST-06 | Phase 06 | Complete |
| TEST-07 | Phase 06 | Complete |
| TEST-08 | Phase 06 | Complete |
| TEST-09 | Phase 06 | Complete |
| TEST-10 | Phase 06 | Complete |
| SSE-01 | Phase 06 | Complete |
| SSE-02 | Phase 06 | Complete |
| SSE-03 | Phase 06 | Complete |
| SSE-04 | Phase 06 | Complete |
| SSE-05 | Phase 06 | Complete |
| SSE-06 | Phase 06 | Complete |
| HOOK-01 | Phase 06 | Complete |
| HOOK-02 | Phase 06 | Complete |
| HOOK-03 | Phase 06 | Complete |
| HOOK-04 | Phase 06 | Complete |
| DOCK-01 | Phase 07 | Complete |
| DOCK-02 | Phase 07 | Complete |
| DOCK-03 | Phase 07 | Complete |
| DOCK-04 | Phase 07 | Complete |
| DOCK-05 | Phase 07 | Complete |
| DOCK-06 | Phase 07 | Complete |
| DOCK-07 | Phase 07 | Complete |

**Coverage:**
- v1.1 requirements: 30 total
- Mapped to phases: 30
- Unmapped: 0

---
*Requirements defined: 2026-05-07*
*Last updated: 2026-05-07 after roadmap creation*
