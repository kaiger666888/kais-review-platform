"""SSE event manager for real-time review status updates.

Provides a singleton EventManager that maintains per-connection asyncio.Queue
instances for broadcasting review_status events to connected SSE clients.
"""

import asyncio

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
