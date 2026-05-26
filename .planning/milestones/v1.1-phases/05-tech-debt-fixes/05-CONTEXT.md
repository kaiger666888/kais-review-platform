# Phase 05: Tech Debt Fixes - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix 2 blocking defects from v1.0 milestone audit so integration tests can verify correct behavior. Note: DEBT-03 (audit_protect_authorizer) was found to be ALREADY registered in database.py:28 — will add a verification test instead of a fix.

</domain>

<decisions>
## Implementation Decisions

### Review Token Endpoint (DEBT-01)
- POST /api/v1/reviews/{id}/token — co-located with review resource
- Any JWT-authenticated client can create tokens (matches submit permission)
- Response includes {token, expires_in, review_url} — ready for external systems to use directly

### Web Auth Enforcement (DEBT-02)
- Unauthenticated users redirected to /login page that sets JWT via cookie
- Only dashboard GET / needs protection — SSE and deep-link routes already have their own auth
- API key / simple login form at /login, sets httpOnly cookie JWT (15 min TTL)

### Audit Authorizer Verification (DEBT-03)
- audit_protect_authorizer IS already registered in database.py:28 via set_authorizer()
- v1.0 audit was incorrect — add a verification test to confirm UPDATE/DELETE on audit_entries raises error

### Claude's Discretion
Implementation details for login page UI (simple form), exact redirect flow, and error messages.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- create_review_token() already defined in app/core/auth.py:82-98 — just needs an endpoint wrapper
- get_template_user() in app/web/auth.py:13-24 — already raises HTTPException(401), just needs route handlers to not catch it
- JWT encode/decode in app/core/auth.py — reusable for login page cookie setting
- Deep link route /t/{token} in app/web/auth.py:27 — pattern for cookie-based auth

### Established Patterns
- API auth: Bearer token via get_current_client dependency (app/api/v1/)
- Web auth: Cookie-based JWT via get_template_user dependency (app/web/)
- Route registration: app/main.py includes api_v1_router and web_router

### Integration Points
- app/api/v1/actions.py — existing approve/reject endpoints, pattern for new token endpoint
- app/web/routes.py:108-117 — dashboard() currently catches auth exceptions, needs to let them propagate
- app/web/auth.py — needs /login route added
- app/core/database.py:28 — set_authorizer(audit_protect_authorizer) already in place

</code_context>

<specifics>
## Specific Ideas

DEBT-03 is a verification-only task — the fix was already implemented during v1.0, just not detected by the audit.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
