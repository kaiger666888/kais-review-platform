# Phase 21: Mobile PWA - Context

**Gathered:** 2026-05-17
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous workflow)

<domain>
## Phase Boundary

Reviewers can approve or reject Shot Cards on mobile with swipe gestures, even when offline, seeing narrative continuity between shots. This phase creates a mobile PWA with card-flow layout, gesture controls, offline caching via Service Worker, and mobile-optimized API endpoints.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — autonomous mode. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key design points from architecture:
- Vertical swipe: shot-to-shot navigation (narrative continuity)
- Horizontal swipe: candidate switching within same shot
- Cards: first/last frame always visible, prompts/audio collapsible
- Gestures: left=approve, right=reject, up=details, pinch=zoom
- Context bar: scene + shot number + emotion curve
- Service Worker: cache 20 most recent Shot Cards
- Mobile API: paginated shot-by-shot, progressive loading (visual first, audio async)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 20 desktop workstation: workstation.html, _media_player.html — media preview patterns
- app/api/v1/shot_cards.py — Shot Card CRUD API endpoints
- app/api/v1/media.py — MinIO presigned URL media endpoints
- app/web/routes.py — HTMX web routes
- app/models/schemas.py — ShotCardResponse model
- app/core/events.py — SSE event manager

### Established Patterns
- HTMX + Alpine.js + Tailwind CSS (zero-build)
- Jinja2 templates with partial rendering
- FastAPI routers with async handlers
- Cursor-based pagination

### Integration Points
- /workstation route in routes.py (desktop entry point)
- /api/v1/shot-cards endpoints (data source)
- /api/v1/media/{id}/video and /image endpoints (media source)
- SSE endpoint for real-time updates

</code_context>

<specifics>
## Specific Ideas

Mobile PWA must follow the Notion V2 architecture design:
- Card flow layout with vertical/horizontal swipe
- PWA manifest.json for install-to-homescreen
- Service Worker with offline cache (20 Shot Cards)
- Mobile API endpoints for paginated shot-by-shot delivery
- Progressive loading: visual first, audio async

</specifics>

<deferred>
## Deferred Ideas

None — autonomous mode.
</deferred>
