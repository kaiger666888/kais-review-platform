import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import Depends, FastAPI, Request

from app.api.v1.actions import router as actions_router
from app.api.v1.audit_api import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.events import router as events_router
from app.api.v1.policies import router as policies_router
from app.api.v1.reviews import router as reviews_router
from app.core.dependencies import get_arq_pool, get_redis
from app.core.config import get_settings
from app.core.database import engine
from app.core.policy import get_policy_engine
from app.models.schema import create_tables

settings = get_settings()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database schema
    async with engine.begin() as conn:
        await conn.run_sync(create_tables)

    # Startup: load default policies from YAML files
    engine_instance = get_policy_engine()
    try:
        loaded = engine_instance.load_from_directory("app/policies")
        logger.info("Loaded %d default policies: %s", len(loaded), loaded)
    except Exception as exc:
        logger.warning("Failed to load default policies: %s", exc)

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

# Register API routers
app.include_router(auth_router)
app.include_router(reviews_router)
app.include_router(actions_router)
app.include_router(audit_router)
app.include_router(policies_router)
app.include_router(events_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
