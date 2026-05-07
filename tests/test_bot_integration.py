"""Integration tests for Telegram Bot wiring into FastAPI lifecycle and events.

Tests that:
- FastAPI lifespan creates/starts/stops bot application
- emit_state_change sends notifications when review enters APPROVING state
- Notifications skipped when bot not configured (application is None)
- Notification failure does not propagate (logged only)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot_application():
    """Create a mock bot Application with a mock bot.send_message."""
    app = MagicMock()
    app.bot = MagicMock()
    app.bot.send_message = AsyncMock()
    return app


@pytest.fixture
def mock_fastapi_app(mock_bot_application):
    """Create a minimal FastAPI app with bot_application on state."""
    from fastapi import FastAPI

    app = FastAPI()
    app.state.bot_application = mock_bot_application
    return app


@pytest.fixture
def no_bot_fastapi_app():
    """Create a FastAPI app without bot_application (bot not configured)."""
    from fastapi import FastAPI

    app = FastAPI()
    app.state.bot_application = None
    return app


@pytest.fixture
def mock_review():
    """Create a mock Review object."""
    review = MagicMock()
    review.id = 42
    review.type = "movie_review"
    review.source_system = "kais-movie-agent"
    review.content_ref = "test content"
    review.priority = "high"
    review.risk_score = 0.7
    review.created_at = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    return review


@pytest.fixture
def mock_audit_entries():
    """Create mock audit entries."""
    entry = MagicMock()
    entry.action = "transition"
    entry.to_state = "APPROVING"
    entry.actor = "policy_engine"
    entry.created_at = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    return [entry]


# ---------------------------------------------------------------------------
# Test 1 & 2: FastAPI lifespan startup/shutdown calls bot lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_startup_creates_and_starts_bot():
    """Lifespan startup should call create_bot_application and bot_start."""
    from fastapi import FastAPI

    mock_bot_app = MagicMock()

    # Create a mock conn that supports run_sync
    mock_conn = AsyncMock()

    # Create a mock redis with async close
    mock_redis = AsyncMock()
    # Create a mock arq pool with async close
    mock_arq_pool = AsyncMock()

    with (
        patch("app.main.create_bot_application", return_value=mock_bot_app) as mock_create,
        patch("app.main.bot_start", new_callable=AsyncMock) as mock_start,
        patch("app.main.bot_stop", new_callable=AsyncMock),
        patch("app.main.aioredis.from_url", return_value=mock_redis),
        patch("app.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool),
        patch("app.main.engine") as mock_engine,
        patch("app.main.get_policy_engine"),
        patch("app.main.create_tables"),
    ):
        # Set up engine.begin() as async context manager
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_engine.dispose = AsyncMock()

        test_app = FastAPI()
        from app.main import lifespan

        async with lifespan(test_app):
            pass

        mock_create.assert_called_once()
        mock_start.assert_called_once_with(mock_bot_app)


@pytest.mark.asyncio
async def test_lifespan_shutdown_calls_bot_stop():
    """Lifespan shutdown should call bot_stop."""
    from fastapi import FastAPI

    mock_bot_app = MagicMock()
    mock_conn = AsyncMock()
    mock_redis = AsyncMock()
    mock_arq_pool = AsyncMock()

    with (
        patch("app.main.create_bot_application", return_value=mock_bot_app),
        patch("app.main.bot_start", new_callable=AsyncMock),
        patch("app.main.bot_stop", new_callable=AsyncMock) as mock_stop,
        patch("app.main.aioredis.from_url", return_value=mock_redis),
        patch("app.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool),
        patch("app.main.engine") as mock_engine,
        patch("app.main.get_policy_engine"),
        patch("app.main.create_tables"),
    ):
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_engine.dispose = AsyncMock()

        test_app = FastAPI()
        from app.main import lifespan

        async with lifespan(test_app):
            pass

        mock_stop.assert_called_once_with(mock_bot_app)


# ---------------------------------------------------------------------------
# Test 3: emit_state_change sends notification on APPROVING state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_state_change_sends_notification_on_approving(
    mock_fastapi_app, mock_bot_application, mock_review, mock_audit_entries
):
    """When new_state=APPROVING, emit_state_change sends bot notifications."""
    with (
        patch("app.core.events.event_manager") as mock_em,
        patch("app.core.database.async_session_factory") as mock_session_factory,
        patch("app.main.app", mock_fastapi_app),
        patch("app.core.config.get_settings") as mock_settings,
    ):
        mock_em.broadcast = AsyncMock()

        # Settings with allowed chat IDs
        settings = MagicMock()
        settings.telegram_allowed_chat_ids = "111,222"
        mock_settings.return_value = settings

        # Mock DB session
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=mock_review)

        # Mock audit query
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_audit_entries
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        from app.core.events import emit_state_change

        await emit_state_change(42, "POLICY_EVAL", "APPROVING", "kais-movie-agent")

        # Should have called send_message for each chat ID
        assert mock_bot_application.bot.send_message.call_count == 2


# ---------------------------------------------------------------------------
# Test 4: emit_state_change skips notification for non-APPROVING states
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_state_change_skips_notification_for_non_approving(
    mock_fastapi_app, mock_bot_application
):
    """When new_state != APPROVING, no bot notification is sent."""
    with (
        patch("app.core.events.event_manager") as mock_em,
        patch("app.main.app", mock_fastapi_app),
    ):
        mock_em.broadcast = AsyncMock()

        from app.core.events import emit_state_change

        await emit_state_change(42, "APPROVING", "COMPLETE", "kais-movie-agent")

        # Bot send_message should NOT have been called
        mock_bot_application.bot.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: Bot notification skipped when application is None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notification_skipped_when_bot_application_is_none(no_bot_fastapi_app):
    """Notification should be skipped when bot_application is None."""
    with (
        patch("app.core.events.event_manager") as mock_em,
        patch("app.main.app", no_bot_fastapi_app),
    ):
        mock_em.broadcast = AsyncMock()

        from app.core.events import emit_state_change

        # Should not raise even though bot is None
        await emit_state_change(42, "POLICY_EVAL", "APPROVING", "kais-movie-agent")


# ---------------------------------------------------------------------------
# Test 6: Bot notification fetches review and audit entries from database
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notification_fetches_review_and_audit_entries(
    mock_fastapi_app, mock_bot_application, mock_review, mock_audit_entries
):
    """Bot notification should fetch review and audit entries from DB."""
    with (
        patch("app.core.events.event_manager") as mock_em,
        patch("app.core.database.async_session_factory") as mock_session_factory,
        patch("app.main.app", mock_fastapi_app),
        patch("app.core.config.get_settings") as mock_settings,
    ):
        mock_em.broadcast = AsyncMock()

        settings = MagicMock()
        settings.telegram_allowed_chat_ids = "111"
        mock_settings.return_value = settings

        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=mock_review)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_audit_entries
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        from app.core.events import emit_state_change

        await emit_state_change(42, "POLICY_EVAL", "APPROVING", "kais-movie-agent")

        # Verify session.get was called with Review model and review_id
        mock_session.get.assert_called_once()
        # Verify execute was called for audit entries (at least once - webhook block also uses it)
        assert mock_session.execute.call_count >= 1


# ---------------------------------------------------------------------------
# Test 7: Bot notification failure does not raise exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notification_failure_does_not_raise(mock_fastapi_app, mock_bot_application):
    """If bot notification fails, it should be logged but not propagate."""
    mock_bot_application.bot.send_message.side_effect = RuntimeError("Telegram API down")

    with (
        patch("app.core.events.event_manager") as mock_em,
        patch("app.core.database.async_session_factory") as mock_session_factory,
        patch("app.main.app", mock_fastapi_app),
        patch("app.core.config.get_settings") as mock_settings,
    ):
        mock_em.broadcast = AsyncMock()

        settings = MagicMock()
        settings.telegram_allowed_chat_ids = "111"
        mock_settings.return_value = settings

        mock_review = MagicMock()
        mock_review.id = 42
        mock_review.type = "test"
        mock_review.source_system = "test"
        mock_review.content_ref = "test"
        mock_review.priority = "normal"
        mock_review.risk_score = None
        mock_review.created_at = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)

        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=mock_review)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        from app.core.events import emit_state_change

        # Should NOT raise despite send_message failing
        await emit_state_change(42, "POLICY_EVAL", "APPROVING", "kais-movie-agent")


# ---------------------------------------------------------------------------
# Test 8: Bot notification skipped for reviews with no matching review in DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notification_skipped_when_review_not_in_db(
    mock_fastapi_app, mock_bot_application
):
    """If review is not found in DB, notification should be skipped silently."""
    with (
        patch("app.core.events.event_manager") as mock_em,
        patch("app.core.database.async_session_factory") as mock_session_factory,
        patch("app.main.app", mock_fastapi_app),
        patch("app.core.config.get_settings") as mock_settings,
    ):
        mock_em.broadcast = AsyncMock()

        settings = MagicMock()
        settings.telegram_allowed_chat_ids = "111"
        mock_settings.return_value = settings

        # Return None for review not found
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=None)

        from app.core.events import emit_state_change

        await emit_state_change(999, "POLICY_EVAL", "APPROVING", "test")

        # send_message should NOT be called since review is None
        mock_bot_application.bot.send_message.assert_not_called()
