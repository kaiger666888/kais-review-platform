"""SSE stream endpoint for real-time review status updates.

Provides GET /api/v1/events/stream -- a Server-Sent Events endpoint that
pushes review_status events to connected browsers without polling.
Connections are JWT-authenticated and cleaned up on disconnect.
"""

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.core.auth import get_current_client
from app.core.events import event_manager

router = APIRouter(tags=["events"])


async def _event_generator(request: Request, client: str):
    """Generate SSE events for a single connection.

    Yields review_status events when broadcast, or heartbeat comments
    every 30 seconds to detect zombie connections.
    """
    queue = event_manager.create_connection()
    try:
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield ServerSentEvent(
                    data=json.dumps(data),
                    event="review_status",
                )
            except asyncio.TimeoutError:
                # Send heartbeat comment to detect zombie connections
                yield ServerSentEvent(comment="heartbeat")
    finally:
        event_manager.remove_connection(queue)


@router.get("/api/v1/events/stream")
async def sse_stream(
    request: Request,
    client: str = Depends(get_current_client),
):
    """SSE endpoint for real-time review status updates.

    Requires JWT authentication. Yields review_status events when
    review state changes occur, with heartbeat comments every 30s.
    Zombie connections are cleaned up via request.is_disconnected()
    and the 30s heartbeat timeout.
    """
    return EventSourceResponse(_event_generator(request, client))
