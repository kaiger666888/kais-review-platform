---
phase: 03-review-frontend
plan: 01
subsystem: web-frontend
tags: [templates, htmx, alpinejs, tailwind, routes, auth]
dependency_graph:
  requires:
    - app/core/auth.py (JWT + one-time tokens)
    - app/core/state_machine.py (transition_state)
    - app/core/database.py (async_session_factory)
    - app/models/schema.py (Review model)
    - app/models/schemas.py (ReviewState, Disposition)
  provides:
    - app/templates/base.html (HTML shell with CDN scripts, tab bar, toasts)
    - app/templates/pages/dashboard.html (dashboard page)
    - app/templates/partials/* (review card, list, detail, empty state, reject confirm)
    - app/web/routes.py (template route handlers)
    - app/web/auth.py (cookie JWT auth, token deep link)
  affects:
    - app/main.py (router registration)
    - requirements.txt (new deps)
tech_stack:
  added:
    - jinja2-fragments==1.8.0
    - python-multipart==0.0.20
  patterns:
    - HTMX 2.0.9 with SSE extension 2.2.4
    - Alpine.js 3.15.12 for client-side state (toasts, dialogs)
    - Tailwind v4 CDN via @tailwindcss/browser
    - jinja2-fragments for partial template rendering
    - Cookie-based JWT auth for template routes
key_files:
  created:
    - app/templates/base.html
    - app/templates/pages/dashboard.html
    - app/templates/partials/_review_card.html
    - app/templates/partials/_review_list.html
    - app/templates/partials/_empty_state.html
    - app/templates/partials/_review_detail.html
    - app/templates/partials/_toast.html
    - app/templates/partials/_reject_confirm.html
    - app/web/__init__.py
    - app/web/auth.py
    - app/web/routes.py
  modified:
    - requirements.txt
    - app/main.py
decisions:
  - "Reviews in PENDING state cannot be approved/rejected directly (must be APPROVING) -- transition errors caught and shown to user"
  - "Pending tab shows both PENDING and APPROVING state reviews (awaiting human action)"
  - "Approved/rejected tabs use audit table subquery to find last action on COMPLETE reviews"
  - "Toast notifications use Alpine.js window event listener from base.html body x-data"
  - "SSE connection in dashboard.html is placeholder for Plan 02 real-time integration"
metrics:
  duration: 5min
  tasks: 2
  files: 13
---

# Phase 03 Plan 01: Template Foundation Summary

Mobile-first review dashboard with HTMX partials, Alpine.js interactivity, cookie-based JWT auth, and direct state machine integration for approve/reject actions.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Template foundation with mobile-first dashboard | e730825 | 9 files (all templates + requirements.txt) |
| 2 | Web route handlers and main.py registration | b7eb47d | 4 files (web/ package + main.py) |

## Key Implementation Details

### Templates
- **base.html**: HTML shell loading HTMX 2.0.9, htmx-ext-sse 2.2.4, Alpine.js 3.15.12, Tailwind v4 CDN. Bottom tab bar with ARIA roles (tablist/tab/aria-selected). Toast container with Alpine.js x-data auto-dismiss after 3s. 44px min touch targets.
- **_review_card.html**: Article element with thumbnail placeholder, type badge (colored by disposition), source system label, elapsed time, critical priority indicator.
- **_review_list.html**: Card loop with "Load more" button for cursor-based pagination.
- **_review_detail.html**: Fixed overlay with slide-up panel, content/metadata sections, approve/reject footer. Inline reject confirmation dialog with required textarea.
- **_empty_state.html**: Tab-specific messaging per UI-SPEC copywriting contract.
- **dashboard.html**: Extends base with SSE wrapper (placeholder for Plan 02), review list area, detail overlay container.

### Routes
- **GET /**: Full dashboard render with tab filtering, toast query param support.
- **GET /partials/review-list**: HTMX partial rendering review list for a given status.
- **GET /reviews/{id}/detail**: HTMX partial rendering review detail overlay.
- **POST /reviews/{id}/approve**: Calls transition_state directly, returns updated list with HX-Trigger toast.
- **POST /reviews/{id}/reject**: Calls transition_state with reason, returns updated list with toast.
- **GET /t/{token}**: One-time token exchange for JWT cookie, redirect to dashboard.

### Auth
- `get_template_user()`: Cookie-based JWT dependency for template routes.
- Token deep link: consume_review_token -> create_jwt -> set httpOnly cookie -> redirect.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

- SSE connection in dashboard.html uses `sse-connect="/api/v1/events/stream"` which requires cookie-based auth modification (Plan 02 will address this).
- Audit history section in _review_detail.html shows version number only -- full audit history list deferred.
- New reviews banner placeholder exists in dashboard.html but SSE event handling not wired (Plan 02).

## Self-Check: PASSED
