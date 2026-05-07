"""Tests for callback delivery: deliver_review_callback arq task.

Tests HMAC-SHA256 signed callback delivery, exponential backoff retry,
Telegram admin notification on final failure, and edge cases.
"""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.models.schema import Review
from app.workers.tasks import deliver_review_callback, CALLBACK_BACKOFF


class TestCallbackDeliverySuccess:
    """Test successful callback delivery with HMAC signing."""

    @pytest.mark.asyncio
    async def test_deliver_callback_with_url_and_secret(self, db_engine):
        """deliver_review_callback delivers HMAC-signed POST when review has callback_url and callback_secret."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        # Create a Review with callback_url and callback_secret
        async with factory() as session:
            review = Review(
                type="video_render",
                content_ref="s3://bucket/output.mp4",
                source_system="kais-gold-team",
                state="COMPLETE",
                disposition="approved",
                callback_url="http://192.168.71.38:8080/callback",
                callback_secret="my-callback-secret",
            )
            session.add(review)
            await session.commit()
            await session.refresh(review)
            review_id = review.id

        # Mock httpx client that returns 200
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        event_data = {
            "review_id": review_id,
            "old_state": "APPROVING",
            "new_state": "COMPLETE",
            "timestamp": "2026-05-07T12:00:00Z",
            "source_system": "kais-gold-team",
        }
        ctx = {"http_client": mock_client, "job_try": 1}

        with patch("app.core.database.async_session_factory", factory):
            result = await deliver_review_callback(ctx, review_id, event_data)

        assert result["status"] == "delivered"
        assert result["status_code"] == 200

        # Verify the POST was called
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["headers"]["Content-Type"] == "application/json"
        assert "X-Callback-Signature" in call_kwargs.kwargs["headers"]
        assert call_kwargs.kwargs["headers"]["X-Callback-Signature"].startswith("sha256=")

    @pytest.mark.asyncio
    async def test_callback_hmac_signature_matches(self, db_engine):
        """HMAC signature matches hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        secret = "test-callback-secret"
        async with factory() as session:
            review = Review(
                type="scene_render",
                content_ref="s3://bucket/scene.png",
                source_system="kais-movie-agent",
                state="COMPLETE",
                disposition="approved",
                callback_url="http://192.168.71.38:9090/hook",
                callback_secret=secret,
            )
            session.add(review)
            await session.commit()
            await session.refresh(review)
            review_id = review.id

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

        event_data = {"review_id": review_id, "new_state": "COMPLETE"}
        ctx = {"http_client": mock_client, "job_try": 1}

        with patch("app.core.database.async_session_factory", factory):
            result = await deliver_review_callback(ctx, review_id, event_data)

        # Compute expected HMAC
        expected_sig = hmac.new(
            secret.encode(), sent_body.encode(), hashlib.sha256
        ).hexdigest()

        assert sent_headers["X-Callback-Signature"] == f"sha256={expected_sig}"

    @pytest.mark.asyncio
    async def test_callback_uses_x_callback_signature_header(self, db_engine):
        """Callback uses X-Callback-Signature header (not X-Webhook-Signature)."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        async with factory() as session:
            review = Review(
                type="video_render",
                content_ref="s3://bucket/out.mp4",
                source_system="kais-gold-team",
                state="COMPLETE",
                callback_url="http://example.com/cb",
                callback_secret="secret",
            )
            session.add(review)
            await session.commit()
            await session.refresh(review)
            review_id = review.id

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        ctx = {"http_client": mock_client, "job_try": 1}

        with patch("app.core.database.async_session_factory", factory):
            result = await deliver_review_callback(ctx, review_id, {"review_id": review_id})

        call_kwargs = mock_client.post.call_args
        assert "X-Callback-Signature" in call_kwargs.kwargs["headers"]
        assert "X-Webhook-Signature" not in call_kwargs.kwargs["headers"]

    @pytest.mark.asyncio
    async def test_callback_payload_includes_required_fields(self, db_engine):
        """Callback payload includes review_id, new_state, disposition, timestamp, source_system."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        async with factory() as session:
            review = Review(
                type="video_render",
                content_ref="s3://bucket/out.mp4",
                source_system="kais-gold-team",
                state="COMPLETE",
                disposition="approved",
                callback_url="http://example.com/cb",
                callback_secret="secret",
            )
            session.add(review)
            await session.commit()
            await session.refresh(review)
            review_id = review.id

        sent_body = None

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def capture_post(url, content, headers, timeout):
            nonlocal sent_body
            sent_body = content
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = capture_post

        event_data = {
            "review_id": review_id,
            "old_state": "APPROVING",
            "new_state": "COMPLETE",
            "timestamp": "2026-05-07T12:00:00Z",
            "source_system": "kais-gold-team",
        }
        ctx = {"http_client": mock_client, "job_try": 1}

        with patch("app.core.database.async_session_factory", factory):
            result = await deliver_review_callback(ctx, review_id, event_data)

        payload = json.loads(sent_body)
        assert payload["review_id"] == review_id
        assert payload["new_state"] == "COMPLETE"
        assert payload["disposition"] == "approved"
        assert "timestamp" in payload
        assert payload["source_system"] == "kais-gold-team"


class TestCallbackDeliveryRetry:
    """Test callback delivery retry logic with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retries_on_first_failure(self, db_engine):
        """deliver_review_callback raises Retry on first HTTP failure (job_try=1)."""
        from arq import Retry as ArqRetry
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        async with factory() as session:
            review = Review(
                type="video_render",
                content_ref="s3://bucket/out.mp4",
                source_system="kais-gold-team",
                state="COMPLETE",
                callback_url="http://example.com/cb",
                callback_secret="secret",
            )
            session.add(review)
            await session.commit()
            await session.refresh(review)
            review_id = review.id

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

        ctx = {"http_client": mock_client, "job_try": 1}

        with patch("app.core.database.async_session_factory", factory):
            with pytest.raises(ArqRetry) as exc_info:
                await deliver_review_callback(ctx, review_id, {"review_id": review_id})

        assert exc_info.value.defer_score == 5000  # CALLBACK_BACKOFF[2] = 5s

    @pytest.mark.asyncio
    async def test_retries_with_defer_on_job_try_2(self, db_engine):
        """deliver_review_callback raises Retry with defer=30000 on job_try=2 failure."""
        from arq import Retry as ArqRetry
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        async with factory() as session:
            review = Review(
                type="video_render",
                content_ref="s3://bucket/out.mp4",
                source_system="kais-gold-team",
                state="COMPLETE",
                callback_url="http://example.com/cb",
                callback_secret="secret",
            )
            session.add(review)
            await session.commit()
            await session.refresh(review)
            review_id = review.id

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Timeout"))

        ctx = {"http_client": mock_client, "job_try": 2}

        with patch("app.core.database.async_session_factory", factory):
            with pytest.raises(ArqRetry) as exc_info:
                await deliver_review_callback(ctx, review_id, {"review_id": review_id})

        assert exc_info.value.defer_score == 30000  # CALLBACK_BACKOFF[3] = 30s

    @pytest.mark.asyncio
    async def test_returns_failed_on_max_retries(self, db_engine):
        """deliver_review_callback returns {"status": "failed"} on job_try=3 (max retries)."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        async with factory() as session:
            review = Review(
                type="video_render",
                content_ref="s3://bucket/out.mp4",
                source_system="kais-gold-team",
                state="COMPLETE",
                callback_url="http://example.com/cb",
                callback_secret="secret",
            )
            session.add(review)
            await session.commit()
            await session.refresh(review)
            review_id = review.id

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

        ctx = {"http_client": mock_client, "job_try": 3}

        with patch("app.core.database.async_session_factory", factory):
            result = await deliver_review_callback(ctx, review_id, {"review_id": review_id})

        assert result["status"] == "failed"
        assert result["tries"] == 3
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_logs_callback_delivery_exhausted_after_all_retries(self, db_engine):
        """deliver_review_callback logs 'callback_delivery_exhausted' after all retries fail."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        async with factory() as session:
            review = Review(
                type="video_render",
                content_ref="s3://bucket/out.mp4",
                source_system="kais-gold-team",
                state="COMPLETE",
                callback_url="http://example.com/cb",
                callback_secret="secret",
            )
            session.add(review)
            await session.commit()
            await session.refresh(review)
            review_id = review.id

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

        mock_logger = MagicMock()

        ctx = {"http_client": mock_client, "job_try": 3}

        with patch("app.core.database.async_session_factory", factory):
            with patch("app.workers.tasks.structlog") as mock_structlog:
                mock_structlog.get_logger.return_value = mock_logger
                result = await deliver_review_callback(ctx, review_id, {"review_id": review_id})

                # Verify callback_delivery_exhausted was logged
                error_calls = [call for call in mock_logger.error.call_args_list]
                exhausted_calls = [
                    c for c in error_calls
                    if c[0][0] == "callback_delivery_exhausted" if c[0]
                ]
                assert len(exhausted_calls) >= 1

    @pytest.mark.asyncio
    async def test_calls_telegram_admin_notification_on_final_failure(self, db_engine):
        """On final failure, _notify_telegram_admin logs telegram_admin_notification_pending."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        async with factory() as session:
            review = Review(
                type="video_render",
                content_ref="s3://bucket/out.mp4",
                source_system="kais-gold-team",
                state="COMPLETE",
                callback_url="http://example.com/cb",
                callback_secret="secret",
            )
            session.add(review)
            await session.commit()
            await session.refresh(review)
            review_id = review.id

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

        mock_logger = MagicMock()

        ctx = {"http_client": mock_client, "job_try": 3}

        with patch("app.core.database.async_session_factory", factory):
            with patch("app.workers.tasks.structlog") as mock_structlog:
                mock_structlog.get_logger.return_value = mock_logger
                result = await deliver_review_callback(ctx, review_id, {"review_id": review_id})

                # Verify telegram_admin_notification_pending was logged
                warning_calls = [call for call in mock_logger.warning.call_args_list]
                telegram_calls = [
                    c for c in warning_calls
                    if len(c[0]) > 0 and c[0][0] == "telegram_admin_notification_pending"
                ]
                assert len(telegram_calls) >= 1


class TestCallbackDeliveryEdgeCases:
    """Test edge cases: no callback_url (skipped), review not found."""

    @pytest.mark.asyncio
    async def test_skips_when_no_callback_url(self, db_engine):
        """deliver_review_callback skips delivery silently when review has no callback_url."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        async with factory() as session:
            review = Review(
                type="video_render",
                content_ref="s3://bucket/out.mp4",
                source_system="kais-gold-team",
                state="COMPLETE",
                # No callback_url or callback_secret
            )
            session.add(review)
            await session.commit()
            await session.refresh(review)
            review_id = review.id

        mock_client = AsyncMock()

        ctx = {"http_client": mock_client, "job_try": 1}

        with patch("app.core.database.async_session_factory", factory):
            result = await deliver_review_callback(ctx, review_id, {"review_id": review_id})

        assert result["status"] == "skipped"
        assert result["reason"] == "no_callback_url"
        # Verify no HTTP POST was made
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_error_for_nonexistent_review(self, db_engine):
        """deliver_review_callback returns error for non-existent review ID."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

        mock_client = AsyncMock()

        ctx = {"http_client": mock_client, "job_try": 1}

        with patch("app.core.database.async_session_factory", factory):
            result = await deliver_review_callback(ctx, 99999, {"review_id": 99999})

        assert result["status"] == "error"
        assert result["reason"] == "review_not_found"
