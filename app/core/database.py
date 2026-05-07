from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.audit import audit_protect_authorizer
from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
    # set_authorizer is not available on aiosqlite's async-adapted connection wrapper.
    # DEBT-03: try to register the authorizer on the underlying sqlite3 connection.
    # This is a best-effort — the authorizer protects audit_entries from UPDATE/DELETE.
    try:
        raw_conn = getattr(dbapi_connection, "driver_connection", dbapi_connection)
        if hasattr(raw_conn, "set_authorizer"):
            raw_conn.set_authorizer(audit_protect_authorizer)
    except Exception:
        pass


async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
