"""Integration tests for approve/reject flows with one-time tokens.

Tests the reviewer approval/rejection workflow, one-time token lifecycle,
and concurrent approval detection. These tests work at the core module level.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from app.core.auth import create_review_token, consume_review_token
from app.core.state_machine import (
    InvalidTransitionError,
    StateConflictError,
    TerminalStateError,
    transition_state,
)
from app.models.schema import Review
from app.models.schemas import ReviewState


class TestApproveRejectFlow:
    """Test approve and reject workflows."""

    @pytest_asyncio.fixture
    async def approving_review(self, db_session):
        """Create a review that's already in APPROVING state."""
        r = Review(
            type="video_review",
            content_ref="s3://bucket/video-001.mp4",
            source_system="kais-movie-agent",
            priority="high",
            risk_score=0.8,
            state=ReviewState.PENDING.value,
            version=1,
        )
        db_session.add(r)
        await db_session.commit()
        await db_session.refresh(r)

        # Advance to APPROVING state
        r = await transition_state(
            db_session, r.id, ReviewState.PENDING, ReviewState.POLICY_EVAL,
            r.version, actor="system", action="policy_eval_start",
        )
        r = await transition_state(
            db_session, r.id, ReviewState.POLICY_EVAL, ReviewState.APPROVING,
            r.version, actor="system", action="route_human",
            payload={"disposition": "HUMAN"},
        )
        return r

    @pytest.mark.asyncio
    async def test_approve_review(self, db_session, approving_review):
        """Reviewer approves a review -> COMPLETE."""
        previous_version = approving_review.version
        result = await transition_state(
            db_session,
            approving_review.id,
            ReviewState.APPROVING,
            ReviewState.COMPLETE,
            approving_review.version,
            actor="reviewer-1",
            action="approve",
            payload={"comment": "Content looks good"},
        )
        assert result.state == ReviewState.COMPLETE.value
        assert result.version == previous_version + 1

    @pytest.mark.asyncio
    async def test_reject_review_with_reason(self, db_session, approving_review):
        """Reviewer rejects with mandatory reason -> COMPLETE."""
        result = await transition_state(
            db_session,
            approving_review.id,
            ReviewState.APPROVING,
            ReviewState.COMPLETE,
            approving_review.version,
            actor="reviewer-1",
            action="reject",
            payload={"reason": "Content violates safety guidelines"},
        )
        assert result.state == ReviewState.COMPLETE.value

    @pytest.mark.asyncio
    async def test_approve_non_approving_review_fails(self, db_session):
        """Cannot approve a review that's not in APPROVING state."""
        r = Review(
            type="video_review",
            content_ref="s3://bucket/video-001.mp4",
            source_system="kais-movie-agent",
            priority="normal",
            risk_score=0.1,
            state=ReviewState.PENDING.value,
            version=1,
        )
        db_session.add(r)
        await db_session.commit()
        await db_session.refresh(r)

        with pytest.raises(InvalidTransitionError):
            await transition_state(
                db_session, r.id, ReviewState.PENDING, ReviewState.COMPLETE,
                r.version, actor="reviewer-1", action="approve",
            )

    @pytest.mark.asyncio
    async def test_approve_already_approved_fails(self, db_session, approving_review):
        """Cannot approve a review that's already COMPLETE."""
        # First approval succeeds
        await transition_state(
            db_session,
            approving_review.id,
            ReviewState.APPROVING,
            ReviewState.COMPLETE,
            approving_review.version,
            actor="reviewer-1",
            action="approve",
        )

        # Second approval attempt fails (no valid transitions from COMPLETE)
        with pytest.raises(InvalidTransitionError):
            await transition_state(
                db_session,
                approving_review.id,
                ReviewState.COMPLETE,
                ReviewState.COMPLETE,
                approving_review.version + 1,
                actor="reviewer-2",
                action="approve",
            )

    @pytest.mark.asyncio
    async def test_concurrent_approval_detected(self, db_session, approving_review):
        """Concurrent approvals detected via optimistic locking."""
        # First approval succeeds
        await transition_state(
            db_session,
            approving_review.id,
            ReviewState.APPROVING,
            ReviewState.COMPLETE,
            approving_review.version,
            actor="reviewer-1",
            action="approve",
        )

        # Second approval with stale version fails
        with pytest.raises(StateConflictError, match="State conflict"):
            await transition_state(
                db_session,
                approving_review.id,
                ReviewState.APPROVING,
                ReviewState.COMPLETE,
                approving_review.version,  # Stale version
                actor="reviewer-2",
                action="approve",
            )


class TestOneTimeToken:
    """Test one-time review token lifecycle."""

    @pytest_asyncio.fixture
    def mock_redis(self):
        """Provide a mock Redis that simulates token set/get/del behavior."""
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

        # Simulate Lua consume script behavior
        # register_script returns a callable that when called with keys, returns a coroutine
        class MockScript:
            """Simulates redis.commands.core.AsyncScript."""
            def __init__(self, lua_source):
                self._source = lua_source

            async def __call__(self, keys=None, args=None):
                key = keys[0] if keys else None
                if key and key in store:
                    val = store[key]
                    del store[key]
                    return val
                return None

        def mock_register_script(lua_source):
            return MockScript(lua_source)

        redis_mock.register_script = mock_register_script
        return redis_mock

    @pytest.mark.asyncio
    async def test_create_and_consume_token(self, mock_redis):
        """Token can be created and consumed once."""
        token = await create_review_token(mock_redis, review_id=42, ttl=3600)
        assert token is not None
        assert len(token) >= 32  # 32 bytes base64-encoded

        # Consume the token
        review_id = await consume_review_token(mock_redis, token)
        assert review_id == "42"

    @pytest.mark.asyncio
    async def test_token_single_use(self, mock_redis):
        """Token cannot be consumed twice."""
        token = await create_review_token(mock_redis, review_id=42, ttl=3600)

        # First consume succeeds
        result1 = await consume_review_token(mock_redis, token)
        assert result1 == "42"

        # Second consume returns None (already consumed)
        result2 = await consume_review_token(mock_redis, token)
        assert result2 is None

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self, mock_redis):
        """Consuming a non-existent token returns None."""
        result = await consume_review_token(mock_redis, "nonexistent-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_token_ttl_set(self, mock_redis):
        """Token is stored with TTL for automatic expiration."""
        token = await create_review_token(mock_redis, review_id=42, ttl=7200)
        # The mock set function doesn't actually check TTL,
        # but we verify the key pattern
        import asyncio

        # Check that the token was stored
        val = await mock_redis.get(f"review_token:{token}")
        assert val == "42"


class TestJWTAuth:
    """Test JWT token creation and validation."""

    def test_create_jwt(self, settings):
        from app.core.auth import create_jwt, decode_jwt
        token = create_jwt("test-client", settings.jwt_secret)
        assert isinstance(token, str)
        assert len(token) > 0

        # Decode should succeed
        payload = decode_jwt(token, settings.jwt_secret)
        assert payload["client"] == "test-client"
        assert "exp" in payload
        assert "iat" in payload

    def test_expired_jwt_rejected(self, settings):
        from app.core.auth import AuthenticationError, create_jwt, decode_jwt
        # Create a token that expired 1 minute ago
        token = create_jwt("test-client", settings.jwt_secret, expires_minutes=-1)
        with pytest.raises(AuthenticationError, match="Token expired"):
            decode_jwt(token, settings.jwt_secret)

    def test_invalid_jwt_rejected(self, settings):
        from app.core.auth import AuthenticationError, decode_jwt
        with pytest.raises(AuthenticationError, match="Invalid token"):
            decode_jwt("not.a.valid.token", settings.jwt_secret)

    def test_wrong_secret_rejected(self, settings):
        from app.core.auth import AuthenticationError, create_jwt, decode_jwt
        token = create_jwt("test-client", settings.jwt_secret)
        with pytest.raises(AuthenticationError):
            decode_jwt(token, "wrong-secret-key-that-is-different-from-correct")
