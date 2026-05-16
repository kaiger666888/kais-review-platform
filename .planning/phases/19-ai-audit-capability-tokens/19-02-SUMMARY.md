---
phase: 19-ai-audit-capability-tokens
plan: 02
subsystem: auth
tags: [jwt, capability-token, redis, single-use, gpu-gating]

# Dependency graph
requires:
  - phase: 19-01
    provides: "capability_token_secret field in Settings config"
provides:
  - "issue_capability_token function for JWT creation with shot_id/node_scope claims"
  - "verify_capability_token function with single-use enforcement via Redis"
  - "POST /api/v1/tokens/verify endpoint for downstream execution gating"
affects: [ai-audit, shot-card-approval, openclaw-execution]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Capability token pattern: JWT with Redis-backed single-use enforcement"
    - "Separate signing secret (capability_token_secret) from session auth (jwt_secret)"

key-files:
  created:
    - app/api/v1/tokens.py
  modified:
    - app/core/auth.py
    - app/api/v1/__init__.py
    - app/main.py
    - tests/test_capability_tokens.py

key-decisions:
  - "Integration tests use standalone FastAPI app to avoid pre-existing broken import in actions.py"
  - "Redis GET+DELETE for single-use enforcement (not Lua script) since race window is acceptable for capability tokens"

patterns-established:
  - "Capability token flow: issue_capability_token -> JWT with shot_id/node_scope -> Redis cap_token:{token} -> verify_capability_token -> consume on success"
  - "Token verification returns structured dict with valid bool and reason string for all failure modes"

requirements-completed: [ROUT-02]

# Metrics
duration: 7min
completed: 2026-05-16
---

# Phase 19 Plan 02: Capability Token Issuance and Verification Summary

**Single-use JWT capability tokens with Redis-backed consumption for gating downstream GPU execution after ShotCard approval**

## Performance

- **Duration:** 7 min
- **Started:** 2026-05-16T15:13:14Z
- **Completed:** 2026-05-16T15:20:00Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments
- issue_capability_token creates JWT with shot_id, node_scope, iat, exp claims using capability_token_secret
- verify_capability_token validates JWT, checks Redis for revocation, and deletes key for single-use enforcement
- Three failure modes handled: token_expired, invalid_token, token_revoked_or_consumed
- POST /api/v1/tokens/verify endpoint with TokenVerifyRequest/TokenVerifyResponse models
- 13 tests passing (9 unit + 4 integration) via TDD

## Task Commits

Each task was committed atomically (TDD: RED -> GREEN -> refactor):

1. **Task 1 (RED): Failing tests for capability tokens** - `79fd8ab` (test)
2. **Task 1 (GREEN): Implement capability token issuance and verification** - `1247e36` (feat)

## Files Created/Modified
- `app/core/auth.py` - Added issue_capability_token and verify_capability_token functions
- `app/api/v1/tokens.py` - New file: POST /api/v1/tokens/verify endpoint with TokenVerifyRequest/TokenVerifyResponse
- `app/api/v1/__init__.py` - Added tokens_router import and export
- `app/main.py` - Registered tokens_router
- `tests/test_capability_tokens.py` - New file: 13 tests covering unit and integration scenarios

## Decisions Made
- Integration tests use standalone FastAPI app (not app.main) to avoid pre-existing broken import chain in actions.py
- Single-use enforcement uses Redis GET+DELETE instead of Lua script since the race window between GET and DELETE is acceptable for capability tokens (unlike review tokens which use atomic Lua consume)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing import error in app/api/v1/actions.py (missing ApproveRequest, RejectRequest, ReviewResponse, ReviewTokenResponse from schemas.py) prevents importing app.main in tests. Worked around by using standalone FastAPI app for integration tests. This issue is out of scope and logged for future cleanup.

## Next Phase Readiness
- Capability token infrastructure ready for integration into ShotCard approval flow
- issue_capability_token should be called after ShotCard reaches APPROVED state
- Downstream systems (kais-movie-agent, kais-gold-team) can verify tokens via POST /api/v1/tokens/verify before executing GPU tasks

---
*Phase: 19-ai-audit-capability-tokens*
*Completed: 2026-05-16*

## Self-Check: PASSED

- All 6 files exist: app/core/auth.py, app/api/v1/tokens.py, app/api/v1/__init__.py, app/main.py, tests/test_capability_tokens.py, 19-02-SUMMARY.md
- All commits found: 79fd8ab (test), 1247e36 (feat)
- 13/13 tests passing
