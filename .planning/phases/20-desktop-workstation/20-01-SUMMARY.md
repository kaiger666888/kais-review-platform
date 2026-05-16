---
phase: 20-desktop-workstation
plan: 01
subsystem: ui
tags: [htmx, alpinejs, tailwind, shot-card, workstation, cursor-pagination]

# Dependency graph
requires:
  - phase: 19
    provides: ShotCard model, audit_status field, API endpoints
provides:
  - Desktop workstation page with 3-column layout (25/45/30 grid)
  - Shot queue with cursor-based pagination and server-side filtering
  - Shot card detail partial with OOB swap for media preview
  - Decision panel with narrative context, prompts, node status, provenance
  - Shot Card approve/reject JSON API and HTMX wrapper endpoints
  - Candidate thumbnail grid in center panel
affects: [20-02, 20-03]

# Tech tracking
tech-stack:
  added: []
patterns:
  - OOB swap pattern: single HTMX request updates both decision panel and media preview
  - HTMX wrapper routes: thin web route handlers wrapping Shot Card state transitions with queue refresh
  - _fetch_shot_queue helper: shared pagination logic between partial and approve/reject routes

key-files:
  created:
    - app/templates/pages/workstation.html
    - app/templates/partials/_shot_queue_list.html
    - app/templates/partials/_shot_queue_card.html
    - app/templates/partials/_shot_queue_filters.html
    - app/templates/partials/_decision_panel.html
  modified:
    - app/web/routes.py
    - app/api/v1/shot_cards.py
    - app/models/schemas.py

key-decisions:
  - "OOB swap pattern for dual-panel update: shot-card-detail returns decision panel as primary + media-preview as OOB swap element"
  - "HTMX wrapper routes in routes.py for approve/reject instead of direct JSON API calls, enabling queue refresh and toast in single response"
  - "Scene filter uses JSONB astext query (narrative_context['scene'].astext == scene) for PostgreSQL JSONB column"

patterns-established:
  - "Workstation page extends base.html but overrides padding via inline style to achieve full-viewport layout"
  - "Shot queue uses intersect once trigger (not revealed) for overflow-y container scrolling"
  - "Filter controls use hx-include to bundle all filter values into every HTMX request"

requirements-completed: [UI-D-01, UI-D-05]

# Metrics
duration: 5min
completed: 2026-05-17
---

# Phase 20 Plan 01: Desktop Workstation Summary

**3-column desktop workstation with shot queue (cursor pagination + server filters), media preview with candidate grid, and decision panel with approve/reject actions via HTMX**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-16T16:45:27Z
- **Completed:** 2026-05-16T16:50:45Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Full 3-column dark-themed workstation page (25/45/30 grid) with Alpine.js state management
- Shot queue with cursor-based pagination (PAGE_SIZE=30), project/scene/risk filters, and infinite scroll
- Decision panel rendering narrative context, prompts, node status, provenance, and approve/reject buttons
- Media preview with candidate thumbnail grid via OOB swap pattern
- Shot Card approve/reject JSON API endpoints with JWT auth and HTMX wrapper routes

## Task Commits

Each task was committed atomically:

1. **Task 1: Create workstation page template and server-side routes** - `3dfbae0` (feat)
2. **Task 2: Create decision panel partial, Shot Card approve/reject API endpoints** - `93ec90b` (feat)

## Files Created/Modified
- `app/templates/pages/workstation.html` - Desktop workstation page with 3-column grid layout and Alpine.js state
- `app/templates/partials/_shot_queue_list.html` - Shot queue with cursor pagination and intersect once trigger
- `app/templates/partials/_shot_queue_card.html` - Individual shot card with thumbnail, title, status badge
- `app/templates/partials/_shot_queue_filters.html` - Project/scene/risk filter controls with HTMX re-fetch
- `app/templates/partials/_decision_panel.html` - Narrative context, prompts, status, provenance, approve/reject buttons, OOB media preview
- `app/web/routes.py` - Added /workstation, /partials/shot-queue, /partials/shot-card-detail, and HTMX approve/reject wrapper routes
- `app/api/v1/shot_cards.py` - Added POST approve/reject JSON API endpoints with AuditStatus transitions
- `app/models/schemas.py` - Added ShotCardApproveRequest and ShotCardRejectRequest Pydantic models

## Decisions Made
- Used OOB swap pattern to update both decision panel and media preview from a single HTMX request, avoiding two requests per card click
- Created thin HTMX wrapper routes in routes.py rather than having HTMX buttons POST to JSON API, enabling queue refresh and toast notification in a single round-trip
- Scene filter uses PostgreSQL JSONB `astext` query operator for filtering by narrative_context.scene field
- Extracted `_fetch_shot_queue` helper to share pagination logic between shot_queue_partial and approve/reject HTMX handlers

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Workstation page and data flow fully functional, ready for Plan 02 (media playback infrastructure)
- Shot Card approve/reject transitions working, ready for Plan 03 (keyboard shortcuts and batch operations)
- OOB swap pattern established, candidate grid renders from visual_bundle.candidates

---
*Phase: 20-desktop-workstation*
*Completed: 2026-05-17*

## Self-Check: PASSED

All 9 files verified present. Both commits (3dfbae0, 93ec90b) found in git history.
