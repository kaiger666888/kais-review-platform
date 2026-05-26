"""Review approve/reject action endpoints.

POST /api/v1/reviews/{review_id}/approve -- Approve a review (REV-04)
POST /api/v1/reviews/{review_id}/reject  -- Reject a review (REV-05)
POST /api/v1/reviews/{review_id}/token   -- Generate one-time review token (DEBT-01)
POST /api/v1/reviews/batch/approve       -- Batch approve multiple reviews
POST /api/v1/reviews/batch/reject        -- Batch reject multiple reviews

Both approve/reject endpoints support JWT auth and one-time review tokens.
Batch endpoints support JWT auth only (programmatic use).
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import consume_review_token, create_review_token, get_current_client
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
    BatchApproveRequest,
    BatchItemResult,
    BatchRejectRequest,
    BatchResponse,
    RejectRequest,
    ReviewResponse,
    ReviewState,
    ReviewTokenResponse,
)

logger = structlog.get_logger(__name__)

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
# POST /batch/approve -- Batch approve multiple reviews
# ---------------------------------------------------------------------------


@router.post(
    "/batch/approve",
    status_code=status.HTTP_207_MULTI_STATUS,
    response_model=ApiResponse[BatchResponse],
)
async def batch_approve_reviews(
    request: BatchApproveRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Batch approve multiple reviews in a single request.

    Processes each review independently. Returns 207 Multi-Status with
    per-item success/failure results. Partial success is the normal model.
    Only reviews in APPROVING state can be approved.
    """
    items: list[BatchItemResult] = []
    success_count = 0
    failure_count = 0
    actor = f"client:{client}"

    for review_id in request.review_ids:
        review = await db.get(Review, review_id)
        if review is None:
            items.append(
                BatchItemResult(
                    review_id=review_id, status="failed", error="Review not found"
                )
            )
            failure_count += 1
            continue

        if review.state != ReviewState.APPROVING.value:
            items.append(
                BatchItemResult(
                    review_id=review_id,
                    status="failed",
                    error=f"Review is not in APPROVING state, current state: {review.state}",
                )
            )
            failure_count += 1
            continue

        try:
            await transition_state(
                db,
                review.id,
                ReviewState.APPROVING,
                ReviewState.COMPLETE,
                review.version,
                actor,
                action="batch_approve",
                payload={"comment": request.comment, "batch": True},
            )
            items.append(
                BatchItemResult(review_id=review_id, status="success")
            )
            success_count += 1
        except StateConflictError:
            items.append(
                BatchItemResult(
                    review_id=review_id,
                    status="failed",
                    error="State conflict: review was modified concurrently",
                )
            )
            failure_count += 1
        except InvalidTransitionError:
            items.append(
                BatchItemResult(
                    review_id=review_id,
                    status="failed",
                    error="Invalid state transition",
                )
            )
            failure_count += 1
        except Exception as e:
            logger.error(
                "batch_approve_item_failed",
                review_id=review_id,
                error=str(e),
            )
            items.append(
                BatchItemResult(
                    review_id=review_id,
                    status="failed",
                    error=str(e),
                )
            )
            failure_count += 1

    return ApiResponse(
        data=BatchResponse(
            total=len(request.review_ids),
            success_count=success_count,
            failure_count=failure_count,
            items=items,
        ).model_dump(),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# POST /batch/reject -- Batch reject multiple reviews
# ---------------------------------------------------------------------------


@router.post(
    "/batch/reject",
    status_code=status.HTTP_207_MULTI_STATUS,
    response_model=ApiResponse[BatchResponse],
)
async def batch_reject_reviews(
    request: BatchRejectRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Batch reject multiple reviews in a single request.

    Processes each review independently. Returns 207 Multi-Status with
    per-item success/failure results. Partial success is the normal model.
    Only reviews in APPROVING state can be rejected.
    """
    items: list[BatchItemResult] = []
    success_count = 0
    failure_count = 0
    actor = f"client:{client}"

    for review_id in request.review_ids:
        review = await db.get(Review, review_id)
        if review is None:
            items.append(
                BatchItemResult(
                    review_id=review_id, status="failed", error="Review not found"
                )
            )
            failure_count += 1
            continue

        if review.state != ReviewState.APPROVING.value:
            items.append(
                BatchItemResult(
                    review_id=review_id,
                    status="failed",
                    error=f"Review is not in APPROVING state, current state: {review.state}",
                )
            )
            failure_count += 1
            continue

        try:
            await transition_state(
                db,
                review.id,
                ReviewState.APPROVING,
                ReviewState.COMPLETE,
                review.version,
                actor,
                action="batch_reject",
                payload={"reason": request.reason, "batch": True},
            )
            items.append(
                BatchItemResult(review_id=review_id, status="success")
            )
            success_count += 1
        except StateConflictError:
            items.append(
                BatchItemResult(
                    review_id=review_id,
                    status="failed",
                    error="State conflict: review was modified concurrently",
                )
            )
            failure_count += 1
        except InvalidTransitionError:
            items.append(
                BatchItemResult(
                    review_id=review_id,
                    status="failed",
                    error="Invalid state transition",
                )
            )
            failure_count += 1
        except Exception as e:
            logger.error(
                "batch_reject_item_failed",
                review_id=review_id,
                error=str(e),
            )
            items.append(
                BatchItemResult(
                    review_id=review_id,
                    status="failed",
                    error=str(e),
                )
            )
            failure_count += 1

    return ApiResponse(
        data=BatchResponse(
            total=len(request.review_ids),
            success_count=success_count,
            failure_count=failure_count,
            items=items,
        ).model_dump(),
        meta={"request_id": _request_id()},
    )


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
        transition_payload = {"comment": request.comment}
        if request.selected_candidates:
            transition_payload["selected_candidates"] = request.selected_candidates
            await db.execute(
                update(Review)
                .where(Review.id == review.id)
                .values(selected_candidates=request.selected_candidates)
            )
        if request.scores:
            transition_payload["scores"] = request.scores
            await db.execute(
                update(Review)
                .where(Review.id == review.id)
                .values(scores_json=request.scores)
            )
        await db.commit()
        await db.refresh(review)

        await transition_state(
            db,
            review.id,
            ReviewState.APPROVING,
            ReviewState.COMPLETE,
            review.version,
            actor,
            action="approve",
            payload=transition_payload,
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

    if request.result:
        metadata = review.metadata_json or {}
        metadata["review_result"] = request.result.model_dump()
        review.metadata_json = metadata

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


# ---------------------------------------------------------------------------
# POST /{review_id}/token
# ---------------------------------------------------------------------------


@router.post(
    "/{review_id}/token",
    response_model=ApiResponse[ReviewTokenResponse],
)
async def generate_review_token_endpoint(
    review_id: int,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
    redis=Depends(get_redis),
):
    """Generate a one-time review token for deep-linking reviewers.

    Any JWT-authenticated client can create tokens for reviews.
    The token is stored in Redis with a 72-hour TTL and can be
    consumed once via the approve/reject endpoints.
    """
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable for token generation",
        )

    review = await db.get(Review, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review {review_id} not found",
        )

    token = await create_review_token(redis, review_id, ttl=259200)
    review_url = f"/t/{token}"

    return ApiResponse(
        data=ReviewTokenResponse(
            token=token,
            expires_in=259200,
            review_url=review_url,
        ).model_dump(),
        meta={"request_id": _request_id()},
    )
