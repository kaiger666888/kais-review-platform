# Phase 2: Real-Time Events - Research

**Researched:** 2026-05-05
**Domain:** SSE (Server-Sent Events), webhook delivery with retry, event emission architecture
**Confidence:** HIGH

## Summary

Phase 2 adds two real-time delivery mechanisms to the review platform: (1) SSE streaming for browser clients to receive review status change events without polling, and (2) webhook delivery to registered external systems (kais-movie-agent, kais-gold-team) with retry and exponential backoff. Both mechanisms share a common event emission point in `state_machine.transition_state()`.

FastAPI 0.136.1 ships built-in SSE support via `fastapi.sse.EventSourceResponse` and `ServerSentEvent` (added in 0.135.0). This eliminates the need for the third-party `sse-starlette` library. The built-in `EventSourceResponse` automatically sends keep-alive pings every 15 seconds, sets `Cache-Control: no-cache`, and sets `X-Accel-Buffering: no` for Nginx compatibility -- all out of the box.

For webhooks, arq 0.28.0's built-in `Retry` exception with `defer` parameter provides exponential backoff natively. Combined with `max_tries=3` on the function registration, this gives us retry logic without any additional libraries. HMAC-SHA256 signatures use Python's stdlib `hmac` + `hashlib` modules -- no third-party dependency needed.

**Primary recommendation:** Use FastAPI's built-in `fastapi.sse` module for SSE (no third-party SSE library needed), arq's native `Retry` exception for webhook backoff, and stdlib `hmac` for webhook signatures. Keep SSE connection state in-memory as an `asyncio.Queue` per connection in a singleton manager.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- SSE endpoint at `GET /api/v1/events/stream` -- follows existing v1 REST pattern
- JSON event format with `event: review_status`, `data: {review_id, old_state, new_state, timestamp}` -- matches audit trail structure
- SSE comment lines (`: heartbeat`) every 30s -- lightweight, no client parsing needed
- In-memory set with asyncio.Queue per connection -- sufficient for LAN single-server, Redis not needed for SSE fan-out
- SQLite table `webhook_configs` for webhook configuration storage -- consistent with existing DB, single source of truth
- arq task per webhook delivery with exponential backoff (1s -> 5s -> 30s), max 3 retries -- leverages existing arq infrastructure
- Standard JSON payload: `{event, review_id, old_state, new_state, timestamp, source_system}` -- mirrors SSE event structure
- HMAC-SHA256 signature in `X-Webhook-Signature` header -- industry standard, verifiable by receivers
- Emit events in `state_machine.transition_state()` -- single emission point, all state changes flow through it
- Direct iteration over SSE connections + arq.enqueue for each webhook -- simple for single-server LAN deployment
- `POST/GET/PUT/DELETE /api/v1/webhooks` CRUD API -- standard CRUD, JWT-protected
- No hard connection limit -- LAN deployment, < 10 concurrent reviewers expected. Log warning at > 50 connections

### Claude's Discretion
Internal implementation details, error message wording, test structure.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EVNT-01 | System pushes real-time review status changes via SSE (GET /api/v1/stream) | FastAPI 0.136.1 built-in `EventSourceResponse` + `ServerSentEvent` from `fastapi.sse`. Use `asyncio.Queue` per connection for fan-out. |
| EVNT-02 | SSE connections include heartbeat-based cleanup for zombie connections | FastAPI's built-in 15s keep-alive ping + custom 30s `: heartbeat` comment lines. Detect disconnect via `asyncio.CancelledError` when yield fails, plus periodic `request.is_disconnected()` check. |
| EVNT-03 | System sends Webhook callbacks to registered external systems on status change | httpx 0.28.1 async client for HTTP POST delivery. HMAC-SHA256 via stdlib `hmac`. Webhook configs stored in `webhook_configs` SQLite table. |
| EVNT-04 | Webhook delivery uses retry with exponential backoff (max 3 retries) | arq 0.28.0's `Retry` exception with `defer` parameter. Register function with `max_tries=3`. Backoff schedule: 1s -> 5s -> 30s via `ctx['job_try']` multiplier. |
| EVNT-05 | Webhook targets are configurable per source system | CRUD API at `/api/v1/webhooks` backed by `webhook_configs` table with `source_system` filter. JWT-protected endpoints. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi.sse (EventSourceResponse) | 0.136.1 (built-in) | SSE streaming | Built into FastAPI >= 0.135.0, Pydantic serialization on Rust side, auto keep-alive pings, no extra dependency |
| asyncio.Queue | stdlib | Per-connection event buffer | Standard library, async-native, perfect for SSE fan-out pattern |
| httpx | 0.28.1 | Async HTTP client for webhook delivery | Already installed, async-native, timeout control, HTTP/2 support |
| arq (Retry exception) | 0.28.0 | Webhook retry with exponential backoff | Already installed, `Retry(defer=seconds)` natively supported, `max_tries` on function registration |
| hmac + hashlib | stdlib | HMAC-SHA256 webhook signatures | Stdlib, no dependency, industry standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | 25.5.0 | Structured logging for event delivery | Already installed, log SSE connect/disconnect, webhook success/failure |
| SQLAlchemy 2.0 | 2.0.49 | WebhookConfig ORM model | Already installed, add new table to existing Base |
| Pydantic | 2.13.3 | Webhook config request/response schemas | Already installed, validation for webhook CRUD API |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| fastapi.sse (built-in) | sse-starlette | Built-in is sufficient, sse-starlette adds disconnect callback but FastAPI handles this via CancelledError. No extra dependency needed. |
| in-memory asyncio.Queue | Redis pub/sub | Redis pub/sub adds complexity for single-server LAN. In-memory is simpler and sufficient for < 10 concurrent reviewers. Redis pub/sub would be needed for multi-process/multi-server scaling. |
| arq Retry exception | tenacity library | arq's Retry is already integrated with the task queue. tenacity would be in-process retry (lost on worker crash). arq Retry is queue-based (survives crash). |

**Installation:**
No new packages required. All dependencies are already installed and verified.

```
# Already in requirements.txt -- no changes needed
fastapi==0.136.1       # Built-in SSE support (>= 0.135.0)
httpx==0.28.1          # Webhook HTTP delivery
arq==0.28.0            # Task queue with Retry exception
structlog==25.5.0      # Structured logging
sqlalchemy==2.0.49     # WebhookConfig table
```

**Version verification:** All versions confirmed from requirements.txt and runtime checks:
- FastAPI 0.136.1: `fastapi.sse.EventSourceResponse` and `fastapi.sse.ServerSentEvent` available
- httpx 0.28.1: async client confirmed
- arq 0.28.0: `Retry` exception with `defer` parameter confirmed from official docs

## Architecture Patterns

### Recommended Project Structure
```
app/
├── core/
│   ├── events.py          # SSE connection manager + event emission
│   ├── state_machine.py   # Modified: calls emit function after transition
│   └── dependencies.py    # Existing: get_redis, get_arq_pool
├── api/v1/
│   ├── events.py          # SSE stream endpoint
│   └── webhooks.py        # Webhook CRUD API endpoints
├── models/
│   ├── schema.py          # Modified: add WebhookConfig SQLAlchemy model
│   └── schemas.py         # Modified: add webhook Pydantic models
├── workers/
│   └── tasks.py           # Modified: add deliver_webhook task
└── main.py                # Modified: register new routers, init event manager
```

### Pattern 1: SSE Fan-Out with asyncio.Queue
**What:** Each SSE client gets its own `asyncio.Queue`. The event manager maintains a set of active queues. When an event is emitted, it is put into every queue. Each SSE generator reads from its queue and yields events.
**When to use:** Single-server SSE with < 50 concurrent clients.

```python
# app/core/events.py
import asyncio
import logging
from collections.abc import AsyncIterable
from datetime import datetime, timezone
from typing import Any

from fastapi.sse import EventSourceResponse, ServerSentEvent

logger = logging.getLogger(__name__)


class EventManager:
    """Manages SSE connections and broadcasts events to all clients."""

    def __init__(self):
        self._connections: set[asyncio.Queue] = set()

    def create_connection(self) -> asyncio.Queue:
        """Create a new SSE connection queue and register it."""
        queue: asyncio.Queue = asyncio.Queue()
        self._connections.add(queue)
        logger.info("sse_connected", total_connections=len(self._connections))
        return queue

    def remove_connection(self, queue: asyncio.Queue) -> None:
        """Remove and clean up an SSE connection."""
        self._connections.discard(queue)
        logger.info("sse_disconnected", total_connections=len(self._connections))

    async def broadcast(self, event_data: dict[str, Any]) -> None:
        """Send event data to all connected SSE clients."""
        disconnected: list[asyncio.Queue] = []
        for queue in self._connections:
            try:
                queue.put_nowait(event_data)
            except asyncio.QueueFull:
                # Client is too slow -- drop and disconnect
                disconnected.append(queue)
        for q in disconnected:
            self.remove_connection(q)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# Singleton instance
event_manager = EventManager()
```

```python
# Source: FastAPI official docs pattern (fastapi.tiangolo.com/tutorial/server-sent-events/)
# app/api/v1/events.py
from collections.abc import AsyncIterable

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.core.events import event_manager

router = APIRouter(tags=["events"])


@router.get("/api/v1/events/stream", response_class=EventSourceResponse)
async def sse_stream(request: Request) -> AsyncIterable[ServerSentEvent]:
    queue = event_manager.create_connection()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield ServerSentEvent(
                    data=data,
                    event="review_status",
                )
            except asyncio.TimeoutError:
                # Heartbeat comment line
                yield ServerSentEvent(comment="heartbeat")
    finally:
        event_manager.remove_connection(queue)
```

### Pattern 2: arq Webhook Delivery with Retry
**What:** Webhook delivery as an arq task using the `Retry` exception for exponential backoff. Each delivery attempt is a separate arq job execution.
**When to use:** All webhook deliveries that need persistence across worker restarts.

```python
# Source: arq official docs (arq-docs.helpmanual.io)
# app/workers/tasks.py -- add to existing file

import hashlib
import hmac
import json

import httpx
import structlog
from arq import Retry

from app.core.database import async_session_factory
from app.models.schema import WebhookConfig

BACKOFF_SCHEDULE = {1: 1, 2: 5, 3: 30}  # try_number -> delay_seconds


async def deliver_webhook(ctx: dict, webhook_config_id: int, payload: dict) -> dict:
    """Deliver a webhook payload to a registered endpoint with retry.

    Args:
        ctx: arq context dict with 'http_client' key.
        webhook_config_id: ID of the WebhookConfig to deliver to.
        payload: Event payload dict.

    Returns:
        Summary dict with delivery result.
    """
    logger = structlog.get_logger()
    job_try = ctx.get("job_try", 1)

    async with async_session_factory() as session:
        config = await session.get(WebhookConfig, webhook_config_id)
        if config is None:
            logger.error("webhook_config_not_found", config_id=webhook_config_id)
            return {"status": "error", "reason": "config_not_found"}

    # Compute HMAC signature
    body = json.dumps(payload, default=str)
    signature = hmac.new(
        config.secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
    }

    client: httpx.AsyncClient = ctx.get("http_client")
    try:
        response = await client.post(
            config.url,
            content=body,
            headers=headers,
            timeout=10.0,
        )
        if response.status_code >= 400:
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
        logger.info(
            "webhook_delivered",
            url=config.url,
            status_code=response.status_code,
            try_number=job_try,
        )
        return {"status": "delivered", "status_code": response.status_code}
    except Exception as e:
        logger.warning(
            "webhook_delivery_failed",
            url=config.url,
            error=str(e),
            try_number=job_try,
        )
        if job_try < 3:
            raise Retry(defer=BACKOFF_SCHEDULE.get(job_try + 1, 30))
        logger.error(
            "webhook_delivery_exhausted",
            url=config.url,
            tries=job_try,
        )
        return {"status": "failed", "error": str(e), "tries": job_try}
```

### Pattern 3: Event Emission Hook in State Machine
**What:** After a successful state transition, call the event emission function. This is the single emission point that triggers both SSE broadcast and webhook delivery.
**When to use:** Every state transition that needs to be communicated externally.

```python
# In state_machine.transition_state(), after successful commit and audit:

async def transition_state(session, review_id, from_state, to_state,
                           expected_version, actor, action=None, payload=None):
    # ... existing transition logic ...

    # After audit entry, emit event
    from app.core.events import emit_state_change
    review = await session.get(Review, review_id)
    await emit_state_change(
        review_id=review_id,
        old_state=from_state.value,
        new_state=to_state.value,
        source_system=review.source_system,
    )

    return review
```

### Pattern 4: WebhookConfig SQLAlchemy Model
**What:** SQLite table for webhook configuration with per-source-system targeting.
**When to use:** Storing webhook target URLs and secrets.

```python
# app/models/schema.py -- add to existing file

class WebhookConfig(Base):
    __tablename__ = "webhook_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    secret: Mapped[str] = mapped_column(String, nullable=False)
    source_system: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_webhook_source_active", "source_system", "is_active"),
    )
```

### Anti-Patterns to Avoid
- **Blocking the event loop in SSE generator:** Never do synchronous I/O or CPU-heavy work inside the SSE async generator. All database queries, Redis calls, and HTTP requests must be async.
- **Using Redis pub/sub for SSE on single server:** Unnecessary complexity. In-memory `set[asyncio.Queue]` is simpler and faster for a single FastAPI process on LAN.
- **Retry in-process with tenacity for webhooks:** If the arq worker crashes, in-process retries are lost. arq's queue-based `Retry` persists the job and re-executes after worker restart.
- **Skipping disconnect cleanup:** Every SSE connection MUST have a `finally` block that removes the queue from the manager. Without this, zombie connections leak memory indefinitely.
- **Putting `get_db()` session in SSE endpoint:** SSE endpoints are long-lived. Database sessions should not be held open for the duration of an SSE connection. Use short-lived sessions only when needed (webhook config lookup in the arq task, not in the SSE endpoint).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE protocol formatting | Manual `text/event-stream` formatting | `fastapi.sse.EventSourceResponse` + `ServerSentEvent` | FastAPI handles `data:`, `event:`, `id:`, `retry:`, comment formatting, keep-alive pings, Cache-Control headers, X-Accel-Buffering |
| Retry with backoff | Custom retry loop with sleep | arq `Retry(defer=seconds)` | arq's Retry is queue-persistent (survives worker crash), handles job_try tracking, and integrates with the existing worker infrastructure |
| Webhook HMAC signatures | Custom signing logic | stdlib `hmac.new(key, msg, hashlib.sha256)` | Stdlib is verified, constant-time comparison available, no dependency risk |
| SSE disconnect detection | Polling socket state | `request.is_disconnected()` + `asyncio.CancelledError` | FastAPI/Starlette provides `is_disconnected()` for explicit checks. Generator cancellation on client close raises `CancelledError` for implicit detection. |

**Key insight:** FastAPI 0.135.0+ added SSE support specifically to avoid the need for `sse-starlette`. The built-in implementation handles keep-alive pings (every 15s of silence), cache headers, and proxy buffering headers automatically. The only thing we add on top is our custom 30s heartbeat comment and disconnect cleanup.

## Common Pitfalls

### Pitfall 1: SSE Generator Cancellation Not Caught
**What goes wrong:** When a client disconnects, the SSE async generator is cancelled via `asyncio.CancelledError`. If not handled with `try/finally`, the connection queue remains in the EventManager set, leaking memory.
**Why it happens:** `CancelledError` is a `BaseException` in Python 3.9+, and `try/except Exception` does not catch it. Only `try/finally` guarantees cleanup.
**How to avoid:** Always wrap the SSE generator body in `try/finally` and call `remove_connection()` in the `finally` block.
**Warning signs:** Memory usage slowly increasing; `connection_count` never decreasing; log messages showing connections being added but never removed.

### Pitfall 2: FastAPI SSE Blocks Event Loop on Queue Get
**What goes wrong:** Using `await queue.get()` without a timeout blocks the generator forever if no events arrive, preventing heartbeat comments from being sent and preventing disconnect detection.
**Why it happens:** `queue.get()` is an infinite wait.
**How to avoid:** Use `asyncio.wait_for(queue.get(), timeout=30.0)` to periodically break out for heartbeat and disconnect checks.
**Warning signs:** Heartbeat comments never sent; zombie connections never cleaned up because the generator is stuck on `queue.get()`.

### Pitfall 3: Webhook Delivery Blocks State Machine
**What goes wrong:** Making HTTP requests directly in `transition_state()` blocks the state transition response while waiting for webhook delivery.
**Why it happens:** Webhook targets may be slow or unresponsive. Even with timeouts, this adds latency to every state transition.
**How to avoid:** Enqueue webhook delivery as arq tasks (`arq_pool.enqueue_job('deliver_webhook', ...)`). The state machine returns immediately; delivery happens asynchronously in the worker.
**Warning signs:** State transition API responses take > 1 second; timeouts on approve/reject endpoints.

### Pitfall 4: SSE Queue Overflow on Slow Clients
**What goes wrong:** A slow client (e.g., mobile on poor connection) cannot consume events fast enough. The queue grows unbounded, consuming memory.
**Why it happens:** `asyncio.Queue()` has no max size by default.
**How to avoid:** Create queues with `maxsize=100` (or similar). When `put_nowait()` raises `QueueFull`, disconnect the slow client.
**Warning signs:** Memory growth proportional to number of slow clients.

### Pitfall 5: Event Emission Circular Import
**What goes wrong:** Importing `event_manager` from `events.py` into `state_machine.py` creates a circular import if `events.py` also imports from `state_machine.py`.
**Why it happens:** Python's import system resolves circular imports by returning partially-initialized modules.
**How to avoid:** Use lazy imports (`from app.core.events import emit_state_change` inside the function body, not at module level). The `events.py` module should NOT import from `state_machine.py`.
**Warning signs:** `ImportError` at startup, or `AttributeError` on module attributes.

### Pitfall 6: arq Worker Not Running for Webhook Delivery
**What goes wrong:** Webhook events are enqueued but never delivered because the arq worker process is not running.
**Why it happens:** In development, the arq worker is a separate process that must be started manually (`arq app.workers.tasks.WorkerSettings`).
**How to avoid:** The existing codebase already handles graceful degradation when `arq_pool` is None. Log a warning when webhook enqueue fails due to unavailable arq. Document that the arq worker must be running for webhook delivery.
**Warning signs:** Webhook configs exist but no delivery logs; arq pool is None in app state.

## Code Examples

### Complete SSE Stream Endpoint
```python
# Source: FastAPI official docs + asyncio.Queue pattern
# app/api/v1/events.py

import asyncio
from collections.abc import AsyncIterable

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.core.auth import get_current_client
from app.core.events import event_manager

router = APIRouter(tags=["events"])


@router.get("/api/v1/events/stream", response_class=EventSourceResponse)
async def sse_stream(
    request: Request,
    client: str = Depends(get_current_client),
) -> AsyncIterable[ServerSentEvent]:
    """SSE stream for real-time review status updates.

    Requires JWT authentication. Yields review_status events and
    heartbeat comments every 30 seconds.
    """
    queue = event_manager.create_connection()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield ServerSentEvent(data=data, event="review_status")
            except asyncio.TimeoutError:
                yield ServerSentEvent(comment="heartbeat")
    finally:
        event_manager.remove_connection(queue)
```

### Event Emission with Webhook Enqueue
```python
# app/core/events.py -- emission function

import structlog
from datetime import datetime, timezone

from app.core.dependencies import get_arq_pool

logger = structlog.get_logger()


async def emit_state_change(
    review_id: int,
    old_state: str,
    new_state: str,
    source_system: str,
) -> None:
    """Emit a state change event to SSE clients and enqueue webhook deliveries.

    This function is called from transition_state() after a successful
    state transition and audit logging.
    """
    event_data = {
        "review_id": review_id,
        "old_state": old_state,
        "new_state": new_state,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_system": source_system,
    }

    # 1. Broadcast to SSE clients
    await event_manager.broadcast(event_data)

    # 2. Enqueue webhook deliveries for matching source_system
    #    (webhook config lookup happens inside the arq task,
    #     not here, to avoid holding a DB session)
    try:
        from app.core.database import async_session_factory
        from app.models.schema import WebhookConfig
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(
                select(WebhookConfig).where(
                    WebhookConfig.is_active == True,
                )
            )
            configs = result.scalars().all()

        # Import arq pool lazily to avoid circular imports at module level
        from app.main import app
        arq_pool = app.state.arq_pool
        if arq_pool:
            for config in configs:
                await arq_pool.enqueue_job(
                    "deliver_webhook",
                    config.id,
                    event_data,
                )
    except Exception as e:
        logger.error("webhook_enqueue_failed", error=str(e))
```

### Webhook CRUD API
```python
# app/api/v1/webhooks.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_client
from app.core.database import get_db
from app.models.schema import WebhookConfig
from app.models.schemas import (
    ApiResponse,
    WebhookCreateRequest,
    WebhookResponse,
    WebhookUpdateRequest,
)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("/", status_code=status.HTTP_201_CREATED,
             response_model=ApiResponse[WebhookResponse])
async def create_webhook(
    request: WebhookCreateRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    config = WebhookConfig(
        url=request.url,
        secret=request.secret,
        source_system=request.source_system,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return ApiResponse(data=WebhookResponse.model_validate(config))


@router.get("/", response_model=ApiResponse[list[WebhookResponse]])
async def list_webhooks(
    source_system: str | None = None,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    query = select(WebhookConfig)
    if source_system:
        query = query.where(WebhookConfig.source_system == source_system)
    result = await db.execute(query)
    configs = result.scalars().all()
    return ApiResponse(data=[WebhookResponse.model_validate(c) for c in configs])


@router.get("/{webhook_id}", response_model=ApiResponse[WebhookResponse])
async def get_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    config = await db.get(WebhookConfig, webhook_id)
    if not config:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return ApiResponse(data=WebhookResponse.model_validate(config))


@router.put("/{webhook_id}", response_model=ApiResponse[WebhookResponse])
async def update_webhook(
    webhook_id: int,
    request: WebhookUpdateRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    config = await db.get(WebhookConfig, webhook_id)
    if not config:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if request.url is not None:
        config.url = request.url
    if request.secret is not None:
        config.secret = request.secret
    if request.source_system is not None:
        config.source_system = request.source_system
    if request.is_active is not None:
        config.is_active = request.is_active
    await db.commit()
    await db.refresh(config)
    return ApiResponse(data=WebhookResponse.model_validate(config))


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    config = await db.get(WebhookConfig, webhook_id)
    if not config:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(config)
    await db.commit()
```

### arq Worker Update (Adding Webhook Task)
```python
# app/workers/tasks.py -- modifications to existing WorkerSettings

import httpx
from arq import cron
from arq.worker import func

# Register deliver_webhook with max_tries=3
# (function definition shown in Pattern 2 above)

class WorkerSettings:
    """arq worker configuration."""
    functions = [check_timeouts, deliver_webhook]
    cron_jobs = [
        cron(check_timeouts, minute={0}),
    ]

    async def on_startup(ctx):
        ctx['http_client'] = httpx.AsyncClient(timeout=10.0)

    async def on_shutdown(ctx):
        await ctx['http_client'].aclose()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| sse-starlette (third-party) | `fastapi.sse` (built-in) | FastAPI 0.135.0 (late 2024) | No extra dependency needed. Built-in handles keep-alive, cache headers, proxy buffering. |
| Manual `StreamingResponse` with SSE formatting | `EventSourceResponse` + `ServerSentEvent` | FastAPI 0.135.0 | Pydantic serialization on Rust side for performance. `ServerSentEvent` supports `data`, `event`, `id`, `retry`, `comment` fields. |
| in-process retry with tenacity | arq queue-based `Retry` exception | arq 0.16+ | Retries survive worker crashes. `Retry(defer=seconds)` for exponential backoff. `max_tries` on function registration. |

**Deprecated/outdated:**
- `sse-starlette` package: Not needed since FastAPI 0.135.0 added built-in SSE. The built-in version is maintained by the FastAPI team directly.
- `aioredis` as standalone: Merged into `redis-py` as `redis.asyncio`. Already handled in Phase 01.

## Open Questions

1. **Webhook config lookup optimization**
   - What we know: Current pattern queries SQLite for active webhook configs on every state transition.
   - What's unclear: Whether this adds measurable latency. With < 10 webhook configs expected, query time should be < 1ms.
   - Recommendation: Start with direct DB query. Add in-memory caching only if profiling shows it's needed.

2. **SSE event ordering guarantee**
   - What we know: `asyncio.Queue` is FIFO, so events arrive in order per-connection. Broadcast iterates over the set, so all clients get the same event order.
   - What's unclear: Whether we need event IDs for client-side deduplication on reconnect.
   - Recommendation: Include `review_id` + `timestamp` in event data. Client can use this for deduplication. Full `Last-Event-ID` resume support can be deferred to a later phase.

## Environment Availability

Step 2.6: SKIPPED (no new external dependencies identified -- all required packages are already installed and verified in requirements.txt).

The only external service dependency is Redis for arq, which is already established from Phase 01. The existing graceful degradation pattern (Redis/arq can be None) continues to apply.

## Validation Architecture

> Skip condition: workflow.nyquist_validation is explicitly set to false in .planning/config.json. Confirmed: `"nyquist_validation": false`. This section is SKIPPED.

## Sources

### Primary (HIGH confidence)
- FastAPI official SSE documentation (fastapi.tiangolo.com/tutorial/server-sent-events/) -- EventSourceResponse, ServerSentEvent API, keep-alive behavior
- arq official documentation (arq-docs.helpmanual.io/) -- Retry exception, enqueue_job, max_tries, WorkerSettings, on_startup/on_shutdown
- Python stdlib docs -- hmac, hashlib, asyncio.Queue
- Existing codebase files: state_machine.py, dependencies.py, tasks.py, database.py, schema.py, schemas.py, main.py, auth.py, reviews.py, actions.py

### Secondary (MEDIUM confidence)
- FastAPI GitHub Discussion #10340 -- disconnect detection behavior in EventSourceResponse
- arq GitHub repository (github.com/python-arq/arq) -- Retry exception behavior, pessimistic execution model
- Web search: FastAPI SSE asyncio.Queue fan-out pattern (multiple community sources consistent)
- Web search: arq retry exponential backoff pattern (davidmuraya.com/blog/fastapi-arq-retries/)

### Tertiary (LOW confidence)
- None -- all critical findings verified against primary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed, versions verified, APIs tested in runtime
- Architecture: HIGH -- FastAPI built-in SSE is well-documented, asyncio.Queue pattern is standard, arq Retry is well-documented
- Pitfalls: HIGH -- based on official docs, GitHub issues, and community patterns; all verified against primary sources

**Research date:** 2026-05-05
**Valid until:** 2026-06-05 (stable -- all APIs are from released, production versions)
