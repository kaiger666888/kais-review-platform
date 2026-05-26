---
phase: 08-schema-callback-infrastructure
plan: 01
subsystem: database, api
tags: [callback, rfc1918, ssrf-mitigation, pydantic, sqlalchemy, migration, telegram]

# Dependency graph
requires:
  - phase: 07-v1.1-completion
    provides: "Stable test suite and codebase for extending"
provides:
  - "Review model with callback_url and callback_secret columns"
  - "RFC1918 callback URL validator (validate_callback_url)"
  - "Pydantic schemas accepting callback fields"
  - "Telegram settings in config (bot_token, chat_ids, timeout)"
  - "Migration script for existing databases"
  - "Review submission endpoint with callback validation"
affects: [09-telegram-bot, 10-gold-team-integration, 11-movie-agent-integration]

# Tech tracking
tech-stack:
  added: [ipaddress, socket, urllib.parse for RFC1918 validation]
  patterns: [RFC1918 SSRF mitigation, nullable column migration, callback-secret exclusion from API responses]

key-files:
  created:
    - app/core/validation.py
    - migrations/add_callback_fields.sql
    - tests/test_callback_validation.py
  modified:
    - app/models/schema.py
    - app/models/schemas.py
    - app/core/config.py
    - app/api/v1/reviews.py

key-decisions:
  - "RFC1918 + loopback + link-local ranges for callback URL validation (CB-04)"
  - "callback_secret excluded from ReviewResponse to prevent API exposure"
  - "Telegram settings default to empty/disabled (no .env changes required for existing deployments)"
  - "review_timeout_minutes defaults to 1440 (24h) matching existing DEFAULT_TIMEOUT constant"

patterns-established:
  - "RFC1918 SSRF mitigation: validate callback URLs resolve to private IPs before storage"
  - "Secret exclusion pattern: callback_secret stored in DB but never returned in API responses"
  - "Idempotent migration: ALTER TABLE ADD COLUMN with nullable columns, no data loss"

requirements-completed: [DB-01, DB-02, DB-03, DB-04, CB-04]

# Metrics
duration: 3min
completed: 2026-05-07
---

# Phase 08 Plan 01: Schema & Callback Fields Summary

**Per-review callback fields with RFC1918 SSRF validation, Telegram config, and migration script for external system integration**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-07T13:13:48Z
- **Completed:** 2026-05-07T13:17:12Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Review model extended with nullable callback_url and callback_secret columns for per-review webhook delivery
- RFC1918 validator prevents SSRF attacks by rejecting callback URLs that resolve to public IPs
- Telegram settings added to config (bot_token, chat_ids, timeout) with safe defaults
- Review submission endpoint validates callback URLs at request time, returns 422 for public IPs
- All 181 tests pass (163 existing + 18 new), fully backward compatible

## Task Commits

Each task was committed atomically:

1. **Task 1: Add callback columns, RFC1918 validator, schemas, migration (TDD)** - `12fe92c` (test) + `5113868` (feat)
2. **Task 2: Add Telegram settings, wire callback into review submission** - `da61bb6` (feat)

## Files Created/Modified
- `app/core/validation.py` - RFC1918 callback URL validator with hostname DNS resolution
- `migrations/add_callback_fields.sql` - Idempotent ALTER TABLE migration for existing databases
- `tests/test_callback_validation.py` - 18 tests covering validation, model, and schema behavior
- `app/models/schema.py` - Review model with callback_url and callback_secret columns
- `app/models/schemas.py` - ReviewCreateRequest and ReviewResponse with callback fields
- `app/core/config.py` - Settings with telegram_bot_token, telegram_allowed_chat_ids, review_timeout_minutes
- `app/api/v1/reviews.py` - Review submission with callback validation and storage

## Decisions Made
- RFC1918 + loopback (127.0.0.0/8) + link-local (169.254.0.0/16) for callback URL validation -- covers local development alongside production private networks
- callback_secret is stored in DB but never exposed via ReviewResponse -- prevents secret leakage through API
- Telegram settings default to empty strings / 1440 minutes so existing deployments work without .env changes
- Used ipaddress.ip_address/ip_network for range checks rather than string manipulation -- cleaner, more correct

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Callback infrastructure ready for Phase 09 (Telegram Bot) to deliver review notifications with callback URLs
- Callback fields ready for Phase 10 (gold-team) and Phase 11 (movie-agent) to register callback URLs on review submission
- Migration script ready for deployment to existing database

---
*Phase: 08-schema-callback-infrastructure*
*Completed: 2026-05-07*

## Self-Check: PASSED

All 7 files verified present. All 3 commits verified in git log.
