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


# ---------------------------------------------------------------------------
# Phase 54-02 R1: decision persistence + waive endpoint (HTTP-level, RED first)
# GATE-03 protocol-gap closure leg 1: every decision lands in
# metadata.review_result where the kmc poller (R2/R3) can read it.
# ---------------------------------------------------------------------------


class TestDecisionPersistenceAndWaive:
    """R1 contract: decision on the record + waive endpoint."""

    @pytest_asyncio.fixture
    async def client_with_db(self, db_session):
        """HTTP client with db/redis overridden onto the shared session.

        redis stub: _resolve_actor only touches redis for one-time tokens
        (query param) — these tests exercise the JWT-less default client
        path, so a no-op async stub suffices for the get_redis override.
        """
        from httpx import ASGITransport, AsyncClient
        from app.core.config import Settings

        # 本地 .env 携带非 Settings 字段(compose 用键)会触发 extra_forbidden
        # ——既有 HTTP 级测试在本地同坏;此处禁读 env_file,字段值全部来自
        # conftest 的 os.environ 注入(docker 测试环境不受影响)。
        Settings.model_config["env_file"] = None
        from app.main import app  # noqa: E402 (import after config patch)
        from app.core.database import get_db
        from app.core.dependencies import get_redis

        class _RedisStub:
            async def get(self, *a, **k):
                return None

            async def set(self, *a, **k):
                return None

            async def delete(self, *a, **k):
                return None

        async def override_get_db():
            yield db_session

        async def override_get_redis():
            return _RedisStub()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_redis] = override_get_redis
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, db_session
        app.dependency_overrides.clear()

    @pytest_asyncio.fixture
    async def approving_http(self, db_session):
        """Review advanced to APPROVING for HTTP tests."""
        r = Review(
            type="video_review",
            content_ref="ep-54/p13_delivery",
            source_system="kais-movie-agent",
            priority="normal",
            risk_score=0.5,
            state=ReviewState.PENDING.value,
            version=1,
        )
        db_session.add(r)
        await db_session.commit()
        await db_session.refresh(r)
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
    async def test_approve_without_result_still_writes_decision(
        self, client_with_db, approving_http
    ):
        """R1: approve 恒写 review_result.decision(不带 result 也写)。"""
        client, _ = client_with_db
        resp = await client.post(
            f"/api/v1/reviews/{approving_http.id}/approve", json={}
        )
        assert resp.status_code == 200, resp.text
        got = await client.get(f"/api/v1/reviews/{approving_http.id}")
        meta = got.json()["data"]["metadata"]
        assert meta["review_result"]["decision"] == "approve"

    @pytest.mark.asyncio
    async def test_approve_with_result_merges_decision(
        self, client_with_db, approving_http
    ):
        """R1: decision 与 result.selected 合并不丢。"""
        client, _ = client_with_db
        resp = await client.post(
            f"/api/v1/reviews/{approving_http.id}/approve",
            json={"result": {"selected": [1]}},
        )
        assert resp.status_code == 200, resp.text
        got = await client.get(f"/api/v1/reviews/{approving_http.id}")
        rr = got.json()["data"]["metadata"]["review_result"]
        assert rr["decision"] == "approve"
        assert rr["selected"] == [1]

    @pytest.mark.asyncio
    async def test_reject_writes_decision_and_reason(
        self, client_with_db, approving_http
    ):
        """R1: reject 补写 review_result = {decision, reason}。"""
        client, _ = client_with_db
        resp = await client.post(
            f"/api/v1/reviews/{approving_http.id}/reject",
            json={"reason": "构图连续性断裂"},
        )
        assert resp.status_code == 200, resp.text
        got = await client.get(f"/api/v1/reviews/{approving_http.id}")
        rr = got.json()["data"]["metadata"]["review_result"]
        assert rr == {"decision": "reject", "reason": "构图连续性断裂"}

    @pytest.mark.asyncio
    async def test_waive_endpoint_round_trip(
        self, client_with_db, approving_http
    ):
        """R1: POST /{id}/waive → COMPLETE + decision=waive + reason 回读。"""
        client, _ = client_with_db
        resp = await client.post(
            f"/api/v1/reviews/{approving_http.id}/waive",
            json={"reason": "phase54 waive contract"},
        )
        assert resp.status_code == 200, resp.text
        got = await client.get(f"/api/v1/reviews/{approving_http.id}")
        data = got.json()["data"]
        assert data["state"] == "COMPLETE"
        rr = data["metadata"]["review_result"]
        assert rr["decision"] == "waive"
        assert rr["reason"] == "phase54 waive contract"

    @pytest.mark.asyncio
    async def test_waive_empty_reason_422(self, client_with_db, approving_http):
        """waive 空 reason → 422(reason 必填 1..500)。"""
        client, _ = client_with_db
        resp = await client.post(
            f"/api/v1/reviews/{approving_http.id}/waive", json={"reason": ""}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_waive_on_complete_409(self, client_with_db, approving_http):
        """waive 于非 APPROVING(已 COMPLETE)→ 409。"""
        client, _ = client_with_db
        first = await client.post(
            f"/api/v1/reviews/{approving_http.id}/waive",
            json={"reason": "first"},
        )
        assert first.status_code == 200
        second = await client.post(
            f"/api/v1/reviews/{approving_http.id}/waive",
            json={"reason": "again"},
        )
        assert second.status_code == 409

    @pytest.mark.asyncio
    async def test_waive_audit_entry(self, client_with_db, approving_http, db_session):
        """audit timeline 出现 action == 'waive' 条目。"""
        from sqlalchemy import select
        from app.models.schema import AuditEntry

        client, _ = client_with_db
        resp = await client.post(
            f"/api/v1/reviews/{approving_http.id}/waive",
            json={"reason": "audit check"},
        )
        assert resp.status_code == 200
        rows = (
            await db_session.execute(
                select(AuditEntry).where(AuditEntry.review_id == approving_http.id)
            )
        ).scalars().all()
        actions = [a.action for a in rows]
        assert "waive" in actions
