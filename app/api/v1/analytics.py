"""Analytics aggregation endpoints.

GET /api/v1/analytics/summary           -- Summary stats (by source, phase, throughput)
GET /api/v1/analytics/routing-ratio     -- AUTO/HUMAN routing ratio from ShotCard data
GET /api/v1/analytics/score-distribution -- AI score distribution histogram
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, cast, func, select, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_client
from app.core.database import get_db
from app.models.schema import AuditEntry, Review
from app.models.schemas import ApiResponse
from app.models.shot_card import ShotCard

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def _parse_date_range(
    start_date: str | None, end_date: str | None
) -> tuple[datetime, datetime]:
    """Parse and validate date range query params. Defaults to last 7 days."""
    today = datetime.now(timezone.utc).date()
    try:
        start = date.fromisoformat(start_date) if start_date else today - timedelta(days=7)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD.")
    try:
        end = date.fromisoformat(end_date) if end_date else today
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD.")

    # Clamp to max 365 days (T-25-01 mitigation)
    if (end - start).days > 365:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 365 days.")

    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)
    return start_dt, end_dt


# ---------------------------------------------------------------------------
# GET /summary -- Aggregated summary stats
# ---------------------------------------------------------------------------


@router.get("/summary", response_model=ApiResponse[dict])
async def get_analytics_summary(
    start_date: str | None = Query(None, description="ISO date, default 7 days ago"),
    end_date: str | None = Query(None, description="ISO date, default today"),
    payload: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate V1 review analytics: by source_system, phase, throughput, avg wait time."""
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    # --- V1 path: decisions grouped by source_system ---
    source_stmt = (
        select(
            Review.source_system,
            func.count().label("total"),
            func.sum(
                case((AuditEntry.action == "approve", 1), else_=0)
            ).label("approved"),
            func.sum(
                case((AuditEntry.action == "reject", 1), else_=0)
            ).label("rejected"),
        )
        .join(AuditEntry, AuditEntry.review_id == Review.id)
        .where(
            AuditEntry.action.in_(["approve", "reject"]),
            AuditEntry.created_at >= start_dt,
            AuditEntry.created_at <= end_dt,
        )
        .group_by(Review.source_system)
        .order_by(func.count().desc())
    )
    source_result = await db.execute(source_stmt)
    by_source = []
    for row in source_result.all():
        total = row.total or 0
        approved = row.approved or 0
        rejected = row.rejected or 0
        by_source.append({
            "source_system": row.source_system,
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": round(approved / total, 4) if total > 0 else 0.0,
        })

    # --- V1 path: decisions grouped by phase ---
    phase_stmt = (
        select(
            func.json_extract_path_text(Review.metadata_json, "phase").label("phase"),
            func.count().label("total"),
            func.sum(
                case((AuditEntry.action == "approve", 1), else_=0)
            ).label("approved"),
            func.sum(
                case((AuditEntry.action == "reject", 1), else_=0)
            ).label("rejected"),
        )
        .join(AuditEntry, AuditEntry.review_id == Review.id)
        .where(
            AuditEntry.action.in_(["approve", "reject"]),
            AuditEntry.created_at >= start_dt,
            AuditEntry.created_at <= end_dt,
        )
        .group_by("phase")
        .order_by(func.count().desc())
    )
    phase_result = await db.execute(phase_stmt)
    by_phase = []
    for row in phase_result.all():
        total = row.total or 0
        approved = row.approved or 0
        rejected = row.rejected or 0
        by_phase.append({
            "phase": row.phase or "unknown",
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": round(approved / total, 4) if total > 0 else 0.0,
        })

    # --- Totals ---
    total_decisions = sum(s["total"] for s in by_source)
    total_approved = sum(s["approved"] for s in by_source)
    total_rejected = sum(s["rejected"] for s in by_source)
    overall_approval_rate = round(total_approved / total_decisions, 4) if total_decisions > 0 else 0.0

    # --- Avg wait time (earliest_subq + decision_subq pattern) ---
    earliest_subq = (
        select(
            AuditEntry.review_id,
            func.min(AuditEntry.created_at).label("first_entry"),
        )
        .group_by(AuditEntry.review_id)
        .subquery()
    )
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
    avg_wait_minutes = round(avg_time_result.scalar() or 0, 1)

    # --- Daily throughput ---
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
            "by_source": by_source,
            "by_phase": by_phase,
            "avg_wait_minutes": avg_wait_minutes,
            "total_decisions": total_decisions,
            "total_approved": total_approved,
            "total_rejected": total_rejected,
            "overall_approval_rate": overall_approval_rate,
            "daily_throughput": daily_throughput,
        },
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# GET /routing-ratio -- ShotCard routing decision ratio
# ---------------------------------------------------------------------------


@router.get("/routing-ratio", response_model=ApiResponse[dict])
async def get_routing_ratio(
    start_date: str | None = Query(None, description="ISO date, default 7 days ago"),
    end_date: str | None = Query(None, description="ISO date, default today"),
    payload: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """AUTO/HUMAN/AI_AUDIT/BLOCK routing ratio from ShotCard data."""
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    stmt = (
        select(
            ShotCard.routing_decision,
            func.count().label("cnt"),
        )
        .where(
            ShotCard.routing_decision.isnot(None),
            ShotCard.created_at >= start_dt,
            ShotCard.created_at <= end_dt,
        )
        .group_by(ShotCard.routing_decision)
    )
    result = await db.execute(stmt)
    rows = result.all()

    total = sum(row.cnt for row in rows)
    counts = {}
    ratios = {}
    for row in rows:
        key = row.routing_decision
        counts[key] = row.cnt
        ratios[key] = round(row.cnt / total, 4) if total > 0 else 0.0

    return ApiResponse(
        data={
            "total": total,
            "counts": counts,
            "ratios": ratios,
        },
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# GET /score-distribution -- AI score distribution histogram
# ---------------------------------------------------------------------------


@router.get("/score-distribution", response_model=ApiResponse[dict])
async def get_score_distribution(
    start_date: str | None = Query(None, description="ISO date, default 7 days ago"),
    end_date: str | None = Query(None, description="ISO date, default today"),
    payload: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """AI score distribution from ShotCard narrative_context JSONB."""
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    # Extract ai_score from narrative_context JSONB
    score_col = ShotCard.narrative_context["ai_score"].astext
    score_int = cast(score_col, Integer)

    bucket_expr = case(
        (score_int >= 90, "90-100"),
        (score_int >= 70, "70-89"),
        (score_int >= 50, "50-69"),
        (score_int >= 30, "30-49"),
        else_="0-29",
    )

    stmt = (
        select(
            bucket_expr.label("bucket"),
            func.count().label("cnt"),
            func.avg(score_int).label("avg_score"),
        )
        .where(
            score_col.isnot(None),
            ShotCard.created_at >= start_dt,
            ShotCard.created_at <= end_dt,
        )
        .group_by("bucket")
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Define bucket order
    bucket_order = ["90-100", "70-89", "50-69", "30-49", "0-29"]
    distribution = {b: {"bucket": b, "count": 0, "avg_score": None} for b in bucket_order}

    total_scored = 0
    weighted_sum = 0
    for row in rows:
        bucket = row.bucket
        if bucket in distribution:
            distribution[bucket]["count"] = row.cnt
            distribution[bucket]["avg_score"] = round(row.avg_score, 1) if row.avg_score else None
            total_scored += row.cnt
            if row.avg_score:
                weighted_sum += row.avg_score * row.cnt

    overall_avg = round(weighted_sum / total_scored, 1) if total_scored > 0 else None

    return ApiResponse(
        data={
            "distribution": [distribution[b] for b in bucket_order],
            "overall_avg": overall_avg,
            "total_scored": total_scored,
        },
        meta={"request_id": _request_id()},
    )
