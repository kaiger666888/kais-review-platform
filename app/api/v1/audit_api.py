"""Audit trail query endpoints.

GET /api/v1/audit/{review_id}        -- Audit history for a specific review (AUDT-04)
GET /api/v1/audit                     -- Global audit log with filters (AUDT-05)
GET /api/v1/audit/merkle/verify       -- Merkle root tamper verification
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_jwt
from app.core.config import get_settings
from app.core.database import get_db
from app.core.merkle import commit_merkle_root_to_git, compute_daily_merkle_root
from app.models.schema import AuditEntry
from app.models.schemas import (
    ApiResponse,
    AuditEntryResponse,
    PaginatedResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# GET /merkle/verify -- Merkle root tamper verification
# ---------------------------------------------------------------------------


@router.get("/merkle/verify", response_model=ApiResponse[dict])
async def verify_merkle_root(
    target_date: str | None = Query(None, description="YYYY-MM-DD, defaults to yesterday"),
    payload: dict = Depends(require_jwt),
):
    """Verify audit log integrity via Merkle root comparison.

    Recomputes the Merkle tree for the given date and compares against the
    anchored root stored in the Git governance repository.

    Returns:
        - 200 {"status": "valid"} if roots match
        - 409 {"status": "tampered"} if roots differ
        - 404 {"status": "no_anchor"} if no stored root found
        - 503 {"status": "git_unavailable"} if Git repo not accessible
    """
    if target_date:
        try:
            check_date = date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    else:
        check_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    # Recompute Merkle tree from audit entries
    merkle_data = await compute_daily_merkle_root(check_date)
    computed_root = merkle_data["root"]

    # Attempt to read stored anchor from Git repo
    settings = get_settings()
    if not settings.git_repo_url:
        return ApiResponse(
            data={"status": "git_unavailable", "date": check_date.isoformat()},
            meta={"request_id": _request_id()},
        )

    try:
        import git

        local_path = Path(".policy_repo")
        if not (local_path.exists() and (local_path / ".git").exists()):
            return ApiResponse(
                data={"status": "git_unavailable", "date": check_date.isoformat()},
                meta={"request_id": _request_id()},
            )

        repo = git.Repo(str(local_path))
        merkle_file_path = f"audit_merkle/merkle_{check_date.isoformat()}.json"

        try:
            blob = repo.head.commit.tree[merkle_file_path]
            stored_data = json.loads(blob.data_stream.read().decode("utf-8"))
            stored_root = stored_data.get("root")
        except (KeyError, AttributeError):
            return ApiResponse(
                data={"status": "no_anchor", "date": check_date.isoformat()},
                meta={"request_id": _request_id()},
            )

    except Exception as exc:
        logger.error("merkle_verify_git_error", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail={"status": "git_unavailable", "date": check_date.isoformat()},
        )

    # Compare roots
    if computed_root == stored_root:
        return ApiResponse(
            data={
                "status": "valid",
                "date": check_date.isoformat(),
                "leaf_count": merkle_data["leaf_count"],
            },
            meta={"request_id": _request_id()},
        )
    else:
        raise HTTPException(
            status_code=409,
            detail={
                "status": "tampered",
                "date": check_date.isoformat(),
                "stored_root": stored_root,
                "computed_root": computed_root,
            },
        )


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
