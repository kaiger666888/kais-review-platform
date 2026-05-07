---
phase: 09-telegram-review-bot
plan: 01
subsystem: bot
tags: [telegram, python-telegram-bot, inline-keyboard, polling, notifications, chinese]

# Dependency graph
requires:
  - phase: 08-schema-callback
    provides: "transition_state(), Review/AuditEntry models, async_session_factory"
provides:
  - "Bot Application lifecycle (create, start, stop) with polling mode"
  - "InlineKeyboard approve/reject with callback_data format approve:{id}:{version}"
  - "Chinese notification message builder with approval history"
  - "Command handlers (/start, /help, /status) with chat ID allowlist"
  - "Idempotent callback handler for duplicate and stale button presses"
affects: [09-02, 12-e2e]

# Tech tracking
tech-stack:
  added: [python-telegram-bot==22.7]
  patterns:
    - "Bot module as standalone package (app/bot/) decoupled from FastAPI lifecycle"
    - "Local imports in handlers to avoid circular dependencies"
    - "callback_data format: action:review_id:version for optimistic locking"

key-files:
  created:
    - app/bot/__init__.py
    - app/bot/lifecycle.py
    - app/bot/notifications.py
    - app/bot/handlers.py
    - tests/test_bot_lifecycle.py
    - tests/test_bot_handlers.py
  modified:
    - requirements.txt

key-decisions:
  - "Bot module decoupled from FastAPI -- lifecycle managed externally, wired in Plan 02"
  - "Chinese message format for all bot interactions per CONTEXT decision"
  - "callback_data uses review version for optimistic locking integration"
  - "Empty telegram_bot_token returns None from create_bot_application (graceful degradation)"

patterns-established:
  - "Local imports in handlers to avoid circular dependency with app.core.database"
  - "Chat ID allowlist enforced on every handler and callback"
  - "bot_start/bot_stop are no-op when application is None"

requirements-completed: [TG-01, TG-02, TG-03, TG-04, TG-05, TG-07]

# Metrics
duration: 7min
completed: 2026-05-07
---

# Phase 09 Plan 01: Telegram Bot Module Summary

**Telegram bot lifecycle, InlineKeyboard approve/reject callbacks, Chinese notifications, and command handlers using python-telegram-bot v22**

## Performance

- **Duration:** 7 min
- **Started:** 2026-05-07T14:18:05Z
- **Completed:** 2026-05-07T14:25:36Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Complete Telegram bot module (app/bot/) with 4 source files, decoupled from FastAPI
- InlineKeyboard approve/reject with optimistic locking via callback_data version embedding
- Chinese-language notification messages with approval history and risk score formatting
- Idempotent callback handling for duplicate taps, stale callbacks, and concurrent modifications
- 38 new unit tests (22 lifecycle + 16 handler), total suite now 233 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Bot lifecycle module and notification builder (RED)** - `fb16ee4` (test)
2. **Task 1: Bot lifecycle module and notification builder (GREEN)** - `8db73fe` (feat)
3. **Task 2: Command handlers and InlineKeyboard callback handler** - `91c52ef` (feat)

_Note: Task 1 used TDD with RED and GREEN phases. No REFACTOR commit needed._

## Files Created/Modified
- `app/bot/__init__.py` - Package init exporting create_bot_application
- `app/bot/lifecycle.py` - Bot lifecycle: parse_allowed_chat_ids, create_bot_application, bot_start, bot_stop
- `app/bot/notifications.py` - build_notification_message (InlineKeyboard + Chinese text), build_status_text
- `app/bot/handlers.py` - start_handler, help_handler, status_handler, callback_handler
- `tests/test_bot_lifecycle.py` - 22 tests for lifecycle and notifications
- `tests/test_bot_handlers.py` - 16 tests for command and callback handlers
- `requirements.txt` - Added python-telegram-bot==22.7

## Decisions Made
- Bot module is standalone (app/bot/) to be wired into FastAPI in Plan 02
- Chinese message format for all bot interactions (per CONTEXT decision)
- callback_data format "action:review_id:version" integrates with optimistic locking
- Empty token returns None from create_bot_application, enabling graceful degradation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed truncation test assertion with unique content**
- **Found during:** Task 1 (TDD GREEN phase)
- **Issue:** Test used repeated "x" chars making substring assertions unreliable
- **Fix:** Changed test to use "abcdefghij" * 25 pattern for unique character sequence
- **Files modified:** tests/test_bot_lifecycle.py
- **Verification:** All 22 lifecycle tests pass
- **Committed in:** 8db73fe (Task 1 GREEN commit)

**2. [Rule 3 - Blocking] Fixed mock patch targets for local imports in handlers**
- **Found during:** Task 2 (test execution)
- **Issue:** async_session_factory and transition_state are locally imported in handlers, so patching app.bot.handlers.* fails
- **Fix:** Changed patch targets to app.core.database.async_session_factory and app.core.state_machine.transition_state
- **Files modified:** tests/test_bot_handlers.py
- **Verification:** All 16 handler tests pass
- **Committed in:** 91c52ef (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes were test-specific issues. No production code changes from deviations.

## Issues Encountered
None - clean execution.

## User Setup Required
None - no external service configuration required. Bot token will be configured via environment variable in Plan 02.

## Next Phase Readiness
- Bot module complete and testable, ready for FastAPI wiring in Plan 02
- callback_data format established: "approve:{review_id}:{version}"
- Actor format established: "telegram:{username_or_id}"
- handlers.py ready for FastAPI startup/shutdown event integration

---
*Phase: 09-telegram-review-bot*
*Completed: 2026-05-07*

## Self-Check: PASSED
- All 6 created files verified on disk
- 3 task commits verified in git log (fb16ee4, 8db73fe, 91c52ef)
- 233 total tests passing (38 new + 195 existing)
- No circular imports verified
