---
phase: 18-routing-checkpoints
plan: 01
subsystem: api
tags: [priority-queue, batch-operations, sqlalchemy, fastapi, pydantic]

requires:
  - phase: 01-core-engine
    provides: state machine, policy engine, review model
  - phase: 08-schema-callback-infrastructure
    provides: callback fields, review submission with callback_url

provides:
  - Priority-ordered approval queue via sort=priority query parameter
  - Batch approve endpoint (POST /api/v1/reviews/batch/approve)
  - Batch reject endpoint (POST /api/v1/reviews/batch/reject)
  - ApprovalRouter service module with priority weight mapping
  - Batch Pydantic schemas (BatchApproveRequest, BatchRejectRequest, BatchResponse)

affects: [reviews-api, actions-api, review-queue, frontend-approval-queue]

tech-stack:
  added: []
  patterns: [priority-weight-mapping, batch-partial-success, sqlalchemy-case-ordering]

key-files:
  created:
    - app/services/__init__.py
    - app/services/approval_router.py
    - tests/test_approval_router.py
    - tests/test_batch_actions.py
  modified:
    - app/models/schemas.py
    - app/models/__init__.py
    - app/api/v1/reviews.py
    - app/api/v1/actions.py

key-decisions:
  - "Priority sort uses SQLAlchemy CASE expression for SQLite compatibility (no new index needed for expected volumes)"
  - "Batch operations use partial success model with 207 Multi-Status (individual failures don't block other items)"
  - "Batch routes registered before parameterized routes to avoid path matching conflicts"
  - "Batch endpoints use JWT auth only (no one-time tokens) since batch is programmatic"

patterns-established:
  - "Priority weight mapping: PRIORITY_WEIGHT dict maps string priority to int for ORDER BY"
  - "Batch response pattern: BatchResponse with per-item BatchItemResult for partial success"
  - "Batch audit trail: batch=True in payload distinguishes batch operations from single actions"

requirements-completed: [ROUTER-01, ROUTER-02, BATCH-01, BATCH-02]

duration: 13min
completed: 2026-05-16
---

# Phase 18 Plan 01: Approval Router with Priority Queues + Batch Approval Summary

**Priority-ordered approval queue with SQLAlchemy CASE-based sorting and batch approve/reject with partial success (207 Multi-Status)**

## Performance

- **Duration:** 13 min
- **Started:** 2026-05-16T11:59:05Z
- **Completed:** 2026-05-16T12:12:11Z
- **Tasks:** 5
- **Files modified:** 8

## Accomplishments
- ApprovalRouter service with priority weight mapping (critical=4 > high=3 > normal=2 > low=1)
- List reviews endpoint supports sort=priority for urgent-first ordering within APPROVING state
- Batch approve/reject endpoints with per-item success/failure reporting (207 Multi-Status)
- 25 new tests covering priority ordering, batch operations, partial success, and schema validation
- All 255 tests passing (no regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ApprovalRouter service module** - `3fa4109` (feat)
2. **Task 2: Add batch schemas** - `fe604f5` (feat)
3. **Task 3: Add priority sort to list reviews** - `62a07a0` (feat)
4. **Task 4: Add batch approve/reject endpoints** - `c1bd00b` (feat)
5. **Task 5: Add comprehensive tests** - `b420cc8` (test)

## Files Created/Modified
- `app/services/__init__.py` - Services package initialization
- `app/services/approval_router.py` - Priority weight mapping, queue query builder, get_priority_sorted_reviews()
- `app/models/schemas.py` - Added BatchApproveRequest, BatchRejectRequest, BatchItemResult, BatchResponse
- `app/models/__init__.py` - Export new batch schemas
- `app/api/v1/reviews.py` - Added sort parameter with priority ordering via SQLAlchemy CASE
- `app/api/v1/actions.py` - Added batch/approve and batch/reject endpoints before parameterized routes
- `tests/test_approval_router.py` - 12 tests: weight mapping, queue ordering, same-priority FIFO, edge cases
- `tests/test_batch_actions.py` - 13 tests: batch approve/reject, partial success, audit trail, schema validation

## Decisions Made
- Priority sort uses SQLAlchemy CASE expression for SQLite compatibility (no new index needed for expected volumes under 1000 pending reviews)
- Batch operations use partial success model with 207 Multi-Status (individual failures don't block other items)
- Batch routes registered before parameterized routes to prevent FastAPI from attempting to match "batch" as a review_id integer
- Batch endpoints restricted to JWT auth only (no one-time tokens) since batch operations are programmatic
- Max batch size set to 100 items to prevent abuse

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Route ordering: batch routes (`/batch/approve`, `/batch/reject`) must be registered before parameterized routes (`/{review_id}/approve`) because FastAPI evaluates routes in registration order. While `review_id: int` would reject "batch" as non-numeric, placing batch routes first is the safer pattern.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Approval queue ready for frontend integration (priority-sorted review list)
- Batch operations ready for Telegram Bot integration (batch approve via Bot)
- Could extend to WebSocket-based real-time queue updates in future phases

## Self-Check: PASSED

- All 8 created/modified files verified present
- All 5 task commits verified in git log (3fa4109, fe604f5, 62a07a0, c1bd00b, b420cc8)
- All 255 tests passing (no regressions)

---
*Phase: 18-routing-checkpoints*
*Completed: 2026-05-16*
