"""SSE event manager for real-time review status updates.

Provides a singleton EventManager that maintains per-connection asyncio.Queue
instances for broadcasting review_status events to connected SSE clients.
Also provides emit_state_change() for wiring state machine transitions
into the SSE + webhook delivery pipeline.
"""

import asyncio
import json
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger(__name__)


class EventManager:
    """Manages SSE connections and broadcasts events to all connected clients.

    Each SSE connection gets its own asyncio.Queue(maxsize=100). Events are
    broadcast to all queues; slow clients that overflow their queue are
    automatically disconnected.
    """

    def __init__(self) -> None:
        self._connections: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    def create_connection(self) -> asyncio.Queue:
        """Create a new SSE connection queue and register it.

        Returns:
            asyncio.Queue with maxsize=100 for receiving broadcast events.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._connections.add(queue)
        logger.info(
            "sse_connected",
            total_connections=len(self._connections),
        )
        return queue

    def remove_connection(self, queue: asyncio.Queue) -> None:
        """Unregister an SSE connection queue.

        Called in the finally block of SSE endpoints to ensure cleanup
        even on unexpected disconnects.
        """
        self._connections.discard(queue)
        logger.info(
            "sse_disconnected",
            total_connections=len(self._connections),
        )

    async def broadcast(self, event_data: dict) -> None:
        """Broadcast an event to all connected SSE clients.

        Slow clients whose queue is full are disconnected and removed.

        Args:
            event_data: Dict to serialize as JSON and send as review_status event.
        """
        disconnected: list[asyncio.Queue] = []
        for queue in self._connections:
            try:
                queue.put_nowait(event_data)
            except asyncio.QueueFull:
                disconnected.append(queue)

        # Clean up slow clients that overflowed
        for queue in disconnected:
            self._connections.discard(queue)
            logger.warning(
                "sse_client_dropped",
                reason="queue_full",
                total_connections=len(self._connections),
            )

        if len(self._connections) > 50:
            logger.warning(
                "sse_connections_high",
                total_connections=len(self._connections),
                message="SSE connection count exceeds 50",
            )

    @property
    def connection_count(self) -> int:
        """Return the current number of active SSE connections."""
        return len(self._connections)


# Module-level singleton instance
event_manager = EventManager()


async def emit_state_change(
    review_id: int,
    old_state: str,
    new_state: str,
    source_system: str,
) -> None:
    """Emit a state change event to SSE clients and enqueue webhook deliveries.

    This function is called from transition_state() after a successful
    state transition and audit logging. It broadcasts the event to all
    connected SSE clients and enqueues a deliver_webhook arq job for each
    active WebhookConfig.

    Args:
        review_id: ID of the review that changed state.
        old_state: Previous state value.
        new_state: New state value.
        source_system: Source system that owns the review.
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

    # 2. Enqueue webhook deliveries for all active configs
    #    (source_system filtering happens per webhook config)
    try:
        from app.core.database import async_session_factory
        from app.models.schema import WebhookConfig
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(
                select(WebhookConfig).where(WebhookConfig.is_active == True)
            )
            configs = result.scalars().all()

        # Import arq pool lazily to avoid circular imports
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

    # 3. Enqueue per-review callback delivery when review reaches COMPLETE state
    if new_state == "COMPLETE":
        try:
            from app.main import app
            from app.models.schema import Review

            async with async_session_factory() as session:
                review = await session.get(Review, review_id)
                if review and review.callback_url:
                    _arq_pool = app.state.arq_pool
                    if _arq_pool:
                        await _arq_pool.enqueue_job(
                            "deliver_review_callback",
                            review_id,
                            event_data,
                        )
        except Exception as e:
            logger.error("callback_enqueue_failed", error=str(e))
