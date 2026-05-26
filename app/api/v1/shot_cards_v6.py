"""V6.0 ShotCard API — minimal review endpoints.

POST   /api/v1/shot-cards                  — create card
GET    /api/v1/shot-cards                  — list (with filters)
GET    /api/v1/shot-cards/{id}             — detail (with video/image preview)
POST   /api/v1/shot-cards/{id}/approve     — approve (optional scores)
POST   /api/v1/shot-cards/{id}/reject      — reject (mandatory reason)
POST   /api/v1/shot-cards/batch/approve    — batch approve
POST   /api/v1/shot-cards/batch/reject     — batch reject
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas_v6 import (
    ApprovalRequest,
    BatchApprovalRequest,
    BatchItemResult,
    BatchRejectionRequest,
    BatchReviewResult,
    CreateShotCardRequest,
    RejectionRequest,
    ReviewCallbackItem,
    ReviewCallbackPayload,
    ReviewResult,
    ScoreVector,
    ShotCardListResponse,
    ShotCardResponse,
    ShotCardSummary,
)
from app.models.shot_card_v6 import PipelinePhase, Priority, ShotCardStatus, ShotCardV6

router = APIRouter(prefix="/api/v1/v6/shot-cards", tags=["ShotCards"])
logger = structlog.get_logger(__name__)


# ─── Helpers ──────────────────────────────────────────

def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def _score_vector_from_orm(sc: ShotCardV6) -> ScoreVector | None:
    """Extract ScoreVector from ORM columns."""
    if all(v is None for v in [
        sc.score_aesthetics, sc.score_consistency, sc.score_compliance,
        sc.score_technical_quality, sc.score_audio_match,
    ]):
        return None
    return ScoreVector(
        aesthetics=sc.score_aesthetics,
        consistency=sc.score_consistency,
        compliance=sc.score_compliance,
        technical_quality=sc.score_technical_quality,
        audio_match=sc.score_audio_match,
    )


def _score_vector_to_orm(sc: ShotCardV6, sv: ScoreVector | None):
    """Write ScoreVector fields into ORM columns."""
    if sv is None:
        return
    if sv.aesthetics is not None:
        sc.score_aesthetics = sv.aesthetics
    if sv.consistency is not None:
        sc.score_consistency = sv.consistency
    if sv.compliance is not None:
        sc.score_compliance = sv.compliance
    if sv.technical_quality is not None:
        sc.score_technical_quality = sv.technical_quality
    if sv.audio_match is not None:
        sc.score_audio_match = sv.audio_match


def _ai_score_overall(sc: ShotCardV6) -> float | None:
    """Compute average of non-null score dimensions."""
    scores = [
        v for v in [
            sc.score_aesthetics, sc.score_consistency, sc.score_compliance,
            sc.score_technical_quality, sc.score_audio_match,
        ]
        if v is not None
    ]
    return round(sum(scores) / len(scores), 1) if scores else None


def _to_response(sc: ShotCardV6) -> ShotCardResponse:
    return ShotCardResponse(
        id=sc.id,
        project_id=sc.project_id,
        shot_id=sc.shot_id,
        phase=sc.phase,
        status=sc.status,
        asset_url=sc.asset_url,
        thumbnail_url=sc.thumbnail_url,
        narrative_context=sc.narrative_context,
        ai_scores=_score_vector_from_orm(sc),
        priority=sc.priority,
        reviewer_id=sc.reviewer_id,
        reviewed_at=sc.reviewed_at,
        reject_reason=sc.reject_reason,
        reject_comment=sc.reject_comment,
        metadata=sc.metadata_,
        callback_sent=sc.callback_sent,
        created_at=sc.created_at,
        updated_at=sc.updated_at,
    )


def _to_summary(sc: ShotCardV6) -> ShotCardSummary:
    return ShotCardSummary(
        id=sc.id,
        project_id=sc.project_id,
        shot_id=sc.shot_id,
        phase=sc.phase,
        status=sc.status,
        thumbnail_url=sc.thumbnail_url,
        priority=sc.priority,
        ai_score_overall=_ai_score_overall(sc),
        created_at=sc.created_at,
    )


async def _send_callback(sc: ShotCardV6, decision: str, reviewer_id: str | None):
    """Fire-and-forget callback to movie-agent after review."""
    if not sc.callback_url:
        return

    payload = ReviewCallbackPayload(
        review_id=f"sc_{sc.id}",
        pipeline_id=sc.metadata_.get("pipeline_id") if sc.metadata_ else None,
        phase=sc.phase,
        decision=decision,
        items=[
            ReviewCallbackItem(
                shot_id=sc.shot_id,
                decision="approved" if decision == "approved" else "rejected",
                reviewer=reviewer_id,
                reviewer_role="review_gov",
                reviewed_at=sc.reviewed_at,
                scores=_score_vector_from_orm(sc),
                reject_reason=sc.reject_reason,
                suggested_action=(
                    sc.metadata_.get("suggested_action")
                    if sc.metadata_ else None
                ),
            )
        ],
        timestamp=datetime.now(timezone.utc),
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                sc.callback_url,
                json=payload.model_dump(mode="json"),
            )
            logger.info(
                "callback_sent",
                shot_card_id=sc.id,
                callback_url=sc.callback_url,
                status_code=resp.status_code,
            )
            sc.callback_sent = True
    except Exception as exc:
        logger.warning(
            "callback_failed",
            shot_card_id=sc.id,
            callback_url=sc.callback_url,
            error=str(exc),
        )
        # Don't mark as sent — will not retry in V6.0 minimal version


# ─── POST / — Create ─────────────────────────────────

@router.post(
    "/",
    response_model=ShotCardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_shot_card(
    body: CreateShotCardRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a review card."""
    sc = ShotCardV6(
        project_id=body.project_id,
        shot_id=body.shot_id,
        phase=body.phase,
        priority=body.priority,
        asset_url=body.asset_url,
        thumbnail_url=body.thumbnail_url,
        narrative_context=body.narrative_context or {},
        callback_url=body.callback_url,
        metadata_=body.metadata or {},
    )

    if body.ai_scores:
        _score_vector_to_orm(sc, body.ai_scores)

    db.add(sc)
    await db.commit()
    await db.refresh(sc)

    logger.info(
        "shot_card_v6_created",
        id=sc.id,
        project_id=sc.project_id,
        shot_id=sc.shot_id,
        phase=sc.phase,
    )

    return _to_response(sc)


# ─── GET / — List ────────────────────────────────────

@router.get(
    "/",
    response_model=ShotCardListResponse,
)
async def list_shot_cards(
    project_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    phase: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: Literal["created_at", "updated_at", "priority"] = Query("created_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    db: AsyncSession = Depends(get_db),
):
    """List shot cards with filters and offset pagination. Returns thumbnails for mobile."""
    query = select(ShotCardV6)
    count_query = select(sa_func.count()).select_from(ShotCardV6)

    if project_id:
        query = query.where(ShotCardV6.project_id == project_id)
        count_query = count_query.where(ShotCardV6.project_id == project_id)
    if status_filter:
        query = query.where(ShotCardV6.status == status_filter)
        count_query = count_query.where(ShotCardV6.status == status_filter)
    if phase:
        query = query.where(ShotCardV6.phase == phase)
        count_query = count_query.where(ShotCardV6.phase == phase)

    # Total count
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sorting
    sort_col = {
        "created_at": ShotCardV6.created_at,
        "updated_at": ShotCardV6.updated_at,
        "priority": ShotCardV6.priority,
    }[sort_by]
    if sort_order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    rows = result.scalars().all()

    return ShotCardListResponse(
        items=[_to_summary(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── GET /{id} — Detail ──────────────────────────────

@router.get(
    "/{shot_card_id}",
    response_model=ShotCardResponse,
)
async def get_shot_card(
    shot_card_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get shot card detail with video/image preview info."""
    sc = await db.get(ShotCardV6, shot_card_id)
    if sc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": f"ShotCard {shot_card_id} not found"},
        )
    return _to_response(sc)


# ─── POST /{id}/approve ─────────────────────────────

@router.post(
    "/{shot_card_id}/approve",
    response_model=ReviewResult,
)
async def approve_shot_card(
    shot_card_id: int,
    body: ApprovalRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Approve a shot card. Optional scores and tags."""
    sc = await db.get(ShotCardV6, shot_card_id)
    if sc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": f"ShotCard {shot_card_id} not found"},
        )

    if sc.status != ShotCardStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "conflict", "message": f"Card is {sc.status}, not pending"},
        )

    # Apply score overrides if provided
    if body and body.scores_override:
        for dim, val in body.scores_override.items():
            col = {
                "aesthetics": "score_aesthetics",
                "consistency": "score_consistency",
                "compliance": "score_compliance",
                "technical_quality": "score_technical_quality",
                "audio_match": "score_audio_match",
            }.get(dim)
            if col:
                setattr(sc, col, val)

    sc.status = ShotCardStatus.APPROVED
    sc.reviewer_id = "anonymous"  # No auth in V6.0 minimal
    sc.reviewed_at = datetime.now(timezone.utc)

    # Store tags in metadata if provided
    if body and body.tags:
        meta = sc.metadata_ or {}
        meta["tags"] = body.tags
        if body.comment:
            meta["approve_comment"] = body.comment
        sc.metadata_ = meta

    await db.commit()
    await db.refresh(sc)

    # Fire callback
    await _send_callback(sc, "approved", sc.reviewer_id)
    await db.commit()

    logger.info("shot_card_v6_approved", id=shot_card_id)

    return ReviewResult(
        id=str(sc.id),
        status="approved",
        reviewer_id=sc.reviewer_id,
        reviewed_at=sc.reviewed_at,
        callback_sent=sc.callback_sent,
    )


# ─── POST /{id}/reject ──────────────────────────────

@router.post(
    "/{shot_card_id}/reject",
    response_model=ReviewResult,
)
async def reject_shot_card(
    shot_card_id: int,
    body: RejectionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reject a shot card. Reason is mandatory."""
    sc = await db.get(ShotCardV6, shot_card_id)
    if sc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": f"ShotCard {shot_card_id} not found"},
        )

    if sc.status != ShotCardStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "conflict", "message": f"Card is {sc.status}, not pending"},
        )

    sc.status = ShotCardStatus.REJECTED
    sc.reviewer_id = "anonymous"
    sc.reviewed_at = datetime.now(timezone.utc)
    sc.reject_reason = body.reason
    sc.reject_comment = body.comment

    # Store rejection details in metadata
    meta = sc.metadata_ or {}
    if body.suggested_action:
        meta["suggested_action"] = body.suggested_action
    if body.reject_dimensions:
        meta["reject_dimensions"] = body.reject_dimensions
    if body.priority:
        meta["reject_priority"] = body.priority
    sc.metadata_ = meta

    await db.commit()
    await db.refresh(sc)

    # Fire callback
    await _send_callback(sc, "rejected", sc.reviewer_id)
    await db.commit()

    logger.info("shot_card_v6_rejected", id=shot_card_id, reason=body.reason)

    return ReviewResult(
        id=str(sc.id),
        status="rejected",
        reviewer_id=sc.reviewer_id,
        reviewed_at=sc.reviewed_at,
        callback_sent=sc.callback_sent,
    )


# ─── POST /batch/approve ────────────────────────────

@router.post(
    "/batch/approve",
    response_model=BatchReviewResult,
)
async def batch_approve(
    body: BatchApprovalRequest,
    db: AsyncSession = Depends(get_db),
):
    """Batch approve multiple pending cards."""
    results: list[BatchItemResult] = []

    for card_id in body.card_ids:
        sc = await db.get(ShotCardV6, card_id)
        if sc is None:
            results.append(BatchItemResult(card_id=card_id, status="error", error="not_found"))
            continue
        if sc.status != ShotCardStatus.PENDING:
            results.append(BatchItemResult(card_id=card_id, status="error", error=f"not_pending:{sc.status}"))
            continue

        sc.status = ShotCardStatus.APPROVED
        sc.reviewer_id = "anonymous"
        sc.reviewed_at = datetime.now(timezone.utc)
        if body.comment:
            meta = sc.metadata_ or {}
            meta["approve_comment"] = body.comment
            sc.metadata_ = meta

        results.append(BatchItemResult(card_id=card_id, status="approved"))

    await db.commit()

    # Fire callbacks in background (after commit so IDs are stable)
    for card_id in body.card_ids:
        sc = await db.get(ShotCardV6, card_id)
        if sc and sc.callback_url and sc.status == ShotCardStatus.APPROVED:
            await _send_callback(sc, "approved", sc.reviewer_id)
    await db.commit()

    succeeded = sum(1 for r in results if r.status == "approved")
    return BatchReviewResult(
        total=len(body.card_ids),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )


# ─── POST /batch/reject ─────────────────────────────

@router.post(
    "/batch/reject",
    response_model=BatchReviewResult,
)
async def batch_reject(
    body: BatchRejectionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Batch reject multiple pending cards."""
    results: list[BatchItemResult] = []

    for card_id in body.card_ids:
        sc = await db.get(ShotCardV6, card_id)
        if sc is None:
            results.append(BatchItemResult(card_id=card_id, status="error", error="not_found"))
            continue
        if sc.status != ShotCardStatus.PENDING:
            results.append(BatchItemResult(card_id=card_id, status="error", error=f"not_pending:{sc.status}"))
            continue

        sc.status = ShotCardStatus.REJECTED
        sc.reviewer_id = "anonymous"
        sc.reviewed_at = datetime.now(timezone.utc)
        sc.reject_reason = body.reason
        sc.reject_comment = body.comment

        meta = sc.metadata_ or {}
        if body.suggested_action:
            meta["suggested_action"] = body.suggested_action
        sc.metadata_ = meta

        results.append(BatchItemResult(card_id=card_id, status="rejected"))

    await db.commit()

    # Fire callbacks
    for card_id in body.card_ids:
        sc = await db.get(ShotCardV6, card_id)
        if sc and sc.callback_url and sc.status == ShotCardStatus.REJECTED:
            await _send_callback(sc, "rejected", sc.reviewer_id)
    await db.commit()

    succeeded = sum(1 for r in results if r.status == "rejected")
    return BatchReviewResult(
        total=len(body.card_ids),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )
