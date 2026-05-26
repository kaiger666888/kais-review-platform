"""Batch review operations and candidate scoring endpoints.

POST /api/v1/reviews/batch/submit   -- Batch submit reviews
POST /api/v1/reviews/batch/approve  -- Batch approve reviews
POST /api/v1/reviews/batch/reject   -- Batch reject reviews
GET  /api/v1/reviews/batch/status   -- Batch query review status
POST /api/v1/reviews/{id}/score     -- Score a review's candidates
POST /api/v1/reviews/{id}/select    -- Select candidates for a review
GET  /api/v1/reviews/{id}/candidates -- Get candidates for a review
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_client
from app.core.database import get_db
from app.core.validation import validate_callback_url
from app.core.state_machine import (
    InvalidTransitionError,
    StateConflictError,
    transition_state,
)
from app.models.schema import Review
from app.models.schemas import (
    ApiResponse,
    BatchActionRequest,
    BatchSubmitRequest,
    CandidateScoreRequest,
    ReviewCreateRequest,
    ReviewResponse,
    ReviewState,
    ReviewSubmitResponse,
    SelectCandidatesRequest,
)

router = APIRouter(prefix="/api/v1/reviews", tags=["batch", "candidates"])


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
        callback_url=review.callback_url,
        candidates=review.candidates_json,
        selected_candidates=review.selected_candidates,
        scores=review.scores_json,
        max_selections=review.max_selections,
        version=review.version,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


# ---------------------------------------------------------------------------
# Candidate Scoring
# ---------------------------------------------------------------------------


@router.post(
    "/{review_id}/score",
    response_model=ApiResponse[ReviewResponse],
)
async def score_review(
    review_id: int,
    request: CandidateScoreRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Score a candidate within a review (1-5 stars with optional comment).

    The review must be in APPROVING state. Scores are accumulated; calling
    this endpoint multiple times adds new score entries.
    """
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

    # Accumulate scores
    scores = list(review.scores_json) if review.scores_json else []
    scores.append({
        "candidate_ref": request.candidate_ref,
        "score": request.score,
        "comment": request.comment,
        "scored_by": client,
    })

    await db.execute(
        update(Review)
        .where(Review.id == review_id)
        .values(scores_json=scores)
    )
    await db.commit()
    await db.refresh(review)

    return ApiResponse(
        data=_review_response(review).model_dump(),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# Candidate Selection
# ---------------------------------------------------------------------------


@router.post(
    "/{review_id}/select",
    response_model=ApiResponse[ReviewResponse],
)
async def select_candidates(
    review_id: int,
    request: SelectCandidatesRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Select candidates for a review. Does not change review state.

    Use this to mark preferred candidates before final approve/reject.
    """
    review = await db.get(Review, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review {review_id} not found",
        )

    # Validate max_selections if set
    if review.max_selections and len(request.selected) > review.max_selections:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot select more than {review.max_selections} candidates",
        )

    await db.execute(
        update(Review)
        .where(Review.id == review_id)
        .values(selected_candidates=request.selected)
    )
    await db.commit()
    await db.refresh(review)

    return ApiResponse(
        data=_review_response(review).model_dump(),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# Get Candidates
# ---------------------------------------------------------------------------


@router.get(
    "/{review_id}/candidates",
    response_model=ApiResponse,
)
async def get_candidates(
    review_id: int,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Get candidates for a review with their current scores."""
    review = await db.get(Review, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review {review_id} not found",
        )

    candidates = review.candidates_json or []
    scores = review.scores_json or []
    selected = review.selected_candidates or []

    # Enrich candidates with scores
    for candidate in candidates:
        ref = candidate.get("ref", "")
        candidate_scores = [s for s in scores if s.get("candidate_ref") == ref]
        candidate["scores"] = candidate_scores
        candidate["avg_score"] = (
            sum(s["score"] for s in candidate_scores) / len(candidate_scores)
            if candidate_scores
            else None
        )
        candidate["is_selected"] = ref in selected

    return ApiResponse(
        data={
            "review_id": review_id,
            "candidates": candidates,
            "max_selections": review.max_selections,
            "total_scores": len(scores),
        },
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# Batch Submit
# ---------------------------------------------------------------------------


@router.post(
    "/batch/submit",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse,
)
async def batch_submit_reviews(
    request: BatchSubmitRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Submit multiple reviews in a single request.

    Each review is processed independently. Returns list of results
    with individual review_ids and routing decisions.
    """
    from app.core.policy import get_policy_engine
    from app.models.schemas import Disposition

    results = []
    engine = get_policy_engine()

    for req in request.reviews:
        # Validate callback URL
        if req.callback_url:
            try:
                validate_callback_url(req.callback_url)
            except ValueError as e:
                results.append({
                    "content_ref": req.content_ref,
                    "error": str(e),
                })
                continue

        # Serialize candidates
        candidates_data = None
        if req.candidates:
            candidates_data = [c.model_dump() for c in req.candidates]

        review = Review(
            type=req.type,
            content_ref=req.content_ref,
            metadata_json=req.metadata,
            source_system=req.source_system,
            priority=req.priority,
            risk_score=req.risk_score,
            state=ReviewState.PENDING.value,
            disposition=None,
            version=1,
            callback_url=req.callback_url,
            callback_secret=req.callback_secret,
            candidates_json=candidates_data,
            max_selections=req.max_selections,
        )
        db.add(review)
        await db.flush()
        await db.refresh(review)

        # Policy evaluation
        review_data = {
            "type": req.type,
            "source_system": req.source_system,
            "priority": req.priority,
            "risk_score": req.risk_score or 0.5,
            "metadata": req.metadata or {},
        }
        disposition = engine.evaluate(review_data)

        # Route
        if disposition == Disposition.AUTO:
            try:
                await transition_state(
                    db, review.id, ReviewState.PENDING, ReviewState.POLICY_EVAL,
                    1, "system", action="batch_policy_eval",
                )
                await db.refresh(review)
                await transition_state(
                    db, review.id, ReviewState.POLICY_EVAL, ReviewState.COMPLETE,
                    review.version, "policy_engine", action="auto_approve",
                    payload={"disposition": disposition.value},
                )
            except (StateConflictError, InvalidTransitionError):
                pass
        elif disposition in (Disposition.HUMAN, Disposition.AI_AUDIT):
            try:
                await transition_state(
                    db, review.id, ReviewState.PENDING, ReviewState.POLICY_EVAL,
                    1, "system", action="batch_policy_eval",
                )
                await db.refresh(review)
                await transition_state(
                    db, review.id, ReviewState.POLICY_EVAL, ReviewState.APPROVING,
                    review.version, "policy_engine",
                    action="route_human" if disposition == Disposition.HUMAN else "route_ai_audit",
                    payload={"disposition": disposition.value},
                )
            except (StateConflictError, InvalidTransitionError):
                pass
        elif disposition == Disposition.BLOCK:
            try:
                await transition_state(
                    db, review.id, ReviewState.PENDING, ReviewState.POLICY_EVAL,
                    1, "system", action="batch_policy_eval",
                )
                await db.refresh(review)
                await transition_state(
                    db, review.id, ReviewState.POLICY_EVAL, ReviewState.COMPLETE,
                    review.version, "policy_engine", action="block",
                    payload={"disposition": disposition.value},
                )
            except (StateConflictError, InvalidTransitionError):
                pass

        await db.refresh(review)
        review.disposition = disposition.value
        await db.flush()

        results.append({
            "review_id": review.id,
            "content_ref": req.content_ref,
            "state": review.state,
            "routing": disposition.value,
        })

    await db.commit()

    return ApiResponse(
        data={"results": results, "total": len(results)},
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# Batch Approve
# ---------------------------------------------------------------------------


@router.post(
    "/batch/approve",
    response_model=ApiResponse,
)
async def batch_approve_reviews(
    request: BatchActionRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Approve multiple reviews in a single request.

    Only reviews in APPROVING state will be approved. Others are skipped.
    """
    results = []

    for review_id in request.review_ids:
        review = await db.get(Review, review_id)
        if review is None:
            results.append({"review_id": review_id, "status": "not_found"})
            continue

        if review.state != ReviewState.APPROVING.value:
            results.append({
                "review_id": review_id,
                "status": "skipped",
                "reason": f"Not in APPROVING state: {review.state}",
            })
            continue

        try:
            await transition_state(
                db, review.id, ReviewState.APPROVING, ReviewState.COMPLETE,
                review.version, f"client:{client}",
                action="batch_approve",
                payload={"comment": request.comment},
            )
            results.append({"review_id": review_id, "status": "approved"})
        except (StateConflictError, InvalidTransitionError) as e:
            results.append({"review_id": review_id, "status": "error", "error": str(e)})

    return ApiResponse(
        data={"results": results, "total": len(results)},
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# Batch Reject
# ---------------------------------------------------------------------------


@router.post(
    "/batch/reject",
    response_model=ApiResponse,
)
async def batch_reject_reviews(
    request: BatchActionRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Reject multiple reviews in a single request.

    Only reviews in APPROVING state will be rejected. Others are skipped.
    A default reason is used if no comment is provided.
    """
    reason = request.comment or "Batch rejected"
    results = []

    for review_id in request.review_ids:
        review = await db.get(Review, review_id)
        if review is None:
            results.append({"review_id": review_id, "status": "not_found"})
            continue

        if review.state != ReviewState.APPROVING.value:
            results.append({
                "review_id": review_id,
                "status": "skipped",
                "reason": f"Not in APPROVING state: {review.state}",
            })
            continue

        try:
            await transition_state(
                db, review.id, ReviewState.APPROVING, ReviewState.COMPLETE,
                review.version, f"client:{client}",
                action="batch_reject",
                payload={"reason": reason},
            )
            results.append({"review_id": review_id, "status": "rejected"})
        except (StateConflictError, InvalidTransitionError) as e:
            results.append({"review_id": review_id, "status": "error", "error": str(e)})

    return ApiResponse(
        data={"results": results, "total": len(results)},
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# Batch Status Query
# ---------------------------------------------------------------------------


@router.get(
    "/batch/status",
    response_model=ApiResponse,
)
async def batch_query_status(
    ids: str = ...,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Query status of multiple reviews by comma-separated IDs.

    Example: GET /api/v1/reviews/batch/status?ids=1,2,3,4,5
    """
    try:
        review_ids = [int(i.strip()) for i in ids.split(",") if i.strip()]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ids must be comma-separated integers",
        )

    if len(review_ids) > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum 100 review IDs per request",
        )

    results = []
    for rid in review_ids:
        review = await db.get(Review, rid)
        if review is None:
            results.append({"review_id": rid, "status": "not_found"})
        else:
            results.append({
                "review_id": rid,
                "state": review.state,
                "disposition": review.disposition,
                "version": review.version,
            })

    return ApiResponse(
        data={"results": results, "total": len(results)},
        meta={"request_id": _request_id()},
    )
