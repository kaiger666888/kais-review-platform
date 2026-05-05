"""Review approve/reject action endpoints.

POST /api/v1/reviews/{review_id}/approve -- Approve a review (REV-04)
POST /api/v1/reviews/{review_id}/reject  -- Reject a review (REV-05)

Both endpoints support JWT auth and one-time review tokens.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import consume_review_token, get_current_client
from app.core.database import get_db
from app.core.state_machine import (
    InvalidTransitionError,
    StateConflictError,
    transition_state,
)
from app.core.dependencies import get_redis
from app.models.schema import Review
from app.models.schemas import (
    ApiResponse,
    ApproveRequest,
    RejectRequest,
    ReviewResponse,
    ReviewState,
)

router = APIRouter(prefix="/api/v1/reviews", tags=["actions"])


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


async def _resolve_actor(
    review_id: int,
    token: str | None,
    client: str,
    redis,
) -> str:
    """Resolve the actor identity from JWT client or one-time token.

    Returns the actor string (e.g. "token_holder" or "client:xyz").
    Raises HTTPException on auth failures.
    """
    if token:
        if redis is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis unavailable for token validation",
            )
        review_id_from_token = await consume_review_token(redis, token)
        if review_id_from_token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalid or already used",
            )
        if int(review_id_from_token) != review_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token does not match review",
            )
        return "token_holder"
    return f"client:{client}"


# ---------------------------------------------------------------------------
# POST /{review_id}/approve
# ---------------------------------------------------------------------------


@router.post(
    "/{review_id}/approve",
    response_model=ApiResponse[ReviewResponse],
)
async def approve_review(
    review_id: int,
    request: ApproveRequest,
    token: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
    redis=Depends(get_redis),
):
    """Approve a review item.

    Supports both JWT auth and one-time review token (via ?token=xxx).
    The review must be in APPROVING state.
    """
    actor = await _resolve_actor(review_id, token, client, redis)

    review = await db.get(Review, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review {review_id} not found",
        )

    if review.state != ReviewState.APPROVING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Review is not in APPROVING state, current state: {review.state}",
        )

    try:
        await transition_state(
            db,
            review.id,
            ReviewState.APPROVING,
            ReviewState.COMPLETE,
            review.version,
            actor,
            action="approve",
            payload={"comment": request.comment},
        )
    except StateConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="State conflict: review was modified concurrently",
        )
    except InvalidTransitionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invalid state transition",
        )

    await db.refresh(review)
    return ApiResponse(
        data=_review_response(review).model_dump(),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# POST /{review_id}/reject
# ---------------------------------------------------------------------------


@router.post(
    "/{review_id}/reject",
    response_model=ApiResponse[ReviewResponse],
)
async def reject_review(
    review_id: int,
    request: RejectRequest,
    token: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
    redis=Depends(get_redis),
):
    """Reject a review item.

    Requires a mandatory reason (min_length=1, max_length=500).
    Supports both JWT auth and one-time review token (via ?token=xxx).
    The review must be in APPROVING state.
    """
    actor = await _resolve_actor(review_id, token, client, redis)

    review = await db.get(Review, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review {review_id} not found",
        )

    if review.state != ReviewState.APPROVING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Review is not in APPROVING state, current state: {review.state}",
        )

    try:
        await transition_state(
            db,
            review.id,
            ReviewState.APPROVING,
            ReviewState.COMPLETE,
            review.version,
            actor,
            action="reject",
            payload={"reason": request.reason},
        )
    except StateConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="State conflict: review was modified concurrently",
        )
    except InvalidTransitionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invalid state transition",
        )

    await db.refresh(review)
    return ApiResponse(
        data=_review_response(review).model_dump(),
        meta={"request_id": _request_id()},
    )
