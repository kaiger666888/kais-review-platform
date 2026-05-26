"""Tests for web authentication: login page, login form, dashboard redirect."""

from unittest.mock import patch, AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.auth import create_jwt
from app.main import app


@pytest.fixture
def valid_cookie(settings) -> dict:
    """Provide a valid access_token cookie for authenticated requests."""
    token = create_jwt("admin", settings.jwt_secret, expires_minutes=15)
    return {"access_token": token}


@pytest.mark.asyncio
async def test_unauthenticated_dashboard_redirects():
    """GET / without access_token cookie returns 303 redirect to /login."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert "/login" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_authenticated_dashboard_renders(valid_cookie):
    """GET / with valid access_token cookie returns 200 (dashboard renders)."""
    # Mock _fetch_reviews to avoid database dependency in auth-focused test
    with patch("app.web.routes._fetch_reviews", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([], False, None)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/", cookies=valid_cookie, follow_redirects=False
            )
    assert response.status_code == 200
    assert "Review" in response.text


@pytest.mark.asyncio
async def test_login_page_renders():
    """GET /login returns 200 with HTML containing a form."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/login")
    assert response.status_code == 200
    assert "<form" in response.text
    assert "api_key" in response.text


@pytest.mark.asyncio
async def test_login_submit_correct_key():
    """POST /login with correct API key returns 303 redirect to / with access_token cookie set."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/login",
            data={"api_key": "test-api-key"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers.get("location", "/")
    # Check that the access_token cookie was set
    cookies = response.cookies
    assert "access_token" in dict(cookies)


@pytest.mark.asyncio
async def test_login_submit_wrong_key():
    """POST /login with incorrect API key returns 200 with error message (no redirect)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/login",
            data={"api_key": "wrong-key"},
            follow_redirects=False,
        )
    assert response.status_code == 200
    assert "Invalid API key" in response.text
    # Should NOT redirect
    assert "location" not in response.headers
