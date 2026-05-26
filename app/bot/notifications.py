"""Review notification message builder with InlineKeyboard markup.

Builds Chinese-language notification messages for review items with
approve/reject InlineKeyboard buttons. Also provides status text
builders for after approve/reject actions.
"""

from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.models.schema import AuditEntry, Review


def _format_datetime(dt: datetime) -> str:
    """Format a datetime for display in notification messages."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _format_risk_score(score: float | None) -> str:
    """Format risk score for display."""
    if score is None:
        return "未评估"
    pct = int(score * 100)
    if pct >= 80:
        return f"🔴 {pct}%"
    elif pct >= 50:
        return f"🟡 {pct}%"
    else:
        return f"🟢 {pct}%"


def build_notification_message(
    review: Review,
    audit_entries: list[AuditEntry],
) -> tuple[str, InlineKeyboardMarkup]:
    """Build a Chinese-language review notification with InlineKeyboard.

    Args:
        review: The Review database object.
        audit_entries: List of AuditEntry objects for approval history.

    Returns:
        Tuple of (message_text, InlineKeyboardMarkup) with approve/reject buttons.
    """
    content_display = review.content_ref[:100]
    if len(review.content_ref) > 100:
        content_display += "..."

    lines = [
        "🔔 新审核请求",
        "",
        f"📋 审核ID: {review.id}",
        f"📌 类型: {review.type}",
        f"🏷 来源: {review.source_system}",
        f"⚠️ 风险: {_format_risk_score(review.risk_score)}",
        f"🚨 优先级: {review.priority}",
        f"📝 内容: {content_display}",
        f"⏰ 提交时间: {_format_datetime(review.created_at)}",
        "",
    ]

    # Approval history section
    history_entries = [
        entry
        for entry in audit_entries
        if entry.action == "transition"
        and entry.to_state in ("APPROVING", "COMPLETE")
    ]

    if history_entries:
        lines.append("📋 历史决策:")
        for entry in history_entries:
            icon = "✓" if entry.to_state == "COMPLETE" else "→"
            lines.append(
                f"  {icon} {entry.actor} {_format_datetime(entry.created_at)} {entry.to_state}"
            )
    else:
        lines.append("📋 历史决策: 暂无历史决策")

    text = "\n".join(lines)

    # InlineKeyboard with approve/reject buttons
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ 批准",
                callback_data=f"approve:{review.id}:{review.version}",
            ),
            InlineKeyboardButton(
                "❌ 驳回",
                callback_data=f"reject:{review.id}:{review.version}",
            ),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    return text, reply_markup


def build_review_captions(metadata: dict, max_images: int = 3) -> list[str]:
    """Build captions for preview images from review metadata.

    Args:
        metadata: Review metadata dict, may contain preview_images list.
        max_images: Maximum number of image captions to generate.

    Returns:
        List of caption strings, one per image.
    """
    phase_name = metadata.get("phase_name", "未知阶段")
    episode = metadata.get("episode", "")
    preview_count = min(len(metadata.get("preview_images", [])), max_images)

    if preview_count == 0:
        return []

    if preview_count == 1:
        return [f"🖼️ {episode} {phase_name} 预览" if episode else f"🖼️ {phase_name} 预览"]

    return [
        f"🖼️ 预览 {i + 1}/{preview_count}" + (f" — {episode} {phase_name}" if episode else f" — {phase_name}")
        for i in range(preview_count)
    ]


def build_status_text(review: Review, action: str, actor: str) -> str:
    """Build status update text after an approve/reject action.

    Args:
        review: The Review database object (after state change).
        action: One of "approve", "reject", "already_processed", "stale".
        actor: Actor identifier (e.g. "telegram:kai").

    Returns:
        Formatted status text string.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if action == "approve":
        return (
            f"✅ 审核已通过\n"
            f"审核ID: {review.id}\n"
            f"操作人: {actor}\n"
            f"时间: {now}"
        )
    elif action == "reject":
        return (
            f"❌ 审核已驳回\n"
            f"审核ID: {review.id}\n"
            f"操作人: {actor}\n"
            f"时间: {now}"
        )
    elif action == "already_processed":
        return (
            f"⚠️ 审核已处理\n"
            f"审核ID: {review.id}\n"
            f"当前状态: {review.state}"
        )
    else:
        # stale or unknown
        return (
            f"⚠️ 审核已结束\n"
            f"审核ID: {review.id}\n"
            f"当前状态: {review.state}"
        )
