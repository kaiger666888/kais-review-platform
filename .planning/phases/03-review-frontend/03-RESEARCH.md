# Phase 3: Review Frontend - Research

**Researched:** 2026-05-06
**Domain:** HTMX + Jinja2 + Alpine.js server-rendered mobile-first dashboard
**Confidence:** HIGH

## Summary

Phase 3 builds a mobile-first review dashboard using FastAPI's Jinja2 template support with HTMX for dynamic HTML-over-the-wire interactions, Alpine.js for lightweight client-side state (toasts, dialogs), and Tailwind v4 CDN for styling. The backend API is fully built in Phases 1-2 -- this phase adds template routes, HTML templates, and server-side form handlers that call existing internal APIs.

The most critical technical finding: **HTMX 2.0 moved SSE support to a separate extension** (`htmx-ext-sse`) with different attribute names (`sse-connect`, `sse-swap` instead of `hx-sse`). The CONTEXT.md references `hx-sse` which is HTMX v1 syntax and will NOT work with HTMX 2.0.9. The plan must use the new extension API.

The project already has `jinja2-fragments` in the stack but NOT in `requirements.txt` -- it must be added. FastAPI natively supports Jinja2 via `Jinja2Templates` -- no additional configuration library needed.

**Primary recommendation:** Use HTMX 2.0 SSE extension (`htmx-ext-sse@2.2.4`) with `sse-connect`/`sse-swap` attributes, add `jinja2-fragments` to requirements, and build server-side route handlers that call existing API functions directly (not HTTP self-calls).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Single-column card list -- mobile-first, each status tab (pending/approved/rejected) shows swipeable cards
- Fixed bottom tab bar with 3 icons (pending/approved/rejected) + settings -- standard mobile pattern
- Compact review cards: thumbnail + type badge + source + elapsed time + large approve/reject buttons
- Full-screen overlay for review detail with content preview + approve (green) / reject (red) footer buttons -- one-tap action
- HTMX `hx-sse` listens to `review_status` events and replaces review list container -- no page refresh
- "New reviews" banner with count badge on click-to-reveal -- doesn't clutter current view
- Inline toast notifications (Alpine.js `x-show`) -- auto-dismiss after 3s
- One-time token flow: JWT exchange via `/api/v1/auth/token` then auto-redirect to review detail then approve/reject then redirect to dashboard
- `app/templates/base.html` (Tailwind CDN + HTMX + Alpine) + `partials/` for HTMX fragments -- jinja2-fragments renders blocks
- Tailwind v4 CDN with neutral gray palette, green for approve, red for reject -- minimal custom CSS
- Server-side form handlers (HTMX `hx-post`) call internal API and return HTML fragments -- JWT managed server-side
- Infinite scroll with "Load more" button -- mobile-friendly, no layout shift on load

### Claude's Discretion
Internal CSS class names, exact Alpine.js state management, error message wording, test structure.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UI-01 | Mobile-first review dashboard showing pending/approved/rejected review lists | Jinja2 templates + HTMX tab switching + cursor pagination via existing `list_reviews` API |
| UI-02 | Review detail page with content preview and approve/reject action buttons | HTMX partial for overlay + `hx-post` to actions API + Alpine.js for reject confirmation dialog |
| UI-03 | Dashboard receives real-time updates via SSE (new reviews appear automatically) | HTMX 2.0 SSE extension (`htmx-ext-sse@2.2.4`) with `sse-connect`/`sse-swap` attributes connecting to existing `/api/v1/events/stream` |
| UI-04 | One-time token deep links open review detail directly for quick approval | New route `/t/{token}` that calls `consume_review_token` internally, sets JWT cookie, renders dashboard with detail open |
| UI-05 | Responsive layout optimized for mobile phone screens (primary target) | Tailwind v4 CDN mobile-first utilities, 56px bottom tab bar, 44px min touch targets, full-width cards |
| UI-06 | HTMX server-rendered with Alpine.js for client-side interactivity | HTMX 2.0.9 + Alpine.js 3.15.12 CDN scripts + jinja2-fragments for partial template rendering |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| HTMX | 2.0.9 | Dynamic HTML over AJAX | 14KB, server-rendered HTML fragments, SSE extension for real-time |
| htmx-ext-sse | 2.2.4 | SSE extension for HTMX 2.0 | Required separately in v2 -- `sse-connect`/`sse-swap` replaces old `hx-sse` |
| Alpine.js | 3.15.12 | Client-side interactivity | 15KB, toast management, dialog state, tab state -- complements HTMX |
| Tailwind CSS | 4.2.3 (CDN) | Utility-first styling | Zero-build via `@tailwindcss/browser` CDN script, mobile-first |
| Jinja2 | 3.1.6 | Server-side templates | FastAPI built-in support via `Jinja2Templates` |
| jinja2-fragments | 1.8.0 | Partial template rendering | Renders named Jinja2 blocks for HTMX responses without duplicating templates |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-multipart | 0.0.20 | Form data parsing | Required by HTMX form submissions (approve/reject POST) |
| FastAPI | 0.136.1 | Template route handlers | `Jinja2Templates` + `HTMLResponse` for page and partial rendering |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| htmx-ext-sse CDN | Inline EventSource JS | Extension handles reconnection, swapping, and DOM management -- hand-rolling is error-prone |
| Tailwind v4 CDN | Tailwind CLI build | CDN sufficient for LAN deployment with no internet concerns, avoids Node.js dependency |
| jinja2-fragments | Duplicate templates | Fragments avoid maintaining two template versions (full page vs partial) |

**Installation:**
```bash
pip install jinja2-fragments==1.8.0 python-multipart==0.0.20
```

Note: `jinja2-fragments` is NOT in current `requirements.txt` and must be added. `python-multipart` is also missing.

**Version verification:**
```
jinja2-fragments: 1.8.0 (current on PyPI)
python-multipart: 0.0.20 (already specified in CLAUDE.md stack)
HTMX: 2.0.9 (pinned, stable)
htmx-ext-sse: 2.2.4 (latest stable per official docs)
Alpine.js: 3.15.12 (pinned, stable)
Tailwind v4: 4.2.3 via @tailwindcss/browser CDN
```

## Architecture Patterns

### Recommended Project Structure
```
app/
├── templates/
│   ├── base.html              # Shell: head (CDN scripts), body wrapper, bottom tab bar
│   ├── pages/
│   │   └── dashboard.html     # Full dashboard page extending base.html
│   └── partials/
│       ├── _review_card.html  # Single review card fragment
│       ├── _review_list.html  # Container of cards + "Load more" button
│       ├── _review_detail.html # Full-screen overlay fragment
│       ├── _empty_state.html  # Empty state per tab
│       ├── _toast.html        # Toast notification (Alpine.js)
│       ├── _new_reviews_banner.html # "N new reviews" banner
│       └── _reject_confirm.html # Reject confirmation dialog
├── web/                       # NEW: web UI route handlers
│   ├── __init__.py
│   ├── routes.py              # Dashboard, review list, review detail routes
│   └── auth.py                # One-time token deep link route
└── main.py                    # Register web router + mount templates
```

### Pattern 1: FastAPI Jinja2Templates Setup
**What:** Configure Jinja2 template rendering in FastAPI with jinja2-fragments support.
**When to use:** All template routes.
**Example:**
```python
# app/web/routes.py
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from jinja2_fragments.fastapi import Jinja2Blocks

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
blocks = Jinja2Blocks(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Full page render."""
    return templates.TemplateResponse("pages/dashboard.html", {
        "request": request,
        "active_tab": "pending",
    })

@router.get("/partials/review-list", response_class=HTMLResponse)
async def review_list_partial(request: Request, status: str = "pending"):
    """HTMX partial render -- returns only the review_list block."""
    return blocks.TemplateResponse(
        "pages/dashboard.html",
        "review_list",  # block name
        {"request": request, "reviews": [...], "active_tab": status}
    )
```

### Pattern 2: HTMX 2.0 SSE Integration (CRITICAL)
**What:** HTMX 2.0 requires a separate SSE extension with different attributes.
**When to use:** Real-time review status updates on dashboard.
**Example:**
```html
<!-- In base.html <head> -->
<script src="https://unpkg.com/htmx.org@2.0.9"></script>
<script src="https://unpkg.com/htmx-ext-sse@2.2.4"></script>

<!-- In dashboard body -->
<div hx-ext="sse" sse-connect="/api/v1/events/stream">
  <!-- SSE event triggers an HTMX GET to refresh the review list -->
  <div id="review-list"
       hx-get="/partials/review-list?status=pending"
       hx-trigger="sse:review_status"
       hx-target="#review-list"
       hx-swap="innerHTML">
    <!-- Initial review cards rendered server-side -->
  </div>
</div>
```

**Migration note:** The old HTMX v1 `hx-sse="connect:/url"` syntax does NOT work in HTMX 2.0. The new syntax is `sse-connect="/url"` with `hx-ext="sse"` enabled. The SSE data payload can be raw HTML that gets swapped directly, OR the SSE event can trigger an HTMX `hx-get` to fetch fresh HTML from the server. The `hx-trigger="sse:review_status"` approach (trigger a GET on SSE event) is recommended because it lets the server render fresh HTML with proper filtering for the active tab.

### Pattern 3: HTMX Response Headers for Toast Triggers
**What:** Use HTMX response headers to trigger Alpine.js toast notifications.
**When to use:** After approve/reject actions.
**Example:**
```python
from fastapi.responses import HTMLResponse

response = HTMLResponse(content=rendered_html)
response.headers["HX-Trigger"] = json.dumps({
    "showToast": {"message": "Review approved", "type": "success"}
})
return response
```
```html
<!-- In base.html -->
<body x-data="{ toasts: [], addToast(msg, type) { ... } }"
      @show-toast.window="addToast($event.detail.message, $event.detail.type)">
  <div id="toast-container">
    <template x-for="toast in toasts" :key="toast.id">
      <div x-show="true" x-init="setTimeout(() => toasts.splice(toasts.indexOf(toast), 1), 3000)"
           :class="toast.type === 'success' ? 'border-green-600' : 'border-red-600'"
           class="fixed top-4 left-4 right-4 bg-white border-l-4 rounded shadow-lg p-4 z-50">
        <span x-text="toast.message"></span>
      </div>
    </template>
  </div>
</body>
```

### Pattern 4: Server-Side Auth for Template Routes
**What:** Template routes manage JWT in httpOnly cookies, not Bearer tokens.
**When to use:** All template routes need authentication.
**Example:**
```python
from fastapi import Cookie, HTTPException

async def get_template_user(access_token: str | None = Cookie(None)):
    """Read JWT from httpOnly cookie set during one-time token exchange."""
    if not access_token:
        raise HTTPException(status_code=401)
    payload = decode_jwt(access_token, settings.jwt_secret)
    return payload["client"]
```

### Anti-Patterns to Avoid
- **HTTP self-calls from template routes to API routes:** Don't use `httpx` to call your own `/api/v1/reviews`. Import and call the service functions directly (SQLAlchemy queries, state machine transitions). Self-calls add latency, network overhead, and auth complexity.
- **HTMX v1 `hx-sse` attribute:** Will silently fail in HTMX 2.0. Must use `hx-ext="sse"` + `sse-connect` + `sse-swap`.
- **Client-side JWT handling:** Never expose JWT to JavaScript. Use httpOnly cookies set by the server during token exchange.
- **Full page re-renders on SSE events:** Use HTMX partial swaps (`hx-swap="innerHTML"`) to update only the review list, not the entire page.
- **Tailwind Play CDN in production note:** The Tailwind v4 Play CDN is officially marked "for development only." For a LAN-deployed internal tool with < 10 concurrent users, this is acceptable. If performance becomes an issue, switch to a pre-built CSS file in Phase 4.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE connection management | Custom EventSource JS | htmx-ext-sse | Handles reconnection, DOM swapping, event routing |
| Template partial rendering | Two separate template files | jinja2-fragments `render_block` | Single source of truth, avoids drift |
| Toast notification system | Custom DOM manipulation | Alpine.js `x-show` + `x-for` | Alpine handles reactive state, auto-dismiss via `setTimeout` |
| Tab state management | Custom JS tab switcher | HTMX `hx-get` + `hx-target` | Server renders correct list, no client state sync |
| Time formatting ("2m ago") | Custom time logic | Humanize or simple server-side formatting | Edge cases in relative time are surprisingly complex |
| CSRF protection | Custom token management | Not needed for httpOnly cookie + SameSite | API-only SSE endpoint, SameSite cookies prevent CSRF |

**Key insight:** HTMX + Alpine.js together cover 95% of client-side needs. Only write custom JS for edge cases like the "new reviews" banner count increment.

## Common Pitfalls

### Pitfall 1: HTMX 2.0 SSE Extension Not Loaded
**What goes wrong:** SSE events never reach the browser, no real-time updates.
**Why it happens:** HTMX 2.0 moved SSE to a separate extension. Without `<script src="htmx-ext-sse">` and `hx-ext="sse"`, SSE attributes are ignored silently.
**How to avoid:** Load `htmx-ext-sse@2.2.4` CDN script after HTMX core, add `hx-ext="sse"` to the parent container.
**Warning signs:** SSE connection opens (visible in DevTools Network tab) but DOM never updates.

### Pitfall 2: SSE Endpoint Requires JWT Auth
**What goes wrong:** SSE EventSource cannot set Bearer token headers.
**Why it happens:** The existing SSE endpoint at `/api/v1/events/stream` uses `Depends(get_current_client)` which expects a Bearer token. EventSource API does not support custom headers.
**How to avoid:** Either (a) create a separate SSE endpoint for template routes that reads JWT from cookie, or (b) pass token as query parameter `?token=xxx` in the `sse-connect` URL, or (c) modify the existing endpoint to accept both cookie and Bearer auth.
**Warning signs:** SSE connection returns 401 or 403.

### Pitfall 3: jinja2-fragments Not in requirements.txt
**What goes wrong:** Import errors at runtime when rendering HTMX partials.
**Why it happens:** The library is listed in CLAUDE.md stack but not installed in the project.
**How to avoid:** Add `jinja2-fragments==1.8.0` to `requirements.txt` before implementation.
**Warning signs:** `ModuleNotFoundError: No module named 'jinja2_fragments'`.

### Pitfall 4: HTMX Form POST Returns JSON Instead of HTML
**What goes wrong:** HTMX expects HTML fragment response but existing API returns JSON `ApiResponse` envelope.
**Why it happens:** Phase 1-2 API endpoints return `ApiResponse[ReviewResponse]` (JSON). HTMX form submissions need HTML fragment responses.
**How to avoid:** Create separate template route handlers for HTMX form POSTs that (1) call internal functions (state machine, database), (2) render HTML partial, (3) set `HX-Trigger` header for toasts. Do NOT reuse API endpoints for HTMX form targets.
**Warning signs:** HTMX shows raw JSON in the DOM after approve/reject.

### Pitfall 5: Alpine.js Initialization Order
**What goes wrong:** Alpine components don't react to HTMX-triggered events.
**Why it happens:** Alpine.js initializes on DOMContentLoaded but HTMX dynamically swaps content after initial load.
**How to avoid:** Use `@show-toast.window` event listener on `body` (not dynamic elements). For Alpine state in swapped content, use `x-data` on the swapped element itself.
**Warning signs:** Toasts work on page load but not after HTMX swaps.

### Pitfall 6: Tailwind v4 CDN Class Differences from v3
**What goes wrong:** Some Tailwind v3 classes don't work in v4.
**Why it happens:** Tailwind v4 changed some utility names and defaults (e.g., `bg-opacity-*` replaced by `bg-{color}/{opacity}`).
**How to avoid:** Use v4 syntax: `bg-black/50` instead of `bg-black bg-opacity-50`, `ring-2` instead of `ring-2 ring-offset-2`.
**Warning signs:** Some styles don't apply, especially opacity modifiers.

## Code Examples

### Complete base.html Template Structure
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kai's Review Platform</title>
  <script src="https://unpkg.com/@tailwindcss/browser@4"></script>
  <script src="https://unpkg.com/htmx.org@2.0.9"></script>
  <script src="https://unpkg.com/htmx-ext-sse@2.2.4"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.15.12/dist/cdn.min.js"></script>
</head>
<body class="bg-gray-50 text-sm leading-relaxed"
      x-data="{ toasts: [] }"
      @show-toast.window="toasts.push($event.detail); setTimeout(() => toasts.shift(), 3000)">

  <!-- Toast container -->
  <div class="fixed top-4 left-4 right-4 z-50 space-y-2">
    <template x-for="toast in toasts" :key="toast.message + Date.now()">
      <div class="bg-white border-l-4 rounded shadow-lg p-4"
           :class="toast.type === 'success' ? 'border-green-600' : toast.type === 'error' ? 'border-red-600' : 'border-blue-600'">
        <span x-text="toast.message" class="text-sm"></span>
      </div>
    </template>
  </div>

  <!-- Main content area with bottom padding for tab bar -->
  <main class="pb-16">
    {% block content %}{% endblock %}
  </main>

  <!-- Fixed bottom tab bar -->
  <nav class="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 h-14 flex items-center justify-around z-40">
    <a href="/?tab=pending" class="flex flex-col items-center text-xs {% if active_tab == 'pending' %}text-blue-600{% else %}text-gray-500{% endif %}">
      <span>Pending</span>
    </a>
    <a href="/?tab=approved" class="flex flex-col items-center text-xs {% if active_tab == 'approved' %}text-green-600{% else %}text-gray-500{% endif %}">
      <span>Approved</span>
    </a>
    <a href="/?tab=rejected" class="flex flex-col items-center text-xs {% if active_tab == 'rejected' %}text-red-600{% else %}text-gray-500{% endif %}">
      <span>Rejected</span>
    </a>
  </nav>
</body>
</html>
```

### SSE Dashboard with HTMX 2.0 Extension
```html
<!-- Inside dashboard.html {% block content %} -->
<div hx-ext="sse" sse-connect="/api/v1/events/stream?token={{ jwt_token }}">
  <!-- New reviews banner -->
  <div id="new-reviews-banner" x-data="{ count: 0 }"
       @review_status.window="if ($event.detail is for different tab) count++"
       x-show="count > 0" x-cloak>
    <span x-text="count + ' new reviews'" class="text-blue-600"></span>
  </div>

  <!-- Review list -- refreshed by SSE events -->
  <div id="review-list"
       hx-get="/partials/review-list?status={{ active_tab }}"
       hx-trigger="sse:review_status, load"
       hx-target="this"
       hx-swap="innerHTML">
  </div>
</div>
```

### One-Time Token Deep Link Route
```python
# app/web/auth.py
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse
from app.core.auth import consume_review_token, create_jwt
from app.core.config import get_settings

router = APIRouter()

@router.get("/t/{token}")
async def token_deep_link(token: str, request: Request):
    """One-time token: validate, exchange for JWT cookie, redirect to review."""
    settings = get_settings()
    redis = request.app.state.redis

    if redis is None:
        raise HTTPException(503, "Service unavailable")

    review_id = await consume_review_token(redis, token)
    if review_id is None:
        # Token expired or used -- redirect to dashboard with error toast
        response = RedirectResponse(url="/?toast=token_expired", status_code=303)
        return response

    # Create JWT and set as httpOnly cookie
    jwt_token = create_jwt("reviewer", settings.jwt_secret)
    response = RedirectResponse(
        url=f"/?detail={review_id}",
        status_code=303
    )
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        max_age=900,  # 15 minutes
        samesite="lax",
    )
    return response
```

### HTMX Approve/Reject Form Handler
```python
# app/web/routes.py (partial -- form handlers)
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

@router.post("/reviews/{review_id}/approve", response_class=HTMLResponse)
async def approve_review_htmx(review_id: int, request: Request):
    """HTMX form handler -- calls internal logic, returns HTML fragment."""
    # Call internal state machine directly (no HTTP self-call)
    db = await get_db_session()
    review = await db.get(Review, review_id)
    # ... validation ...
    await transition_state(db, review.id, ReviewState.APPROVING, ReviewState.COMPLETE, ...)

    # Render updated card HTML
    html = blocks.TemplateResponse(...)
    html.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": "Review approved", "type": "success"}
    })
    return html
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| HTMX v1 built-in `hx-sse` | HTMX v2 separate `htmx-ext-sse` extension | HTMX 2.0 (2024) | Must load extension separately, use `sse-connect`/`sse-swap` attributes |
| Tailwind v3 `bg-opacity-*` | Tailwind v4 `bg-{color}/{opacity}` | Tailwind v4 (2025) | Use modifier syntax for opacity |
| Tailwind CLI build | Tailwind v4 `@tailwindcss/browser` CDN | Tailwind v4 (2025) | Zero-build for dev/prototyping -- acceptable for internal LAN tool |
| `aioredis` package | `redis.asyncio` module | redis-py 4.2 (2022) | Already handled in project -- redis-py 5.3.1 in requirements |

**Deprecated/outdated:**
- `hx-sse` attribute (HTMX v1): Replaced by `sse-connect`/`sse-swap` via extension in HTMX 2.0.
- `@tailwindcss/browser@4` CDN via `cdn.tailwindcss.com`: Use `@tailwindcss/browser@4.2.3` from unpkg/jsdelivr for pinned version.

## Open Questions

1. **SSE Auth via Cookie or Query Parameter**
   - What we know: EventSource API cannot set HTTP headers. Existing SSE endpoint requires Bearer JWT.
   - What's unclear: Whether to modify existing endpoint to accept cookie auth, create a separate template-only SSE endpoint, or pass token as query parameter.
   - Recommendation: Create a lightweight SSE wrapper endpoint at `/events/stream` that reads JWT from httpOnly cookie and proxies to the same event_manager queue. This avoids modifying the existing API endpoint.

2. **Elapsed Time Formatting**
   - What we know: Review cards show "2m ago", "1h ago" relative timestamps.
   - What's unclear: Whether to use a library (humanize) or simple server-side helper.
   - Recommendation: Simple Jinja2 filter function -- calculate diff between `now` and `created_at`, render as "{n}m ago" / "{n}h ago" / "{n}d ago". No library needed for this scope.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | Runtime | Yes | 3.12+ | -- |
| FastAPI 0.136 | Template routes | Yes | 0.136.1 | -- |
| jinja2-fragments | Partial rendering | No (not installed) | -- | Must install |
| python-multipart | Form handling | No (not installed) | -- | Must install |
| Redis | One-time tokens | Yes (runtime) | 7.x | Graceful degradation for dev |
| SQLite | Review data | Yes | system | -- |

**Missing dependencies with no fallback:**
- `jinja2-fragments==1.8.0` -- must be added to `requirements.txt`
- `python-multipart==0.0.20` -- must be added to `requirements.txt`

**Missing dependencies with fallback:**
- None -- all other dependencies are CDN-loaded or already installed.

## Sources

### Primary (HIGH confidence)
- HTMX SSE Extension official docs (htmx.org/extensions/sse/) -- confirmed `sse-connect`/`sse-swap` attribute names, `hx-ext="sse"` requirement, `htmx-ext-sse@2.2.4` CDN URL
- Tailwind CSS Play CDN docs (tailwindcss.com/docs/installation/play-cdn) -- confirmed `@tailwindcss/browser` package for v4 CDN
- Existing codebase: `app/api/v1/events.py`, `app/api/v1/actions.py`, `app/api/v1/auth.py`, `app/models/schemas.py` -- verified API shapes, auth patterns, SSE implementation

### Secondary (MEDIUM confidence)
- jinja2-fragments GitHub README -- `render_block` API for FastAPI integration
- Alpine.js documentation -- `x-data`, `x-show`, `x-for`, `@event.window` patterns

### Tertiary (LOW confidence)
- None -- all findings verified against primary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries verified, versions confirmed against PyPI and official docs
- Architecture: HIGH -- patterns directly from HTMX official docs and existing codebase analysis
- Pitfalls: HIGH -- HTMX 2.0 SSE migration issue verified on official htmx.org docs

**Research date:** 2026-05-06
**Valid until:** 2026-06-06 (stable libraries, low churn expected)
