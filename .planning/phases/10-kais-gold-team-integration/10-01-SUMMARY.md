---
phase: 10-kais-gold-team-integration
plan: 01
subsystem: api
tags: [yaml-policy, httpx, review-client, risk-routing, gpu-tasks]

# Dependency graph
requires:
  - phase: 08-callback-infrastructure
    provides: Callback delivery infrastructure for review result notifications
provides:
  - Risk-based routing policy for gold-team GPU engine types (blender/facefusion=HUMAN, tts/woosh/acestep=AUTO)
  - ReviewPlatformClient async Python module for gold-team to submit GPU task reviews
  - ReviewQueryResult and ReviewSubmitResult dataclasses
  - ReviewClientError exception hierarchy
affects: [10-02, 12-e2e-testing]

# Tech tracking
tech-stack:
  added: [httpx.AsyncClient (client module)]
  patterns: [integrations package pattern, risk-score-from-task-type, JWT cache with expiry]

key-files:
  created:
    - app/policies/gold_team_risk.yaml
    - app/integrations/__init__.py
    - app/integrations/gold_team/__init__.py
    - app/integrations/gold_team/client.py
    - tests/test_gold_team_client.py
  modified: []

key-decisions:
  - "Client code lives in review-platform at app/integrations/gold_team/client.py -- gold-team imports it as a dependency"
  - "Risk score auto-calculated from task_type (HIGH_RISK_TYPES=0.8, LOW_RISK_TYPES=0.2, unknown=0.5)"
  - "JWT cached with 60s safety margin before expiry to avoid edge-case auth failures"

patterns-established:
  - "Integrations package: app/integrations/<system>/client.py pattern for external system clients"
  - "Risk score mapping via frozenset type lookup for O(1) classification"

requirements-completed: [GT-01, GT-02, GT-03]

# Metrics
duration: 4min
completed: 2026-05-07
---

# Phase 10 Plan 01: Gold-Team Risk Policy & Review Client Summary

**YAML risk-tier routing policy (blender/facefusion=HUMAN, tts/woosh/acestep=AUTO) plus async ReviewPlatformClient with JWT auth, auto risk scoring, and 14 unit tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-05-07T15:04:12Z
- **Completed:** 2026-05-07T15:08:28Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created gold_team_risk.yaml policy with engine-type-based risk routing validated against POLICY_JSON_SCHEMA
- Built ReviewPlatformClient async module with submit_gpu_review and query_review_status methods
- Implemented risk score auto-calculation from task_type using frozenset lookup (HIGH=0.8, LOW=0.2, unknown=0.5)
- JWT authentication with automatic token caching and refresh
- 14 unit tests covering routing responses, metadata mapping, auth flow, and error handling

## Task Commits

Each task was committed atomically:

1. **Task 1: Create gold-team risk routing policy YAML** - `7506549` (feat)
2. **Task 2: Create gold-team review client module** - `d675fdf` (feat)

## Files Created/Modified
- `app/policies/gold_team_risk.yaml` - Risk-tier routing policy: high-risk GPU engines to HUMAN, low-risk to AUTO
- `app/integrations/__init__.py` - Integrations package root
- `app/integrations/gold_team/__init__.py` - Gold-team integration package, exports ReviewPlatformClient
- `app/integrations/gold_team/client.py` - Async review client with JWT auth, risk scoring, submit/query methods
- `tests/test_gold_team_client.py` - 14 unit tests for client module

## Decisions Made
- Client code lives in review-platform at app/integrations/gold_team/client.py -- gold-team imports it as a dependency (per CONTEXT.md GT-01)
- Risk score auto-calculated from task_type via frozenset membership (HIGH_RISK_TYPES=0.8, LOW_RISK_TYPES=0.2, unknown=0.5) for O(1) classification
- JWT cached with 60s safety margin before expiry to avoid edge-case auth failures
- httpx.AsyncClient used for all HTTP calls (already in project stack)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Gold-team risk policy ready for PolicyEngine loading at startup
- ReviewPlatformClient ready for gold-team Plan 02 to import and use in Guardian._dispatch_task() interception
- Plan 10-02 will integrate the client into gold-team's control_node callback endpoint

## Self-Check: PASSED

All 6 created files verified on disk. Both task commits (7506549, d675fdf) found in git log. 230 total tests passing with 0 regressions.

---
*Phase: 10-kais-gold-team-integration*
*Completed: 2026-05-07*
