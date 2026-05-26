---
phase: 08-schema-callback-infrastructure
plan: 02
subsystem: api, task-queue
tags: [arq, hmac, callback, httpx, retry, telegram, sse]

# Dependency graph
requires:
  - phase: 08-01
    provides: "Review.callback_url/callback_secret fields, Settings.telegram_bot_token/telegram_allowed_chat_ids"
provides:
  - "deliver_review_callback arq task with HMAC-SHA256 signing and exponential backoff retry"
  - "emit_state_change callback enqueue on COMPLETE state"
  - "_notify_telegram_admin helper for failure notification logging"
  - "CALLBACK_BACKOFF retry delay dict"
affects: [09-telegram-bot, 10-gold-team-integration, 11-movie-agent-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: [callback-delivery-task, hmac-signed-callback, telegram-notification-stub]

key-files:
  created:
    - tests/test_callback_delivery.py
  modified:
    - app/workers/tasks.py
    - app/core/events.py

key-decisions:
  - "Callback block in emit_state_change is self-contained with own arq_pool import to avoid dependency on webhook block success"
  - "Telegram notification is log-only stub; actual Bot delivery deferred to Phase 09"
  - "CALLBACK_BACKOFF separate from WEBHOOK_BACKOFF for independent tuning"

patterns-established:
  - "Callback delivery: same pattern as webhook delivery but per-review with X-Callback-Signature header"
  - "Failure notification: _notify_telegram_admin logs intent, actual delivery in later phase"

requirements-completed: [CB-01, CB-02, CB-03, CB-05]

# Metrics
duration: 6min
completed: 2026-05-07
---

# Phase 08 Plan 02: Callback Delivery Summary

**deliver_review_callback arq task with HMAC-SHA256 signing, 3x exponential backoff retry (1s/5s/30s), and Telegram failure notification stub wired into emit_state_change on COMPLETE state**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-07T13:19:39Z
- **Completed:** 2026-05-07T13:26:30Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- deliver_review_callback arq task delivers HMAC-SHA256 signed POST payloads to review.callback_url
- Exponential backoff retry with CALLBACK_BACKOFF (1s/5s/30s), max 3 attempts
- Telegram admin notification logged on permanent failure (actual Bot delivery deferred to Phase 09)
- emit_state_change enqueues callback delivery when review reaches COMPLETE state and has callback_url
- Reviews without callback_url skip callback delivery silently
- 14 comprehensive tests (11 unit + 3 integration), all 195 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement deliver_review_callback arq task with HMAC signing, retry, and Telegram failure logging** - `b18df12` (feat)
2. **Task 2: Wire emit_state_change to enqueue callback delivery and add integration test** - `a8077e4` (feat)

## Files Created/Modified
- `app/workers/tasks.py` - Added CALLBACK_BACKOFF, _notify_telegram_admin, deliver_review_callback; registered in WorkerSettings
- `app/core/events.py` - Added callback delivery enqueue block in emit_state_change for COMPLETE state
- `tests/test_callback_delivery.py` - 14 tests: success/HMAC signing, retry/backoff, edge cases, integration

## Decisions Made
- Callback block in emit_state_change is self-contained with its own `from app.main import app` to avoid NameError if webhook block fails before defining arq_pool
- Telegram notification uses log-only stub `_notify_telegram_admin`; actual Bot delivery deferred to Phase 09
- CALLBACK_BACKOFF is a separate dict from WEBHOOK_BACKOFF to allow independent tuning of retry delays

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed test mock pattern for structlog logger**
- **Found during:** Task 1 (TDD GREEN phase)
- **Issue:** Tests tried to patch `app.workers.tasks.logger` but logger is a local variable from `structlog.get_logger()`, not a module attribute
- **Fix:** Changed tests to patch `app.workers.tasks.structlog` and mock `get_logger()` return value
- **Files modified:** tests/test_callback_delivery.py
- **Verification:** All 14 tests pass
- **Committed in:** b18df12 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed callback block arq_pool variable scoping**
- **Found during:** Task 2 (events.py wiring)
- **Issue:** Plan referenced `arq_pool` from webhook block, but if webhook block throws exception, `arq_pool` is undefined, causing NameError in callback block
- **Fix:** Callback block has its own `from app.main import app` and creates `_arq_pool = app.state.arq_pool` independently
- **Files modified:** app/core/events.py
- **Verification:** Integration tests verify callback enqueue works independently
- **Committed in:** a8077e4 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes necessary for correctness and test reliability. No scope creep.

## Issues Encountered
- Integration test mocking required careful handling of `app.main.app` lazy import in emit_state_change; resolved by patching `app.main.app` directly rather than `app.core.events.app`

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Callback delivery infrastructure complete; Phase 09 (Telegram Bot) can implement actual `_notify_telegram_admin` delivery
- Phase 10 (gold-team integration) and Phase 11 (movie-agent integration) can rely on callback_url/callback_secret fields and deliver_review_callback task
- CB-04 (callback URL validation) was handled in Plan 08-01 (RFC1918 + loopback + link-local SSRF validation)

---
*Phase: 08-schema-callback-infrastructure*
*Completed: 2026-05-07*

## Self-Check: PASSED
- All 3 modified/created files verified present
- Both task commits (b18df12, a8077e4) verified in git log
- 195 tests passing (14 new callback delivery + 181 existing)
