"""Webhook integration tests for HOOK-01 through HOOK-04.

Tests webhook config CRUD through the HTTP layer (httpx.AsyncClient + ASGI transport)
and webhook delivery behavior (HMAC signatures, retry backoff, max retries, source_system
filtering) by directly testing the deliver_webhook task function with mock httpx clients.
"""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.schema import WebhookConfig
from app.workers.tasks import WEBHOOK_BACKOFF, deliver_webhook


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_webhook_via_http(client, url, secret, source_system, headers):
    """Create a webhook config via HTTP POST and return the response JSON."""
    resp = await client.post(
        "/api/v1/webhooks/",
        json={"url": url, "secret": secret, "source_system": source_system},
        headers=headers,
    )
    return resp


# ---------------------------------------------------------------------------
# Test: Webhook CRUD through HTTP layer
# ---------------------------------------------------------------------------


class TestWebhookCRUDHTTP:
    """Tests webhook config CRUD through the HTTP layer using httpx.AsyncClient."""

    @pytest.mark.asyncio
    async def test_create_webhook_via_http(self, client, auth_headers):
        """POST /api/v1/webhooks/ creates a webhook config and returns 201."""
        resp = await _create_webhook_via_http(
            client,
            url="http://example.com/hook",
            secret="mysecret",
            source_system="kais-movie-agent",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["url"] == "http://example.com/hook"
        assert data["source_system"] == "kais-movie-agent"
        assert data["is_active"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_webhooks_with_source_filter(self, client, auth_headers):
        """GET /api/v1/webhooks/?source_system=X returns only matching configs."""
        # Create two webhooks with different source_system values
        await _create_webhook_via_http(
            client,
            url="http://a.com/hook",
            secret="s1",
            source_system="kais-movie-agent",
            headers=auth_headers,
        )
        await _create_webhook_via_http(
            client,
            url="http://b.com/hook",
            secret="s2",
            source_system="kais-gold-team",
            headers=auth_headers,
        )

        # Filter by source_system
        resp = await client.get(
            "/api/v1/webhooks/?source_system=kais-movie-agent",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        items = resp.json()["data"]
        assert len(items) == 1
        assert items[0]["source_system"] == "kais-movie-agent"

    @pytest.mark.asyncio
    async def test_list_webhooks_all(self, client, auth_headers):
        """GET /api/v1/webhooks/ without filter returns all configs."""
        await _create_webhook_via_http(
            client,
            url="http://a.com/hook",
            secret="s1",
            source_system="kais-movie-agent",
            headers=auth_headers,
        )
        await _create_webhook_via_http(
            client,
            url="http://b.com/hook",
            secret="s2",
            source_system="kais-gold-team",
            headers=auth_headers,
        )

        resp = await client.get("/api/v1/webhooks/", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()["data"]
        assert len(items) >= 2

    @pytest.mark.asyncio
    async def test_delete_webhook_via_http(self, client, auth_headers):
        """DELETE /api/v1/webhooks/{id} removes the config and returns 204."""
        create_resp = await _create_webhook_via_http(
            client,
            url="http://example.com/hook",
            secret="s1",
            source_system="kais-movie-agent",
            headers=auth_headers,
        )
        webhook_id = create_resp.json()["data"]["id"]

        delete_resp = await client.delete(
            f"/api/v1/webhooks/{webhook_id}", headers=auth_headers
        )
        assert delete_resp.status_code == 204

        # Verify it's gone
        get_resp = await client.get(
            f"/api/v1/webhooks/{webhook_id}", headers=auth_headers
        )
        assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Webhook delivery (HOOK-01 through HOOK-03)
# ---------------------------------------------------------------------------


class TestWebhookDelivery:
    """Tests the deliver_webhook task function with mock httpx client.

    Uses the integration test db_engine for real database operations and
    patches async_session_factory to route through the test engine.
    """

    @pytest.mark.asyncio
    async def test_webhook_delivers_with_hmac(self, db_engine):
        """HOOK-01: Webhook delivers with correct HMAC-SHA256 signature header."""
        factory = async_sessionmaker(
            db_engine, expire_on_commit=False, class_=AsyncSession
        )

        # Create a WebhookConfig in the test database
        secret = "test-hmac-secret"
        async with factory() as session:
            config = WebhookConfig(
                url="http://example.com/webhook",
                secret=secret,
                source_system="kais-movie-agent",
            )
            session.add(config)
            await session.commit()
            await session.refresh(config)
            config_id = config.id

        # Capture the actual POST request details
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

        payload = {"review_id": 42, "new_state": "COMPLETE"}
        ctx = {"http_client": mock_client, "job_try": 1}

        with patch("app.core.database.async_session_factory", factory):
            result = await deliver_webhook(ctx, config_id, payload)

        # Verify delivery succeeded
        assert result["status"] == "delivered"
        assert result["status_code"] == 200

        # Verify HMAC-SHA256 signature
        expected_sig = hmac.new(
            secret.encode(), sent_body.encode(), hashlib.sha256
        ).hexdigest()

        assert sent_headers["X-Webhook-Signature"] == f"sha256={expected_sig}"
        assert sent_headers["Content-Type"] == "application/json"

        # Verify body is valid JSON with the payload
        parsed_body = json.loads(sent_body)
        assert parsed_body["review_id"] == 42
        assert parsed_body["new_state"] == "COMPLETE"

    @pytest.mark.asyncio
    async def test_webhook_retries_on_failure(self, db_engine):
        """HOOK-02: Webhook raises Retry with correct backoff on connection failure."""
        from arq import Retry as ArqRetry

        factory = async_sessionmaker(
            db_engine, expire_on_commit=False, class_=AsyncSession
        )

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

        # Test job_try=1 -> Retry with WEBHOOK_BACKOFF[2] = 5s (5000ms)
        ctx = {"http_client": mock_client, "job_try": 1}
        with patch("app.core.database.async_session_factory", factory):
            with pytest.raises(ArqRetry) as exc_info:
                await deliver_webhook(ctx, config_id, {"review_id": 1})

        assert exc_info.value.defer_score == 5000  # WEBHOOK_BACKOFF[2] = 5s in ms

        # Test job_try=2 -> Retry with WEBHOOK_BACKOFF[3] = 30s (30000ms)
        ctx2 = {"http_client": mock_client, "job_try": 2}
        with patch("app.core.database.async_session_factory", factory):
            with pytest.raises(ArqRetry) as exc_info2:
                await deliver_webhook(ctx2, config_id, {"review_id": 1})

        assert exc_info2.value.defer_score == 30000  # WEBHOOK_BACKOFF[3] = 30s in ms

    @pytest.mark.asyncio
    async def test_webhook_fails_after_max_retries(self, db_engine):
        """HOOK-03: Webhook returns failed status after max retries (job_try=3)."""
        factory = async_sessionmaker(
            db_engine, expire_on_commit=False, class_=AsyncSession
        )

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


# ---------------------------------------------------------------------------
# Test: Source system filtering (HOOK-04)
# ---------------------------------------------------------------------------


class TestWebhookSourceSystemFilter:
    """Tests that webhook configs can be filtered by source_system at both
    the API query level and the active-config query level."""

    @pytest.mark.asyncio
    async def test_webhook_source_system_filter_api(self, client, auth_headers):
        """HOOK-04: API-level source_system filter returns only matching webhooks."""
        # Create two webhooks with different source_systems
        await _create_webhook_via_http(
            client,
            url="http://a.com/hook",
            secret="s1",
            source_system="kais-movie-agent",
            headers=auth_headers,
        )
        await _create_webhook_via_http(
            client,
            url="http://b.com/hook",
            secret="s2",
            source_system="kais-gold-team",
            headers=auth_headers,
        )

        # Filter by kais-gold-team -> only 1 result
        resp = await client.get(
            "/api/v1/webhooks/?source_system=kais-gold-team",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        items = resp.json()["data"]
        assert len(items) == 1
        assert items[0]["source_system"] == "kais-gold-team"
        assert items[0]["url"] == "http://b.com/hook"

        # Filter by nonexistent source_system -> empty
        resp2 = await client.get(
            "/api/v1/webhooks/?source_system=nonexistent-system",
            headers=auth_headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["data"] == []

    @pytest.mark.asyncio
    async def test_webhook_active_config_excludes_inactive(self, db_engine):
        """HOOK-04: Active config query excludes inactive webhooks."""
        factory = async_sessionmaker(
            db_engine, expire_on_commit=False, class_=AsyncSession
        )

        # Create two active, one inactive config
        async with factory() as session:
            configs = [
                WebhookConfig(
                    url="http://a.com/hook",
                    secret="s1",
                    source_system="kais-movie-agent",
                    is_active=True,
                ),
                WebhookConfig(
                    url="http://b.com/hook",
                    secret="s2",
                    source_system="kais-gold-team",
                    is_active=True,
                ),
                WebhookConfig(
                    url="http://c.com/hook",
                    secret="s3",
                    source_system="kais-movie-agent",
                    is_active=False,
                ),
            ]
            session.add_all(configs)
            await session.commit()

        # Query active configs (same query emit_state_change uses)
        async with factory() as session:
            result = await session.execute(
                select(WebhookConfig).where(WebhookConfig.is_active == True)
            )
            active = result.scalars().all()

        assert len(active) == 2
        assert all(c.is_active for c in active)
        sources = {c.source_system for c in active}
        assert sources == {"kais-movie-agent", "kais-gold-team"}
