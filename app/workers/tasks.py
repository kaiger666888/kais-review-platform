"""arq auto-escalation timeout task.

Scans for reviews in APPROVING state that have exceeded their timeout
threshold and escalates them back to POLICY_EVAL for re-evaluation.
"""

from datetime import datetime, timezone, timedelta

from arq import cron
from sqlalchemy import select

# Timeout thresholds per route type (seconds)
TIMEOUT_THRESHOLDS: dict[str, int] = {
    "AI_AUDIT": 300,    # 5 minutes for AI review
    "HUMAN": 86400,     # 24 hours for human review
}
DEFAULT_TIMEOUT = 86400  # 24 hours default


async def check_timeouts(ctx: dict) -> list[int]:
    """Scan for reviews in APPROVING state that have exceeded timeout threshold.

    Escalates timed-out reviews by transitioning them back to POLICY_EVAL
    for re-evaluation. Returns list of escalated review IDs.
    """
    import structlog

    from app.core.database import async_session_factory
    from app.core.state_machine import transition_state
    from app.models.schema import Review
    from app.models.schemas import ReviewState

    logger = structlog.get_logger()
    escalated: list[int] = []

    async with async_session_factory() as session:
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=DEFAULT_TIMEOUT)

        query = select(Review).where(
            Review.state == ReviewState.APPROVING.value,
            Review.updated_at < cutoff_time,
        )
        result = await session.execute(query)
        timed_out_reviews = result.scalars().all()

        for review in timed_out_reviews:
            try:
                await transition_state(
                    session,
                    review.id,
                    ReviewState.APPROVING,
                    ReviewState.POLICY_EVAL,
                    review.version,
                    actor="timeout",
                    action="auto_escalate",
                    payload={
                        "reason": "Review exceeded timeout threshold",
                        "timeout_seconds": DEFAULT_TIMEOUT,
                    },
                )
                escalated.append(review.id)
                logger.info(
                    "review_escalated",
                    review_id=review.id,
                    reason="timeout",
                )
            except Exception as e:
                logger.error(
                    "escalation_failed",
                    review_id=review.id,
                    error=str(e),
                )

    return escalated


class WorkerSettings:
    """arq worker configuration."""

    functions = [check_timeouts]
    cron_jobs = [
        cron(check_timeouts, minute={0}),  # Run every hour at minute 0
    ]
