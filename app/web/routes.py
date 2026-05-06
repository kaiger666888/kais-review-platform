"""Template route handlers for the mobile-first review dashboard."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from jinja2_fragments.fastapi import Jinja2Blocks
from sqlalchemy import select, func

from app.core.database import async_session_factory
from app.core.state_machine import transition_state, StateConflictError, InvalidTransitionError
from app.models.schemas import ReviewState
from app.models.schema import Review, AuditEntry
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
    """Full page dashboard render."""
    user = None
    try:
        user = await get_template_user(
            access_token=request.cookies.get("access_token"),
        )
    except Exception:
        pass  # Allow unauthenticated access for now (auth can be enforced later)

    reviews, has_more, next_cursor = await _fetch_reviews(tab)

    toast_message = ""
    toast_type = "info"
    if toast == "token_expired":
        toast_message = "This link has expired. Request a new review link."
        toast_type = "error"

    return templates.TemplateResponse("pages/dashboard.html", {
        "request": request,
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

    return templates.TemplateResponse("partials/_review_list.html", {
        "request": request,
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

    return templates.TemplateResponse("partials/_review_detail.html", {
        "request": request,
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

    rendered = templates.TemplateResponse("partials/_review_list.html", {
        "request": request,
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

    rendered = templates.TemplateResponse("partials/_review_list.html", {
        "request": request,
        "reviews": reviews,
        "active_tab": "pending",
        "has_more": has_more,
        "cursor": next_cursor,
    })
    rendered.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": "Review rejected", "type": "success"},
    })
    return rendered
