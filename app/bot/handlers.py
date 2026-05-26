"""Telegram Bot command handlers and InlineKeyboard callback handler.

Handles /start, /help, /status commands and approve/reject callback queries.
"""

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from app.bot.lifecycle import parse_allowed_chat_ids
from app.bot.notifications import build_status_text
from app.core.config import get_settings

logger = structlog.get_logger(__name__)


def _is_allowed_chat(chat_id: int) -> bool:
    """Check if a chat ID is in the allowed list."""
    settings = get_settings()
    allowed_ids = parse_allowed_chat_ids(settings.telegram_allowed_chat_ids)
    if not allowed_ids:
        # If no allowlist configured, allow all (dev mode)
        return True
    return chat_id in allowed_ids


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command with Chinese welcome message."""
    if not update.effective_chat or not _is_allowed_chat(update.effective_chat.id):
        return

    welcome_text = (
        "👋 欢迎！我是审核通知机器人\n"
        "\n"
        "当有新审核请求时，我会向您发送通知。\n"
        "您可以直接通过按钮批准或驳回审核。\n"
        "\n"
        "可用命令:\n"
        "/help - 查看帮助\n"
        "/status - 查看待审核数量"
    )
    await update.message.reply_text(welcome_text)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command with Chinese command list."""
    if not update.effective_chat or not _is_allowed_chat(update.effective_chat.id):
        return

    help_text = (
        "📖 命令列表\n"
        "\n"
        "/start - 开始使用\n"
        "/help - 查看此帮助\n"
        "/status - 查看当前待审核数量\n"
        "\n"
        "收到审核通知时，点击\"批准\"或\"驳回\"按钮即可完成审核。"
    )
    await update.message.reply_text(help_text)


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command, query APPROVING review count from database."""
    if not update.effective_chat or not _is_allowed_chat(update.effective_chat.id):
        return

    try:
        from sqlalchemy import func, select

        from app.core.database import async_session_factory
        from app.models.schema import Review

        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(Review).where(Review.state == "APPROVING")
            )
            count = result.scalar() or 0

        await update.message.reply_text(f"📊 当前有 {count} 个待审核请求")
    except Exception as e:
        logger.error("status_handler_error", error=str(e))
        await update.message.reply_text("查询失败，请稍后重试")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle InlineKeyboard approve/reject callback queries.

    Parses callback_data in format "approve:{review_id}:{version}" or
    "reject:{review_id}:{version}". Transitions review state and edits
    the notification message with the result.
    """
    callback_query = update.callback_query
    await callback_query.answer()

    # Check allowed chat
    if not callback_query.message or not _is_allowed_chat(callback_query.message.chat.id):
        return

    # Parse callback_data
    try:
        parts = callback_query.data.split(":")
        if len(parts) != 3 or parts[0] not in ("approve", "reject"):
            logger.error("callback_malformed_data", data=callback_query.data)
            return
        action = parts[0]
        review_id = int(parts[1])
        version = int(parts[2])
    except (ValueError, AttributeError) as e:
        logger.error("callback_parse_error", error=str(e), data=callback_query.data)
        return

    try:
        from sqlalchemy import select

        from app.core.database import async_session_factory
        from app.core.state_machine import StateConflictError, transition_state
        from app.models.schema import Review
        from app.models.schemas import ReviewState

        async with async_session_factory() as session:
            # Fetch review
            review = await session.get(Review, review_id)

            if review is None:
                await callback_query.edit_message_text("审核不存在")
                return

            # Check current state
            if review.state != ReviewState.APPROVING.value:
                if review.state == ReviewState.COMPLETE.value:
                    status_text = build_status_text(review, "already_processed", "")
                else:
                    status_text = build_status_text(review, "stale", "")
                await callback_query.edit_message_text(text=status_text)
                return

            # Determine actor name
            username = callback_query.from_user.username
            user_id = callback_query.from_user.id
            actor = f"telegram:{username or user_id}"

            # Determine target disposition
            disposition_action = action  # "approve" or "reject"

            try:
                updated_review = await transition_state(
                    session,
                    review_id=review_id,
                    from_state=ReviewState.APPROVING,
                    to_state=ReviewState.COMPLETE,
                    expected_version=version,
                    actor=actor,
                    action=disposition_action,
                    payload={
                        "telegram_user": username,
                        "chat_id": callback_query.message.chat.id,
                    },
                )

                actor_display = username or str(user_id)
                status_text = build_status_text(updated_review, action, actor_display)
                await callback_query.edit_message_text(text=status_text)

            except StateConflictError:
                # Version mismatch - another process already handled it
                current_review = await session.get(Review, review_id)
                if current_review and current_review.state == ReviewState.COMPLETE.value:
                    status_text = build_status_text(current_review, "already_processed", "")
                else:
                    status_text = build_status_text(current_review, "stale", "") if current_review else "操作失败，请重试"
                await callback_query.edit_message_text(text=status_text)

    except Exception as e:
        logger.error("callback_handler_error", error=str(e), review_id=review_id)
        try:
            await callback_query.edit_message_text("操作失败，请重试")
        except Exception:
            pass
