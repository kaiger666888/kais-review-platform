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

# Exponential backoff delays for callback delivery retries (try_number -> seconds)
CALLBACK_BACKOFF = {1: 1, 2: 5, 3: 30}


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


async def _notify_telegram_admin(review_id: int, callback_url: str, error: str) -> None:
    """Send Telegram admin notification about callback delivery failure.

    Sends actual Telegram message to all allowed chat IDs. If bot is not
    configured (application is None), logs a warning and returns.
    """
    logger = structlog.get_logger()
    try:
        from app.main import app
        from app.bot.lifecycle import parse_allowed_chat_ids
        from app.core.config import get_settings

        bot_app = getattr(app.state, 'bot_application', None)
        if bot_app is None:
            logger.warning("telegram_admin_notification_skipped", reason="bot_not_configured", review_id=review_id)
            return

        settings = get_settings()
        chat_ids = parse_allowed_chat_ids(settings.telegram_allowed_chat_ids)
        message = (
            f"⚠️ 回调投递失败\n"
            f"审核ID: {review_id}\n"
            f"回调URL: {callback_url}\n"
            f"错误: {error}"
        )
        for chat_id in chat_ids:
            try:
                await bot_app.bot.send_message(chat_id=chat_id, text=message)
            except Exception as e:
                logger.error("telegram_admin_send_failed", chat_id=chat_id, error=str(e))
    except Exception as e:
        logger.error("telegram_admin_notification_error", error=str(e))
    # Keep the log entry for debugging
    logger.warning(
        "telegram_admin_notification_sent",
        review_id=review_id,
        callback_url=callback_url,
        error=error,
    )


async def check_timeout_reminders(ctx: dict) -> list[int]:
    """Send reminder notifications for reviews approaching timeout in APPROVING state.

    Reviews in APPROVING state that have exceeded 80% of the configured timeout
    threshold receive a reminder notification to all allowed Telegram chat IDs.

    Args:
        ctx: arq context dict with 'bot_application' key.

    Returns:
        List of review IDs that received reminder notifications.
    """
    logger = structlog.get_logger()
    from app.core.config import get_settings
    from app.core.database import async_session_factory
    from app.models.schema import Review
    from app.models.schemas import ReviewState

    settings = get_settings()
    timeout_seconds = settings.review_timeout_minutes * 60
    reminder_threshold = timeout_seconds * 0.8  # Remind at 80% of timeout
    reminded: list[int] = []

    bot_app = ctx.get("bot_application")
    if bot_app is None:
        return reminded

    chat_ids_str = settings.telegram_allowed_chat_ids
    if not chat_ids_str:
        return reminded

    from app.bot.lifecycle import parse_allowed_chat_ids
    chat_ids = parse_allowed_chat_ids(chat_ids_str)

    async with async_session_factory() as session:
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=reminder_threshold)
        query = select(Review).where(
            Review.state == ReviewState.APPROVING.value,
            Review.updated_at < cutoff_time,
        )
        result = await session.execute(query)
        approaching_timeout = result.scalars().all()

        for review in approaching_timeout:
            updated_at_utc = review.updated_at
            if updated_at_utc.tzinfo is None:
                updated_at_utc = updated_at_utc.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - updated_at_utc).total_seconds()
            remaining_minutes = int((timeout_seconds - elapsed) / 60)
            message = (
                f"⏰ 审核超时提醒\n"
                f"审核ID: {review.id}\n"
                f"类型: {review.type}\n"
                f"来源: {review.source_system}\n"
                f"剩余时间: {remaining_minutes} 分钟\n"
                f"请尽快处理"
            )
            for chat_id in chat_ids:
                try:
                    await bot_app.bot.send_message(chat_id=chat_id, text=message)
                except Exception as e:
                    logger.error("timeout_reminder_send_failed", chat_id=chat_id, review_id=review.id, error=str(e))
            reminded.append(review.id)
            logger.info("timeout_reminder_sent", review_id=review.id, remaining_minutes=remaining_minutes)

    return reminded


async def deliver_review_callback(
    ctx: dict, review_id: int, event_data: dict
) -> dict:
    """Deliver a callback payload to a review's callback_url with retry.

    Uses arq's Retry exception for exponential backoff (1s, 5s, 30s).
    Retries up to 3 times before giving up. On final failure, logs
    a Telegram admin notification intent (actual delivery deferred to Phase 09).

    Args:
        ctx: arq context dict with 'http_client' key.
        review_id: ID of the Review to deliver callback for.
        event_data: Event payload dict from emit_state_change.

    Returns:
        Summary dict with delivery result.
    """
    logger = structlog.get_logger()
    job_try = ctx.get("job_try", 1)

    from app.core.database import async_session_factory
    from app.models.schema import Review

    async with async_session_factory() as session:
        review = await session.get(Review, review_id)
        if review is None:
            logger.error("callback_review_not_found", review_id=review_id)
            return {"status": "error", "reason": "review_not_found"}

    # Skip delivery if review has no callback_url
    if not review.callback_url:
        return {"status": "skipped", "reason": "no_callback_url"}

    # Build enriched callback payload
    callback_payload = {
        **event_data,
        "disposition": review.disposition,
        "review_id": review.id,
        "source_system": review.source_system,
    }

    # Compute HMAC-SHA256 signature using review's callback_secret
    body = json.dumps(callback_payload, default=str)
    if review.callback_secret:
        signature = hmac.new(
            review.callback_secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
    else:
        signature = ""

    headers = {
        "Content-Type": "application/json",
        "X-Callback-Signature": f"sha256={signature}",
    }

    client: httpx.AsyncClient = ctx.get("http_client")
    if client is None:
        logger.error("callback_no_http_client")
        return {"status": "error", "reason": "no_http_client"}

    try:
        response = await client.post(
            review.callback_url,
            content=body,
            headers=headers,
            timeout=10.0,
        )
        if response.status_code >= 400:
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
        logger.info(
            "callback_delivered",
            url=review.callback_url,
            status_code=response.status_code,
            try_number=job_try,
        )
        return {"status": "delivered", "status_code": response.status_code}
    except Exception as e:
        logger.warning(
            "callback_delivery_failed",
            url=review.callback_url,
            error=str(e),
            try_number=job_try,
        )
        if job_try < 3:
            raise Retry(defer=CALLBACK_BACKOFF.get(job_try + 1, 30))
        logger.error(
            "callback_delivery_exhausted",
            review_id=review_id,
            callback_url=review.callback_url,
            tries=job_try,
        )
        await _notify_telegram_admin(review_id, review.callback_url, str(e))
        return {"status": "failed", "error": str(e), "tries": job_try}


class WorkerSettings:
    """arq worker configuration."""

    functions = [check_timeouts, deliver_webhook, deliver_review_callback, check_timeout_reminders]
    cron_jobs = [
        cron(check_timeouts, minute={0}),  # Run every hour at minute 0
        cron(check_timeout_reminders, minute={0, 30}),  # Run every 30 minutes
    ]

    async def on_startup(ctx):
        ctx["http_client"] = httpx.AsyncClient(timeout=10.0)
        try:
            from app.main import app
            ctx["bot_application"] = getattr(app.state, 'bot_application', None)
        except Exception:
            ctx["bot_application"] = None

    async def on_shutdown(ctx):
        await ctx["http_client"].aclose()
