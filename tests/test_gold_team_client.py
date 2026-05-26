"""Unit tests for gold-team ReviewPlatformClient.

Tests cover:
- submit_gpu_review with high-risk and low-risk task types
- Risk score auto-calculation from task type
- query_review_status
- Error handling (connection errors, HTTP errors, timeout)
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.integrations.gold_team.client import (
    HIGH_RISK_TYPES,
    LOW_RISK_TYPES,
    ReviewClientError,
    ReviewPlatformClient,
    ReviewQueryResult,
    ReviewSubmitResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_response_factory():
    """Factory to create mock httpx Response objects."""

    def _make(
        status_code: int = 200,
        json_data: dict | None = None,
    ):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.text = str(json_data) if json_data else ""
        return resp

    return _make


@pytest_asyncio.fixture
async def client():
    """Provide a ReviewPlatformClient with mocked httpx client."""
    c = ReviewPlatformClient(
        base_url="http://localhost:8090",
        api_key="test-api-key",
        timeout=5.0,
    )
    yield c
    await c.close()


# ---------------------------------------------------------------------------
# Test: Risk score mapping
# ---------------------------------------------------------------------------


class TestRiskScoreMapping:
    """Test that risk_score is correctly derived from task_type."""

    def test_high_risk_types_defined(self):
        assert "blender_render" in HIGH_RISK_TYPES
        assert "face_swap" in HIGH_RISK_TYPES
        assert "face_enhance" in HIGH_RISK_TYPES
        assert "frame_enhance" in HIGH_RISK_TYPES
        assert "lip_sync_ff" in HIGH_RISK_TYPES
        assert "colorize" in HIGH_RISK_TYPES
        assert "age_modify" in HIGH_RISK_TYPES
        assert "face_edit" in HIGH_RISK_TYPES
        assert "bg_remove" in HIGH_RISK_TYPES
        assert "face_pipeline" in HIGH_RISK_TYPES
        assert "custom_script" in HIGH_RISK_TYPES

    def test_low_risk_types_defined(self):
        assert "tts_generation" in LOW_RISK_TYPES
        assert "sfx_generation" in LOW_RISK_TYPES
        assert "vfx_audio_generation" in LOW_RISK_TYPES
        assert "music_generation" in LOW_RISK_TYPES
        assert "music_cover" in LOW_RISK_TYPES
        assert "music_remix" in LOW_RISK_TYPES
        assert "music_repaint" in LOW_RISK_TYPES
        assert "music_extract" in LOW_RISK_TYPES

    def test_compute_risk_score_high(self, client):
        score = client._compute_risk_score("blender_render")
        assert score == 0.8

    def test_compute_risk_score_low(self, client):
        score = client._compute_risk_score("tts_generation")
        assert score == 0.2

    def test_compute_risk_score_unknown(self, client):
        score = client._compute_risk_score("unknown_engine")
        assert score == 0.5


# ---------------------------------------------------------------------------
# Test: submit_gpu_review
# ---------------------------------------------------------------------------


class TestSubmitGpuReview:
    """Test submit_gpu_review with various task types and routing responses."""

    @pytest.mark.asyncio
    async def test_submit_review_high_risk_human_routing(
        self, client, mock_response_factory
    ):
        """High-risk task returns HUMAN routing."""
        # Mock auth token
        client._token = "test-jwt-token"
        client._token_expires = 9999999999.0

        mock_resp = mock_response_factory(
            status_code=202,
            json_data={
                "data": {
                    "review_id": 42,
                    "state": "APPROVING",
                    "routing": "HUMAN",
                },
                "meta": {"request_id": "abc123"},
            },
        )

        with patch.object(
            client._http_client, "post", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await client.submit_gpu_review(
                task_id="task-uuid-001",
                task_type="blender_render",
                created_by="telegram",
                metadata={"gpu_required": True},
            )

        assert isinstance(result, ReviewSubmitResult)
        assert result.review_id == 42
        assert result.state == "APPROVING"
        assert result.routing == "HUMAN"

    @pytest.mark.asyncio
    async def test_submit_review_low_risk_auto_routing(
        self, client, mock_response_factory
    ):
        """Low-risk task returns AUTO routing (immediate approval)."""
        client._token = "test-jwt-token"
        client._token_expires = 9999999999.0

        mock_resp = mock_response_factory(
            status_code=202,
            json_data={
                "data": {
                    "review_id": 43,
                    "state": "COMPLETE",
                    "routing": "AUTO",
                },
                "meta": {"request_id": "def456"},
            },
        )

        with patch.object(
            client._http_client, "post", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await client.submit_gpu_review(
                task_id="task-uuid-002",
                task_type="tts_generation",
                created_by="telegram",
            )

        assert result.review_id == 43
        assert result.state == "COMPLETE"
        assert result.routing == "AUTO"

    @pytest.mark.asyncio
    async def test_submit_review_includes_correct_metadata(
        self, client, mock_response_factory
    ):
        """Verify the request body includes correct metadata fields."""
        client._token = "test-jwt-token"
        client._token_expires = 9999999999.0

        mock_resp = mock_response_factory(
            status_code=202,
            json_data={
                "data": {
                    "review_id": 44,
                    "state": "APPROVING",
                    "routing": "HUMAN",
                },
                "meta": {},
            },
        )

        with patch.object(
            client._http_client, "post", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_post:
            await client.submit_gpu_review(
                task_id="task-uuid-003",
                task_type="face_swap",
                created_by="alice",
                metadata={"gpu_required": True, "params": {"model": "v3"}},
                callback_url="http://gold-team:8900/callback",
                callback_secret="secret-123",
            )

            # Verify the POST was called with correct payload
            call_args = mock_post.call_args
            body = call_args.kwargs.get("json", call_args[1].get("json", {}))

            assert body["type"] == "gpu_task"
            assert body["content_ref"] == "task-uuid-003"
            assert body["source_system"] == "kais-gold-team"
            assert body["metadata"]["task_type"] == "face_swap"
            assert body["metadata"]["created_by"] == "alice"
            assert body["metadata"]["gpu_required"] is True
            assert body["metadata"]["params"] == {"model": "v3"}
            assert body["risk_score"] == 0.8
            assert body["callback_url"] == "http://gold-team:8900/callback"
            assert body["callback_secret"] == "secret-123"

    @pytest.mark.asyncio
    async def test_submit_review_authenticates_first(
        self, client, mock_response_factory
    ):
        """Client obtains JWT token before submitting."""
        # No cached token
        client._token = None
        client._token_expires = 0.0

        auth_resp = mock_response_factory(
            status_code=200,
            json_data={
                "data": {
                    "access_token": "new-jwt-token",
                    "token_type": "bearer",
                    "expires_in": 900,
                }
            },
        )

        submit_resp = mock_response_factory(
            status_code=202,
            json_data={
                "data": {
                    "review_id": 45,
                    "state": "COMPLETE",
                    "routing": "AUTO",
                },
                "meta": {},
            },
        )

        async def mock_post(url, **kwargs):
            if "/auth/token" in url:
                return auth_resp
            return submit_resp

        with patch.object(
            client._http_client, "post", side_effect=mock_post
        ):
            result = await client.submit_gpu_review(
                task_id="task-uuid-004",
                task_type="music_generation",
            )

        assert result.routing == "AUTO"
        assert client._token == "new-jwt-token"


# ---------------------------------------------------------------------------
# Test: query_review_status
# ---------------------------------------------------------------------------


class TestQueryReviewStatus:
    """Test query_review_status method."""

    @pytest.mark.asyncio
    async def test_query_review_status_success(
        self, client, mock_response_factory
    ):
        """Query returns review state and disposition."""
        client._token = "test-jwt-token"
        client._token_expires = 9999999999.0

        mock_resp = mock_response_factory(
            status_code=200,
            json_data={
                "data": {
                    "id": 42,
                    "type": "gpu_task",
                    "content_ref": "task-uuid-001",
                    "metadata": {"task_type": "blender_render"},
                    "source_system": "kais-gold-team",
                    "priority": "normal",
                    "risk_score": 0.8,
                    "state": "APPROVING",
                    "disposition": "HUMAN",
                    "callback_url": "http://gold-team:8900/callback",
                    "version": 3,
                    "created_at": "2026-05-07T10:00:00Z",
                    "updated_at": "2026-05-07T10:05:00Z",
                },
                "meta": {"request_id": "xyz"},
            },
        )

        with patch.object(
            client._http_client, "get", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await client.query_review_status(42)

        assert isinstance(result, ReviewQueryResult)
        assert result.review_id == 42
        assert result.state == "APPROVING"
        assert result.disposition == "HUMAN"
        assert result.version == 3


# ---------------------------------------------------------------------------
# Test: Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test error handling for network and HTTP errors."""

    @pytest.mark.asyncio
    async def test_connection_error_raises_client_error(self, client):
        """Connection refused raises ReviewClientError."""
        client._token = "test-jwt-token"
        client._token_expires = 9999999999.0

        import httpx

        with patch.object(
            client._http_client,
            "post",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            with pytest.raises(ReviewClientError, match="Connection"):
                await client.submit_gpu_review(
                    task_id="task-uuid-err",
                    task_type="blender_render",
                )

    @pytest.mark.asyncio
    async def test_timeout_raises_client_error(self, client):
        """Request timeout raises ReviewClientError."""
        client._token = "test-jwt-token"
        client._token_expires = 9999999999.0

        import httpx

        with patch.object(
            client._http_client,
            "post",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("Request timed out"),
        ):
            with pytest.raises(ReviewClientError, match="[Tt]imeout"):
                await client.submit_gpu_review(
                    task_id="task-uuid-timeout",
                    task_type="blender_render",
                )

    @pytest.mark.asyncio
    async def test_http_4xx_raises_client_error(
        self, client, mock_response_factory
    ):
        """HTTP 4xx response raises ReviewClientError with status code."""
        client._token = "test-jwt-token"
        client._token_expires = 9999999999.0

        mock_resp = mock_response_factory(
            status_code=422,
            json_data={
                "error": {"error": "validation_error", "detail": "Invalid callback_url"}
            },
        )

        with patch.object(
            client._http_client, "post", new_callable=AsyncMock, return_value=mock_resp
        ):
            with pytest.raises(ReviewClientError, match="422"):
                await client.submit_gpu_review(
                    task_id="task-uuid-4xx",
                    task_type="blender_render",
                )

    @pytest.mark.asyncio
    async def test_http_5xx_raises_client_error(
        self, client, mock_response_factory
    ):
        """HTTP 5xx response raises ReviewClientError."""
        client._token = "test-jwt-token"
        client._token_expires = 9999999999.0

        mock_resp = mock_response_factory(
            status_code=500,
            json_data={"error": {"error": "internal_error"}},
        )

        with patch.object(
            client._http_client, "post", new_callable=AsyncMock, return_value=mock_resp
        ):
            with pytest.raises(ReviewClientError, match="500"):
                await client.submit_gpu_review(
                    task_id="task-uuid-5xx",
                    task_type="blender_render",
                )
