---
phase: 01-core-engine
plan: 02
subsystem: auth, state-machine
tags: [jwt, one-time-tokens, redis-lua, state-machine, optimistic-locking, hs256]

# Dependency graph
requires: [01]
provides:
  - JWT creation/validation with HS256, 15min expiry, client claim
  - FastAPI auth dependencies: require_jwt, get_current_client
  - One-time review tokens with Redis Lua atomic GET+DEL consume
  - POST /api/v1/auth/token endpoint for API key to JWT exchange
  - 4-state checkpoint state machine with transition validation
  - Optimistic locking via version column for concurrent state transitions
  - StateMachineError hierarchy: InvalidTransitionError, StateConflictError, TerminalStateError
affects: [03-core-engine, 04-core-engine, 05-core-engine]

# Tech tracking
tech-stack:
  added: []
  patterns: [jwt-hs256-bearer-auth, redis-lua-atomic-consume, optimistic-locking-state-transitions, 4-state-directed-graph]

key-files:
  created:
    - app/core/auth.py
    - app/core/state_machine.py
    - app/api/__init__.py
    - app/api/v1/__init__.py
    - app/api/v1/auth.py
  modified: []

key-decisions:
  - "Import ReviewState/Disposition from app.models.schemas rather than redefining in state_machine.py"
  - "Transition function refreshes Review object via session.get() after commit for accurate return"

requirements-completed: [AUTH-01, AUTH-02, AUTH-03, AUTH-04, SM-01, SM-02, SM-03, SM-04]

# Metrics
duration: 3min
completed: 2026-05-05
---

# Phase 1 Plan 02: Summary

**JWT auth with one-time Redis tokens and 4-state checkpoint state machine with optimistic locking**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-05T15:22:26Z
- **Completed:** 2026-05-05T15:25:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- JWT authentication: create/decode with HS256, 15min expiry, client identity claim
- FastAPI dependencies: require_jwt validates Bearer tokens, get_current_client extracts identity
- One-time review tokens: 43-char base64 tokens stored in Redis with TTL, consumed atomically via Lua script (GET+DEL)
- POST /api/v1/auth/token endpoint: exchanges static API key for short-lived JWT
- 4-state directed graph: PENDING -> POLICY_EVAL -> APPROVING -> COMPLETE with reject/escalate/expire paths
- Optimistic locking: UPDATE WHERE version=? prevents concurrent state conflicts, raises StateConflictError on mismatch
- Audit trail integration: every state transition automatically appends an audit entry

## Task Commits

Each task was committed atomically:

1. **Task 1: JWT auth, one-time tokens, and auth token endpoint** - `11be449` (feat)
2. **Task 2: 4-state checkpoint state machine with optimistic locking** - `8f12599` (feat)

## Files Created
- `app/core/auth.py` - JWT creation/validation, FastAPI auth dependencies, Redis one-time token management
- `app/core/state_machine.py` - ReviewState transition map, optimistic locking transition function, helper functions
- `app/api/__init__.py` - API package init
- `app/api/v1/__init__.py` - V1 API package init
- `app/api/v1/auth.py` - POST /api/v1/auth/token endpoint

## Decisions Made
- **Import enums from schemas.py:** ReviewState and Disposition are already defined in app.models.schemas. The state machine imports them rather than redefining, keeping a single source of truth.
- **Refresh after commit:** transition_state uses session.get() after commit to return a fully hydrated Review object with updated state and version.

## Deviations from Plan

None - plan executed exactly as written.

## Next Phase Readiness
- JWT auth and state machine are complete and verified
- Ready for Plan 03 which will build the YAML policy engine
- Redis must be running for one-time token features at runtime

---
*Phase: 01-core-engine*
*Completed: 2026-05-05*

## Self-Check: PASSED

All 5 claimed files verified present. Both commit hashes (11be449, 8f12599) verified in git log.
