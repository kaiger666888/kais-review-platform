---
phase: 20-desktop-workstation
plan: 03
subsystem: interaction
tags: [keyboard-shortcuts, comparison-view, batch-operations, policy-drawer, alpine-js]

# Dependency graph
requires:
  - phase: 20 plan: 01
    provides: Workstation page, decision panel, shot queue, OOB swap pattern
  - phase: 20 plan: 02
    provides: Media player with video playback, frame extraction, candidate grid
provides:
  - Keyboard shortcut listeners via Alpine.js @keydown.document (Space/Y/N/J/K/D/B/G/Esc)
  - Input field guard preventing shortcut firing during text entry
  - Dual-column comparison overlay with first-last, current-history, current-reference modes
  - Batch mode with Ctrl+click individual toggle and Shift+click range selection
  - Batch approve/reject HTMX routes with partial success pattern
  - Git policy slide-over drawer with HTMX content loading
  - Shot queue card data attributes for DOM-based Alpine.js state tracking
affects: []

# Tech tracking
tech-stack:
  added: []
patterns:
  - Keyboard shortcut pattern: @keydown.document.prevent with isInputFocused() guard
  - Batch selection pattern: toggleSelect() with Ctrl/Shift event handling, DOM-based allShotIds tracking
  - Comparison overlay: fixed overlay with grid-cols-2, mode switching via comparisonMode state
  - Policy drawer: x-transition slide-in from right with HTMX hx-get content loading
  - Batch routes: fetch() POST with JSON body, partial success counting, queue refresh

key-files:
  created:
    - app/templates/partials/_comparison_view.html
    - app/templates/partials/_batch_toolbar.html
    - app/templates/partials/_policy_drawer.html
  modified:
    - app/templates/pages/workstation.html
    - app/templates/partials/_shot_queue_card.html
    - app/web/routes.py

key-decisions:
  - "Used @keydown.document.prevent instead of @keydown.window.prevent per research (Alpine.js .prevent unreliable with .window scope)"
  - "refreshShotIds() reads data-shot-id from DOM after HTMX settles, keeping Alpine state in sync with server-rendered queue"
  - "Shot queue cards include data-first-frame and data-last-frame attributes for comparison view image loading"
  - "Batch approve/reject use fetch() with JSON body (not HTMX form) since selection state lives in Alpine.js client-side"
  - "Policy drawer uses hx-trigger='load' to fetch content on mount, with Refresh button for manual reload"

patterns-established:
  - "Keyboard handler pattern: @keydown.document.prevent.{key}='handleKey($event, key)' with isInputFocused() guard"
  - "Batch HTMX route pattern: POST /partials/shot-cards/batch/{action} returning updated queue HTML with toast trigger"

requirements-completed: [UI-D-02, UI-D-03, UI-D-04]

# Metrics
duration: 3min
completed: 2026-05-17
---

# Phase 20 Plan 03: Keyboard Shortcuts, Comparison, Batch, Policy Summary

**Keyboard-driven navigation, dual-column comparison view, batch operations with Ctrl/Shift selection, and Git policy drawer**

## Performance

- **Duration:** 3 min
- **Tasks:** 1
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments
- Keyboard shortcuts via Alpine.js @keydown.document: Space (play/pause), Y (approve), N (reject), J (next shot), K (prev shot), D (comparison), B (batch), G (policy), Esc (reset)
- Input field guard prevents shortcuts from firing when typing in filter inputs, reject reason textarea, or select elements
- Dual-column comparison overlay with three modes: first-vs-last frame, current-vs-history, current-vs-reference
- Batch mode: B toggles batch mode, Ctrl+click toggles individual selection, Shift+click range-selects, yellow ring highlights selected cards
- Batch approve/reject buttons appear in header when items selected, with count display
- Batch route handlers in routes.py with partial success counting and toast notifications
- Git policy drawer slides in from right with x-transition, loads content via HTMX from /api/v1/policies/current
- Shot queue cards include data-shot-id, data-first-frame, data-last-frame attributes for Alpine.js DOM tracking
- refreshShotIds() syncs Alpine state with server-rendered queue after HTMX settles

## Task Commits

1. **Task 1: Add keyboard shortcuts, comparison view, batch operations, and policy drawer** - `92b5f7e` (feat)

## Files Created/Modified
- `app/templates/pages/workstation.html` - Added 9 keyboard listeners, expanded workstationState with navigation, batch, comparison, policy methods
- `app/templates/partials/_comparison_view.html` - Side-by-side comparison overlay with mode selector, frame images, keyboard hint
- `app/templates/partials/_batch_toolbar.html` - Reusable batch mode status indicator
- `app/templates/partials/_policy_drawer.html` - Slide-over drawer with policy content, commit SHA display, refresh button
- `app/templates/partials/_shot_queue_card.html` - Added data-shot-id, data-first-frame, data-last-frame attributes, toggleSelect click handler
- `app/web/routes.py` - Added batch approve/reject HTMX endpoints with partial success pattern

## Decisions Made
- Used @keydown.document.prevent instead of @keydown.window.prevent for reliable keyboard event interception
- DOM-based shot ID tracking via data-shot-id attributes instead of maintaining separate Alpine state array
- Comparison images loaded from card data attributes instead of separate API call
- Batch operations use fetch() with JSON body (not HTMX form) because selection state is client-side Alpine.js

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None

## Next Phase Readiness
- Desktop workstation interaction model is complete (Plans 01-03)
- Ready for mobile PWA (Phase 21) or additional workstation enhancements
- Policy drawer depends on /api/v1/policies/current endpoint being implemented

---
*Phase: 20-desktop-workstation*
*Completed: 2026-05-17*
