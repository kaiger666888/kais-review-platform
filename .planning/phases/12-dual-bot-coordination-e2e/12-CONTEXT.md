# Phase 12: Dual Bot Coordination & E2E - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning

<domain>
## Phase Boundary

All review notifications flow through a single channel (review-platform Bot), and the complete integration works end-to-end across both external systems. This phase verifies the full review lifecycle for both gold-team and movie-agent integrations, including approval and rejection flows with callback delivery verification.

Requirements: E2E-01, E2E-02, E2E-03, E2E-04

</domain>

<decisions>
## Implementation Decisions

### Bot Forwarding (E2E-01)
- Gold-team uses review-platform Bot directly for review notifications — no forwarding bridge needed. Gold-team already submits reviews via API, review-platform Bot sends notifications automatically.
- Integration test verifies single-channel notification: submit review via gold-team client → verify review-platform Bot receives notification with InlineKeyboard
- Document coordination pattern in gold-team client docstring

### E2E Testing Strategy (E2E-02, E2E-03, E2E-04)
- HTTP-level integration tests with mock callback servers — no need to run actual external systems
- Tests live in `tests/integration/test_e2e_flows.py`
- 6 test cases total: gold-team approve, gold-team reject, movie-agent approve, movie-agent reject, callback retry on failure, invalid callback signature
- Direct API calls with `httpx.AsyncClient` + JWT auth, mock callback servers for receiving results

### Test Implementation Details
- Mock callback server: `aiohttp` test servers that record received callbacks — lightweight, async-first
- Verify HMAC signature in callback handler, payload fields (review_id, disposition, source_system), correct callback URL
- Shared fixtures in `tests/integration/conftest.py` — gold-team and movie-agent review submission payloads

### Claude's Discretion
- Exact test function names and structure
- Fixture implementation details
- Error message format in tests
- Test ordering and isolation strategy

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/bot/notifications.py` — build_notification_message(), build_review_captions(), build_status_text()
- `app/bot/handlers.py` — InlineKeyboard callback handlers for approve/reject
- `app/bot/lifecycle.py` — Bot lifecycle management (init/start/stop)
- `app/core/events.py` — emit_state_change() with SSE + webhook + Telegram notification + sendPhoto for preview images
- `app/workers/tasks.py` — deliver_review_callback with HMAC signing, retry with backoff
- `app/integrations/gold_team/client.py` — ReviewPlatformClient with submit_gpu_review(), query_review_status()
- `app/api/v1/reviews.py` — POST /api/v1/reviews, GET /api/v1/reviews/{id}
- `app/core/state_machine.py` — transition_state() for approve/reject

### Established Patterns
- Integration tests: `tests/integration/test_api_flows.py`, `test_sse_flows.py`, `test_webhook_flows.py`
- Test fixtures: `tests/conftest.py` with async client, db session, auth helpers
- Integration fixtures: `tests/integration/conftest.py` with shared test infrastructure
- Callback delivery: HMAC-SHA256 signed POST to callback_url with X-Callback-Signature header
- Bot testing: `tests/test_bot_integration.py` with mocked Bot instance

### Integration Points
- Review submission API → policy evaluation → state transition → Bot notification → callback delivery
- Gold-team review flow: POST /api/v1/reviews (source_system=kais-gold-team) → approve → callback to gold-team
- Movie-agent review flow: POST /api/v1/reviews (source_system=kais-movie-agent) → approve → callback to movie-agent
- Callback payload: review_id, old_state, new_state, timestamp, source_system, disposition, disposition_action

</code_context>

<specifics>
## Specific Ideas

- Gold-team callback URL format: http://192.168.71.140:8900/callback/review_result
- Movie-agent callback URL format: http://192.168.71.38:8766/callback
- Both systems already submit reviews with callback_url and callback_secret
- Review platform Bot already sends notifications for ALL reviews regardless of source_system
- The "dual bot coordination" is primarily about verification that the single-channel notification pattern works
- 260 existing tests pass — E2E tests should not break any

</specifics>

<deferred>
## Deferred Ideas

- Full Docker Compose E2E with actual external systems running — too heavy for this phase
- Performance/stress testing under concurrent review submissions
- Telegram Bot forwarding between separate Bot instances (not needed — single Bot pattern)

</deferred>
