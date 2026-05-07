"""Unit tests for bot lifecycle, notification builder, and status text."""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure test env vars are set before importing app modules
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-min-32-chars-long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


# --- parse_allowed_chat_ids tests ---


class TestParseAllowedChatIds:
    def test_parse_comma_separated_ids(self):
        from app.bot.lifecycle import parse_allowed_chat_ids

        result = parse_allowed_chat_ids("123456,789012,111222")
        assert result == [123456, 789012, 111222]

    def test_parse_empty_string_returns_empty_list(self):
        from app.bot.lifecycle import parse_allowed_chat_ids

        result = parse_allowed_chat_ids("")
        assert result == []

    def test_parse_single_id(self):
        from app.bot.lifecycle import parse_allowed_chat_ids

        result = parse_allowed_chat_ids("123456")
        assert result == [123456]

    def test_parse_non_numeric_raises_value_error(self):
        from app.bot.lifecycle import parse_allowed_chat_ids

        with pytest.raises(ValueError):
            parse_allowed_chat_ids("123,abc,456")


# --- create_bot_application tests ---


class TestCreateBotApplication:
    @patch("app.bot.lifecycle.get_settings")
    def test_returns_application_with_correct_token(self, mock_get_settings):
        from app.bot.lifecycle import create_bot_application

        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "123456:ABC-DEF"
        mock_get_settings.return_value = mock_settings

        app = create_bot_application()
        assert app is not None
        assert app.bot.token == "123456:ABC-DEF"

    @patch("app.bot.lifecycle.get_settings")
    def test_returns_none_when_token_empty(self, mock_get_settings):
        from app.bot.lifecycle import create_bot_application

        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = ""
        mock_get_settings.return_value = mock_settings

        app = create_bot_application()
        assert app is None

    @patch("app.bot.lifecycle.get_settings")
    def test_registers_command_and_callback_handlers(self, mock_get_settings):
        from app.bot.lifecycle import create_bot_application

        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "123456:ABC-DEF"
        mock_get_settings.return_value = mock_settings

        app = create_bot_application()
        assert app is not None
        # Check that handlers were registered (groups contain handlers)
        handler_groups = app.handlers
        # python-telegram-bot stores handlers in groups dict
        total_handlers = sum(len(group) for group in handler_groups.values())
        assert total_handlers >= 4  # start, help, status commands + callback


# --- bot_start tests ---


class TestBotStart:
    @pytest.mark.asyncio
    async def test_bot_start_initializes_and_starts_polling(self):
        from app.bot.lifecycle import bot_start

        mock_app = AsyncMock()
        mock_app.updater = AsyncMock()

        await bot_start(mock_app)

        mock_app.initialize.assert_called_once()
        mock_app.start.assert_called_once()
        mock_app.updater.start_polling.assert_called_once_with(
            drop_pending_updates=True
        )

    @pytest.mark.asyncio
    async def test_bot_start_is_noop_when_application_none(self):
        from app.bot.lifecycle import bot_start

        # Should not raise
        await bot_start(None)

    @pytest.mark.asyncio
    async def test_bot_start_logs_warning_on_failure(self):
        from app.bot.lifecycle import bot_start

        mock_app = AsyncMock()
        mock_app.initialize.side_effect = Exception("connection failed")

        # Should not raise, just log warning
        await bot_start(mock_app)


# --- bot_stop tests ---


class TestBotStop:
    @pytest.mark.asyncio
    async def test_bot_stop_stops_updater_and_shuts_down(self):
        from app.bot.lifecycle import bot_stop

        mock_app = AsyncMock()
        mock_app.updater = AsyncMock()
        mock_app.updater.running = True
        mock_app.running = True

        await bot_stop(mock_app)

        mock_app.updater.stop.assert_called_once()
        mock_app.stop.assert_called_once()
        mock_app.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_bot_stop_is_noop_when_application_none(self):
        from app.bot.lifecycle import bot_stop

        # Should not raise
        await bot_stop(None)


# --- build_notification_message tests ---


class TestBuildNotificationMessage:
    def test_creates_inline_keyboard_with_approve_reject_buttons(self):
        from app.bot.notifications import build_notification_message

        review = MagicMock()
        review.id = 42
        review.type = "image_review"
        review.source_system = "kais-movie-agent"
        review.risk_score = 0.75
        review.priority = "high"
        review.content_ref = "s3://bucket/image.png"
        review.state = "APPROVING"
        review.created_at = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
        review.version = 3

        text, reply_markup = build_notification_message(review, [])

        # Check keyboard has 2 buttons
        assert len(reply_markup.inline_keyboard) == 1
        buttons = reply_markup.inline_keyboard[0]
        assert len(buttons) == 2

        approve_btn = buttons[0]
        reject_btn = buttons[1]

        assert "approve" in approve_btn.callback_data
        assert "reject" in reject_btn.callback_data
        assert approve_btn.text == "✅ 批准"
        assert reject_btn.text == "❌ 驳回"

    def test_includes_review_details_in_message(self):
        from app.bot.notifications import build_notification_message

        review = MagicMock()
        review.id = 42
        review.type = "image_review"
        review.source_system = "kais-movie-agent"
        review.risk_score = 0.75
        review.priority = "high"
        review.content_ref = "s3://bucket/image.png"
        review.state = "APPROVING"
        review.created_at = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
        review.version = 3

        text, _ = build_notification_message(review, [])

        assert "42" in text
        assert "image_review" in text
        assert "kais-movie-agent" in text
        assert "high" in text

    def test_truncates_content_ref_to_100_chars(self):
        from app.bot.notifications import build_notification_message

        long_ref = "x" * 200
        review = MagicMock()
        review.id = 1
        review.type = "test"
        review.source_system = "test-system"
        review.risk_score = 0.5
        review.priority = "normal"
        review.content_ref = long_ref
        review.state = "APPROVING"
        review.created_at = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
        review.version = 1

        text, _ = build_notification_message(review, [])

        # Content should be truncated to 100 chars + ellipsis
        assert long_ref[:100] in text
        assert long_ref[101:] not in text

    def test_includes_approval_history(self):
        from app.bot.notifications import build_notification_message

        review = MagicMock()
        review.id = 10
        review.type = "gpu_task"
        review.source_system = "kais-gold-team"
        review.risk_score = 0.9
        review.priority = "critical"
        review.content_ref = "task-123"
        review.state = "APPROVING"
        review.created_at = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
        review.version = 2

        audit1 = MagicMock()
        audit1.action = "transition"
        audit1.actor = "policy_engine"
        audit1.to_state = "APPROVING"
        audit1.created_at = datetime(2026, 5, 7, 12, 5, 0, tzinfo=timezone.utc)

        audit2 = MagicMock()
        audit2.action = "transition"
        audit2.actor = "admin:kai"
        audit2.to_state = "COMPLETE"
        audit2.created_at = datetime(2026, 5, 7, 12, 10, 0, tzinfo=timezone.utc)

        text, _ = build_notification_message(review, [audit1, audit2])

        assert "policy_engine" in text
        assert "APPROVING" in text

    def test_shows_no_history_message_when_empty(self):
        from app.bot.notifications import build_notification_message

        review = MagicMock()
        review.id = 1
        review.type = "test"
        review.source_system = "test"
        review.risk_score = 0.1
        review.priority = "normal"
        review.content_ref = "ref"
        review.state = "APPROVING"
        review.created_at = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
        review.version = 1

        text, _ = build_notification_message(review, [])

        assert "暂无历史决策" in text  # "暂无历史决策"

    def test_callback_data_format(self):
        from app.bot.notifications import build_notification_message

        review = MagicMock()
        review.id = 42
        review.type = "test"
        review.source_system = "test"
        review.risk_score = 0.5
        review.priority = "normal"
        review.content_ref = "ref"
        review.state = "APPROVING"
        review.created_at = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
        review.version = 5

        _, reply_markup = build_notification_message(review, [])

        buttons = reply_markup.inline_keyboard[0]
        assert buttons[0].callback_data == "approve:42:5"
        assert buttons[1].callback_data == "reject:42:5"


# --- build_status_text tests ---


class TestBuildStatusText:
    def test_approve_status_text(self):
        from app.bot.notifications import build_status_text

        review = MagicMock()
        review.id = 42
        review.state = "COMPLETE"

        text = build_status_text(review, "approve", "telegram:kai")
        assert "✅" in text  # Checkmark
        assert "42" in text
        assert "telegram:kai" in text

    def test_reject_status_text(self):
        from app.bot.notifications import build_status_text

        review = MagicMock()
        review.id = 42
        review.state = "COMPLETE"

        text = build_status_text(review, "reject", "telegram:kai")
        assert "❌" in text  # Cross mark
        assert "42" in text

    def test_already_processed_status_text(self):
        from app.bot.notifications import build_status_text

        review = MagicMock()
        review.id = 42
        review.state = "COMPLETE"

        text = build_status_text(review, "already_processed", "")
        assert "⚠️" in text  # Warning sign
        assert "42" in text

    def test_stale_callback_status_text(self):
        from app.bot.notifications import build_status_text

        review = MagicMock()
        review.id = 42
        review.state = "PENDING"

        text = build_status_text(review, "stale", "")
        assert "⚠️" in text
        assert "PENDING" in text
