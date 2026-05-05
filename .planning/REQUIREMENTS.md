# Requirements: Kai's Review Platform

**Defined:** 2026-05-05
**Core Value:** 策略引擎驱动的审核路由 — 每个 AI 生产任务执行前必须通过策略评估

## v1 Requirements

### Authentication

- [ ] **AUTH-01**: System can issue short-lived JWT tokens (15min) for API access
- [ ] **AUTH-02**: System can generate one-time review tokens (32-char, unguessable, time-limited) for approval links
- [ ] **AUTH-03**: API endpoints enforce JWT authentication on protected routes
- [ ] **AUTH-04**: One-time tokens are invalidated after single use (atomic operation)

### Policy Engine

- [ ] **POLC-01**: System evaluates YAML-based policy rules for each review submission
- [ ] **POLC-02**: Policy rules route items to AUTO/HUMAN/AI_AUDIT/BLOCK based on configurable conditions
- [ ] **POLC-03**: Risk-tier routing supports threshold-based classification (low → auto, medium → AI, high → human)
- [ ] **POLC-04**: Policies are validated against JSON Schema before activation
- [ ] **POLC-05**: Policy CRUD via API (create, read, update, delete with version tracking)
- [ ] **POLC-06**: Policy changes are logged in audit trail

### State Machine

- [ ] **SM-01**: Review items follow a 4-state directed graph (PENDING → POLICY_EVAL → APPROVING → COMPLETE)
- [ ] **SM-02**: State transitions are persisted with checkpoint to SQLite
- [ ] **SM-03**: Concurrent state transitions are protected by optimistic locking (version column)
- [ ] **SM-04**: State machine supports reject/escalate/expire transitions at each state
- [ ] **SM-05**: Timeout-based auto-escalation (AI review 5min → human review 24h)

### Review API

- [ ] **REV-01**: External systems can submit review items via REST API (POST /api/v1/reviews)
- [ ] **REV-02**: Review submission includes: type, content_ref, metadata, source_system, priority
- [ ] **REV-03**: Submitters receive immediate response with review_id and routing decision
- [ ] **REV-04**: Reviewers can approve items with optional comment (POST /api/v1/reviews/{id}/approve)
- [ ] **REV-05**: Reviewers can reject items with mandatory reason (POST /api/v1/reviews/{id}/reject)
- [ ] **REV-06**: System queries review status by ID (GET /api/v1/reviews/{id})
- [ ] **REV-07**: System lists reviews with filters (status, type, source, date range) and pagination

### Event Bus

- [ ] **EVNT-01**: System pushes real-time review status changes via SSE (GET /api/v1/stream)
- [ ] **EVNT-02**: SSE connections include heartbeat-based cleanup for zombie connections
- [ ] **EVNT-03**: System sends Webhook callbacks to registered external systems on status change
- [ ] **EVNT-04**: Webhook delivery uses retry with exponential backoff (max 3 retries)
- [ ] **EVNT-05**: Webhook targets are configurable per source system (kais-movie-agent, kais-gold-team)

### Audit Trail

- [ ] **AUDT-01**: Every state transition creates an immutable audit log entry in SQLite
- [ ] **AUDT-02**: Audit entries include: timestamp, review_id, previous_state, new_state, actor, action, metadata
- [ ] **AUDT-03**: Audit log is append-only (no update or delete operations)
- [ ] **AUDT-04**: System queries audit history for a review item (GET /api/v1/audit/{review_id})
- [ ] **AUDT-05**: System queries audit log with filters (date range, action type, actor)

### Frontend

- [ ] **UI-01**: Mobile-first review dashboard showing pending/approved/rejected review lists
- [ ] **UI-02**: Review detail page with content preview and approve/reject action buttons
- [ ] **UI-03**: Dashboard receives real-time updates via SSE (new reviews appear automatically)
- [ ] **UI-04**: One-time token deep links open review detail directly for quick approval
- [ ] **UI-05**: Responsive layout optimized for mobile phone screens (primary target)
- [ ] **UI-06**: HTMX server-rendered with Alpine.js for client-side interactivity

### Deployment

- [ ] **DEPL-01**: Docker Compose with 4 services (api, nginx, redis, optional dozzle)
- [ ] **DEPL-02**: Total container memory usage under 400MB
- [ ] **DEPL-03**: Nginx reverse proxy with SSE support and rate limiting
- [ ] **DEPL-04**: SQLite data persisted via bind mount with WAL mode
- [ ] **DEPL-05**: Redis data persisted for state machine and task queue
- [ ] **DEPL-06**: Docker security hardening (read_only, cap_drop ALL, non-root user)
- [ ] **DEPL-07**: Health check endpoints for all services with auto-restart

## v2 Requirements

### AI Scoring Plugin Bus

- **AISC-01**: Pluggable metric interface for AI scoring models (CLIP, aesthetic scoring)
- **AISC-02**: Weighted score combination with configurable thresholds
- **AISC-03**: AI audit results logged alongside human decisions

### Advanced Integrations

- **INTG-01**: Telegram/Enterprise WeChat bot for review notifications
- **INTG-02**: Git-synced policy file management
- **INTG-03**: Advanced backup with Git versioning

### Monitoring

- **MON-01**: Dozzle web-based log viewer
- **MON-02**: Automated backup script with hourly SQLite snapshots
- **MON-03**: Merkle Root anchoring for audit trail integrity verification

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

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | — | Pending |
| AUTH-02 | — | Pending |
| AUTH-03 | — | Pending |
| AUTH-04 | — | Pending |
| POLC-01 | — | Pending |
| POLC-02 | — | Pending |
| POLC-03 | — | Pending |
| POLC-04 | — | Pending |
| POLC-05 | — | Pending |
| POLC-06 | — | Pending |
| SM-01 | — | Pending |
| SM-02 | — | Pending |
| SM-03 | — | Pending |
| SM-04 | — | Pending |
| SM-05 | — | Pending |
| REV-01 | — | Pending |
| REV-02 | — | Pending |
| REV-03 | — | Pending |
| REV-04 | — | Pending |
| REV-05 | — | Pending |
| REV-06 | — | Pending |
| REV-07 | — | Pending |
| EVNT-01 | — | Pending |
| EVNT-02 | — | Pending |
| EVNT-03 | — | Pending |
| EVNT-04 | — | Pending |
| EVNT-05 | — | Pending |
| AUDT-01 | — | Pending |
| AUDT-02 | — | Pending |
| AUDT-03 | — | Pending |
| AUDT-04 | — | Pending |
| AUDT-05 | — | Pending |
| UI-01 | — | Pending |
| UI-02 | — | Pending |
| UI-03 | — | Pending |
| UI-04 | — | Pending |
| UI-05 | — | Pending |
| UI-06 | — | Pending |
| DEPL-01 | — | Pending |
| DEPL-02 | — | Pending |
| DEPL-03 | — | Pending |
| DEPL-04 | — | Pending |
| DEPL-05 | — | Pending |
| DEPL-06 | — | Pending |
| DEPL-07 | — | Pending |

**Coverage:**
- v1 requirements: 44 total
- Mapped to phases: 0
- Unmapped: 44 ⚠️

---
*Requirements defined: 2026-05-05*
*Last updated: 2026-05-05 after initial definition*
