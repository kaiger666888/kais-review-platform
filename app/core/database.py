from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.postgres_url,
    echo=settings.log_level == "DEBUG",
    # Pool settings only apply to PostgreSQL; SQLite ignores them
    **({"pool_size": 10, "max_overflow": 5, "pool_timeout": 30,
        "pool_recycle": 1800, "pool_pre_ping": True, "pool_use_lifo": True}
       if settings.postgres_url.startswith("postgresql") else {}),
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
