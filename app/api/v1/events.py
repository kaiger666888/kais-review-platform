"""SSE stream endpoint for real-time review status updates.

Provides GET /api/v1/events/stream -- a Server-Sent Events endpoint that
pushes review_status events to connected browsers without polling.
Connections are JWT-authenticated and cleaned up on disconnect.

FastAPI 0.136 pattern: async generator yielding ServerSentEvent with
response_class=EventSourceResponse on the route decorator. FastAPI handles
SSE wire-format encoding and inserts keep-alive pings automatically.
"""

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.core.auth import get_current_client
from app.core.events import event_manager

router = APIRouter(tags=["events"])


@router.get("/api/v1/events/stream", response_class=EventSourceResponse)
async def sse_stream(
    request: Request,
    client: str = Depends(get_current_client),
):
    """SSE endpoint for real-time review status updates.

    Requires JWT authentication. Yields review_status events when
    review state changes occur. FastAPI inserts keep-alive pings
    automatically every 15s. Connections are cleaned up when the
    generator exits (client disconnect or queue.get cancelled).
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
