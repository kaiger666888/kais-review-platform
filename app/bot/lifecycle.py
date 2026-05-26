"""Bot lifecycle management: initialization, start, stop, shutdown."""

import structlog
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


def parse_allowed_chat_ids(chat_ids_str: str) -> list[int]:
    """Parse comma-separated chat IDs string to list of integers.

    Args:
        chat_ids_str: Comma-separated chat IDs, e.g. "123456,789012".

    Returns:
        List of integer chat IDs. Empty list for empty string.

    Raises:
        ValueError: If any value is not a valid integer.
    """
    if not chat_ids_str:
        return []
    result = []
    for part in chat_ids_str.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.append(int(part))
        except ValueError:
            raise ValueError(f"Invalid chat ID: {part!r} is not a number")
    return result


def _register_handlers(application: Application) -> None:
    """Register command and callback handlers on the application.

    Imported here to avoid circular imports at module level.
    """
    from app.bot.handlers import (
        callback_handler,
        help_handler,
        start_handler,
        status_handler,
    )

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("status", status_handler))
    application.add_handler(CallbackQueryHandler(callback_handler))


def create_bot_application() -> Application | None:
    """Create a Telegram Bot Application instance.

    Reads telegram_bot_token from settings. Returns None if the token
    is not configured (empty string), allowing the app to run without
    bot functionality.

    Returns:
        Configured Application instance, or None if token is empty.
    """
    settings = get_settings()
    token = settings.telegram_bot_token

    if not token:
        logger.info("bot_token_not_configured", message="Telegram Bot token is empty, bot disabled")
        return None

    application = Application.builder().token(token).build()
    _register_handlers(application)

    logger.info("bot_application_created", message="Telegram Bot application created with registered handlers")
    return application


async def bot_start(application: Application | None) -> None:
    """Start the bot: initialize, start, and begin polling.

    Safe to call with None (no-op). On failure, logs warning and returns
    without raising -- bot failure does not block the main application.

    Args:
        application: The Application instance from create_bot_application(), or None.
    """
    if application is None:
        logger.warning("bot_start_skipped", reason="application is None (token not configured)")
        return

    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        logger.info("bot_started", message="Telegram Bot polling started")
    except Exception as e:
        logger.error("bot_start_failed", error=str(e))


async def bot_stop(application: Application | None) -> None:
    """Stop the bot: stop updater, stop application, and shutdown.

    Safe to call with None (no-op). On failure, logs error silently.

    Args:
        application: The Application instance, or None.
    """
    if application is None:
        return

    try:
        if application.updater and application.updater.running:
            await application.updater.stop()
        if application.running:
            await application.stop()
        await application.shutdown()
        logger.info("bot_stopped", message="Telegram Bot stopped and shut down")
    except Exception as e:
        logger.error("bot_stop_failed", error=str(e))
