"""Shared integration test fixtures.

Provides httpx.AsyncClient with ASGI transport, in-memory SQLite database,
and mock Redis for full HTTP-level integration testing.
"""

import os

# Set test environment variables BEFORE importing any app modules
os.environ["API_KEY"] = "test-api-key"
os.environ["JWT_SECRET"] = "test-jwt-secret-for-testing-min-32-chars-long"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

import aiohttp
from aiohttp import web

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.auth import create_jwt
from app.core.config import Settings
from app.core.database import get_db
from app.core.dependencies import get_arq_pool, get_redis
from app.core.policy import get_policy_engine
from app.main import app
from app.models.schema import Base, create_tables


@pytest_asyncio.fixture
async def db_engine():
    """Provide an in-memory SQLite async engine with tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(create_tables)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Provide an async database session for tests."""
    factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with factory() as session:
        yield session


@pytest.fixture
def settings():
    """Provide test Settings instance."""
    return Settings(
        api_key="test-api-key",
        jwt_secret="test-jwt-secret-for-testing-min-32-chars-long",
    )


@pytest.fixture
def auth_headers(settings):
    """Provide Authorization header with valid JWT for test client."""
    token = create_jwt("test-client", settings.jwt_secret)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_redis():
    """Provide a mock Redis that simulates set/get/del/register_script behavior."""
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

    class MockScript:
        """Simulates redis.commands.core.AsyncScript for Lua consume token."""

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


@pytest_asyncio.fixture
async def client(db_engine, mock_redis):
    """Provide an httpx.AsyncClient wired to the FastAPI app with test overrides.

    Each request gets its own database session from the test engine to avoid
    SQLite session conflicts during concurrent requests. Overrides get_redis,
    get_arq_pool, and patches emit_state_change to a no-op.
    """
    # Save original app.state values to restore later
    orig_redis = getattr(app.state, "redis", None)
    orig_arq_pool = getattr(app.state, "arq_pool", None)

    # Set app.state directly so endpoints that access app.state work
    app.state.redis = mock_redis
    app.state.arq_pool = None

    # Load default policies (lifespan doesn't run with ASGITransport)
    engine_instance = get_policy_engine()
    if not engine_instance.list_policies():
        engine_instance.load_from_directory("app/policies")

    # Create a session factory from the test engine -- each request gets a new session
    factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def override_get_db():
        async with factory() as session:
            yield session

    def override_get_redis():
        return mock_redis

    def override_get_arq_pool():
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_arq_pool] = override_get_arq_pool

    # Patch emit_state_change to no-op to avoid SQLite session conflicts.
    # SSE broadcasting and webhook delivery are tested separately.
    async def _noop_emit(*args, **kwargs):
        pass

    with patch("app.core.events.emit_state_change", side_effect=_noop_emit):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client

    # Cleanup
    app.dependency_overrides.clear()
    app.state.redis = orig_redis
    app.state.arq_pool = orig_arq_pool


# ---------------------------------------------------------------------------
# E2E shared fixtures for dual-bot coordination tests (Phase 12)
# ---------------------------------------------------------------------------


@pytest.fixture
def e2e_gold_team_review_payload():
    """Provide a gold-team review submission payload for E2E tests."""
    return {
        "title": "E2E: GPU Render Task",
        "source_system": "kais-gold-team",
        "task_type": "gpu_render",
        "callback_url": "http://192.168.71.140:8900/callback/review_result",
        "callback_secret": "e2e-test-secret-gold-team",
        "metadata": {
            "task_type": "gpu_render",
            "gpu_engine": "blender",
            "requesting_user": "test_user",
        },
    }


@pytest.fixture
def e2e_movie_agent_review_payload():
    """Provide a movie-agent review submission payload for E2E tests."""
    return {
        "title": "E2E: Storyboard Review",
        "source_system": "kais-movie-agent",
        "task_type": "storyboard",
        "callback_url": "http://192.168.71.38:8766/callback",
        "callback_secret": "e2e-test-secret-movie-agent",
        "metadata": {
            "pipeline_phase": "storyboard",
            "project": "test-project",
        },
    }


@pytest_asyncio.fixture
async def mock_callback_server():
    """Provide a mock aiohttp callback server that records POST requests.

    Starts a local HTTP server on a random port with a single POST /callback
    handler. The handler records received payloads and their X-Callback-Signature
    headers for assertion in tests.

    Yields:
        tuple[str, list[dict]]: (base_url, received_callbacks)
            base_url: e.g. "http://127.0.0.1:12345"
            received_callbacks: list of {"headers": dict, "body": dict}
    """
    received: list[dict] = []

    async def handle_callback(request: web.Request) -> web.Response:
        """Record incoming callback with headers and body."""
        body = await request.json()
        received.append(
            {
                "headers": dict(request.headers),
                "body": body,
            }
        )
        return web.json_response({"status": "ok"})

    app = web.Application()
    app.router.add_post("/callback", handle_callback)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    # Retrieve the actual port assigned by the OS
    # site._server.sockets[0].getsockname() returns (host, port)
    actual_port = site._server.sockets[0].getsockname()[1]
    base_url = f"http://127.0.0.1:{actual_port}"

    yield base_url, received

    await runner.cleanup()
