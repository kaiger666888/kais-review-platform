---
phase: 09-telegram-review-bot
plan: 02
subsystem: bot-integration
tags: [telegram, fastapi-lifespan, notifications, timeout-reminders, inline-keyboard, integration]

# Dependency graph
requires:
  - phase: 09-01
    provides: "Bot module (app/bot/) with lifecycle, handlers, notifications, InlineKeyboard"
provides:
  - "Bot wired into FastAPI lifespan (startup/shutdown with graceful degradation)"
  - "APPROVING state triggers InlineKeyboard notification to all allowed chat IDs"
  - "Timeout reminder notifications at 80% of timeout threshold"
  - "Real _notify_telegram_admin replacing log-only stub"
affects: [12-e2e]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Bot lifecycle managed via FastAPI lifespan with try/except graceful degradation"
    - "Self-contained notification block in emit_state_change with own imports"
    - "arq worker context passes bot_application for timeout reminder delivery"
    - "Source-level mocking for locally imported modules in tests"

key-files:
  created:
    - tests/test_bot_integration.py
  modified:
    - app/main.py
    - app/core/events.py
    - app/workers/tasks.py
    - tests/test_callback_delivery.py

key-decisions:
  - "Bot startup failure logged but does not crash FastAPI (graceful degradation)"
  - "Telegram notification block in emit_state_change is self-contained with own imports (same pattern as callback block)"
  - "check_timeout_reminders runs every 30 minutes via arq cron, warns at 80% of timeout threshold"
  - "bot_application passed via arq on_startup context for worker access"

patterns-established:
  - "Source-level mocking (app.core.database.* not app.core.events.*) for locally imported modules"
  - "try/except around bot lifecycle to prevent bot failures from affecting FastAPI"

requirements-completed: [TG-06]

# Metrics
duration: 11min
completed: 2026-05-07
---

# Phase 09 Plan 02: Bot Integration Wiring Summary

**Telegram bot wired into FastAPI lifespan with APPROVING notifications, timeout reminders at 80% threshold, and real admin notification delivery**

## Performance

- **Duration:** 11 min
- **Started:** 2026-05-07T14:28:49Z
- **Completed:** 2026-05-07T14:40:44Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Bot starts/stops automatically with FastAPI lifecycle (graceful degradation on failure)
- Reviews entering APPROVING state trigger InlineKeyboard notifications to all allowed chat IDs
- Timeout reminder cron job sends warnings at 80% of configured timeout threshold
- _notify_telegram_admin delivers actual Telegram messages (replaces Phase 08 log-only stub)
- 13 integration tests covering all wiring behaviors, 246 total tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire bot into FastAPI lifespan and emit_state_change notification trigger** - `84cc150` (feat)
2. **Task 2: Timeout reminder and real _notify_telegram_admin delivery** - `df74706` (feat)

## Files Created/Modified
- `app/main.py` - Bot lifecycle init/start/stop in FastAPI lifespan with error handling
- `app/core/events.py` - Telegram notification block for APPROVING state transitions
- `app/workers/tasks.py` - Real _notify_telegram_admin, check_timeout_reminders cron job
- `tests/test_bot_integration.py` - 13 integration tests for bot wiring and notification triggers
- `tests/test_callback_delivery.py` - Updated test for new _notify_telegram_admin log event name

## Decisions Made
- Bot startup failure does not crash FastAPI -- logs warning and sets bot_application to None
- Telegram notification block in emit_state_change is self-contained with its own imports (follows callback block pattern from Phase 08)
- check_timeout_reminders uses 80% threshold to warn before escalation (not after)
- bot_application passed via arq worker context for background task access to bot

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing callback delivery test for new _notify_telegram_admin log event**
- **Found during:** Task 2 (full test suite regression)
- **Issue:** Existing test expected log event "telegram_admin_notification_pending" which was renamed to "telegram_admin_notification_sent" in new implementation. Test also needed to handle "telegram_admin_notification_skipped" when bot not configured.
- **Fix:** Updated test assertion to accept both "sent" and "skipped" event names
- **Files modified:** tests/test_callback_delivery.py
- **Verification:** All 246 tests pass
- **Committed in:** df74706 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor test adjustment for renamed log event. No production code deviation.

## Issues Encountered
None - clean execution.

## User Setup Required
None - no external service configuration required. Bot token and chat IDs configured via environment variables (TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_CHAT_IDS).

## Next Phase Readiness
- Phase 09 complete -- Telegram bot fully wired into FastAPI with notifications and reminders
- Ready for Phase 10 (gold-team integration) or Phase 11 (movie-agent integration)
- Both depend on Phase 08 callback infrastructure (already complete)

---
*Phase: 09-telegram-review-bot*
*Completed: 2026-05-07*

## Self-Check: PASSED
- All 5 modified files verified on disk
- 2 task commits verified in git log (84cc150, df74706)
- 246 total tests passing (13 new + 233 existing)
- No import errors verified
