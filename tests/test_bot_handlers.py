"""Unit tests for Telegram bot command handlers and InlineKeyboard callback handler."""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure test env vars are set before importing app modules
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-min-32-chars-long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


def _make_update_with_message(text: str, chat_id: int = 123456) -> MagicMock:
    """Create a mock Update with a message in a specific chat."""
    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.message.chat = MagicMock()
    update.message.chat.id = chat_id
    update.callback_query = None
    return update


def _make_update_with_callback(
    callback_data: str,
    chat_id: int = 123456,
    username: str = "testuser",
    user_id: int = 111222,
    message_id: int = 999,
) -> MagicMock:
    """Create a mock Update with a callback query."""
    update = MagicMock()
    update.callback_query = AsyncMock()
    update.callback_query.data = callback_data
    update.callback_query.from_user = MagicMock()
    update.callback_query.from_user.username = username
    update.callback_query.from_user.id = user_id
    update.callback_query.message = AsyncMock()
    update.callback_query.message.chat = MagicMock()
    update.callback_query.message.chat.id = chat_id
    update.callback_query.message.message_id = message_id
    update.callback_query.edit_message_text = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    return update


# --- /start command tests ---


class TestStartHandler:
    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_start_replies_with_welcome(self, mock_get_settings):
        from app.bot.handlers import start_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "123456"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_message("/start", chat_id=123456)
        context = MagicMock()

        await start_handler(update, context)

        update.message.reply_text.assert_called_once()
        reply = update.message.reply_text.call_args[0][0]
        assert "欢迎" in reply  # "欢迎"
        assert "/help" in reply
        assert "/status" in reply

    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_start_ignores_non_allowed_chat(self, mock_get_settings):
        from app.bot.handlers import start_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "999999"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_message("/start", chat_id=123456)
        context = MagicMock()

        await start_handler(update, context)

        update.message.reply_text.assert_not_called()


# --- /help command tests ---


class TestHelpHandler:
    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_help_replies_with_command_list(self, mock_get_settings):
        from app.bot.handlers import help_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "123456"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_message("/help", chat_id=123456)
        context = MagicMock()

        await help_handler(update, context)

        update.message.reply_text.assert_called_once()
        reply = update.message.reply_text.call_args[0][0]
        assert "/start" in reply
        assert "/help" in reply
        assert "/status" in reply

    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_help_ignores_non_allowed_chat(self, mock_get_settings):
        from app.bot.handlers import help_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "999999"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_message("/help", chat_id=123456)
        context = MagicMock()

        await help_handler(update, context)

        update.message.reply_text.assert_not_called()


# --- /status command tests ---


class TestStatusHandler:
    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_status_returns_approving_count(self, mock_get_settings):
        from app.bot.handlers import status_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "123456"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_message("/status", chat_id=123456)
        context = MagicMock()

        # Mock database session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 3
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.core.database.async_session_factory") as mock_factory:
            mock_factory.return_value = mock_session
            await status_handler(update, context)

        update.message.reply_text.assert_called_once()
        reply = update.message.reply_text.call_args[0][0]
        assert "3" in reply

    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_status_returns_zero_when_no_approving(self, mock_get_settings):
        from app.bot.handlers import status_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "123456"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_message("/status", chat_id=123456)
        context = MagicMock()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.core.database.async_session_factory") as mock_factory:
            mock_factory.return_value = mock_session
            await status_handler(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "0" in reply

    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_status_ignores_non_allowed_chat(self, mock_get_settings):
        from app.bot.handlers import status_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "999999"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_message("/status", chat_id=123456)
        context = MagicMock()

        await status_handler(update, context)

        update.message.reply_text.assert_not_called()


# --- Callback handler tests ---


class TestCallbackHandler:
    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_approve_transitions_to_complete_human(self, mock_get_settings):
        from app.bot.handlers import callback_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "123456"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_callback("approve:42:3", chat_id=123456)
        context = MagicMock()

        # Mock review in APPROVING state
        mock_review = MagicMock()
        mock_review.id = 42
        mock_review.state = "APPROVING"
        mock_review.version = 3

        # Mock transition_state result
        mock_updated_review = MagicMock()
        mock_updated_review.id = 42
        mock_updated_review.state = "COMPLETE"

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_review)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.core.database.async_session_factory") as mock_factory,
            patch("app.core.state_machine.transition_state", new_callable=AsyncMock) as mock_transition,
        ):
            mock_factory.return_value = mock_session
            mock_transition.return_value = mock_updated_review

            await callback_handler(update, context)

        # Verify callback was answered
        update.callback_query.answer.assert_called_once()
        # Verify transition was called with correct args
        mock_transition.assert_called_once()
        call_kwargs = mock_transition.call_args
        assert call_kwargs.kwargs["from_state"].value == "APPROVING"
        assert call_kwargs.kwargs["to_state"].value == "COMPLETE"
        # Verify message was edited
        update.callback_query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_reject_transitions_to_complete_block(self, mock_get_settings):
        from app.bot.handlers import callback_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "123456"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_callback("reject:42:3", chat_id=123456)
        context = MagicMock()

        mock_review = MagicMock()
        mock_review.id = 42
        mock_review.state = "APPROVING"

        mock_updated_review = MagicMock()
        mock_updated_review.id = 42
        mock_updated_review.state = "COMPLETE"

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_review)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.core.database.async_session_factory") as mock_factory,
            patch("app.core.state_machine.transition_state", new_callable=AsyncMock) as mock_transition,
        ):
            mock_factory.return_value = mock_session
            mock_transition.return_value = mock_updated_review

            await callback_handler(update, context)

        # Verify reject action was passed
        call_kwargs = mock_transition.call_args
        assert call_kwargs.kwargs["action"] == "reject"

    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_approve_edits_message_with_approved_text(self, mock_get_settings):
        from app.bot.handlers import callback_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "123456"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_callback("approve:42:3", chat_id=123456)
        context = MagicMock()

        mock_review = MagicMock()
        mock_review.id = 42
        mock_review.state = "APPROVING"

        mock_updated_review = MagicMock()
        mock_updated_review.id = 42
        mock_updated_review.state = "COMPLETE"

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_review)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.core.database.async_session_factory") as mock_factory,
            patch("app.core.state_machine.transition_state", new_callable=AsyncMock) as mock_transition,
        ):
            mock_factory.return_value = mock_session
            mock_transition.return_value = mock_updated_review

            await callback_handler(update, context)

        # Verify the edited message contains approval confirmation
        edited_text = update.callback_query.edit_message_text.call_args[1]["text"]
        assert "✅" in edited_text

    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_reject_edits_message_with_rejected_text(self, mock_get_settings):
        from app.bot.handlers import callback_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "123456"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_callback("reject:42:3", chat_id=123456)
        context = MagicMock()

        mock_review = MagicMock()
        mock_review.id = 42
        mock_review.state = "APPROVING"

        mock_updated_review = MagicMock()
        mock_updated_review.id = 42
        mock_updated_review.state = "COMPLETE"

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_review)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.core.database.async_session_factory") as mock_factory,
            patch("app.core.state_machine.transition_state", new_callable=AsyncMock) as mock_transition,
        ):
            mock_factory.return_value = mock_session
            mock_transition.return_value = mock_updated_review

            await callback_handler(update, context)

        edited_text = update.callback_query.edit_message_text.call_args[1]["text"]
        assert "❌" in edited_text

    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_duplicate_approve_shows_already_processed(self, mock_get_settings):
        from app.bot.handlers import callback_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "123456"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_callback("approve:42:3", chat_id=123456)
        context = MagicMock()

        # Review already in COMPLETE state
        mock_review = MagicMock()
        mock_review.id = 42
        mock_review.state = "COMPLETE"

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_review)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.core.database.async_session_factory") as mock_factory:
            mock_factory.return_value = mock_session
            await callback_handler(update, context)

        edited_text = update.callback_query.edit_message_text.call_args[1]["text"]
        assert "⚠️" in edited_text  # Warning sign for already processed
        assert "已处理" in edited_text  # "已处理"

    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_stale_callback_shows_current_status(self, mock_get_settings):
        from app.bot.handlers import callback_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "123456"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_callback("approve:42:3", chat_id=123456)
        context = MagicMock()

        # Review in PENDING state (stale - not APPROVING anymore)
        mock_review = MagicMock()
        mock_review.id = 42
        mock_review.state = "PENDING"

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_review)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.core.database.async_session_factory") as mock_factory:
            mock_factory.return_value = mock_session
            await callback_handler(update, context)

        edited_text = update.callback_query.edit_message_text.call_args[1]["text"]
        assert "⚠️" in edited_text
        assert "PENDING" in edited_text

    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_callback_ignores_non_allowed_chat(self, mock_get_settings):
        from app.bot.handlers import callback_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "999999"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_callback("approve:42:3", chat_id=123456)
        context = MagicMock()

        await callback_handler(update, context)

        # Should answer the query but not edit message
        update.callback_query.answer.assert_called_once()
        update.callback_query.edit_message_text.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_callback_answers_query_to_remove_spinner(self, mock_get_settings):
        from app.bot.handlers import callback_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "123456"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_callback("approve:42:3", chat_id=123456)
        context = MagicMock()

        mock_review = MagicMock()
        mock_review.id = 42
        mock_review.state = "APPROVING"

        mock_updated_review = MagicMock()
        mock_updated_review.id = 42
        mock_updated_review.state = "COMPLETE"

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_review)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.core.database.async_session_factory") as mock_factory,
            patch("app.core.state_machine.transition_state", new_callable=AsyncMock) as mock_transition,
        ):
            mock_factory.return_value = mock_session
            mock_transition.return_value = mock_updated_review
            await callback_handler(update, context)

        # answer() should be called BEFORE edit_message_text
        update.callback_query.answer.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.bot.handlers.get_settings")
    async def test_malformed_callback_data_logs_error(self, mock_get_settings):
        from app.bot.handlers import callback_handler

        mock_settings = MagicMock()
        mock_settings.telegram_allowed_chat_ids = "123456"
        mock_get_settings.return_value = mock_settings

        update = _make_update_with_callback("invalid_data", chat_id=123456)
        context = MagicMock()

        await callback_handler(update, context)

        # Should answer query but not attempt DB operations
        update.callback_query.answer.assert_called_once()
        update.callback_query.edit_message_text.assert_not_called()
