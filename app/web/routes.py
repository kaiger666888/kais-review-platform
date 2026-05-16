"""Template route handlers for the mobile-first review dashboard."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2_fragments.fastapi import Jinja2Blocks
from sqlalchemy import select, func, distinct

from app.core.database import async_session_factory
from app.core.state_machine import transition_state, StateConflictError, InvalidTransitionError
from app.models.schemas import ReviewState
from app.models.schema import Review, AuditEntry
from app.models.shot_card import ShotCard, AuditStatus
from app.web.auth import get_template_user

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")
blocks = Jinja2Blocks(directory="app/templates")


def elapsed_time(dt: datetime) -> str:
    """Format a datetime as relative time string: '{n}m ago' / '{n}h ago' / '{n}d ago'."""
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    # Ensure dt is timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


# Register Jinja2 filter
templates.env.filters["elapsed_time"] = elapsed_time

PAGE_SIZE = 20


async def _fetch_reviews(status: str, cursor: int | None = None):
    """Fetch reviews for a given status tab with cursor-based pagination.

    - pending: reviews in PENDING or APPROVING state (awaiting human action)
    - approved: reviews in COMPLETE state where last audit action was 'approve'
    - rejected: reviews in COMPLETE state where last audit action was 'reject'
    """
    async with async_session_factory() as session:
        if status == "pending":
            query = (
                select(Review)
                .where(Review.state.in_([
                    ReviewState.PENDING.value,
                    ReviewState.APPROVING.value,
                ]))
                .order_by(Review.created_at.desc())
                .limit(PAGE_SIZE + 1)
            )
        else:
            # For approved/rejected, find COMPLETE reviews with matching last action
            # Subquery: get the latest audit entry per review
            latest_audit = (
                select(
                    AuditEntry.review_id,
                    AuditEntry.action,
                    func.row_number()
                    .over(partition_by=AuditEntry.review_id, order_by=AuditEntry.created_at.desc())
                    .label("rn"),
                )
                .subquery()
            )
            action_filter = "approve" if status == "approved" else "reject"
            query = (
                select(Review)
                .join(latest_audit, latest_audit.c.review_id == Review.id)
                .where(
                    Review.state == ReviewState.COMPLETE.value,
                    latest_audit.c.rn == 1,
                    latest_audit.c.action == action_filter,
                )
                .order_by(Review.created_at.desc())
                .limit(PAGE_SIZE + 1)
            )

        if cursor:
            query = query.where(Review.id < cursor)

        result = await session.execute(query)
        reviews = list(result.scalars().all())
        has_more = len(reviews) > PAGE_SIZE
        reviews = reviews[:PAGE_SIZE]
        next_cursor = reviews[-1].id if has_more and reviews else None
        return reviews, has_more, next_cursor


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, tab: str = "pending", detail: int | None = None,
                    toast: str | None = None):
    """Full page dashboard render. Requires cookie-based JWT auth."""
    try:
        user = await get_template_user(
            access_token=request.cookies.get("access_token"),
        )
    except Exception:
        return RedirectResponse(url="/login", status_code=303)

    reviews, has_more, next_cursor = await _fetch_reviews(tab)

    toast_message = ""
    toast_type = "info"
    if toast == "token_expired":
        toast_message = "This link has expired. Request a new review link."
        toast_type = "error"

    return templates.TemplateResponse(request, "pages/dashboard.html", {
        "reviews": reviews,
        "active_tab": tab,
        "has_more": has_more,
        "cursor": next_cursor,
        "toast_message": toast_message,
        "toast_type": toast_type,
        "detail_id": detail,
        "user": user,
    })


@router.get("/partials/review-list", response_class=HTMLResponse)
async def review_list_partial(request: Request, status: str = "pending",
                              cursor: int | None = None):
    """HTMX partial: render review list block only."""
    reviews, has_more, next_cursor = await _fetch_reviews(status, cursor)

    return templates.TemplateResponse(request, "partials/_review_list.html", {
        "reviews": reviews,
        "active_tab": status,
        "has_more": has_more,
        "cursor": next_cursor,
    })


@router.get("/reviews/{review_id}/detail", response_class=HTMLResponse)
async def review_detail_partial(request: Request, review_id: int):
    """HTMX partial: render review detail overlay."""
    async with async_session_factory() as session:
        review = await session.get(Review, review_id)
        if review is None:
            return HTMLResponse("<p>Review not found.</p>", status_code=404)

    return templates.TemplateResponse(request, "partials/_review_detail.html", {
        "review": review,
    })


@router.post("/reviews/{review_id}/approve", response_class=HTMLResponse)
async def approve_review_htmx(request: Request, review_id: int):
    """HTMX form handler: approve review, return updated list with toast trigger."""
    async with async_session_factory() as session:
        review = await session.get(Review, review_id)
        if review is None:
            return HTMLResponse("<p>Review not found.</p>", status_code=404)

        try:
            await transition_state(
                session=session,
                review_id=review_id,
                from_state=ReviewState(review.state),
                to_state=ReviewState.COMPLETE,
                expected_version=review.version,
                actor="reviewer",
                action="approve",
                payload={"comment": None},
            )
        except (StateConflictError, InvalidTransitionError) as e:
            return HTMLResponse(
                f"<p>Error: {e}</p>", status_code=409,
                headers={"HX-Trigger": json.dumps({"showToast": {"message": str(e), "type": "error"}})},
            )

    # Re-fetch current tab's reviews
    # Determine tab from referer or default to pending
    reviews, has_more, next_cursor = await _fetch_reviews("pending")

    rendered = templates.TemplateResponse(request, "partials/_review_list.html", {
        "reviews": reviews,
        "active_tab": "pending",
        "has_more": has_more,
        "cursor": next_cursor,
    })
    rendered.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": "Review approved", "type": "success"},
    })
    return rendered


@router.post("/reviews/{review_id}/reject", response_class=HTMLResponse)
async def reject_review_htmx(request: Request, review_id: int, reason: str = Form(...)):
    """HTMX form handler: reject review with reason, return updated list with toast trigger."""
    async with async_session_factory() as session:
        review = await session.get(Review, review_id)
        if review is None:
            return HTMLResponse("<p>Review not found.</p>", status_code=404)

        try:
            await transition_state(
                session=session,
                review_id=review_id,
                from_state=ReviewState(review.state),
                to_state=ReviewState.COMPLETE,
                expected_version=review.version,
                actor="reviewer",
                action="reject",
                payload={"reason": reason},
            )
        except (StateConflictError, InvalidTransitionError) as e:
            return HTMLResponse(
                f"<p>Error: {e}</p>", status_code=409,
                headers={"HX-Trigger": json.dumps({"showToast": {"message": str(e), "type": "error"}})},
            )

    # Re-fetch current tab's reviews
    reviews, has_more, next_cursor = await _fetch_reviews("pending")

    rendered = templates.TemplateResponse(request, "partials/_review_list.html", {
        "reviews": reviews,
        "active_tab": "pending",
        "has_more": has_more,
        "cursor": next_cursor,
    })
    rendered.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": "Review rejected", "type": "success"},
    })
    return rendered


# ---------------------------------------------------------------------------
# Desktop Workstation Routes
# ---------------------------------------------------------------------------


@router.get("/workstation", response_class=HTMLResponse)
async def workstation(request: Request):
    """Desktop workstation for efficient Shot Card review."""
    try:
        user = await get_template_user(
            access_token=request.cookies.get("access_token"),
        )
    except Exception:
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse(request, "pages/workstation.html", {
        "user": user,
    })


@router.get("/partials/shot-queue", response_class=HTMLResponse)
async def shot_queue_partial(
    request: Request,
    project: str | None = None,
    scene: str | None = None,
    risk: str | None = None,
    cursor: int | None = None,
):
    """HTMX partial: Shot card queue with filters and cursor-based pagination."""
    PAGE_SIZE = 30
    async with async_session_factory() as session:
        query = select(ShotCard).order_by(ShotCard.id.asc()).limit(PAGE_SIZE + 1)

        if cursor:
            query = query.where(ShotCard.id > cursor)
        if project:
            query = query.where(ShotCard.project_id == project)
        if risk:
            query = query.where(ShotCard.audit_status == risk)
        if scene:
            query = query.where(
                ShotCard.narrative_context["scene"].astext == scene
            )

        result = await session.execute(query)
        shots = list(result.scalars().all())

        has_more = len(shots) > PAGE_SIZE
        shots = shots[:PAGE_SIZE]
        next_cursor = shots[-1].id if has_more and shots else None

        # Fetch distinct project IDs for filter dropdown
        project_result = await session.execute(
            select(distinct(ShotCard.project_id)).order_by(ShotCard.project_id)
        )
        projects = [row[0] for row in project_result.all()]

    return templates.TemplateResponse(request, "partials/_shot_queue_list.html", {
        "shots": shots,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "projects": projects,
        "current_project": project,
        "current_scene": scene,
        "current_risk": risk,
    })


@router.get("/partials/shot-card-detail/{shot_card_id}", response_class=HTMLResponse)
async def shot_card_detail_partial(request: Request, shot_card_id: int):
    """HTMX partial: Shot card detail for center and right panels.

    Returns the decision panel content as the primary response,
    plus an OOB swap element for #media-preview to update the center panel.
    """
    async with async_session_factory() as session:
        shot_card = await session.get(ShotCard, shot_card_id)

    if shot_card is None:
        return HTMLResponse("<p>Shot card not found.</p>", status_code=404)

    return templates.TemplateResponse(request, "partials/_decision_panel.html", {
        "shot": shot_card,
    })


async def _fetch_shot_queue(
    project: str | None = None,
    scene: str | None = None,
    risk: str | None = None,
    cursor: int | None = None,
):
    """Fetch shot cards for the workstation queue with cursor-based pagination."""
    PAGE_SIZE = 30
    async with async_session_factory() as session:
        query = select(ShotCard).order_by(ShotCard.id.asc()).limit(PAGE_SIZE + 1)

        if cursor:
            query = query.where(ShotCard.id > cursor)
        if project:
            query = query.where(ShotCard.project_id == project)
        if risk:
            query = query.where(ShotCard.audit_status == risk)
        if scene:
            query = query.where(
                ShotCard.narrative_context["scene"].astext == scene
            )

        result = await session.execute(query)
        shots = list(result.scalars().all())

        has_more = len(shots) > PAGE_SIZE
        shots = shots[:PAGE_SIZE]
        next_cursor = shots[-1].id if has_more and shots else None

        project_result = await session.execute(
            select(distinct(ShotCard.project_id)).order_by(ShotCard.project_id)
        )
        projects = [row[0] for row in project_result.all()]

    return shots, has_more, next_cursor, projects


@router.post("/shot-cards/{shot_card_id}/approve", response_class=HTMLResponse)
async def approve_shot_card_htmx(request: Request, shot_card_id: int):
    """HTMX form handler: approve shot card, return updated queue with toast trigger."""
    async with async_session_factory() as session:
        shot_card = await session.get(ShotCard, shot_card_id)
        if shot_card is None:
            return HTMLResponse(
                "<p>Shot card not found.</p>", status_code=404,
                headers={"HX-Trigger": json.dumps({"showToast": {"message": "Shot card not found", "type": "error"}})},
            )

        if shot_card.audit_status != AuditStatus.AWAITING_AUDIT:
            return HTMLResponse(
                f"<p>Cannot approve: status is {shot_card.audit_status}</p>", status_code=409,
                headers={"HX-Trigger": json.dumps({"showToast": {"message": f"Cannot approve: status is {shot_card.audit_status}", "type": "error"}})},
            )

        shot_card.audit_status = AuditStatus.APPROVED
        await session.commit()

    # Re-fetch shot queue
    shots, has_more, next_cursor, projects = await _fetch_shot_queue()

    rendered = templates.TemplateResponse(request, "partials/_shot_queue_list.html", {
        "shots": shots,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "projects": projects,
        "current_project": None,
        "current_scene": None,
        "current_risk": None,
    })
    rendered.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": "Shot card approved", "type": "success"},
    })
    return rendered


@router.post("/shot-cards/{shot_card_id}/reject", response_class=HTMLResponse)
async def reject_shot_card_htmx(request: Request, shot_card_id: int, reason: str = Form(...)):
    """HTMX form handler: reject shot card with reason, return updated queue with toast trigger."""
    async with async_session_factory() as session:
        shot_card = await session.get(ShotCard, shot_card_id)
        if shot_card is None:
            return HTMLResponse(
                "<p>Shot card not found.</p>", status_code=404,
                headers={"HX-Trigger": json.dumps({"showToast": {"message": "Shot card not found", "type": "error"}})},
            )

        if shot_card.audit_status != AuditStatus.AWAITING_AUDIT:
            return HTMLResponse(
                f"<p>Cannot reject: status is {shot_card.audit_status}</p>", status_code=409,
                headers={"HX-Trigger": json.dumps({"showToast": {"message": f"Cannot reject: status is {shot_card.audit_status}", "type": "error"}})},
            )

        shot_card.audit_status = AuditStatus.REJECTED
        await session.commit()

    # Re-fetch shot queue
    shots, has_more, next_cursor, projects = await _fetch_shot_queue()

    rendered = templates.TemplateResponse(request, "partials/_shot_queue_list.html", {
        "shots": shots,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "projects": projects,
        "current_project": None,
        "current_scene": None,
        "current_risk": None,
    })
    rendered.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": "Shot card rejected", "type": "success"},
    })
    return rendered


# ---------------------------------------------------------------------------
# Desktop Workstation — Batch Operations
# ---------------------------------------------------------------------------


@router.post("/partials/shot-cards/batch/approve", response_class=HTMLResponse)
async def batch_approve_shot_cards_htmx(request: Request):
    """HTMX endpoint: batch approve shot cards. Accepts JSON body with shot_card_ids."""
    body = await request.json()
    shot_card_ids = body.get("shot_card_ids", [])
    if not shot_card_ids:
        return HTMLResponse(
            "<p>No shot cards selected.</p>", status_code=400,
            headers={"HX-Trigger": json.dumps({"showToast": {"message": "No shot cards selected", "type": "error"}})},
        )

    approved_count = 0
    errors = []

    async with async_session_factory() as session:
        for card_id in shot_card_ids:
            shot_card = await session.get(ShotCard, card_id)
            if shot_card is None:
                errors.append(f"Shot card {card_id} not found")
                continue
            if shot_card.audit_status != AuditStatus.AWAITING_AUDIT:
                errors.append(f"Shot card {card_id}: status is {shot_card.audit_status}")
                continue
            shot_card.audit_status = AuditStatus.APPROVED
            approved_count += 1

        await session.commit()

    # Re-fetch shot queue
    shots, has_more, next_cursor, projects = await _fetch_shot_queue()

    rendered = templates.TemplateResponse(request, "partials/_shot_queue_list.html", {
        "shots": shots,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "projects": projects,
        "current_project": None,
        "current_scene": None,
        "current_risk": None,
    })

    msg = f"{approved_count} shot card(s) approved"
    if errors:
        msg += f" ({len(errors)} skipped)"
    rendered.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": msg, "type": "success" if approved_count > 0 else "warning"},
    })
    return rendered


@router.post("/partials/shot-cards/batch/reject", response_class=HTMLResponse)
async def batch_reject_shot_cards_htmx(request: Request):
    """HTMX endpoint: batch reject shot cards. Accepts JSON body with shot_card_ids and reason."""
    body = await request.json()
    shot_card_ids = body.get("shot_card_ids", [])
    reason = body.get("reason", "")

    if not shot_card_ids:
        return HTMLResponse(
            "<p>No shot cards selected.</p>", status_code=400,
            headers={"HX-Trigger": json.dumps({"showToast": {"message": "No shot cards selected", "type": "error"}})},
        )

    rejected_count = 0
    errors = []

    async with async_session_factory() as session:
        for card_id in shot_card_ids:
            shot_card = await session.get(ShotCard, card_id)
            if shot_card is None:
                errors.append(f"Shot card {card_id} not found")
                continue
            if shot_card.audit_status != AuditStatus.AWAITING_AUDIT:
                errors.append(f"Shot card {card_id}: status is {shot_card.audit_status}")
                continue
            shot_card.audit_status = AuditStatus.REJECTED
            rejected_count += 1

        await session.commit()

    # Re-fetch shot queue
    shots, has_more, next_cursor, projects = await _fetch_shot_queue()

    rendered = templates.TemplateResponse(request, "partials/_shot_queue_list.html", {
        "shots": shots,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "projects": projects,
        "current_project": None,
        "current_scene": None,
        "current_risk": None,
    })

    msg = f"{rejected_count} shot card(s) rejected"
    if errors:
        msg += f" ({len(errors)} skipped)"
    rendered.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": msg, "type": "success" if rejected_count > 0 else "warning"},
    })
    return rendered
