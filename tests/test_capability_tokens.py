"""Tests for capability token issuance and verification (Phase 19 Plan 02).

TDD RED phase: Tests for issue_capability_token, verify_capability_token,
and POST /api/v1/tokens/verify endpoint.
"""

import os
import time

import jwt
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from httpx import ASGITransport, AsyncClient

# Must set env before app imports
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-min-32-chars-long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CAPABILITY_TOKEN_SECRET", "test-capability-secret-min-32-chars-long!!")

from app.core.auth import issue_capability_token, verify_capability_token


def _make_mock_redis():
    """Create a mock Redis with dict-backed store for token tests."""
    store = {}
    redis_mock = AsyncMock()

    async def mock_set(key, value, ex=None):
        store[key] = value

    async def mock_get(key):
        return store.get(key)

    async def mock_delete(key):
        store.pop(key, None)

    redis_mock.set = mock_set
    redis_mock.get = mock_get
    redis_mock.delete = mock_delete
    return redis_mock, store


@pytest_asyncio.fixture
def mock_redis():
    """Provide a mock Redis for capability token tests."""
    redis_mock, _store = _make_mock_redis()
    return redis_mock


CAPABILITY_SECRET = "test-capability-secret-min-32-chars-long!!"


# ---------------------------------------------------------------------------
# Unit tests: issue_capability_token
# ---------------------------------------------------------------------------


class TestIssueCapabilityToken:
    """Tests for issue_capability_token function."""

    @pytest.mark.asyncio
    async def test_returns_jwt_string(self, mock_redis):
        token = await issue_capability_token(
            redis=mock_redis,
            shot_id="s1",
            node_scope=["node_a", "node_b"],
            secret=CAPABILITY_SECRET,
            ttl=3600,
        )
        assert isinstance(token, str)
        assert len(token) > 20  # JWTs are always long strings

    @pytest.mark.asyncio
    async def test_jwt_payload_contains_required_claims(self, mock_redis):
        token = await issue_capability_token(
            redis=mock_redis,
            shot_id="s1",
            node_scope=["node_a", "node_b"],
            secret=CAPABILITY_SECRET,
            ttl=3600,
        )
        payload = jwt.decode(token, CAPABILITY_SECRET, algorithms=["HS256"])
        assert payload["shot_id"] == "s1"
        assert payload["node_scope"] == ["node_a", "node_b"]
        assert "iat" in payload
        assert "exp" in payload

    @pytest.mark.asyncio
    async def test_stores_in_redis_with_ttl(self, mock_redis):
        token = await issue_capability_token(
            redis=mock_redis,
            shot_id="s1",
            node_scope=["node_a"],
            secret=CAPABILITY_SECRET,
            ttl=3600,
        )
        stored = await mock_redis.get(f"cap_token:{token}")
        assert stored is not None
        assert stored == "s1"

    @pytest.mark.asyncio
    async def test_expiration_set_correctly(self, mock_redis):
        token = await issue_capability_token(
            redis=mock_redis,
            shot_id="s1",
            node_scope=["node_a"],
            secret=CAPABILITY_SECRET,
            ttl=3600,
        )
        payload = jwt.decode(token, CAPABILITY_SECRET, algorithms=["HS256"])
        # exp should be roughly now + 3600
        assert abs(payload["exp"] - (time.time() + 3600)) < 5


# ---------------------------------------------------------------------------
# Unit tests: verify_capability_token
# ---------------------------------------------------------------------------


class TestVerifyCapabilityToken:
    """Tests for verify_capability_token function."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_valid(self, mock_redis):
        token = await issue_capability_token(
            redis=mock_redis,
            shot_id="s1",
            node_scope=["node_a", "node_b"],
            secret=CAPABILITY_SECRET,
            ttl=3600,
        )
        result = await verify_capability_token(
            redis=mock_redis,
            token=token,
            secret=CAPABILITY_SECRET,
        )
        assert result["valid"] is True
        assert result["shot_id"] == "s1"
        assert result["node_scope"] == ["node_a", "node_b"]
        assert "expires_at" in result

    @pytest.mark.asyncio
    async def test_valid_token_is_consumed_single_use(self, mock_redis):
        token = await issue_capability_token(
            redis=mock_redis,
            shot_id="s1",
            node_scope=["node_a"],
            secret=CAPABILITY_SECRET,
            ttl=3600,
        )
        # First verification succeeds
        result1 = await verify_capability_token(
            redis=mock_redis, token=token, secret=CAPABILITY_SECRET
        )
        assert result1["valid"] is True

        # Second verification fails (consumed)
        result2 = await verify_capability_token(
            redis=mock_redis, token=token, secret=CAPABILITY_SECRET
        )
        assert result2["valid"] is False
        assert result2["reason"] == "token_revoked_or_consumed"

    @pytest.mark.asyncio
    async def test_expired_token_returns_token_expired(self, mock_redis):
        # Issue token with very short TTL (1 second)
        token = await issue_capability_token(
            redis=mock_redis,
            shot_id="s1",
            node_scope=["node_a"],
            secret=CAPABILITY_SECRET,
            ttl=1,
        )
        # Wait for token to expire
        time.sleep(2)
        result = await verify_capability_token(
            redis=mock_redis, token=token, secret=CAPABILITY_SECRET
        )
        assert result["valid"] is False
        assert result["reason"] == "token_expired"

    @pytest.mark.asyncio
    async def test_invalid_token_string_returns_invalid(self, mock_redis):
        result = await verify_capability_token(
            redis=mock_redis,
            token="this-is-not-a-jwt",
            secret=CAPABILITY_SECRET,
        )
        assert result["valid"] is False
        assert result["reason"] == "invalid_token"

    @pytest.mark.asyncio
    async def test_tampered_token_returns_invalid(self, mock_redis):
        token = await issue_capability_token(
            redis=mock_redis,
            shot_id="s1",
            node_scope=["node_a"],
            secret=CAPABILITY_SECRET,
            ttl=3600,
        )
        # Tamper with the token by changing last char
        tampered = token[:-2] + ("XX" if token[-2:] != "XX" else "YY")
        result = await verify_capability_token(
            redis=mock_redis, token=tampered, secret=CAPABILITY_SECRET
        )
        assert result["valid"] is False
        assert result["reason"] == "invalid_token"


# ---------------------------------------------------------------------------
# Integration tests: POST /api/v1/tokens/verify
# ---------------------------------------------------------------------------


class TestTokenVerifyEndpoint:
    """Tests for the POST /api/v1/tokens/verify endpoint.

    Uses a standalone FastAPI app with just the tokens router to avoid
    importing app.main which has a pre-existing broken import chain
    in actions.py (unrelated to capability tokens).
    """

    @pytest_asyncio.fixture
    async def client(self, mock_redis):
        """Create test client with mock Redis injected on a standalone app."""
        from fastapi import FastAPI
        from app.api.v1.tokens import router as tokens_router
        from app.core.config import Settings, get_settings

        test_settings = Settings(
            api_key="test-api-key",
            jwt_secret="test-jwt-secret-for-testing-min-32-chars-long",
            capability_token_secret=CAPABILITY_SECRET,
        )

        app = FastAPI()
        app.include_router(tokens_router)
        app.state.redis = mock_redis
        app.dependency_overrides[get_settings] = lambda: test_settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_verify_valid_token(self, client, mock_redis):
        token = await issue_capability_token(
            redis=mock_redis,
            shot_id="shot-123",
            node_scope=["render", "composite"],
            secret=CAPABILITY_SECRET,
            ttl=3600,
        )
        resp = await client.post(
            "/api/v1/tokens/verify",
            json={"token": token},
        )
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert data["valid"] is True
        assert data["shot_id"] == "shot-123"
        assert data["node_scope"] == ["render", "composite"]
        assert data["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_verify_expired_token(self, client, mock_redis):
        token = await issue_capability_token(
            redis=mock_redis,
            shot_id="shot-exp",
            node_scope=["render"],
            secret=CAPABILITY_SECRET,
            ttl=1,
        )
        time.sleep(2)
        resp = await client.post(
            "/api/v1/tokens/verify",
            json={"token": token},
        )
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert data["valid"] is False
        assert data["reason"] == "token_expired"

    @pytest.mark.asyncio
    async def test_verify_invalid_token(self, client):
        resp = await client.post(
            "/api/v1/tokens/verify",
            json={"token": "garbage-string"},
        )
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert data["valid"] is False
        assert data["reason"] == "invalid_token"

    @pytest.mark.asyncio
    async def test_verify_consumed_token(self, client, mock_redis):
        token = await issue_capability_token(
            redis=mock_redis,
            shot_id="shot-consume",
            node_scope=["render"],
            secret=CAPABILITY_SECRET,
            ttl=3600,
        )
        # First verification
        resp1 = await client.post(
            "/api/v1/tokens/verify",
            json={"token": token},
        )
        assert resp1.json()["data"]["valid"] is True

        # Second verification (consumed)
        resp2 = await client.post(
            "/api/v1/tokens/verify",
            json={"token": token},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()["data"]
        assert data2["valid"] is False
        assert data2["reason"] == "token_revoked_or_consumed"
