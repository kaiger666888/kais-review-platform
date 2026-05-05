"""arq background tasks: auto-escalation timeout and webhook delivery.

Provides check_timeouts (cron) and deliver_webhook (on-demand) tasks
for the arq worker. deliver_webhook uses Retry exception for exponential
backoff (1s, 5s, 30s) with max 3 attempts.
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta

import httpx
import structlog
from arq import Retry, cron
from sqlalchemy import select

# Timeout thresholds per route type (seconds)
TIMEOUT_THRESHOLDS: dict[str, int] = {
    "AI_AUDIT": 300,    # 5 minutes for AI review
    "HUMAN": 86400,     # 24 hours for human review
}
DEFAULT_TIMEOUT = 86400  # 24 hours default

# Exponential backoff delays for webhook delivery retries (try_number -> seconds)
WEBHOOK_BACKOFF = {1: 1, 2: 5, 3: 30}


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


async def deliver_webhook(ctx: dict, webhook_config_id: int, payload: dict) -> dict:
    """Deliver a webhook payload to a registered endpoint with retry.

    Uses arq's Retry exception for exponential backoff (1s, 5s, 30s).
    Retries up to 3 times before giving up.

    Args:
        ctx: arq context dict with 'http_client' key.
        webhook_config_id: ID of the WebhookConfig to deliver to.
        payload: Event payload dict.

    Returns:
        Summary dict with delivery result.
    """
    logger = structlog.get_logger()
    job_try = ctx.get("job_try", 1)

    from app.core.database import async_session_factory
    from app.models.schema import WebhookConfig

    async with async_session_factory() as session:
        config = await session.get(WebhookConfig, webhook_config_id)
        if config is None:
            logger.error("webhook_config_not_found", config_id=webhook_config_id)
            return {"status": "error", "reason": "config_not_found"}

    # Compute HMAC-SHA256 signature
    body = json.dumps(payload, default=str)
    signature = hmac.new(
        config.secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
    }

    client: httpx.AsyncClient = ctx.get("http_client")
    if client is None:
        logger.error("webhook_no_http_client")
        return {"status": "error", "reason": "no_http_client"}

    try:
        response = await client.post(
            config.url,
            content=body,
            headers=headers,
            timeout=10.0,
        )
        if response.status_code >= 400:
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
        logger.info(
            "webhook_delivered",
            url=config.url,
            status_code=response.status_code,
            try_number=job_try,
        )
        return {"status": "delivered", "status_code": response.status_code}
    except Exception as e:
        logger.warning(
            "webhook_delivery_failed",
            url=config.url,
            error=str(e),
            try_number=job_try,
        )
        if job_try < 3:
            raise Retry(defer=WEBHOOK_BACKOFF.get(job_try + 1, 30))
        logger.error(
            "webhook_delivery_exhausted",
            url=config.url,
            tries=job_try,
        )
        return {"status": "failed", "error": str(e), "tries": job_try}


class WorkerSettings:
    """arq worker configuration."""

    functions = [check_timeouts, deliver_webhook]
    cron_jobs = [
        cron(check_timeouts, minute={0}),  # Run every hour at minute 0
    ]

    async def on_startup(ctx):
        ctx["http_client"] = httpx.AsyncClient(timeout=10.0)

    async def on_shutdown(ctx):
        await ctx["http_client"].aclose()
