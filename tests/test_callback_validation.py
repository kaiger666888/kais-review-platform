"""Tests for callback URL validation and Review model callback fields.

Tests RFC1918 private IP validation for callback URLs,
Review model with callback_url/callback_secret columns,
and Pydantic schema acceptance of callback fields.
"""

import socket
from unittest.mock import patch

import pytest
import pytest_asyncio
from pydantic import ValidationError

from app.models.schema import Review
from app.models.schemas import ReviewCreateRequest, ReviewResponse


# ---------------------------------------------------------------------------
# RFC1918 Validator Tests
# ---------------------------------------------------------------------------


class TestCallbackUrlValidation:
    """Test validate_callback_url rejects public IPs, accepts RFC1918/loopback/None."""

    def test_rfc1918_192_168_range_accepted(self):
        """192.168.x.x URLs are accepted (RFC1918)."""
        from app.core.validation import validate_callback_url

        result = validate_callback_url("http://192.168.1.100:8080/callback")
        assert result == "http://192.168.1.100:8080/callback"

    def test_rfc1918_10_range_accepted(self):
        """10.x.x.x URLs are accepted (RFC1918)."""
        from app.core.validation import validate_callback_url

        result = validate_callback_url("http://10.0.0.1/hook")
        assert result == "http://10.0.0.1/hook"

    def test_rfc1918_172_16_range_accepted(self):
        """172.16.x.x URLs are accepted (RFC1918 172.16.0.0/12)."""
        from app.core.validation import validate_callback_url

        result = validate_callback_url("http://172.16.0.1/hook")
        assert result == "http://172.16.0.1/hook"

    def test_rfc1918_172_31_range_accepted(self):
        """172.31.x.x URLs are accepted (top of RFC1918 172.16.0.0/12 range)."""
        from app.core.validation import validate_callback_url

        result = validate_callback_url("http://172.31.255.255/hook")
        assert result == "http://172.31.255.255/hook"

    def test_public_ip_rejected(self):
        """Public IP (8.8.8.8) raises ValueError."""
        from app.core.validation import validate_callback_url

        with pytest.raises(ValueError, match="private IP"):
            validate_callback_url("http://8.8.8.8/hook")

    def test_hostname_resolving_to_public_rejected(self):
        """Hostname resolving to a public IP raises ValueError."""
        from app.core.validation import validate_callback_url

        with patch("app.core.validation.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80))
            ]
            with pytest.raises(ValueError, match="private IP"):
                validate_callback_url("http://example.com/hook")

    def test_none_returns_none(self):
        """None callback URL returns None (callback is optional)."""
        from app.core.validation import validate_callback_url

        result = validate_callback_url(None)
        assert result is None

    def test_loopback_accepted(self):
        """127.0.0.1 is accepted (loopback for local development)."""
        from app.core.validation import validate_callback_url

        result = validate_callback_url("http://127.0.0.1:9090/callback")
        assert result == "http://127.0.0.1:9090/callback"

    def test_link_local_accepted(self):
        """169.254.x.x is accepted (link-local for local development)."""
        from app.core.validation import validate_callback_url

        result = validate_callback_url("http://169.254.0.1/hook")
        assert result == "http://169.254.0.1/hook"

    def test_hostname_resolving_to_private_accepted(self):
        """Hostname resolving to RFC1918 IP is accepted."""
        from app.core.validation import validate_callback_url

        with patch("app.core.validation.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 80))
            ]
            result = validate_callback_url("http://my-server.local/hook")
            assert result == "http://my-server.local/hook"

    def test_172_32_rejected(self):
        """172.32.x.x is rejected (outside RFC1918 172.16.0.0/12 range)."""
        from app.core.validation import validate_callback_url

        with pytest.raises(ValueError, match="private IP"):
            validate_callback_url("http://172.32.0.1/hook")


# ---------------------------------------------------------------------------
# Review Model Callback Fields Tests
# ---------------------------------------------------------------------------


class TestReviewCallbackModel:
    """Test Review SQLAlchemy model with callback fields."""

    @pytest.mark.asyncio
    async def test_review_without_callback(self, db_session):
        """Review can be created with callback_url and callback_secret as None."""
        review = Review(
            type="movie_scene",
            content_ref="s3://bucket/image.jpg",
            source_system="kais-movie-agent",
            priority="normal",
            state="PENDING",
        )
        db_session.add(review)
        await db_session.commit()
        await db_session.refresh(review)

        assert review.id is not None
        assert review.callback_url is None
        assert review.callback_secret is None

    @pytest.mark.asyncio
    async def test_review_with_callback(self, db_session):
        """Review can be created with callback_url and callback_secret set."""
        review = Review(
            type="gpu_task",
            content_ref="task://render-001",
            source_system="kais-gold-team",
            priority="high",
            state="PENDING",
            callback_url="http://192.168.1.100:8080/callback",
            callback_secret="my-secret",
        )
        db_session.add(review)
        await db_session.commit()
        await db_session.refresh(review)

        assert review.callback_url == "http://192.168.1.100:8080/callback"
        assert review.callback_secret == "my-secret"


# ---------------------------------------------------------------------------
# Pydantic Schema Tests
# ---------------------------------------------------------------------------


class TestCallbackSchemas:
    """Test Pydantic request/response schemas for callback fields."""

    def test_create_request_accepts_callback_fields(self):
        """ReviewCreateRequest accepts optional callback_url and callback_secret."""
        req = ReviewCreateRequest(
            type="gpu_task",
            content_ref="task://render-001",
            source_system="kais-gold-team",
            callback_url="http://192.168.1.100:8080/callback",
            callback_secret="my-secret",
        )
        assert req.callback_url == "http://192.168.1.100:8080/callback"
        assert req.callback_secret == "my-secret"

    def test_create_request_without_callback(self):
        """ReviewCreateRequest works without callback fields (backward compatible)."""
        req = ReviewCreateRequest(
            type="movie_scene",
            content_ref="s3://bucket/image.jpg",
            source_system="kais-movie-agent",
        )
        assert req.callback_url is None
        assert req.callback_secret is None

    def test_response_includes_callback_url(self):
        """ReviewResponse includes callback_url."""
        resp = ReviewResponse(
            id=1,
            type="gpu_task",
            content_ref="task://render-001",
            metadata=None,
            source_system="kais-gold-team",
            priority="high",
            risk_score=None,
            state="PENDING",
            disposition=None,
            version=1,
            callback_url="http://192.168.1.100:8080/callback",
            created_at="2026-05-07T00:00:00Z",
            updated_at="2026-05-07T00:00:00Z",
        )
        assert resp.callback_url == "http://192.168.1.100:8080/callback"

    def test_response_never_includes_callback_secret(self):
        """ReviewResponse must never expose callback_secret."""
        # Verify callback_secret is not in the model fields
        field_names = ReviewResponse.model_fields.keys()
        assert "callback_secret" not in field_names

    def test_response_with_none_callback_url(self):
        """ReviewResponse with callback_url=None serializes correctly."""
        resp = ReviewResponse(
            id=1,
            type="movie_scene",
            content_ref="s3://bucket/image.jpg",
            metadata=None,
            source_system="kais-movie-agent",
            priority="normal",
            risk_score=None,
            state="PENDING",
            disposition=None,
            version=1,
            callback_url=None,
            created_at="2026-05-07T00:00:00Z",
            updated_at="2026-05-07T00:00:00Z",
        )
        data = resp.model_dump()
        assert data["callback_url"] is None
