"""Shot Card REST API endpoints.

POST /api/v1/shot-cards/events/node-completed  -- Mock event ingestion (dev/test)
GET  /api/v1/shot-cards                         -- List Shot Cards (paginated)
GET  /api/v1/shot-cards/{shot_card_id}          -- Get Shot Card by ID
GET  /api/v1/shot-cards/by-shot/{shot_id}       -- Get Shot Card by natural key
POST /api/v1/shot-cards/{shot_card_id}/approve  -- Approve a Shot Card
POST /api/v1/shot-cards/{shot_card_id}/reject   -- Reject a Shot Card
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_client
from app.core.database import get_db
from app.core.event_types import NodeCompletedEvent
from app.models.schemas import (
    ApiResponse,
    PaginatedResponse,
    ShotCardApproveRequest,
    ShotCardRejectRequest,
    ShotCardResponse,
)
from app.models.shot_card import ShotCard, AuditStatus
from app.services.aggregator import ShotCardAggregator

router = APIRouter(prefix="/api/v1/shot-cards", tags=["shot-cards"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def _shot_card_response(shot_card: ShotCard) -> ShotCardResponse:
    """Convert a ShotCard ORM object to a ShotCardResponse."""
    return ShotCardResponse(
        id=shot_card.id,
        shot_id=shot_card.shot_id,
        project_id=shot_card.project_id,
        narrative_context=shot_card.narrative_context,
        visual_bundle=shot_card.visual_bundle,
        audio_bundle=shot_card.audio_bundle,
        audit_status=shot_card.audit_status,
        routing_decision=shot_card.routing_decision,
        min_audit_set=shot_card.min_audit_set,
        blocking_reason=shot_card.blocking_reason,
        workflow_version=shot_card.workflow_version,
        policy_commit_sha=shot_card.policy_commit_sha,
        execution_id=shot_card.execution_id,
        created_at=shot_card.created_at,
        updated_at=shot_card.updated_at,
    )


# ---------------------------------------------------------------------------
# POST /events/node-completed -- Mock event ingestion
# ---------------------------------------------------------------------------


@router.post(
    "/events/node-completed",
    status_code=status.HTTP_200_OK,
)
async def ingest_node_completed(
    event: NodeCompletedEvent,
):
    """Mock event ingestion endpoint for development/testing.

    Accepts a NodeCompletedEvent, runs it through the full aggregation
    pipeline (collapse -> ensure -> fill -> check -> emit), and returns
    the result. Production will use OpenClaw event bus integration.
    """
    aggregator = ShotCardAggregator()
    result = await aggregator.handle_node_completion(event.model_dump())

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result,
        )

    return result


# ---------------------------------------------------------------------------
# GET / -- List Shot Cards
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=ApiResponse[PaginatedResponse[ShotCardResponse]],
)
async def list_shot_cards(
    project_id: str | None = Query(None),
    audit_status: str | None = Query(None, alias="audit_status"),
    cursor: int | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List Shot Cards with optional filters and cursor-based pagination.

    Results are ordered by id ascending. Cursor is an id value:
    Shot Cards with id > cursor are returned.
    """
    query = select(ShotCard).order_by(ShotCard.id.asc()).limit(limit + 1)

    if cursor:
        query = query.where(ShotCard.id > cursor)
    if project_id:
        query = query.where(ShotCard.project_id == project_id)
    if audit_status:
        query = query.where(ShotCard.audit_status == audit_status)

    result = await db.execute(query)
    rows = result.scalars().all()

    # Determine pagination
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1].id if has_more and items else None

    return ApiResponse(
        data=PaginatedResponse(
            items=[_shot_card_response(r).model_dump() for r in items],
            next_cursor=next_cursor,
            has_more=has_more,
        ),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# GET /{shot_card_id} -- Get by ID
# ---------------------------------------------------------------------------


@router.get(
    "/{shot_card_id}",
    response_model=ApiResponse[ShotCardResponse],
)
async def get_shot_card(
    shot_card_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a Shot Card by its primary key ID. Returns 404 if not found."""
    shot_card = await db.get(ShotCard, shot_card_id)
    if shot_card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shot Card {shot_card_id} not found",
        )

    return ApiResponse(
        data=_shot_card_response(shot_card).model_dump(),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# GET /by-shot/{shot_id} -- Get by natural key
# ---------------------------------------------------------------------------


@router.get(
    "/by-shot/{shot_id}",
    response_model=ApiResponse[ShotCardResponse],
)
async def get_shot_card_by_shot_id(
    shot_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a Shot Card by its natural key (shot_id). Returns 404 if not found."""
    result = await db.execute(
        select(ShotCard).where(ShotCard.shot_id == shot_id)
    )
    shot_card = result.scalar_one_or_none()

    if shot_card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shot Card with shot_id '{shot_id}' not found",
        )

    return ApiResponse(
        data=_shot_card_response(shot_card).model_dump(),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# POST /{shot_card_id}/approve -- Approve Shot Card
# ---------------------------------------------------------------------------


logger = structlog.get_logger(__name__)


@router.post(
    "/{shot_card_id}/approve",
    response_model=ApiResponse[ShotCardResponse],
)
async def approve_shot_card(
    shot_card_id: int,
    request: ShotCardApproveRequest | None = None,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Approve a Shot Card.

    Transitions audit_status from awaiting_audit to approved.
    Requires JWT authentication.
    """
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

    shot_card.audit_status = AuditStatus.APPROVED
    await db.commit()
    await db.refresh(shot_card)

    logger.info(
        "shot_card_approved",
        shot_card_id=shot_card_id,
        actor=f"client:{client}",
        comment=request.comment if request else None,
    )

    return ApiResponse(
        data=_shot_card_response(shot_card).model_dump(),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# POST /{shot_card_id}/reject -- Reject Shot Card
# ---------------------------------------------------------------------------


@router.post(
    "/{shot_card_id}/reject",
    response_model=ApiResponse[ShotCardResponse],
)
async def reject_shot_card(
    shot_card_id: int,
    request: ShotCardRejectRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Reject a Shot Card.

    Requires a mandatory reason (min_length=1, max_length=500).
    Transitions audit_status from awaiting_audit to rejected.
    Requires JWT authentication.
    """
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

    shot_card.audit_status = AuditStatus.REJECTED
    await db.commit()
    await db.refresh(shot_card)

    logger.info(
        "shot_card_rejected",
        shot_card_id=shot_card_id,
        actor=f"client:{client}",
        reason=request.reason,
    )

    return ApiResponse(
        data=_shot_card_response(shot_card).model_dump(),
        meta={"request_id": _request_id()},
    )
