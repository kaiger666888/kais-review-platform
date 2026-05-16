# Research: Phase 18 — Approval Router with Priority Queues + Batch Approval

**Date:** 2026-05-16
**Status:** Complete

## Problem Statement

Currently reviews land in APPROVING state without any ordering. When multiple reviews are pending approval, reviewers see them in database insertion order (id-desc). High-priority and critical reviews should surface first.

Additionally, approving/rejecting multiple reviews requires individual API calls — no batch operation exists. For reviewers handling bursts (e.g., gold-team dispatches 20 GPU tasks), this is tedious.

## Current Architecture

### Data Flow
1. `POST /api/v1/reviews/` → PolicyEngine evaluates → routes to APPROVING
2. `GET /api/v1/reviews/?status=APPROVING` → Lists reviews by id-desc (no priority sort)
3. `POST /api/v1/reviews/{id}/approve` → One review at a time
4. `POST /api/v1/reviews/{id}/reject` → One review at a time

### Priority Field
- `Review.priority`: `low`, `normal`, `high`, `critical` (validated in Pydantic)
- Currently used for policy evaluation only (critical → HUMAN route)
- NOT used for queue ordering in list_reviews endpoint

### Database Indexes
- `ix_reviews_state_created` on (state, created_at) — covers status filter but not priority ordering

## Design Decisions

### 1. Priority Ordering in List Endpoint
**Option A:** Modify `list_reviews` to sort by priority weight, then created_at when status=APPROVING
**Option B:** New dedicated endpoint `/api/v1/reviews/approval-queue`

**Choice: Option A** — Simpler, backward-compatible. Add `sort` query parameter. Default `id-desc` for backward compat, `priority` for new callers. Priority sort uses weight mapping: critical=4, high=3, normal=2, low=1.

### 2. Batch Approval/Reject
**Option A:** New endpoint `POST /api/v1/reviews/batch/approve` with `{"review_ids": [1,2,3]}`
**Option B:** Add `batch` flag to existing approve/reject endpoints with comma-separated IDs

**Choice: Option A** — Cleaner separation, dedicated request/response schemas. Batch operations are semantically different from single operations (partial success, per-item errors).

### 3. Priority Queue Service
**Option A:** Separate ApprovalRouter service class encapsulating priority logic
**Option B:** Inline logic in endpoint handlers

**Choice: Option A** — Testable in isolation, encapsulates priority weight mapping and queue retrieval logic. Placed in `app/services/approval_router.py`.

### 4. Database Index for Priority Sort
**Approving reviews sorted by priority weight** — SQLite can compute this with CASE expressions. No new index needed for expected volumes (<1000 pending reviews). If performance becomes an issue later, add a computed column.

### 5. Batch Atomicity
Each review in a batch is processed independently. Partial success is the model:
- Some succeed → their state transitions complete
- Some fail (wrong state, version conflict) → reported in response
- Overall HTTP 207 Multi-Status returned

## Priority Weight Mapping

```python
PRIORITY_WEIGHT = {"critical": 4, "high": 3, "normal": 2, "low": 1}
```

## API Design

### Sort Parameter for List Endpoint
```
GET /api/v1/reviews/?status=APPROVING&sort=priority
```
Returns reviews sorted by priority weight (desc), then created_at (asc).

### Batch Approve
```
POST /api/v1/reviews/batch/approve
{
  "review_ids": [1, 2, 3],
  "comment": "Batch approved"
}
```
Response (207 Multi-Status):
```json
{
  "data": {
    "succeeded": [1, 2],
    "failed": [{"review_id": 3, "error": "Review is not in APPROVING state"}],
    "total": 3,
    "success_count": 2,
    "failure_count": 1
  }
}
```

### Batch Reject
```
POST /api/v1/reviews/batch/reject
{
  "review_ids": [1, 2],
  "reason": "Batch rejected"
}
```

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `app/services/approval_router.py` | Create | Priority weight mapping, queue query builder |
| `app/models/schemas.py` | Modify | Add BatchApproveRequest, BatchRejectRequest, BatchResponse |
| `app/api/v1/actions.py` | Modify | Add batch approve/reject endpoints |
| `app/api/v1/reviews.py` | Modify | Add sort parameter with priority ordering |
| `tests/test_approval_router.py` | Create | Unit + integration tests for approval router |
| `tests/test_batch_actions.py` | Create | Tests for batch approve/reject endpoints |

## Constraints Verified

- **No new dependencies** — Uses existing SQLAlchemy, FastAPI, Pydantic
- **SQLite compatible** — CASE expression for priority ordering works in SQLite
- **Backward compatible** — Default sort is id-desc (existing behavior)
- **< 400MB RAM** — No in-memory queues, database-driven ordering
- **Audit trail** — Each batch item gets its own audit entry (no coalescing)
