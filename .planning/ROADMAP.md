# Roadmap: Kai's Review Platform

## Overview

Build a policy-driven review governance platform in four phases. Phase 1 establishes the core engine: database, policy evaluation, state machine, audit trail, authentication, and the review API -- everything testable via curl with no UI yet. Phase 2 adds the real-time event layer (SSE push, webhook callbacks) so that status changes propagate immediately to browsers and external systems. Phase 3 delivers the mobile-first review frontend using HTMX, consuming the API and SSE layer built in Phases 1-2. Phase 4 hardens the deployment: Docker Compose, Nginx reverse proxy, security hardening, health checks, and end-to-end integration testing with kais-movie-agent and kais-gold-team.

Frontend and backend are developed as parallel tracks within Phase 3 (the backend API is already complete, frontend is pure consumption). Phases 1 and 2 focus on backend because the frontend has nothing to consume until the core engine and event bus are operational.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Core Engine** - Database, policy engine, state machine, audit trail, auth, review API -- fully testable via REST
- [ ] **Phase 2: Real-Time Events** - Event bus, SSE push, webhook delivery with retry -- status changes propagate instantly
- [ ] **Phase 3: Review Frontend** - Mobile-first HTMX review UI consuming the API and SSE layer, one-time token deep links
- [ ] **Phase 4: Deployment & Hardening** - Docker Compose, Nginx, security hardening, health checks, integration testing

## Phase Details

### Phase 1: Core Engine
**Goal**: External systems can submit review items, have them evaluated against YAML policy rules, routed to the correct disposition, and all state transitions are recorded in an immutable audit trail -- all via REST API.
**Depends on**: Nothing (first phase)
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, POLC-01, POLC-02, POLC-03, POLC-04, POLC-05, POLC-06, SM-01, SM-02, SM-03, SM-04, SM-05, REV-01, REV-02, REV-03, REV-04, REV-05, REV-06, REV-07, AUDT-01, AUDT-02, AUDT-03, AUDT-04, AUDT-05
**Success Criteria** (what must be TRUE):
  1. An external system can POST a review item and receive a review_id with routing decision (auto/human/ai_audit/block)
  2. A reviewer can approve or reject a pending review item via REST API with appropriate status response
  3. Every state transition is queryable in an append-only audit log with timestamp, actor, previous state, and new state
  4. YAML policy rules route items based on risk-tier thresholds and invalid YAML is rejected with clear validation errors
  5. JWT-protected endpoints reject unauthenticated requests and one-time review tokens work exactly once
**Plans**: 5 plans in 3 waves

Plans:
- [x] 01-PLAN.md -- Project foundation: FastAPI skeleton, SQLite WAL, SQLAlchemy models, Pydantic schemas, audit trail
- [x] 02-PLAN.md -- Auth (JWT + one-time tokens) and 4-state checkpoint state machine with optimistic locking
- [x] 03-PLAN.md -- YAML policy engine with JSON Schema validation and Policy CRUD API
- [x] 04-PLAN.md -- Review API: submit, approve/reject, query, list, audit query endpoints
- [x] 05-PLAN.md -- Auto-escalation task and integration tests for full review lifecycle

### Phase 2: Real-Time Events
**Goal**: Review status changes are pushed to browsers in real-time via SSE and delivered to registered external systems via webhooks with retry -- no polling required.
**Depends on**: Phase 1
**Requirements**: EVNT-01, EVNT-02, EVNT-03, EVNT-04, EVNT-05
**Success Criteria** (what must be TRUE):
  1. A browser connected to the SSE stream receives review status change events in real-time without polling
  2. Zombie SSE connections are detected and cleaned up via heartbeat mechanism, preventing memory leaks
  3. Registered external systems receive webhook callbacks when review status changes, with automatic retry on failure (up to 3 attempts with backoff)
  4. Webhook targets are configurable per source system (kais-movie-agent, kais-gold-team) and can be added/updated without code changes
**Plans**: 2 plans in 2 waves

Plans:
- [x] 02-01-PLAN.md -- SSE streaming endpoint (EventManager + heartbeat cleanup) and WebhookConfig CRUD API
- [x] 02-02-PLAN.md -- Webhook delivery with retry (arq task + HMAC signatures) and event emission integration into state machine

### Phase 3: Review Frontend
**Goal**: Reviewers have a mobile-first web interface to view pending reviews, approve or reject items with one tap, receive real-time updates, and open one-time approval links directly on their phone.
**Depends on**: Phase 1, Phase 2
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, UI-06
**Success Criteria** (what must be TRUE):
  1. A reviewer can open the dashboard on a mobile phone and see lists of pending, approved, and rejected reviews
  2. Tapping a review opens a detail page showing content preview with approve and reject action buttons that work
  3. New reviews appear on the dashboard automatically without page refresh (SSE-driven)
  4. Opening a one-time token link on a phone opens the review detail page directly for quick approval
  5. The layout renders correctly on mobile phone screens (primary target) with responsive HTMX + Alpine.js interactions
**Plans**: 3 plans in 2 waves

Plans:
- [x] 03-01-PLAN.md -- Template foundation: base.html, dashboard, review card/list/detail partials, web route handlers, approve/reject form actions
- [ ] 03-02-PLAN.md -- SSE real-time updates: cookie-auth SSE wrapper, htmx-ext-sse integration, new reviews banner
- [x] 03-03-PLAN.md -- One-time token deep link flow: JWT cookie exchange, auto-open detail, error toast handling

### Phase 4: Deployment & Hardening
**Goal**: The entire platform runs as a Docker Compose stack on the target machine (192.168.71.140) with Nginx reverse proxy, resource limits under 400MB, security hardening, and validated integration with external AI systems.
**Depends on**: Phase 3
**Requirements**: DEPL-01, DEPL-02, DEPL-03, DEPL-04, DEPL-05, DEPL-06, DEPL-07
**Success Criteria** (what must be TRUE):
  1. `docker compose up` brings up the full stack (api, nginx, redis) and the review dashboard is accessible at http://192.168.71.140:8090
  2. Total container memory usage stays under 400MB under normal operation
  3. Nginx correctly proxies SSE connections (no buffering) and enforces rate limiting
  4. SQLite data persists across container restarts via bind mount with WAL mode confirmed
  5. All services have health check endpoints and auto-restart on failure; containers run with security hardening (read_only, cap_drop ALL, non-root)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Engine | 5/5 | Complete | 2026-05-05 |
| 2. Real-Time Events | 0/2 | Not started | - |
| 3. Review Frontend | 0/3 | Not started | - |
| 4. Deployment & Hardening | 0/? | Not started | - |
