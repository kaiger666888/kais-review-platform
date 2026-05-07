# Roadmap: Kai's Review Platform

## Completed Milestones

- [x] **v1.0** — Policy-driven review governance platform with REST API, SSE real-time events, mobile-first HTMX frontend, Docker deployment — [archived roadmap](milestones/v1.0-ROADMAP.md) | [requirements](milestones/v1.0-REQUIREMENTS.md)

## Active Milestone

- [ ] **v1.1 Integration Tests & Tech Debt** — Integration tests covering API end-to-end, SSE, webhooks, Docker stack; 3 tech debt fixes — Phases 5-7

## Phases

**Phase Numbering:**
- Phases 1-4: v1.0 (archived)
- Phases 5-7: v1.1 (current milestone)
- Integer phases (5, 6, 7): Planned milestone work
- Decimal phases (5.1, 5.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 05: Tech Debt Fixes** - Fix 3 blocking issues: review token endpoint, web auth redirects, audit log protection (completed 2026-05-07)
- [ ] **Phase 06: API + Event Integration Tests** - TestClient-based tests for core API flows, SSE real-time push, webhook delivery with retry
- [ ] **Phase 07: Docker Stack Integration Tests** - Black-box tests against full Docker Compose deployment

## Phase Details

### v1.1 Integration Tests & Tech Debt (In Progress)

**Milestone Goal:** v1.0 platform gains full integration test coverage (HTTP layer through Docker stack) and 3 tech debt fixes resolved

### Phase 05: Tech Debt Fixes
**Goal**: Three blocking defects fixed so integration tests can verify correct behavior
**Depends on**: Phase 04 (v1.0 shipped)
**Requirements**: DEBT-01, DEBT-02, DEBT-03
**Success Criteria** (what must be TRUE):
  1. Admin can call an API endpoint to generate a one-time review token that external systems (kais-movie-agent, kais-gold-team) can use
  2. Unauthenticated users visiting web template routes are redirected to login instead of seeing page content
  3. Attempting to UPDATE or DELETE from audit_entries table raises an authorization error at the SQLite connection level
**Plans**: 2 plans

Plans:
- [x] 05-01-PLAN.md — Review token endpoint (DEBT-01) + audit authorizer verification test (DEBT-03)
- [x] 05-02-PLAN.md — Web auth enforcement: login page and dashboard redirect (DEBT-02)

### Phase 06: API + Event Integration Tests
**Goal**: All core workflows verified end-to-end through the HTTP layer (not just unit tests)
**Depends on**: Phase 05
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, TEST-06, TEST-07, TEST-08, TEST-09, TEST-10, SSE-01, SSE-02, SSE-03, SSE-04, SSE-05, SSE-06, HOOK-01, HOOK-02, HOOK-03, HOOK-04
**Success Criteria** (what must be TRUE):
  1. A developer can run pytest and verify that submitting, approving, rejecting, and querying reviews all produce correct state transitions and audit log entries through the actual API
  2. A developer can run pytest and verify that SSE connections receive real-time state change events, heartbeats, and that disconnected clients are cleaned up without affecting others
  3. A developer can run pytest and verify that webhooks deliver with HMAC signatures, retry on failure with backoff, and stop after max retries
  4. Edge cases return correct HTTP status codes: 401 without auth, 404 for missing reviews, 409 on conflicting transitions, 422 on invalid state changes
  5. Multiple concurrent review submissions maintain independent state machines (no cross-contamination)
**Plans**: 3 plans

Plans:
- [x] 06-01-PLAN.md — Integration test fixtures + API flow tests (TEST-01 through TEST-10)
- [ ] 06-02-PLAN.md — SSE integration tests (SSE-01 through SSE-06)
- [x] 06-03-PLAN.md — Webhook integration tests (HOOK-01 through HOOK-04)

### Phase 07: Docker Stack Integration Tests
**Goal**: Full Docker Compose deployment verified as a black-box system through Nginx
**Depends on**: Phase 06
**Requirements**: DOCK-01, DOCK-02, DOCK-03, DOCK-04, DOCK-05, DOCK-06, DOCK-07
**Success Criteria** (what must be TRUE):
  1. Developer can run a test script against a running Docker Compose stack and verify the API responds through Nginx with healthy dependency status
  2. Redis-dependent features (state transitions, token operations) work correctly through the containerized stack
  3. SSE connections work through Nginx with long-lived connection support (no premature timeout)
  4. Total container memory usage stays under 400MB, API container filesystem is read-only, and API process runs as non-root
**Plans**: TBD

Plans:
- [ ] 07-01: TBD
- [ ] 07-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 5 -> 6 -> 7

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 05. Tech Debt Fixes | v1.1 | 2/2 | Complete    | 2026-05-07 |
| 06. API + Event Integration Tests | v1.1 | 2/3 | In Progress|  |
| 07. Docker Stack Integration Tests | v1.1 | 0/2 | Not started | - |
