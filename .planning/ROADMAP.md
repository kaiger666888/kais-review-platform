# Roadmap: Kai's Review Platform

## Milestones

- [x] **v1.0** — Policy-driven review governance platform with REST API, SSE real-time events, mobile-first HTMX frontend, Docker deployment — [archived roadmap](milestones/v1.0-ROADMAP.md) | [requirements](milestones/v1.0-REQUIREMENTS.md)
- [x] **v1.1** — Integration tests covering API end-to-end, SSE, webhooks, Docker stack; 3 tech debt fixes — [archived roadmap](milestones/v1.1-ROADMAP.md) | [requirements](milestones/v1.1-REQUIREMENTS.md)
- [ ] **v1.2** — External system integration: Telegram Bot, kais-gold-team + kais-movie-agent callback automation, dual Bot coordination, E2E testing

## Phases

<details>
<summary>v1.0 Foundation (Phases 01-04) — Shipped 2026-05-05</summary>

- [x] Phase 01: Core Engine (5/5 plans)
- [x] Phase 02: Real-time Events (2/2 plans)
- [x] Phase 03: Review Frontend (3/3 plans)
- [x] Phase 04: Deployment & Hardening (2/2 plans)

</details>

<details>
<summary>v1.1 Integration Tests & Tech Debt (Phases 05-07) — Shipped 2026-05-07</summary>

- [x] Phase 05: Tech Debt Fixes (2/2 plans) — completed 2026-05-07
- [x] Phase 06: API + Event Integration Tests (3/3 plans) — completed 2026-05-07
- [x] Phase 07: Docker Stack Integration Tests (1/1 plan) — completed 2026-05-07

</details>

## Active Milestone

**v1.2 External System Integration** — Phases 08-12

- [x] **Phase 08: Schema & Callback Infrastructure** — Database migration for callback fields + arq callback delivery task with HMAC signing, retry, and SSRF protection (completed 2026-05-07)
- [x] **Phase 09: Telegram Review Bot** — Complete Telegram Bot (polling mode, InlineKeyboard approve/reject, timeout reminder, history) running inside FastAPI process (completed 2026-05-07)
- [x] **Phase 10: kais-gold-team Integration** — Control node review interception, risk-based routing, callback endpoint, auto-resume on approval (completed 2026-05-07)
- [x] **Phase 11: kais-movie-agent Integration** — Node.js HTTP client, 7 review gate replacements, callback endpoint, rollback on rejection, preview images (completed 2026-05-07)
- [ ] **Phase 12: Dual Bot Coordination & E2E** — Gold-team Bot forwards to review-platform Bot, end-to-end tests covering all integration flows

## Phase Details

### Phase 08: Schema & Callback Infrastructure
**Goal**: External systems can register a callback URL when submitting reviews, and the platform reliably delivers signed results when reviews complete
**Depends on**: Phase 07 (v1.1 complete)
**Requirements**: DB-01, DB-02, DB-03, DB-04, CB-01, CB-02, CB-03, CB-04, CB-05
**Success Criteria** (what must be TRUE):
  1. A review submitted with a callback_url stores the URL and secret in the database without data loss to existing reviews
  2. When a review reaches COMPLETE state, the platform POSTs a HMAC-SHA256 signed payload to the callback_url
  3. Failed callback deliveries retry 3 times with exponential backoff, and the admin receives a Telegram notification after all retries exhaust
  4. Callback URLs pointing to non-RFC1918 addresses are rejected at submission time
  5. Telegram Bot token and allowed chat IDs are configurable via settings without code changes
**Plans**: 2 plans

Plans:
- [x] 08-01-PLAN.md — Add callback columns to Review model, Pydantic schemas, RFC1918 validator, Telegram settings, migration script
- [x] 08-02-PLAN.md — deliver_review_callback arq task with HMAC signing/retry, wire emit_state_change, integration tests

### Phase 09: Telegram Review Bot
**Goal**: Reviewers can approve or reject reviews entirely within Telegram, with inline buttons and status feedback
**Depends on**: Phase 08 (callback infrastructure for notification on failure)
**Requirements**: TG-01, TG-02, TG-03, TG-04, TG-05, TG-06, TG-07
**Success Criteria** (what must be TRUE):
  1. Telegram Bot starts automatically with FastAPI and stops gracefully on shutdown, sharing the event loop
  2. When a review enters APPROVING state, the bot sends an InlineKeyboard message with approve/reject buttons to allowed chat IDs
  3. Reviewer taps approve or reject and the review state transitions accordingly, with the message updated to show the final decision
  4. Reviews still in APPROVING state beyond the configured timeout trigger a reminder notification
  5. Review notification messages show previous approval decisions with timestamps
**UI hint**: yes
**Plans**: 2 plans

Plans:
- [x] 09-01-PLAN.md — Bot module: lifecycle, InlineKeyboard handlers, command handlers, notification builder (TG-01..05, TG-07)
- [x] 09-02-PLAN.md — FastAPI integration: lifespan wiring, APPROVING notification trigger, timeout reminder, real admin delivery (TG-06)

### Phase 10: kais-gold-team Integration
**Goal**: GPU tasks in kais-gold-team are automatically intercepted for review before dispatch, and resume on approval or fail on rejection
**Depends on**: Phase 08 (callback delivery)
**Requirements**: GT-01, GT-02, GT-03, GT-04, GT-05, GT-06
**Success Criteria** (what must be TRUE):
  1. Control node submits a review before dispatching a GPU task, including task type, GPU requirements, and requesting user as metadata
  2. High-risk GPU engines (Blender/FaceFusion) are automatically routed to HUMAN review; low-risk engines (TTS/SFX) are AUTO-approved
  3. Control node exposes /callback/review_result endpoint that receives approval/rejection from the review platform
  4. On approval callback, Guardian scheduling resumes for the approved task without manual intervention
  5. On rejection callback, the task is marked failed with the rejection reason and the user is notified via Telegram
**Plans**: 2 plans

Plans:
- [x] 10-01-PLAN.md -- Risk routing policy (gold_team_risk.yaml) + ReviewPlatformClient module for gold-team (GT-01, GT-02, GT-03)
- [x] 10-02-PLAN.md -- Guardian review interception, callback endpoint, polling + crash recovery (GT-01, GT-04, GT-05, GT-06)

### Phase 11: kais-movie-agent Integration
**Goal**: Movie-agent pipeline review gates use the remote review platform instead of local interactive review, with automatic resume or rollback
**Depends on**: Phase 08 (callback delivery)
**Requirements**: MA-01, MA-02, MA-03, MA-04, MA-05, MA-06, MA-07
**Success Criteria** (what must be TRUE):
  1. Node.js ReviewPlatformClient module can submit reviews, query status, and authenticate against the review platform REST API
  2. All 7 pipeline review gates call the review platform instead of launching local interactive-review.js servers
  3. Pipeline pauses after review submission and waits for callback approval/rejection before proceeding
  4. On approval callback, the pipeline auto-resumes to the next production phase
  5. On rejection callback, the pipeline rolls back to the previous phase using the existing git checkpoint mechanism
  6. Review notifications include material preview images (scene renders, storyboard frames) sent as Telegram photo messages
**Plans**: 2 plans

Plans:
- [x] 11-01-PLAN.md — Node.js ReviewPlatformClient, pipeline _runRemoteReview replacement, callback server with HMAC + resume/rollback (MA-01, MA-02, MA-03, MA-04, MA-05, MA-06)
- [x] 11-02-PLAN.md — Telegram sendPhoto for preview images in APPROVING notification (MA-07)

### Phase 12: Dual Bot Coordination & E2E
**Goal**: All review notifications flow through a single channel (review-platform Bot), and the complete integration works end-to-end across both external systems
**Depends on**: Phase 09, Phase 10, Phase 11
**Requirements**: E2E-01, E2E-02, E2E-03, E2E-04
**Success Criteria** (what must be TRUE):
  1. Gold-team Bot forwards review-related messages to the review-platform Bot so reviewers see all reviews in one place
  2. End-to-end flow works for gold-team: task submitted -> review created -> Telegram approval -> callback delivered -> task execution resumes
  3. End-to-end flow works for movie-agent: phase review submitted -> Telegram approval -> callback delivered -> pipeline resumes
  4. Rejection flows work end-to-end: review rejected -> callback delivered -> gold-team marks task failed / movie-agent rolls back
**Plans**: 2 plans

Plans:
- [ ] 12-01: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 01. Core Engine | v1.0 | 5/5 | Complete | 2026-05-05 |
| 02. Real-time Events | v1.0 | 2/2 | Complete | 2026-05-05 |
| 03. Review Frontend | v1.0 | 3/3 | Complete | 2026-05-05 |
| 04. Deployment & Hardening | v1.0 | 2/2 | Complete | 2026-05-05 |
| 05. Tech Debt Fixes | v1.1 | 2/2 | Complete | 2026-05-07 |
| 06. API + Event Integration Tests | v1.1 | 3/3 | Complete | 2026-05-07 |
| 07. Docker Stack Integration Tests | v1.1 | 1/1 | Complete | 2026-05-07 |
| 08. Schema & Callback Infrastructure | v1.2 | 2/2 | Complete    | 2026-05-07 |
| 09. Telegram Review Bot | v1.2 | 2/2 | Complete    | 2026-05-07 |
| 10. kais-gold-team Integration | v1.2 | 2/2 | Complete    | 2026-05-07 |
| 11. kais-movie-agent Integration | v1.2 | 2/2 | Complete   | 2026-05-07 |
| 12. Dual Bot Coordination & E2E | v1.2 | 0/? | Not started | - |
