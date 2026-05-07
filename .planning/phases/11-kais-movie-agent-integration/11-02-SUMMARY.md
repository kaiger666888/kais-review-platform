---
phase: 11-kais-movie-agent-integration
plan: 02
subsystem: api
tags: [telegram-bot, preview-images, send_photo, base64, movie-agent]

# Dependency graph
requires:
  - phase: 09-telegram-bot
    provides: "Telegram Bot lifecycle, notification message builder, InlineKeyboard handlers"
  - phase: 10-kais-gold-team-integration
    provides: "emit_state_change APPROVING notification block pattern"
provides:
  - "Preview image caption builder (build_review_captions)"
  - "send_photo calls before InlineKeyboard notification for movie-agent reviews"
  - "MA-07: Material preview images in Telegram for movie-agent APPROVING state"
affects: [phase-12-e2e-testing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Preview image sending with graceful degradation: photo failures logged but do not block text notification"
    - "Source-system-filtered image sending: only kais-movie-agent triggers photos"

key-files:
  created: []
  modified:
    - app/bot/notifications.py
    - app/core/events.py

key-decisions:
  - "Photo sending only for kais-movie-agent source system (gold-team reviews have no images)"
  - "Max 3 preview images per review notification"
  - "Images sent BEFORE InlineKeyboard text so they appear above approve/reject buttons in Telegram"

patterns-established:
  - "Pre-notification media delivery: send visual context before interactive UI elements"

requirements-completed: [MA-07]

# Metrics
duration: 3min
completed: 2026-05-07
---

# Phase 11 Plan 02: Telegram Preview Images Summary

**Telegram Bot sends up to 3 base64-decoded preview images as photo messages before the InlineKeyboard approve/reject notification for movie-agent reviews entering APPROVING state**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-07T16:16:01Z
- **Completed:** 2026-05-07T16:19:07Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Added `build_review_captions` helper that generates Chinese-language captions with phase name, episode, and image index
- Extended `emit_state_change` APPROVING block to decode and send preview images via `send_photo` before the text+InlineKeyboard notification
- Photo sending failures are caught per-image and per-chat, logged as warnings, and never block text notification delivery
- Only `kais-movie-agent` source system triggers photo sending (gold-team reviews have no images)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add preview image sending to Telegram notification flow** - `830a62c` (feat)

## Files Created/Modified
- `app/bot/notifications.py` - Added `build_review_captions` function for generating image captions from review metadata
- `app/core/events.py` - Added preview image sending block with base64 decode, send_photo, and error handling in APPROVING notification flow

## Decisions Made
- Photo sending only for `kais-movie-agent` source system -- gold-team reviews don't have preview images
- Max 3 images per review to avoid Telegram rate limiting
- Images sent BEFORE text+InlineKeyboard so they appear above the approve/reject buttons in Telegram chat
- Each image decode failure and each per-chat send failure logged separately for debugging

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Preview image delivery complete for movie-agent reviews
- 260 tests passing, no regressions
- Ready for Phase 12 E2E testing which will exercise the full movie-agent review flow including preview images

---
*Phase: 11-kais-movie-agent-integration*
*Completed: 2026-05-07*
