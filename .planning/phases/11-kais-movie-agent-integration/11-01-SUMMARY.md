---
phase: 11-kais-movie-agent-integration
plan: 01
subsystem: integration
tags: [nodejs, native-fetch, jwt, hmac, callback, pipeline, htmx, telegram]

# Dependency graph
requires:
  - phase: 08-callback-delivery
    provides: Callback infrastructure (HMAC signing, retry logic, deliver_review_callback)
  - phase: 09-telegram-bot
    provides: Telegram Bot InlineKeyboard approve/reject, photo sending
provides:
  - Node.js ReviewPlatformClient with JWT auth and zero npm dependencies
  - Pipeline remote review submission replacing local interactive-review
  - Callback server receiving HMAC-signed approval/rejection results
  - Pipeline resume/rollback triggered by callback delivery
affects: [12-e2e-testing]

# Tech tracking
tech-stack:
  added: [native-fetch, node:http, node:crypto, AbortSignal.timeout]
  patterns: [callback-driven-pipeline-pause-resume, fail-open-on-review-failure, jwt-cache-with-safety-margin]

key-files:
  created:
    - ../kais-movie-agent/lib/review-platform-client.js
    - ../kais-movie-agent/bin/callback-server.js
  modified:
    - ../kais-movie-agent/lib/pipeline.js

key-decisions:
  - "Pipeline resume spawns as detached child process via execFile (process isolation)"
  - "Callback server retries review_id lookup 3 times with 1s/3s delays (race condition mitigation)"
  - "All 6 review gates use moderate risk score 0.5 (tunable per phase later)"
  - "Callback handler uses workdir from review metadata to locate correct pipeline state"

patterns-established:
  - "ReviewPlatformClient: native fetch + AbortSignal.timeout + JWT cache with 60s safety margin"
  - "Callback-driven pipeline: submit review, save state, exit process; callback server spawns resume"
  - "Fail-open: review submission failure logs warning and proceeds without review"

requirements-completed: [MA-01, MA-02, MA-03, MA-04, MA-05, MA-06]

# Metrics
duration: 7min
completed: 2026-05-07
---

# Phase 11 Plan 01: Movie-Agent Review Platform Client Summary

**Node.js ReviewPlatformClient with native fetch JWT auth, pipeline remote review submission replacing 6 local review gates, and HMAC-verified callback server spawning pipeline resume/rollback**

## Performance

- **Duration:** 7 min
- **Started:** 2026-05-07T16:15:16Z
- **Completed:** 2026-05-07T16:22:41Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- ReviewPlatformClient class authenticates via JWT, submits reviews, queries status using zero npm dependencies (native fetch)
- All 6 pipeline review gates (art-direction, character, voice, scene, storyboard, camera) now submit to remote review platform instead of launching local HTTP servers
- Callback server verifies HMAC-SHA256 signatures and spawns pipeline resume on approval, git rollback on rejection
- Fail-open behavior when review platform is unreachable (logs warning, proceeds without review)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ReviewPlatformClient and callback-server modules** - `3650b01` (feat)
2. **Task 2: Replace pipeline review gates with remote review submission** - `4f255a2` (feat)

## Files Created/Modified
- `../kais-movie-agent/lib/review-platform-client.js` - ReviewPlatformClient class with JWT auth, submitReview, queryReviewStatus; ReviewClientError custom error
- `../kais-movie-agent/bin/callback-server.js` - HMAC-verified callback HTTP server (port 8766) with resume/rollback spawning
- `../kais-movie-agent/lib/pipeline.js` - Added _runRemoteReview() and _collectPreviewImages(); runPhase() now calls _runRemoteReview for all review gates

## Decisions Made
- Pipeline resume spawns as detached child process via execFile with unref() for clean process isolation
- Callback server retries review_id lookup 3 times with 1s/3s delays to handle race condition between callback and state file write
- All 6 review gates use moderate risk score 0.5 (tunable per phase in future)
- Callback handler uses workdir from review metadata to locate correct pipeline state file, with fallback search of PIPELINE_WORKDIR children
- Old _runReview() method preserved in pipeline.js but no longer called (anti-pattern: do not delete interactive-review.js)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ReviewPlatformClient ready for integration testing with live review platform API
- Callback server ready for deployment as long-running daemon on 192.168.71.38
- Pipeline remote review flow ready for end-to-end testing in Phase 12
- Plan 11-02 will handle Telegram photo notification for movie-agent review material

---
*Phase: 11-kais-movie-agent-integration*
*Completed: 2026-05-07*

## Self-Check: PASSED

- [x] lib/review-platform-client.js exists
- [x] bin/callback-server.js exists
- [x] lib/pipeline.js modified
- [x] 11-01-SUMMARY.md exists
- [x] Commit 3650b01 exists
- [x] Commit 4f255a2 exists
