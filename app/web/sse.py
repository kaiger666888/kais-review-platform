"""Cookie-auth SSE stream endpoint for template routes.

Provides GET /events/stream -- a Server-Sent Events endpoint that
reads JWT from httpOnly cookie (not Bearer header) so the browser
EventSource API can connect without custom headers.

This is the template-route counterpart to /api/v1/events/stream
which requires Bearer JWT auth. Both share the same event_manager
singleton and broadcast pipeline.

FastAPI 0.136 pattern: async generator yielding ServerSentEvent with
response_class=EventSourceResponse on the route decorator.
"""

import asyncio
import json

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.core.auth import AuthenticationError, decode_jwt
from app.core.config import get_settings
from app.core.events import event_manager

router = APIRouter(tags=["sse"])


@router.get("/events/stream", response_class=EventSourceResponse)
async def sse_stream(
    request: Request,
    access_token: str | None = Cookie(None),
):
    """SSE endpoint for real-time review status updates (cookie auth).

    Reads JWT from httpOnly cookie set during one-time token exchange.
    EventSource API cannot set Bearer headers, so cookie auth is required
    for browser-initiated SSE connections.

    Yields review_status events when review state changes occur.
    FastAPI inserts keep-alive pings automatically every 15s.
    """
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    settings = get_settings()
    try:
        decode_jwt(access_token, settings.jwt_secret)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

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
