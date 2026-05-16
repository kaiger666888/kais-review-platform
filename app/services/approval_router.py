"""Approval Router: priority-ordered queue for reviews awaiting approval.

Provides priority weight mapping and SQLAlchemy query builder for fetching
APPROVING reviews sorted by priority (critical first), then by creation time
(oldest first within same priority tier).
"""

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schema import Review
from app.models.schemas import ReviewState

# Priority weight mapping: higher weight = more urgent
PRIORITY_WEIGHT: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "normal": 2,
    "low": 1,
}

# Maximum number of items allowed in a batch operation
MAX_BATCH_SIZE = 100


def build_approval_queue_query(limit: int = 50, offset: int = 0):
    """Build a priority-ordered SELECT query for APPROVING reviews.

    Reviews are sorted by priority weight (descending: critical first),
    then by created_at (ascending: oldest first within same priority).

    Args:
        limit: Maximum number of reviews to return.
        offset: Number of reviews to skip.

    Returns:
        SQLAlchemy Select statement.
    """
    priority_order = case(
        *[
            (Review.priority == p, w)
            for p, w in sorted(PRIORITY_WEIGHT.items(), key=lambda x: -x[1])
        ],
        else_=0,
    )
    return (
        select(Review)
        .where(Review.state == ReviewState.APPROVING.value)
        .order_by(priority_order.desc(), Review.created_at.asc())
        .limit(limit)
        .offset(offset)
    )


async def get_priority_sorted_reviews(
    session: AsyncSession, limit: int = 50, offset: int = 0
) -> list[Review]:
    """Fetch APPROVING reviews sorted by priority then creation time.

    Args:
        session: Async database session.
        limit: Maximum number of reviews to return.
        offset: Number of reviews to skip.

    Returns:
        List of Review ORM objects in priority order.
    """
    query = build_approval_queue_query(limit, offset)
    result = await session.execute(query)
    return list(result.scalars().all())
