import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from sqlalchemy import text
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import Depends, FastAPI, Request

from app.api.v1.actions import router as actions_router
from app.api.v1.audit_api import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.events import router as events_router
from app.api.v1.policies import router as policies_router
from app.api.v1.reviews import router as reviews_router
from app.api.v1.webhooks import router as webhooks_router
from app.web.routes import router as web_router
from app.web.auth import router as web_auth_router
from app.web.sse import router as sse_router
from app.core.dependencies import get_arq_pool, get_redis
from app.core.config import get_settings
from app.core.database import engine
from app.core.policy import get_policy_engine
from app.models.schema import create_tables
from app.bot import create_bot_application
from app.bot.lifecycle import bot_start, bot_stop

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

    # Startup: initialize Telegram Bot
    try:
        app.state.bot_application = create_bot_application()
        await bot_start(app.state.bot_application)
    except Exception as exc:
        app.state.bot_application = None
        logger.warning("Bot startup failed, continuing without Telegram Bot: %s", exc)

    yield

    # Shutdown: stop Telegram Bot
    try:
        await bot_stop(app.state.bot_application)
    except Exception as exc:
        logger.warning("Bot stop failed: %s", exc)

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
app.include_router(webhooks_router)
app.include_router(web_auth_router)
app.include_router(sse_router)
app.include_router(web_router)


@app.get("/health")
async def health():
    checks = {"status": "ok"}

    # Check Redis connectivity
    try:
        redis = getattr(app.state, "redis", None)
        if redis:
            await redis.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "unavailable"
            checks["status"] = "degraded"
    except Exception:
        checks["redis"] = "error"
        checks["status"] = "degraded"

    # Check SQLite connectivity
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        checks["status"] = "degraded"

    status_code = 200 if checks["status"] == "ok" else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(content=checks, status_code=status_code)
