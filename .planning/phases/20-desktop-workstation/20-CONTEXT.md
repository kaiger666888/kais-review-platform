# Phase 20: Desktop Workstation - Context

**Gathered:** 2026-05-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Reviewers use a 3-column desktop workstation to efficiently review Shot Cards with keyboard shortcuts, media playback, comparisons, and batch operations. This phase builds the complete desktop review UI with three panels (shot queue, media preview, decision), keyboard-driven navigation, dual-column comparison, batch operations, and media playback infrastructure.

</domain>

<decisions>
## Implementation Decisions

### Layout & Panel Design
- 3-column layout: Left 25% / Center 45% / Right 30% via Tailwind grid `grid-cols-[25fr_45fr_30fr]`
- Left panel shot queue uses cursor-based pagination via HTMX infinite scroll (`hx-get="/partials/shot-queue?cursor={last_id}"`)
- Server-side filtering via HTMX: filter controls send `hx-get` with query params (`?project=X&scene=Y&risk=HIGH`)
- Collapsible panels only — click to collapse left/right panels to icon-only sidebar via Alpine.js `x-show` toggle. No drag-resize

### Media Playback & Thumbnails
- HTML5 `<video>` element — native browser support, `currentTime` for scrubbing, styled with Tailwind
- Video source via MinIO presigned URLs — `GET /api/v1/media/{shot_card_id}/video` generates presigned URL, template embeds as `<video src>`
- Frame extraction via Canvas API client-side — `video.currentTime = frame_time`, draw to `<canvas>`, export as `toDataURL()`. First/last frame at `t=0` and `t=duration-0.1`
- Candidate thumbnail grid: Tailwind `grid-cols-3 gap-2` — small thumbnails (80x45px, 16:9), click-to-switch via `hx-post`

### Keyboard Shortcuts & Interactions
- Alpine.js `@keydown.window` — global listener in base template, maps keys to actions (Space=play/pause, Y/N=approve/reject, J/K=navigate, D=diff, B=batch, G=policy)
- Batch selection via Alpine.js array + CSS highlight — `selectedItems: []`, Ctrl+click append, Shift+click range-select, `x-bind:class` for ring highlight. Batch action buttons appear when selection > 0
- Dual-column comparison: Overlay toggle in center panel — Alpine.js `showComparison` toggles single view to side-by-side `grid-cols-2`. Mode selector: first-vs-last / current-vs-history / current-vs-reference
- Git policy view (G key): Slide-over panel from right — Alpine.js drawer showing policy YAML + commit SHA, fetched via `hx-get="/api/v1/policies/{sha}"`

### Claude's Discretion
Implementation details for template structure, component decomposition, and test structure are at Claude's discretion.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/templates/base.html` — Master layout with Tailwind CDN, HTMX 2.0.9, Alpine.js 3.15.12
- `app/templates/pages/dashboard.html` — Existing review dashboard (V1 pattern, extend for V2)
- `app/templates/partials/` — HTMX partial templates (_review_card, _review_list, _review_detail, _toast, etc.)
- `app/web/routes.py` — Jinja2Templates + Jinja2Blocks configured, web route handlers
- `app/web/sse.py` — SSE stream endpoint with cookie-based JWT auth
- `app/core/events.py` — EventManager with broadcast pattern
- `app/api/v1/shot_cards.py` — Shot Card CRUD API endpoints
- `app/services/approval_router.py` — Routing logic for shot cards
- `app/models/shot_card.py` — ShotCard model with visual_bundle, audio_bundle, narrative_context JSONB fields

### Established Patterns
- HTMX: `hx-get` for partial loads, `hx-post` for actions, `hx-target` for DOM updates, `hx-sse` for real-time
- Alpine.js: `x-data` for component state, `x-show` for visibility, `x-bind:class` for conditional styling
- Tailwind v4 CDN: `<script src="https://unpkg.com/@tailwindcss/browser@4"></script>`
- Jinja2Fragments: `Jinja2Blocks` configured but not actively used — partials use standard template rendering
- SSE: `hx-ext="sse"` with `sse-connect="/events/stream"` for real-time updates

### Integration Points
- Desktop workstation is a new page template (`app/templates/pages/workstation.html`) extending `base.html`
- Shot queue loads from Shot Card API via HTMX partials
- Decision actions (approve/reject) POST to existing or new endpoints
- SSE events update shot queue in real-time
- Media URLs generated from MinIO presigned URL endpoint (new)
- Keyboard shortcuts in Alpine.js global store in base template or workstation page

</code_context>

<specifics>
## Specific Ideas

Follow existing V1 template patterns (HTMX partials, Alpine.js state, Tailwind utilities). Extend base.html for the workstation layout. Create new partial templates for shot queue cards, media player, comparison view, and decision panel. Media endpoints are new API routes.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
