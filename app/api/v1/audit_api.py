"""Audit trail query endpoints.

GET /api/v1/audit/{review_id} -- Audit history for a specific review (AUDT-04)
GET /api/v1/audit             -- Global audit log with filters (AUDT-05)
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_client
from app.core.database import get_db
from app.models.schema import AuditEntry
from app.models.schemas import (
    ApiResponse,
    AuditEntryResponse,
    PaginatedResponse,
)

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def _audit_response(entry: AuditEntry) -> AuditEntryResponse:
    """Convert an AuditEntry ORM object to an AuditEntryResponse."""
    return AuditEntryResponse(
        id=entry.id,
        review_id=entry.review_id,
        action=entry.action,
        actor=entry.actor,
        from_state=entry.from_state,
        to_state=entry.to_state,
        payload=entry.payload,
        created_at=entry.created_at,
    )


# ---------------------------------------------------------------------------
# GET /{review_id} -- Audit history for a review
# ---------------------------------------------------------------------------


@router.get("/{review_id}", response_model=ApiResponse[list[AuditEntryResponse]])
async def get_review_audit(
    review_id: int,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Get the chronological audit history for a specific review.

    Returns an empty list if the review has no audit entries yet (not a 404).
    """
    stmt = (
        select(AuditEntry)
        .where(AuditEntry.review_id == review_id)
        .order_by(AuditEntry.created_at.asc())
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()

    return ApiResponse(
        data=[_audit_response(e).model_dump() for e in entries],
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# GET / -- Audit log with filters and pagination
# ---------------------------------------------------------------------------


@router.get("/", response_model=ApiResponse[PaginatedResponse[AuditEntryResponse]])
async def list_audit(
    action: str | None = Query(None),
    actor: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    cursor: int | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Query the global audit log with optional filters and cursor pagination.

    Filters: action type, actor, date range (ISO 8601).
    Results are ordered by id descending (newest first).
    """
    query = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit + 1)

    if cursor:
        query = query.where(AuditEntry.id < cursor)
    if action:
        query = query.where(AuditEntry.action == action)
    if actor:
        query = query.where(AuditEntry.actor == actor)
    if start_date:
        query = query.where(
            AuditEntry.created_at >= datetime.fromisoformat(start_date)
        )
    if end_date:
        query = query.where(
            AuditEntry.created_at <= datetime.fromisoformat(end_date)
        )

    result = await db.execute(query)
    rows = result.scalars().all()

    # Determine pagination
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1].id if has_more and items else None

    return ApiResponse(
        data=PaginatedResponse(
            items=[_audit_response(e).model_dump() for e in items],
            next_cursor=next_cursor,
            has_more=has_more,
        ),
        meta={"request_id": _request_id()},
    )
