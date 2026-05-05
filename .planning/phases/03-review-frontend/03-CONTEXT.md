# Phase 3: Review Frontend - Context

**Gathered:** 2026-05-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Reviewers have a mobile-first web interface to view pending reviews, approve or reject items with one tap, receive real-time updates, and open one-time approval links directly on their phone.

This phase delivers: mobile-first HTMX dashboard with card-based review lists, real-time SSE updates via HTMX, one-time token deep link flow, server-side form handlers with JWT management, and Tailwind v4 CDN styling.

</domain>

<decisions>
## Implementation Decisions

### Layout & Navigation
- Single-column card list — mobile-first, each status tab (pending/approved/rejected) shows swipeable cards
- Fixed bottom tab bar with 3 icons (pending/approved/rejected) + settings — standard mobile pattern
- Compact review cards: thumbnail + type badge + source + elapsed time + large approve/reject buttons
- Full-screen overlay for review detail with content preview + approve (green) / reject (red) footer buttons — one-tap action

### Real-Time Updates & Interaction
- HTMX `hx-sse` listens to `review_status` events → replaces review list container — no page refresh
- "New reviews" banner with count badge on click-to-reveal — doesn't clutter current view
- Inline toast notifications (Alpine.js `x-show`) — auto-dismiss after 3s
- One-time token flow: JWT exchange via `/api/v1/auth/token` → auto-redirect to review detail → approve/reject → redirect to dashboard

### Technical Architecture
- `app/templates/base.html` (Tailwind CDN + HTMX + Alpine) + `partials/` for HTMX fragments — jinja2-fragments renders blocks
- Tailwind v4 CDN with neutral gray palette, green for approve, red for reject — minimal custom CSS
- Server-side form handlers (HTMX `hx-post`) → backend calls internal API → returns HTML fragment — JWT managed server-side
- Infinite scroll with "Load more" button — mobile-friendly, no layout shift on load

### Claude's Discretion
Internal CSS class names, exact Alpine.js state management, error message wording, test structure.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/api/v1/` — Full REST API (reviews, actions, audit, policies, webhooks, events, auth)
- `app/api/v1/events.py` — SSE endpoint at `GET /api/v1/events/stream` for real-time updates
- `app/api/v1/actions.py` — Approve/reject endpoints with one-time token support
- `app/api/v1/auth.py` — JWT token exchange endpoint
- `app/core/auth.py` — JWT creation/validation, one-time token management
- `app/models/schemas.py` — Pydantic response models (ReviewResponse, etc.)

### Established Patterns
- FastAPI with Jinja2 template support (built-in)
- jinja2-fragments for partial rendering (in stack)
- HTMX + Alpine.js CDN loading (zero-build)
- Tailwind v4 CDN (zero-build)
- JWT auth on all protected routes

### Integration Points
- `app/main.py` — register new template routes
- `app/templates/` — new template directory for HTML
- SSE stream at `/api/v1/events/stream` — HTMX `hx-sse` connects here
- Review API at `/api/v1/reviews` — server-side fetches review data
- Actions API at `/api/v1/reviews/{id}/approve|reject` — form submissions
- Auth API at `/api/v1/auth/token` — one-time token exchange

</code_context>

<specifics>
## Specific Ideas

- Mobile-first: bottom tab bar, full-screen overlays, large tap targets
- HTMX `hx-sse` for real-time review status updates
- Server-side rendering: no client-side API calls, JWT managed in httpOnly cookies or server session
- One-time token deep link flow: open link → exchange for JWT → show review detail → approve/reject → dashboard

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>
