---
phase: 10-kais-gold-team-integration
plan: 02
subsystem: integration
tags: [gold-team, gpu-task-review, callback, polling, checkpoint-recovery, hmac, guardian]

# Dependency graph
requires:
  - phase: 10-kais-gold-team-integration/01
    provides: ReviewPlatformClient, submit_gpu_review API, JWT auth for gold-team
provides:
  - REVIEWING state in gold-team TaskStatus enum
  - POST /callback/review_result endpoint on control_node
  - Guardian GPU task review interception with poll-based approval waiting
  - Crash recovery via .review_checkpoint files
affects: [12-e2e-testing, gold-team-guardian-lifecycle]

# Tech tracking
tech-stack:
  added: [httpx for review platform REST calls in worker_node]
  patterns: [review-checkpoint-recovery, fail-open-on-submission-error, gpu-task-review-interception]

key-files:
  created:
    - ../kais-gold-team/kais-hub/worker_node/review_check.py
  modified:
    - ../kais-gold-team/kais-hub/shared/status.py
    - ../kais-gold-team/kais-hub/control_node/api/__init__.py
    - ../kais-gold-team/kais-hub/worker_node/guardian.py

key-decisions:
  - "Review interception uses direct httpx REST calls instead of importing ReviewPlatformClient to avoid cross-repo dependency at runtime"
  - "Fail-open on review submission failure: if review platform unreachable, task proceeds without review (logged warning)"
  - "Polling with 30s interval and 24h max duration, JWT token auto-refresh on 401"
  - "Checkpoint recovery via .review_checkpoint JSON files in .running/ directory"

patterns-established:
  - "GPU task review gate: Guardian._handle_review() before executor.execute() with APPROVED/REJECTED/TIMEOUT flow"
  - "Review checkpoint: save review_id on submission, load on crash recovery, clear after resolution"

requirements-completed: [GT-01, GT-04, GT-05, GT-06]

# Metrics
duration: 4min
completed: 2026-05-07
---

# Phase 10 Plan 02: Gold-team Review Interception Summary

**Guardian GPU task review interception with REVIEWING state, /callback/review_result endpoint, 30s polling loop, and crash recovery via checkpoint files**

## Performance

- **Duration:** 4 min
- **Started:** 2026-05-07T15:11:38Z
- **Completed:** 2026-05-07T15:15:36Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added REVIEWING state to gold-team TaskStatus enum with valid transitions (SYNCED_TO_WORKER->REVIEWING->RUNNING/FAILED)
- Created /callback/review_result HMAC-verified endpoint on control_node for receiving review platform callbacks
- Guardian intercepts GPU tasks before execution, submits to review platform, waits for approval via polling
- Crash recovery via .review_checkpoint files -- on restart, Guardian resumes polling from saved review_id

## Task Commits

Each task was committed atomically:

1. **Task 1: Add REVIEWING state and /callback/review_result endpoint** - `d43e03a` (feat)
2. **Task 2: Intercept GPU tasks in Guardian for review with polling and crash recovery** - `f97fd28` (feat)

## Files Created/Modified
- `../kais-gold-team/kais-hub/shared/status.py` - Added REVIEWING enum value, updated VALID_TRANSITIONS and WORKER_STATES
- `../kais-gold-team/kais-hub/control_node/api/__init__.py` - Added ReviewResultPayload model and POST /callback/review_result endpoint
- `../kais-gold-team/kais-hub/worker_node/review_check.py` - New module: submit_for_review(), poll_review_status(), checkpoint save/load/clear
- `../kais-gold-team/kais-hub/worker_node/guardian.py` - Added review interception in _execute_task(), _handle_review() method

## Decisions Made
- Used direct httpx REST calls instead of importing ReviewPlatformClient to avoid cross-repo runtime dependency -- worker_node runs independently
- Fail-open on review submission failure -- if review platform is unreachable, task proceeds with logged warning rather than blocking the entire GPU pipeline
- 24-hour max poll duration with 30-second intervals -- long enough for human review cycles, short enough interval for responsive feedback
- Checkpoint files stored in .running/ directory alongside existing PID markers for consistency with Guardian file management

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- `python` command not available on system, used `python3` instead for verification -- no code impact

## User Setup Required

Environment variables needed for review platform integration:
- `REVIEW_PLATFORM_API_KEY` - API key for authenticating with review platform
- `REVIEW_CALLBACK_SECRET` - HMAC secret for callback payload verification

## Next Phase Readiness
- Gold-team review integration complete (Plan 10-01 client + Plan 10-02 interception)
- Phase 11 (movie-agent integration) can proceed independently
- Phase 12 (E2E testing) depends on Phases 10 and 11 completion

---
*Phase: 10-kais-gold-team-integration*
*Completed: 2026-05-07*

## Self-Check: PASSED

- All 4 modified/created files verified present in gold-team repo
- Both task commits found in gold-team git log (d43e03a, f97fd28)
- SUMMARY.md created in plan directory
