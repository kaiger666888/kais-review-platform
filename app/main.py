from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import Depends, FastAPI, Request

from app.core.config import get_settings
from app.core.database import engine
from app.models.schema import create_tables

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database schema
    async with engine.begin() as conn:
        await conn.run_sync(create_tables)

    # Startup: initialize Redis connection
    try:
        app.state.redis = aioredis.from_url(
            settings.redis_url, decode_responses=True
        )
    except Exception:
        app.state.redis = None

    # Startup: initialize arq pool
    try:
        app.state.arq_pool = await create_pool(
            RedisSettings.from_dsn(settings.redis_url)
        )
    except Exception:
        app.state.arq_pool = None

    yield

    # Shutdown: cleanup connections
    if app.state.redis:
        await app.state.redis.close()
    if app.state.arq_pool:
        await app.state.arq_pool.close()
    await engine.dispose()


app = FastAPI(
    lifespan=lifespan,
    title="Kai's Review Platform",
    version="1.0.0",
)


@app.get("/health")
async def health():
    return {"status": "ok"}


def get_redis(request: Request):
    return request.app.state.redis


def get_arq_pool(request: Request):
    return request.app.state.arq_pool
