---
phase: 16-shot-card-aggregation
plan: 01
subsystem: api
tags: [aggregation, event-driven, jsonb, sqlalchemy, pydantic, topology-collapser, progressive-fill]

# Dependency graph
requires:
  - phase: 15-foundation
    provides: ShotCard SQLAlchemy model, PostgreSQL database.py, async_session_factory, base.py
provides:
  - Typed event protocol (NodeCompletedEvent, BundleReadyEvent, ShotCardUpdatedEvent)
  - TopologyCollapser with NODE_BUNDLE_MAP registry (9 node types)
  - ProgressiveFillEngine with deep_merge + readiness checks
  - ShotCardAggregator orchestrator (collapse -> ensure -> fill -> check -> emit)
affects: [16-02, api-endpoints, arq-tasks, event-bus]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Event-driven aggregation pipeline: node_completed -> collapse -> fill -> emit"
    - "Order-agnostic deep merge for JSONB progressive fill"
    - "IntegrityError race handling for concurrent Shot Card creation"
    - "flag_modified() on every JSONB mutation for SQLAlchemy dirty tracking"

key-files:
  created:
    - app/core/event_types.py
    - app/services/__init__.py
    - app/services/topology_collapser.py
    - app/services/progressive_fill.py
    - app/services/aggregator.py
  modified: []

key-decisions:
  - "AudioGen node override: merge_data={'status': 'ready'} regardless of node_output"
  - "visual_bundle check_bundle_complete requires keyframes.first (not just keyframes) AND prompt"
  - "Default min_audit_set is ['visual_bundle'] on new Shot Cards"
  - "_ensure_shot_card uses IntegrityError catch + re-query for concurrent creation safety"

patterns-established:
  - "NODE_BUNDLE_MAP dict registry for node type -> bundle path mapping (data-driven, easy to extend)"
  - "Three-layer service architecture: Collapser (mapping) -> Filler (persistence) -> Aggregator (orchestration)"
  - "Event broadcast via existing EventManager.broadcast() for SSE fan-out"

requirements-completed: [SHOT-03, SHOT-04]

# Metrics
duration: 6min
completed: 2026-05-16
---

# Phase 16 Plan 01: Shot Card Aggregation Pipeline Summary

**Event-driven aggregation pipeline with topology collapser (9 node types), progressive fill engine (deep merge + flag_modified), and aggregator orchestrator (IntegrityError-safe creation)**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-16T08:14:40Z
- **Completed:** 2026-05-16T08:21:19Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Typed Pydantic event protocol for node_completed, bundle_ready, and shot_card_updated events
- TopologyCollapser maps all 9 OpenClaw node types to correct Shot Card bundle fields (FLUX.1-dev -> visual_bundle.keyframes.first, AudioPrompt -> audio_bundle.bgm_prompt, etc.)
- ProgressiveFillEngine with order-agnostic deep merge that preserves existing nested keys when new data arrives
- ShotCardAggregator orchestrator handles full pipeline with IntegrityError race condition for concurrent creation

## Task Commits

Each task was committed atomically:

1. **Task 1: Create event types, topology collapser, and progressive fill engine** - `2463396` (feat)
2. **Task 2: Create aggregator orchestrator service** - `e1a30b4` (feat)

## Files Created/Modified
- `app/core/event_types.py` - Pydantic event models (NodeCompletedEvent, BundleReadyEvent, ShotCardUpdatedEvent)
- `app/services/__init__.py` - Package init exporting all three service classes
- `app/services/topology_collapser.py` - NODE_BUNDLE_MAP registry + TopologyCollapser class
- `app/services/progressive_fill.py` - ProgressiveFillEngine with fill(), _deep_merge(), check_min_audit_set(), check_bundle_complete()
- `app/services/aggregator.py` - ShotCardAggregator orchestrator with handle_node_completion(), _ensure_shot_card(), _emit_events()

## Decisions Made
- AudioGen node overrides node_output with fixed `{"status": "ready"}` since audio generation completion signals status change, not data payload
- check_bundle_complete for visual_bundle checks keyframes.first specifically (not just keyframes), ensuring the first frame image exists before marking visual bundle complete
- Default min_audit_set on new Shot Cards is ["visual_bundle"] -- audio is not required for initial audit readiness
- _ensure_shot_card uses IntegrityError catch + rollback + re-query pattern for concurrent creation safety, relying on shot_id unique constraint

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Worktree was behind master (pre-Phase 15). Resolved by fast-forward merging master into worktree branch to get ShotCard model and updated database.py/config.py.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All four service modules importable and functional
- ShotCardAggregator ready to be wired into API endpoints (Plan 16-02)
- Event types ready for arq task integration
- ProgressiveFillEngine ready for database testing with live PostgreSQL

## Self-Check: PASSED

- app/core/event_types.py: FOUND
- app/services/__init__.py: FOUND
- app/services/topology_collapser.py: FOUND
- app/services/progressive_fill.py: FOUND
- app/services/aggregator.py: FOUND
- .planning/phases/16-shot-card-aggregation/16-01-SUMMARY.md: FOUND
- Commit 2463396 (Task 1): FOUND
- Commit e1a30b4 (Task 2): FOUND

---
*Phase: 16-shot-card-aggregation*
*Completed: 2026-05-16*
