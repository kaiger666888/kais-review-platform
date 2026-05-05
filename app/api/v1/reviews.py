"""Review submission and query endpoints.

POST /api/v1/reviews       -- Submit a review item (REV-01, REV-02, REV-03)
GET  /api/v1/reviews/{id}  -- Query review status (REV-06)
GET  /api/v1/reviews       -- List reviews with filters and cursor pagination (REV-07)
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_client
from app.core.database import get_db
from app.core.policy import get_policy_engine
from app.core.state_machine import (
    InvalidTransitionError,
    StateConflictError,
    transition_state,
)
from app.models.schema import Review
from app.models.schemas import (
    ApiResponse,
    Disposition,
    PaginatedResponse,
    ReviewCreateRequest,
    ReviewResponse,
    ReviewState,
    ReviewSubmitResponse,
)

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def _review_response(review: Review) -> ReviewResponse:
    """Convert a Review ORM object to a ReviewResponse."""
    return ReviewResponse(
        id=review.id,
        type=review.type,
        content_ref=review.content_ref,
        metadata=review.metadata_json,
        source_system=review.source_system,
        priority=review.priority,
        risk_score=review.risk_score,
        state=review.state,
        disposition=review.disposition,
        version=review.version,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


# ---------------------------------------------------------------------------
# POST / -- Submit review
# ---------------------------------------------------------------------------


@router.post(
    "/",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[ReviewSubmitResponse],
)
async def submit_review(
    request: ReviewCreateRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Submit a review item for policy evaluation and routing.

    Creates the review record, evaluates it against the policy engine,
    and routes it to the appropriate state based on the disposition.
    Returns 202 Accepted with review_id, state, and routing decision.
    """
    # a. Create Review record in PENDING state
    review = Review(
        type=request.type,
        content_ref=request.content_ref,
        metadata_json=request.metadata,
        source_system=request.source_system,
        priority=request.priority,
        risk_score=request.risk_score,
        state=ReviewState.PENDING.value,
        disposition=None,
        version=1,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    # b. Transition PENDING -> POLICY_EVAL
    try:
        await transition_state(
            db,
            review.id,
            ReviewState.PENDING,
            ReviewState.POLICY_EVAL,
            1,
            "system",
            action="policy_eval_start",
        )
    except (StateConflictError, InvalidTransitionError):
        # Rare edge case: log and continue with current state
        pass

    # Refresh to pick up version after transition
    await db.refresh(review)

    # c. Evaluate policy
    engine = get_policy_engine()
    review_data = {
        "type": request.type,
        "source_system": request.source_system,
        "priority": request.priority,
        "risk_score": request.risk_score or 0.5,
        "metadata": request.metadata or {},
    }
    disposition = engine.evaluate(review_data)

    # d. Route based on disposition
    if disposition == Disposition.AUTO:
        await transition_state(
            db,
            review.id,
            ReviewState.POLICY_EVAL,
            ReviewState.COMPLETE,
            review.version,
            "policy_engine",
            action="auto_approve",
            payload={"disposition": disposition.value},
        )
    elif disposition in (Disposition.HUMAN, Disposition.AI_AUDIT):
        await transition_state(
            db,
            review.id,
            ReviewState.POLICY_EVAL,
            ReviewState.APPROVING,
            review.version,
            "policy_engine",
            action="route_human" if disposition == Disposition.HUMAN else "route_ai_audit",
            payload={"disposition": disposition.value},
        )
    elif disposition == Disposition.BLOCK:
        await transition_state(
            db,
            review.id,
            ReviewState.POLICY_EVAL,
            ReviewState.COMPLETE,
            review.version,
            "policy_engine",
            action="block",
            payload={"disposition": disposition.value},
        )

    # e. Update review disposition
    await db.refresh(review)
    review.disposition = disposition.value
    await db.commit()
    await db.refresh(review)

    # f. Return 202 Accepted with envelope
    return ApiResponse(
        data=ReviewSubmitResponse(
            review_id=review.id,
            state=review.state,
            routing=disposition.value,
        ),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# GET /{review_id} -- Query review status
# ---------------------------------------------------------------------------


@router.get("/{review_id}", response_model=ApiResponse[ReviewResponse])
async def get_review(
    review_id: int,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Query a review by ID. Returns full review data or 404."""
    review = await db.get(Review, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review {review_id} not found",
        )

    return ApiResponse(
        data=_review_response(review).model_dump(),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# GET / -- List reviews with filters and cursor pagination
# ---------------------------------------------------------------------------


@router.get("/", response_model=ApiResponse[PaginatedResponse[ReviewResponse]])
async def list_reviews(
    status_filter: str | None = Query(None, alias="status"),
    type_filter: str | None = Query(None, alias="type"),
    source: str | None = Query(None),
    priority: str | None = Query(None),
    cursor: int | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """List reviews with optional filters and id-based cursor pagination.

    Results are ordered by id descending (newest first).
    Cursor is an id value: reviews with id < cursor are returned.
    """
    query = select(Review).order_by(Review.id.desc()).limit(limit + 1)

    if cursor:
        query = query.where(Review.id < cursor)
    if status_filter:
        query = query.where(Review.state == status_filter)
    if type_filter:
        query = query.where(Review.type == type_filter)
    if source:
        query = query.where(Review.source_system == source)
    if priority:
        query = query.where(Review.priority == priority)

    result = await db.execute(query)
    rows = result.scalars().all()

    # Determine pagination
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1].id if has_more and items else None

    return ApiResponse(
        data=PaginatedResponse(
            items=[_review_response(r).model_dump() for r in items],
            next_cursor=next_cursor,
            has_more=has_more,
        ),
        meta={"request_id": _request_id()},
    )
