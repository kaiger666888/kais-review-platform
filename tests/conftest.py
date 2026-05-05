"""Shared test fixtures for all test modules."""

import os

# Set test environment variables BEFORE importing any app modules
os.environ["API_KEY"] = "test-api-key"
os.environ["JWT_SECRET"] = "test-jwt-secret-for-testing-min-32-chars-long"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.auth import create_jwt
from app.core.config import Settings, get_settings
from app.models.schema import Base, create_tables


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
