"""Tests for webhook delivery and WebhookConfig model.

Tests the deliver_webhook arq task with HMAC-SHA256 signatures,
retry logic with exponential backoff, and WebhookConfig CRUD model.
"""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.core.events import EventManager, emit_state_change
from app.models.schema import WebhookConfig
from app.workers.tasks import deliver_webhook, WEBHOOK_BACKOFF


class TestWebhookConfigModel:
    """Test WebhookConfig SQLAlchemy model CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_webhook_config(self, db_session):
        """Create a WebhookConfig and verify defaults."""
        config = WebhookConfig(
            url="http://example.com/hook",
            secret="secret123",
            source_system="kais-movie-agent",
        )
        db_session.add(config)
        await db_session.commit()
        await db_session.refresh(config)

        assert config.id is not None
        assert config.is_active is True
        assert config.url == "http://example.com/hook"
        assert config.secret == "secret123"
        assert config.source_system == "kais-movie-agent"

    @pytest.mark.asyncio
    async def test_webhook_config_source_system_filter(self, db_session):
        """Query WebhookConfig by source_system."""
        from sqlalchemy import select

        c1 = WebhookConfig(
            url="http://a.com/hook",
            secret="s1",
            source_system="kais-movie-agent",
        )
        c2 = WebhookConfig(
            url="http://b.com/hook",
            secret="s2",
            source_system="kais-gold-team",
        )
        db_session.add_all([c1, c2])
        await db_session.commit()

        stmt = select(WebhookConfig).where(
            WebhookConfig.source_system == "kais-movie-agent"
        )
        result = await db_session.execute(stmt)
        configs = result.scalars().all()

        assert len(configs) == 1
        assert configs[0].source_system == "kais-movie-agent"


class TestDeliverWebhookSuccess:
    """Test successful webhook delivery."""

    @pytest.mark.asyncio
    async def test_deliver_webhook_success(self, db_engine):
        """deliver_webhook returns delivered status on 200 response."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        # Create a WebhookConfig in the test database
        async with factory() as session:
            config = WebhookConfig(
                url="http://example.com/webhook",
                secret="test-secret",
                source_system="kais-movie-agent",
            )
            session.add(config)
            await session.commit()
            await session.refresh(config)
            config_id = config.id

        # Mock httpx client that returns 200
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        ctx = {"http_client": mock_client, "job_try": 1}

        with patch("app.core.database.async_session_factory", factory):
            result = await deliver_webhook(ctx, config_id, {"review_id": 1, "new_state": "COMPLETE"})

        assert result["status"] == "delivered"
        assert result["status_code"] == 200

        # Verify the POST was called with the right args
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["headers"]["Content-Type"] == "application/json"
        assert "X-Webhook-Signature" in call_kwargs.kwargs["headers"]

    @pytest.mark.asyncio
    async def test_deliver_webhook_hmac_signature(self, db_engine):
        """Verify HMAC-SHA256 signature matches expected value."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        secret = "test-secret"
        async with factory() as session:
            config = WebhookConfig(
                url="http://example.com/webhook",
                secret=secret,
                source_system="test",
            )
            session.add(config)
            await session.commit()
            await session.refresh(config)
            config_id = config.id

        # Capture the actual request
        sent_body = None
        sent_headers = None

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def capture_post(url, content, headers, timeout):
            nonlocal sent_body, sent_headers
            sent_body = content
            sent_headers = headers
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = capture_post

        payload = {"review_id": 1}

        ctx = {"http_client": mock_client, "job_try": 1}

        with patch("app.core.database.async_session_factory", factory):
            result = await deliver_webhook(ctx, config_id, payload)

        # Compute expected HMAC
        expected_sig = hmac.new(
            secret.encode(), sent_body.encode(), hashlib.sha256
        ).hexdigest()

        assert sent_headers["X-Webhook-Signature"] == f"sha256={expected_sig}"


class TestDeliverWebhookRetry:
    """Test webhook delivery retry logic."""

    @pytest.mark.asyncio
    async def test_retries_on_failure(self, db_engine):
        """deliver_webhook raises Retry on first failure."""
        from arq import Retry as ArqRetry
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        async with factory() as session:
            config = WebhookConfig(
                url="http://example.com/webhook",
                secret="secret",
                source_system="test",
            )
            session.add(config)
            await session.commit()
            await session.refresh(config)
            config_id = config.id

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

        ctx = {"http_client": mock_client, "job_try": 1}

        with patch("app.core.database.async_session_factory", factory):
            with pytest.raises(ArqRetry) as exc_info:
                await deliver_webhook(ctx, config_id, {"review_id": 1})

        assert exc_info.value.defer_score == 5000  # WEBHOOK_BACKOFF[2] = 5s (next try delay)

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, db_engine):
        """deliver_webhook returns failed status after max retries."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        async with factory() as session:
            config = WebhookConfig(
                url="http://example.com/webhook",
                secret="secret",
                source_system="test",
            )
            session.add(config)
            await session.commit()
            await session.refresh(config)
            config_id = config.id

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

        ctx = {"http_client": mock_client, "job_try": 3}

        with patch("app.core.database.async_session_factory", factory):
            result = await deliver_webhook(ctx, config_id, {"review_id": 1})

        assert result["status"] == "failed"
        assert result["tries"] == 3
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_retry_on_http_error_status(self, db_engine):
        """deliver_webhook retries on 4xx/5xx HTTP responses."""
        from arq import Retry as ArqRetry
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        async with factory() as session:
            config = WebhookConfig(
                url="http://example.com/webhook",
                secret="secret",
                source_system="test",
            )
            session.add(config)
            await session.commit()
            await session.refresh(config)
            config_id = config.id

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        ctx = {"http_client": mock_client, "job_try": 2}

        with patch("app.core.database.async_session_factory", factory):
            with pytest.raises(ArqRetry) as exc_info:
                await deliver_webhook(ctx, config_id, {"review_id": 1})

        assert exc_info.value.defer_score == 30000  # WEBHOOK_BACKOFF[3] = 30s (next try delay)


class TestDeliverWebhookEdgeCases:
    """Test edge cases in webhook delivery."""

    @pytest.mark.asyncio
    async def test_config_not_found(self, db_engine):
        """deliver_webhook returns error for non-existent config ID."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        ctx = {"http_client": AsyncMock(), "job_try": 1}

        with patch("app.core.database.async_session_factory", factory):
            result = await deliver_webhook(ctx, 99999, {"review_id": 1})

        assert result["status"] == "error"
        assert result["reason"] == "config_not_found"

    @pytest.mark.asyncio
    async def test_no_http_client(self, db_engine):
        """deliver_webhook returns error when http_client is missing."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        async with factory() as session:
            config = WebhookConfig(
                url="http://example.com/webhook",
                secret="secret",
                source_system="test",
            )
            session.add(config)
            await session.commit()
            await session.refresh(config)
            config_id = config.id

        ctx = {"job_try": 1}  # No http_client

        with patch("app.core.database.async_session_factory", factory):
            result = await deliver_webhook(ctx, config_id, {"review_id": 1})

        assert result["status"] == "error"
        assert result["reason"] == "no_http_client"
