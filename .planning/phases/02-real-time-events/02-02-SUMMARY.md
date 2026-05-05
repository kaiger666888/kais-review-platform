---
phase: 02-real-time-events
plan: 02
subsystem: api, real-time, workers
tags: [webhooks, arq, retry, exponential-backoff, hmac, sse, events, asyncio, httpx]

# Dependency graph
requires:
  - phase: 02-real-time-events/01
    provides: EventManager singleton, SSE endpoint, WebhookConfig model, webhook CRUD API
provides:
  - deliver_webhook arq task with HMAC-SHA256 signatures and exponential backoff retry
  - emit_state_change function wiring state transitions to SSE broadcast and webhook enqueue
  - State machine integration via lazy import to avoid circular dependencies
  - WorkerSettings with httpx client lifecycle management
affects: [03-phase-webhooks, event-pipeline, state-machine]

# Tech tracking
tech-stack:
  added: [httpx.AsyncClient, arq.Retry, hmac/hmac.new, hashlib.sha256]
  patterns: [arq Retry for exponential backoff, lazy import to break circular deps, HMAC-SHA256 webhook signatures]

key-files:
  created:
    - tests/test_events.py
    - tests/test_webhooks.py
  modified:
    - app/workers/tasks.py
    - app/core/events.py
    - app/core/state_machine.py

key-decisions:
  - "Lazy import of emit_state_change inside transition_state to avoid circular import (events imports app.main)"
  - "emit_state_change catches all exceptions from webhook enqueue path for graceful degradation"
  - "WorkerSettings on_startup/on_shutdown manage httpx.AsyncClient lifecycle in arq context"
  - "WEBHOOK_BACKOFF {1:1, 2:5, 3:30} maps try_number to delay in seconds"

patterns-established:
  - "Webhook delivery pattern: arq task per delivery with HMAC signature, exponential backoff via Retry exception"
  - "Event emission pattern: state machine emits to SSE + webhook queue after audit logging"
  - "Test mock pattern: patch app.core.database.async_session_factory for deliver_webhook tests with in-memory DB"

requirements-completed: [EVNT-03, EVNT-04]

# Metrics
duration: 7min
completed: 2026-05-05
---

# Phase 02 Plan 02: Event Emission & Webhook Delivery Summary

**Webhook delivery with HMAC-SHA256 signatures and exponential backoff retry wired into state machine transitions, completing the real-time event pipeline from state change to SSE broadcast and external system notification**

## Performance

- **Duration:** 7 min
- **Started:** 2026-05-05T23:07:13Z
- **Completed:** 2026-05-05T23:14:58Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- deliver_webhook arq task with HMAC-SHA256 signing, exponential backoff (1s, 5s, 30s), max 3 retries
- emit_state_change function broadcasts SSE events and enqueues webhook deliveries for all active configs
- State machine integration via lazy import -- transition_state emits events after every successful transition
- WorkerSettings updated with on_startup/on_shutdown for httpx.AsyncClient lifecycle
- 20 new tests covering EventManager, emit_state_change, webhook delivery, retry logic, HMAC signatures
- All 109 tests pass (89 existing + 20 new)

## Task Commits

Each task was committed atomically:

1. **Task 1: deliver_webhook arq task and emit_state_change integration into state machine** - `a5aabf8` (feat)
2. **Task 2: Tests for EventManager, SSE, webhook delivery, and event emission pipeline** - `1804f10` (test)

## Files Created/Modified
- `app/workers/tasks.py` - Added deliver_webhook arq task with HMAC-SHA256, Retry backoff, updated WorkerSettings with on_startup/on_shutdown
- `app/core/events.py` - Added emit_state_change function for SSE broadcast + webhook enqueue
- `app/core/state_machine.py` - Added lazy import of emit_state_change call after audit logging in transition_state
- `tests/test_events.py` - 11 tests for EventManager broadcast, connection management, slow client drop, emit_state_change SSE and graceful arq degradation
- `tests/test_webhooks.py` - 9 tests for WebhookConfig model, deliver_webhook success/HMAC/retry/exhaustion/edge cases

## Decisions Made
- Lazy import pattern inside transition_state body to break circular import chain (events.py -> app.main -> state_machine)
- emit_state_change catches all exceptions from webhook path so SSE broadcast always succeeds even when arq/DB unavailable
- arq Retry exception raised with defer=WEBHOOK_BACKOFF[job_try+1] (looks up next try's delay, not current)
- Test patching targets app.core.database.async_session_factory (not app.workers.tasks) since deliver_webhook uses lazy imports

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertions used wrong arq Retry attribute name**
- **Found during:** Task 2 (test execution)
- **Issue:** Plan specified `Retry.defer` but arq uses `defer_score` (in milliseconds)
- **Fix:** Updated test assertions to use `exc_info.value.defer_score` with correct millisecond values
- **Files modified:** tests/test_webhooks.py
- **Verification:** All 20 new tests pass
- **Committed in:** 1804f10 (Task 2 commit)

**2. [Rule 1 - Bug] Test mock path was wrong for lazy imports**
- **Found during:** Task 2 (test execution)
- **Issue:** Patching `app.workers.tasks.async_session_factory` fails because deliver_webhook uses `from app.core.database import async_session_factory` inside the function body
- **Fix:** Changed mock target to `app.core.database.async_session_factory` where the name is actually defined
- **Files modified:** tests/test_webhooks.py
- **Verification:** All 20 new tests pass
- **Committed in:** 1804f10 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes were test-only corrections for correct arq API usage and Python mock targeting. No production code changes needed.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Complete event pipeline operational: state change -> SSE broadcast + webhook enqueue -> HMAC-signed delivery with retry
- Ready for Phase 03 to build consuming systems and production monitoring
- Webhook delivery requires Redis/arq to be running for production; gracefully degrades without it

---
*Phase: 02-real-time-events*
*Completed: 2026-05-05*

## Self-Check: PASSED

- FOUND: app/workers/tasks.py
- FOUND: app/core/events.py
- FOUND: app/core/state_machine.py
- FOUND: tests/test_events.py
- FOUND: tests/test_webhooks.py
- FOUND: .planning/phases/02-real-time-events/02-02-SUMMARY.md
- FOUND: a5aabf8 (Task 1 commit)
- FOUND: 1804f10 (Task 2 commit)
