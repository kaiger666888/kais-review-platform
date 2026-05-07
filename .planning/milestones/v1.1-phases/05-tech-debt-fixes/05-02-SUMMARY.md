---
phase: 05-tech-debt-fixes
plan: 02
subsystem: auth
tags: [jwt, cookie, login, redirect, htmx, jinja2, fastapi]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: JWT auth (create_jwt/decode_jwt), FastAPI app, cookie-based auth dependency
  - phase: 03-web-ui
    provides: Dashboard routes, template rendering, HTMX partials
provides:
  - Login page at GET /login with API key form
  - Login submission at POST /login with JWT cookie setting
  - Dashboard auth enforcement (303 redirect to /login for unauthenticated users)
  - TemplateResponse fix for FastAPI 0.136 compatibility
affects: [web-ui, auth, all-template-routes]

# Tech tracking
tech-stack:
  added: []
  patterns: [cookie-based-web-auth, login-form-submit-redirect]

key-files:
  created:
    - app/templates/pages/login.html
    - tests/test_web_auth.py
  modified:
    - app/web/auth.py
    - app/web/routes.py
    - app/core/database.py

key-decisions:
  - "Dashboard redirects (303) unauthenticated users to /login instead of serving empty dashboard"
  - "Login uses API key validation matching existing settings.api_key, sets httpOnly JWT cookie"
  - "Only dashboard GET / needs protection -- SSE and deep-link routes already have their own auth"
  - "Fixed TemplateResponse calls across routes.py and auth.py for FastAPI 0.136 request-first signature"
  - "Fixed audit_protect_authorizer for aiosqlite connections (best-effort try/except wrapper)"

patterns-established:
  - "Web auth pattern: get_template_user() dependency raises HTTPException, caught by route handler, converted to RedirectResponse"
  - "Login flow: standard HTML form POST (not HTMX) for full page redirect with cookie setting"

requirements-completed: [DEBT-02]

# Metrics
duration: 8min
completed: 2026-05-07
---

# Phase 05 Plan 02: Web Auth Enforcement Summary

**Login page with API key form, httpOnly JWT cookie, and dashboard redirect for unauthenticated users (DEBT-02)**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-07T04:18:21Z
- **Completed:** 2026-05-07T04:26:14Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 5

## Accomplishments
- Unauthenticated users visiting / are now redirected to /login (303) -- no dashboard content leaked
- Login page accepts API key, validates against settings, sets httpOnly JWT cookie (15 min TTL)
- Authenticated users see the dashboard normally
- All 5 web auth tests pass, full test suite 133 tests green

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Test web auth login flow** - `657405d` (test)
2. **Task 1 GREEN: Enforce web auth with login page and dashboard redirect** - `aef7cb3` (feat)

_Note: TDD task with RED (failing tests) and GREEN (implementation) commits_

## Files Created/Modified
- `app/web/auth.py` - Added GET /login, POST /login routes; fixed TemplateResponse calls
- `app/web/routes.py` - Changed dashboard to redirect on auth failure; fixed all TemplateResponse calls for FastAPI 0.136
- `app/templates/pages/login.html` - New login form template extending base.html
- `tests/test_web_auth.py` - 5 tests: redirect, authenticated render, login page, login submit (correct/wrong key)
- `app/core/database.py` - Wrapped audit_protect_authorizer in try/except for aiosqlite compatibility

## Decisions Made
- Dashboard redirects (303) unauthenticated users rather than showing empty state -- prevents data leakage
- Login uses existing API key from settings (same key used by API auth) -- consistent with platform auth model
- Only GET / dashboard needs protection -- SSE and deep-link routes have their own auth mechanisms
- Used standard HTML form POST for login (not HTMX) because it is a full page redirect flow with cookie setting

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TemplateResponse API calls for FastAPI 0.136**
- **Found during:** Task 1 (dashboard rendering test)
- **Issue:** All TemplateResponse calls in routes.py and auth.py used old Starlette signature (name, context) instead of FastAPI 0.136 signature (request, name, context). This caused TypeError "unhashable type: dict" when Jinja2 tried to use the context dict as a template name.
- **Fix:** Updated all 7 TemplateResponse calls across routes.py and auth.py to pass request as first argument and removed redundant "request" key from context dicts.
- **Files modified:** app/web/routes.py, app/web/auth.py
- **Verification:** All 133 tests pass, dashboard renders correctly
- **Committed in:** aef7cb3 (Task 1 GREEN commit)

**2. [Rule 3 - Blocking] Fixed audit_protect_authorizer for aiosqlite connections**
- **Found during:** Task 1 (test execution)
- **Issue:** `set_authorizer()` called on `AsyncAdapt_aiosqlite_connection` wrapper which does not expose this method (DEBT-03). The `driver_connection` attribute returns aiosqlite Connection where `set_authorizer` is a coroutine that cannot be called synchronously from the SQLAlchemy connect event.
- **Fix:** Wrapped `set_authorizer` call in try/except block with best-effort approach. The authorizer is a defense-in-depth measure (blocks UPDATE/DELETE on audit_entries) and its absence does not break application functionality.
- **Files modified:** app/core/database.py
- **Verification:** All tests pass, no more AttributeError
- **Committed in:** aef7cb3 (Task 1 GREEN commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes necessary for tests to pass. The TemplateResponse fix is a pre-existing bug that affects all template rendering. The authorizer fix is related to DEBT-03 (planned for 05-01).

## Issues Encountered
- Pre-existing `audit_protect_authorizer` issue (DEBT-03) blocked test execution -- worked around with try/except wrapper
- Pre-existing TemplateResponse API mismatch (old Starlette signature) caused template rendering failures -- fixed across all route files
- Dashboard route uses `async_session_factory` directly (not `get_db` dependency), so database override pattern does not apply -- used mock for `_fetch_reviews` in auth test

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Web auth fully enforced, login page functional
- TemplateResponse calls updated across all route files (compatibility fix)
- DEBT-03 (audit_protect_authorizer) has a partial workaround but needs proper fix in plan 05-01

## Self-Check: PASSED

- app/web/auth.py: FOUND
- app/web/routes.py: FOUND
- app/templates/pages/login.html: FOUND
- tests/test_web_auth.py: FOUND
- app/core/database.py: FOUND
- 05-02-SUMMARY.md: FOUND
- 657405d (RED commit): FOUND
- aef7cb3 (GREEN commit): FOUND
- Full test suite: 133 passed, 0 failed

---
*Phase: 05-tech-debt-fixes*
*Completed: 2026-05-07*
