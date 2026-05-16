---
phase: 22-audit-compliance
plan: 02
subsystem: auth
tags: [jwt, rbac, role-based-access, fastapi-depends]

# Dependency graph
requires:
  - phase: prior-phases
    provides: "JWT auth foundation (create_jwt, decode_jwt, require_jwt, HTTPBearer)"
provides:
  - "Role enum with ADMIN, REVIEWER, AUDITOR, AI_SERVICE"
  - "require_role dependency factory for endpoint-level RBAC"
  - "Convenience dependencies: require_admin, require_reviewer, require_auditor, require_ai_service, require_any_role"
  - "JWT role claim in token payload"
  - "Role-aware token exchange API endpoint"
  - "Role-aware template auth returning client + role dict"
affects: [22-03, future-api-endpoints]

# Tech tracking
tech-stack:
  added: []
  patterns: ["role-based FastAPI dependency factory pattern", "JWT role claim with backward-compatible default"]

key-files:
  created: []
  modified:
    - "app/core/auth.py"
    - "app/api/v1/auth.py"
    - "app/web/auth.py"
    - "app/models/schemas.py"

key-decisions:
  - "Default role is reviewer for backward compatibility with existing callers"
  - "require_reviewer allows ADMIN too (admin can do everything a reviewer can)"
  - "require_auditor allows ADMIN too (admin can see analytics)"
  - "require_ai_service is strict (only ai_service role)"
  - "get_template_user changed from str return to dict return -- no templates render {{ user }} so no breakage"
  - "API key login grants admin role; one-time token deep link grants reviewer role"

patterns-established:
  - "require_role(*roles) dependency factory: returns async FastAPI dependency that validates JWT + checks role"
  - "Role enum as str enum: Role.ADMIN.value == 'admin' for direct comparison and JWT serialization"

requirements-completed: [AUTH-01]

# Metrics
duration: 3min
completed: 2026-05-17
---

# Phase 22 Plan 02: Multi-Role Authentication Summary

**Four-role JWT auth with Role enum, require_role dependency factory, role-validated token exchange, and role-aware template context**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-16T17:34:57Z
- **Completed:** 2026-05-16T17:38:04Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Role enum with four platform roles (admin, reviewer, auditor, ai_service) and JWT role claims
- require_role dependency factory producing FastAPI dependencies that return 403 for unauthorized roles
- Role-aware token exchange endpoint that validates requested roles against the enum
- Template auth returning role context dict for future UI role-based rendering

## Task Commits

Each task was committed atomically:

1. **Task 1: Role enum, JWT role claims, and role-based access dependencies** - `54c5745` (feat)
2. **Task 2: Role-aware token exchange and template auth** - `b2ea605` (feat)

## Files Created/Modified
- `app/core/auth.py` - Added Role enum, extended create_jwt with role param, added require_role factory and convenience dependencies
- `app/models/schemas.py` - Added role field to TokenRequest with default "reviewer"
- `app/api/v1/auth.py` - Role validation in token exchange, passes role to create_jwt
- `app/web/auth.py` - get_template_user returns dict with client + role, login grants admin, deep link grants reviewer

## Decisions Made
- Default role is "reviewer" for full backward compatibility -- existing JWTs and callers without role awareness continue to work
- require_reviewer and require_auditor both allow admin access (admin has blanket access to reviewer and auditor features)
- require_ai_service is strict: only ai_service role can submit scores, not even admin
- get_template_user return type changed from str to dict; safe because no templates currently render `{{ user }}`
- API key login always grants admin role; one-time review token deep link always grants reviewer role

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Role infrastructure complete, ready for 22-03 (audit dashboard UI) to use role context for conditional rendering
- All API endpoints can now use require_role dependencies for access control
- Template routes pass user dict with "client" and "role" keys to all page templates

## Self-Check: PASSED

All files verified present. All commits verified in git log.

---
*Phase: 22-audit-compliance*
*Completed: 2026-05-17*
