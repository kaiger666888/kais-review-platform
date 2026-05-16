"""Audit trail query endpoints.

GET /api/v1/audit/{review_id}        -- Audit history for a specific review (AUDT-04)
GET /api/v1/audit                     -- Global audit log with filters (AUDT-05)
GET /api/v1/audit/merkle/verify       -- Merkle root tamper verification
GET /api/v1/audit/stats               -- Audit statistics aggregation
GET /api/v1/audit/timeline            -- Chronological audit timeline with review metadata
GET /api/v1/audit/policy-diff         -- Policy version diff between two Git commits
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_jwt, require_auditor
from app.core.config import get_settings
from app.core.database import get_db
from app.core.merkle import commit_merkle_root_to_git, compute_daily_merkle_root
from app.models.schema import AuditEntry, Review
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
# GET /stats -- Audit statistics aggregation
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=ApiResponse[dict])
async def get_audit_stats(
    start_date: str | None = Query(None, description="ISO date, default 7 days ago"),
    end_date: str | None = Query(None, description="ISO date, default today"),
    project_id: str | None = Query(None, description="Optional project filter"),
    payload: dict = Depends(require_auditor),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate audit statistics: throughput, approval rate, rejection reasons, policy hit rates."""
    today = datetime.now(timezone.utc).date()
    start = date.fromisoformat(start_date) if start_date else today - timedelta(days=7)
    end = date.fromisoformat(end_date) if end_date else today

    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)

    # Base filter: decision actions in date range
    base = (
        select(AuditEntry)
        .where(
            AuditEntry.action.in_(["approve", "reject"]),
            AuditEntry.created_at >= start_dt,
            AuditEntry.created_at <= end_dt,
        )
    )

    # Total decisions
    total_stmt = select(func.count()).select_from(
        base.with_only_columns(AuditEntry.id).subquery()
    )
    total_result = await db.execute(total_stmt)
    total_decisions = total_result.scalar() or 0

    # Approved count
    approved_stmt = select(func.count()).select_from(
        base.with_only_columns(AuditEntry.id)
        .where(AuditEntry.action == "approve")
        .subquery()
    )
    approved_result = await db.execute(approved_stmt)
    approved = approved_result.scalar() or 0

    # Rejected count
    rejected_stmt = select(func.count()).select_from(
        base.with_only_columns(AuditEntry.id)
        .where(AuditEntry.action == "reject")
        .subquery()
    )
    rejected_result = await db.execute(rejected_stmt)
    rejected = rejected_result.scalar() or 0

    # Approval rate
    approval_rate = round(approved / total_decisions, 4) if total_decisions > 0 else 0.0

    # Average decision time: for each review_id, find time between first entry and first decision
    # Subquery: earliest audit entry per review_id
    earliest_subq = (
        select(
            AuditEntry.review_id,
            func.min(AuditEntry.created_at).label("first_entry"),
        )
        .group_by(AuditEntry.review_id)
        .subquery()
    )
    # Subquery: first decision entry per review_id
    decision_subq = (
        select(
            AuditEntry.review_id,
            func.min(AuditEntry.created_at).label("first_decision"),
        )
        .where(
            AuditEntry.action.in_(["approve", "reject"]),
            AuditEntry.created_at >= start_dt,
            AuditEntry.created_at <= end_dt,
        )
        .group_by(AuditEntry.review_id)
        .subquery()
    )
    avg_time_stmt = select(
        func.avg(
            func.extract("epoch", decision_subq.c.first_decision - earliest_subq.c.first_entry)
            / 60.0
        ).label("avg_minutes")
    ).join(
        earliest_subq,
        earliest_subq.c.review_id == decision_subq.c.review_id,
    )
    avg_time_result = await db.execute(avg_time_stmt)
    avg_decision_time_minutes = round(avg_time_result.scalar() or 0, 1)

    # Rejection reasons: extract payload.reason from reject entries
    reject_entries_stmt = (
        select(AuditEntry.payload)
        .where(AuditEntry.action == "reject", AuditEntry.created_at >= start_dt, AuditEntry.created_at <= end_dt)
    )
    reject_result = await db.execute(reject_entries_stmt)
    reject_payloads = [row[0] for row in reject_result.all() if row[0]]

    reason_counts: dict[str, int] = {}
    for p in reject_payloads:
        reason = p.get("reason", "unspecified")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    rejection_reasons = sorted(
        [{"reason": k, "count": v} for k, v in reason_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]

    # Policy hit rates: extract payload.policy_name from reject entries
    policy_counts: dict[str, int] = {}
    for p in reject_payloads:
        policy_name = p.get("policy_name")
        if policy_name:
            policy_counts[policy_name] = policy_counts.get(policy_name, 0) + 1
    policy_hit_rates = sorted(
        [{"policy": k, "count": v} for k, v in policy_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    # Daily throughput
    daily_subq = (
        select(
            func.date(AuditEntry.created_at).label("day"),
            func.count().label("cnt"),
        )
        .where(
            AuditEntry.action.in_(["approve", "reject"]),
            AuditEntry.created_at >= start_dt,
            AuditEntry.created_at <= end_dt,
        )
        .group_by(func.date(AuditEntry.created_at))
        .subquery()
    )
    daily_result = await db.execute(
        select(daily_subq.c.day, daily_subq.c.cnt).order_by(daily_subq.c.day)
    )
    daily_throughput = [
        {"date": str(row[0]) if row[0] else "", "count": row[1]}
        for row in daily_result.all()
    ]

    return ApiResponse(
        data={
            "total_decisions": total_decisions,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": approval_rate,
            "avg_decision_time_minutes": avg_decision_time_minutes,
            "rejection_reasons": rejection_reasons,
            "policy_hit_rates": policy_hit_rates,
            "daily_throughput": daily_throughput,
        },
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# GET /timeline -- Chronological audit timeline with review metadata
# ---------------------------------------------------------------------------


@router.get("/timeline", response_model=ApiResponse[PaginatedResponse[dict]])
async def get_audit_timeline(
    cursor: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    action: str | None = Query(None),
    actor: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    payload: dict = Depends(require_auditor),
    db: AsyncSession = Depends(get_db),
):
    """Paginated audit timeline with review metadata for display."""
    query = (
        select(AuditEntry, Review.type, Review.source_system)
        .join(Review, AuditEntry.review_id == Review.id, isouter=True)
        .order_by(AuditEntry.id.desc())
        .limit(limit + 1)
    )

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
    rows = result.all()

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1][0].id if has_more and items else None

    timeline_items = []
    for entry, review_type, source_system in items:
        item = _audit_response(entry).model_dump()
        item["review_type"] = review_type
        item["source_system"] = source_system
        timeline_items.append(item)

    return ApiResponse(
        data=PaginatedResponse(
            items=timeline_items,
            next_cursor=next_cursor,
            has_more=has_more,
        ),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# GET /policy-diff -- Compare policy versions between two Git commits
# ---------------------------------------------------------------------------


@router.get("/policy-diff", response_model=ApiResponse[dict])
async def get_policy_diff(
    commit_sha_1: str = Query(..., min_length=7, description="First commit SHA"),
    commit_sha_2: str = Query(..., min_length=7, description="Second commit SHA"),
    payload: dict = Depends(require_auditor),
):
    """Compare policy YAML files between two Git commits.

    Returns a list of policy files with their content at each commit
    and whether they differ.
    """
    settings = get_settings()
    if not settings.git_repo_url:
        raise HTTPException(
            status_code=503,
            detail="Git integration not configured",
        )

    try:
        import git

        local_path = Path(".policy_repo")
        if not (local_path.exists() and (local_path / ".git").exists()):
            raise HTTPException(
                status_code=503,
                detail="Git policy repository not available",
            )

        repo = git.Repo(str(local_path))

        commit_1 = repo.commit(commit_sha_1)
        commit_2 = repo.commit(commit_sha_2)

        # Collect policy YAML files from both commits
        def _get_policy_files(tree) -> dict[str, str]:
            """Extract policy YAML files from a git tree."""
            files = {}
            policies_dir = None
            try:
                policies_dir = tree["policies"]
            except KeyError:
                pass
            if policies_dir is not None:
                for blob in policies_dir:
                    if blob.name.endswith((".yaml", ".yml")):
                        try:
                            files[blob.name] = blob.data_stream.read().decode("utf-8")
                        except Exception:
                            files[blob.name] = ""
            return files

        files_1 = _get_policy_files(commit_1.tree)
        files_2 = _get_policy_files(commit_2.tree)

        # Build diff list
        all_files = sorted(set(files_1.keys()) | set(files_2.keys()))
        diffs = []
        for fname in all_files:
            content_1 = files_1.get(fname, "")
            content_2 = files_2.get(fname, "")
            diffs.append({
                "file": fname,
                "from": content_1,
                "to": content_2,
                "changed": content_1 != content_2,
            })

        return ApiResponse(
            data={
                "commit_1": commit_sha_1,
                "commit_2": commit_sha_2,
                "diffs": diffs,
            },
            meta={"request_id": _request_id()},
        )

    except git.exc.GitCommandError as exc:
        logger.error("policy_diff_git_error", error=str(exc))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid commit SHA: {exc}",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("policy_diff_error", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail=f"Failed to compute policy diff: {exc}",
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
