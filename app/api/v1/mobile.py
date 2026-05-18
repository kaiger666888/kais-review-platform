"""Mobile-optimized API endpoints for Shot Card bundles.

GET  /api/v1/mobile/cards                          -- List Shot Card bundles (paginated, awaiting_audit only)
GET  /api/v1/mobile/cards/{shot_card_id}/audio     -- Async audio bundle loading
POST /api/v1/mobile/cards/{shot_card_id}/swipe-decision  -- Approve/reject via swipe gesture
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from typing import Literal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_client
from app.core.database import get_db
from app.models.schemas import (
    ApiResponse,
    MobileAudioBundle,
    MobileShotCardBundle,
    PaginatedResponse,
)
from app.models.shot_card import AuditStatus, ShotCard

router = APIRouter(prefix="/api/v1/mobile", tags=["mobile"])

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def _shot_card_to_bundle(shot_card: ShotCard) -> MobileShotCardBundle:
    """Convert a ShotCard ORM object to a flat MobileShotCardBundle.

    Extracts fields from nested JSONB columns (narrative_context,
    visual_bundle, audio_bundle) into flat fields for mobile consumption.
    Uses safe chained .get() calls to handle missing or partial data.
    Also resolves template_config from TemplateRegistry for client-side
    conditional rendering.
    """
    from app.core.template_registry import derive_source_system, get_template_registry

    # Narrative context -- always present (NOT NULL in DB)
    nc = shot_card.narrative_context or {}
    scene = nc.get("scene", "")
    shot_number = nc.get("shot_number", 0)
    emotion_curve = nc.get("emotion_curve", "")
    continuity_tags = nc.get("continuity_tags", [])

    # Visual bundle -- may be None
    vb = shot_card.visual_bundle or {}
    keyframes = vb.get("keyframes", {}) or {}
    first_kf = keyframes.get("first", {}) or {}
    last_kf = keyframes.get("last", {}) or {}
    video_clip = vb.get("video_clip", {}) or {}

    first_frame_url = first_kf.get("url")
    last_frame_url = last_kf.get("url")
    video_url = video_clip.get("url")
    visual_prompt = vb.get("prompt")
    candidates = vb.get("candidates")

    # Audio bundle -- may be None
    ab = shot_card.audio_bundle or {}
    audio_status = ab.get("status", "pending")
    bgm_prompt = ab.get("bgm_prompt")
    sfx_prompt = ab.get("sfx_prompt")

    # Template resolution for mobile card variant
    source_system = derive_source_system(shot_card)
    phase = nc.get("phase") or nc.get("pipeline_phase")
    tc = get_template_registry().resolve(source_system, phase)
    template_config = {
        "card_variant": tc.mobile_card_variant,
        "show_scores": tc.show_scores,
        "show_candidates": tc.show_candidates,
    }

    return MobileShotCardBundle(
        id=shot_card.id,
        shot_id=shot_card.shot_id,
        project_id=shot_card.project_id,
        scene=scene,
        shot_number=shot_number,
        emotion_curve=emotion_curve,
        continuity_tags=continuity_tags,
        first_frame_url=first_frame_url,
        last_frame_url=last_frame_url,
        video_url=video_url,
        visual_prompt=visual_prompt,
        candidates=candidates,
        audio_status=audio_status,
        bgm_prompt=bgm_prompt,
        sfx_prompt=sfx_prompt,
        audit_status=shot_card.audit_status,
        routing_decision=shot_card.routing_decision,
        template_config=template_config,
    )


# ---------------------------------------------------------------------------
# GET /cards -- List mobile Shot Card bundles (paginated)
# ---------------------------------------------------------------------------


@router.get(
    "/cards",
    response_model=ApiResponse[PaginatedResponse[MobileShotCardBundle]],
)
async def list_mobile_cards(
    project_id: str | None = Query(None),
    cursor: int | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """List Shot Card bundles optimized for mobile consumption.

    Returns only cards with audit_status=awaiting_audit.
    Default page size is 10 (mobile-friendly).
    Cursor-based pagination: results with id > cursor, ordered by id asc.
    """
    query = (
        select(ShotCard)
        .where(ShotCard.audit_status == AuditStatus.AWAITING_AUDIT)
        .order_by(ShotCard.id.asc())
        .limit(limit + 1)
    )

    if cursor:
        query = query.where(ShotCard.id > cursor)
    if project_id:
        query = query.where(ShotCard.project_id == project_id)

    result = await db.execute(query)
    rows = result.scalars().all()

    # Determine pagination (fetch limit+1 pattern)
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1].id if has_more and items else None

    return ApiResponse(
        data=PaginatedResponse(
            items=[_shot_card_to_bundle(r).model_dump() for r in items],
            next_cursor=next_cursor,
            has_more=has_more,
        ),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# GET /cards/{shot_card_id}/audio -- Async audio loading
# ---------------------------------------------------------------------------


@router.get(
    "/cards/{shot_card_id}/audio",
    response_model=ApiResponse[MobileAudioBundle],
)
async def get_mobile_audio(
    shot_card_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get audio bundle data for a single Shot Card.

    Designed for progressive loading: mobile clients load visual content
    first via the cards endpoint, then fetch audio data asynchronously
    via this endpoint to reduce initial payload size.
    """
    shot_card = await db.get(ShotCard, shot_card_id)
    if shot_card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shot Card {shot_card_id} not found",
        )

    ab = shot_card.audio_bundle or {}
    audio_bundle = MobileAudioBundle(
        shot_card_id=shot_card.id,
        audio_status=ab.get("status", "pending"),
        bgm_prompt=ab.get("bgm_prompt"),
        sfx_prompt=ab.get("sfx_prompt"),
    )

    return ApiResponse(
        data=audio_bundle.model_dump(),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# POST /cards/{shot_card_id}/swipe-decision -- Approve/reject via gesture
# ---------------------------------------------------------------------------


class SwipeDecisionRequest(BaseModel):
    """Request body for mobile swipe-decision endpoint."""

    action: Literal["approve", "reject"]
    reason: str | None = None


@router.post(
    "/cards/{shot_card_id}/swipe-decision",
    response_model=ApiResponse[MobileShotCardBundle],
)
async def swipe_decision(
    shot_card_id: int,
    body: SwipeDecisionRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Approve or reject a Shot Card via mobile swipe gesture.

    - action: "approve" or "reject"
    - reason: Required when action is "reject" (returns 422 if missing)
    - Requires JWT authentication

    Returns the updated Shot Card bundle after state transition.
    """
    # Validate reject requires reason
    if body.action == "reject" and not body.reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Reason is required when rejecting a Shot Card",
        )

    shot_card = await db.get(ShotCard, shot_card_id)
    if shot_card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shot Card {shot_card_id} not found",
        )

    if shot_card.audit_status != AuditStatus.AWAITING_AUDIT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shot Card is not in awaiting_audit state, current: {shot_card.audit_status}",
        )

    # Transition state
    if body.action == "approve":
        shot_card.audit_status = AuditStatus.APPROVED
    else:
        shot_card.audit_status = AuditStatus.REJECTED

    await db.commit()
    await db.refresh(shot_card)

    logger.info(
        "mobile_swipe_decision",
        shot_card_id=shot_card_id,
        action=body.action,
        actor=f"client:{client}",
        reason=body.reason,
    )

    return ApiResponse(
        data=_shot_card_to_bundle(shot_card).model_dump(),
        meta={"request_id": _request_id()},
    )
