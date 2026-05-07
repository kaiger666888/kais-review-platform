# Requirements: Kai's Review Platform — v1.2 External System Integration

**Defined:** 2026-05-07
**Core Value:** Strategy-engine-driven review routing — every AI production task must pass policy evaluation before execution

## v1.2 Requirements

### Database & Config Extension

- [x] **DB-01**: Review model supports per-review `callback_url` field for external system callbacks
- [x] **DB-02**: Review model supports per-review `callback_secret` field for HMAC-SHA256 callback signatures
- [x] **DB-03**: Settings model supports Telegram Bot configuration (token, allowed chat IDs, review timeout)
- [x] **DB-04**: Database migration script adds new columns to existing Review table without data loss

### Callback Delivery

- [x] **CB-01**: New arq task `deliver_review_callback` delivers review result to callback_url when review reaches COMPLETE state
- [x] **CB-02**: Callback payloads are HMAC-SHA256 signed using per-review callback_secret
- [x] **CB-03**: Callback delivery retries on failure (3 attempts, exponential backoff: 1s/5s/30s)
- [x] **CB-04**: Callback URL validated as RFC1918 private address only (SSRF mitigation for LAN deployment)
- [x] **CB-05**: Telegram admin notification when all callback retry attempts fail

### Telegram Bot Core

- [x] **TG-01**: Telegram Bot runs in polling mode inside FastAPI process, sharing event loop via python-telegram-bot v22
- [x] **TG-02**: Bot lifecycle managed in FastAPI lifespan (initialize + start + graceful shutdown)
- [x] **TG-03**: Bot sends review notification with InlineKeyboard approve/reject buttons when review enters APPROVING state
- [x] **TG-04**: Bot handles InlineKeyboard callback: approve or reject review via direct `transition_state()` call
- [x] **TG-05**: Bot edits notification message after approval/rejection to show final status
- [x] **TG-06**: Bot sends timeout reminder if review remains in APPROVING state beyond configured threshold
- [x] **TG-07**: Bot displays approval history (previous decisions with timestamps) in review notification

### kais-gold-team Integration

- [x] **GT-01**: gold-team control_node submits review to review-platform before dispatching GPU task to worker
- [x] **GT-02**: Review submission includes task type, GPU resource requirements, and requesting user as metadata
- [x] **GT-03**: Risk score auto-calculated based on GPU engine type (Blender/FaceFusion = high, TTS/SFX = low)
- [x] **GT-04**: gold-team adds callback endpoint `/callback/review_result` on control_node to receive approval/rejection
- [x] **GT-05**: On approval callback, control_node automatically resumes Guardian scheduling for the approved task
- [x] **GT-06**: On rejection callback, control_node marks task as failed with rejection reason and notifies user via Telegram

### kais-movie-agent Integration

- [ ] **MA-01**: Node.js HTTP client module (`ReviewPlatformClient`) for calling review-platform REST API (submit, query, auth)
- [ ] **MA-02**: Pipeline review gates replaced: `interactive-review.js` submits to review-platform instead of launching local HTTP server
- [ ] **MA-03**: Pipeline pauses after review submission, waiting for callback approval/rejection
- [ ] **MA-04**: movie-agent adds callback HTTP endpoint to receive approval/rejection results
- [ ] **MA-05**: On approval callback, pipeline auto-resumes to next phase
- [ ] **MA-06**: On rejection callback, pipeline rolls back to previous phase using existing git checkpoint mechanism
- [x] **MA-07**: Review notification includes material preview images (scene renders, storyboard frames) sent as Telegram photo messages

### Dual Bot Coordination & E2E

- [ ] **E2E-01**: gold-team Bot forwards review-related messages to review-platform Bot (single review notification channel)
- [ ] **E2E-02**: End-to-end test: gold-team task → review submission → Telegram approval → callback → task execution resumes
- [ ] **E2E-03**: End-to-end test: movie-agent phase → review submission → Telegram approval → callback → pipeline resumes
- [ ] **E2E-04**: End-to-end test: review rejection → callback → gold-team marks task failed / movie-agent rolls back

## Future Requirements

### Deferred to v1.3+

- **TG-AI-01**: Bot supports conversational approval (ask reviewer follow-up questions before deciding)
- **GT-BATCH-01**: Batch review submission for multiple GPU tasks
- **MA-MULTI-01**: Parallel review gates (submit multiple phases for review simultaneously)
- **DASH-01**: Review analytics dashboard (approval rates, response times, per-system breakdown)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Webhook mode for Telegram Bot | LAN deployment has no public IP; polling mode is the only viable option |
| OAuth/SSO for external systems | API key + JWT sufficient for LAN deployment |
| Real-time WebSocket bidirectional communication | SSE + callback HTTP sufficient; WebSocket adds complexity without benefit |
| Cross-system file transfer via review-platform | Artifacts stay in their respective systems; review-platform only handles metadata and decisions |
| Mobile native app | Mobile web + Telegram Bot cover all review scenarios |
| AI-powered auto-approval | v1.2 focuses on human-in-the-loop; AI audit plugin deferred to future milestone |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DB-01 | Phase 08 | Complete |
| DB-02 | Phase 08 | Complete |
| DB-03 | Phase 08 | Complete |
| DB-04 | Phase 08 | Complete |
| CB-01 | Phase 08 | Complete |
| CB-02 | Phase 08 | Complete |
| CB-03 | Phase 08 | Complete |
| CB-04 | Phase 08 | Complete |
| CB-05 | Phase 08 | Complete |
| TG-01 | Phase 09 | Complete |
| TG-02 | Phase 09 | Complete |
| TG-03 | Phase 09 | Complete |
| TG-04 | Phase 09 | Complete |
| TG-05 | Phase 09 | Complete |
| TG-06 | Phase 09 | Complete |
| TG-07 | Phase 09 | Complete |
| GT-01 | Phase 10 | Complete |
| GT-02 | Phase 10 | Complete |
| GT-03 | Phase 10 | Complete |
| GT-04 | Phase 10 | Complete |
| GT-05 | Phase 10 | Complete |
| GT-06 | Phase 10 | Complete |
| MA-01 | Phase 11 | Pending |
| MA-02 | Phase 11 | Pending |
| MA-03 | Phase 11 | Pending |
| MA-04 | Phase 11 | Pending |
| MA-05 | Phase 11 | Pending |
| MA-06 | Phase 11 | Pending |
| MA-07 | Phase 11 | Complete |
| E2E-01 | Phase 12 | Pending |
| E2E-02 | Phase 12 | Pending |
| E2E-03 | Phase 12 | Pending |
| E2E-04 | Phase 12 | Pending |

**Coverage:**
- v1.2 requirements: 33 total
- Mapped to phases: 33
- Unmapped: 0

---
*Requirements defined: 2026-05-07*
*Last updated: 2026-05-07 after roadmap creation*
