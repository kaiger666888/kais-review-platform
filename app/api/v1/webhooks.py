"""Webhook configuration CRUD API.

Provides endpoints for managing webhook targets that external systems
(kais-movie-agent, kais-gold-team) register to receive event notifications.

POST   /api/v1/webhooks/           -- Create webhook config
GET    /api/v1/webhooks/           -- List webhook configs (with source_system filter)
GET    /api/v1/webhooks/{id}       -- Get single webhook config
PUT    /api/v1/webhooks/{id}       -- Update webhook config
DELETE /api/v1/webhooks/{id}       -- Delete webhook config
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def _webhook_response(config: WebhookConfig) -> WebhookResponse:
    """Convert a WebhookConfig ORM object to a WebhookResponse."""
    return WebhookResponse.model_validate(config)


# ---------------------------------------------------------------------------
# POST / -- Create webhook config
# ---------------------------------------------------------------------------


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[WebhookResponse],
)
async def create_webhook(
    request: WebhookCreateRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Create a new webhook configuration.

    Registers a target URL that will receive event notifications for
    the specified source_system.
    """
    config = WebhookConfig(
        url=request.url,
        secret=request.secret,
        source_system=request.source_system,
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    return ApiResponse(
        data=_webhook_response(config).model_dump(),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# GET / -- List webhook configs
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=ApiResponse[list[WebhookResponse]],
)
async def list_webhooks(
    source_system: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """List all webhook configurations, optionally filtered by source_system."""
    query = select(WebhookConfig).order_by(WebhookConfig.id.desc())

    if source_system:
        query = query.where(WebhookConfig.source_system == source_system)

    result = await db.execute(query)
    configs = result.scalars().all()

    return ApiResponse(
        data=[_webhook_response(c).model_dump() for c in configs],
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# GET /{webhook_id} -- Get single webhook
# ---------------------------------------------------------------------------


@router.get(
    "/{webhook_id}",
    response_model=ApiResponse[WebhookResponse],
)
async def get_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Get a single webhook configuration by ID."""
    config = await db.get(WebhookConfig, webhook_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook {webhook_id} not found",
        )

    return ApiResponse(
        data=_webhook_response(config).model_dump(),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# PUT /{webhook_id} -- Update webhook
# ---------------------------------------------------------------------------


@router.put(
    "/{webhook_id}",
    response_model=ApiResponse[WebhookResponse],
)
async def update_webhook(
    webhook_id: int,
    request: WebhookUpdateRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Update a webhook configuration. Only non-None fields are updated."""
    config = await db.get(WebhookConfig, webhook_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook {webhook_id} not found",
        )

    # Partial update: only set fields that are not None
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

    return ApiResponse(
        data=_webhook_response(config).model_dump(),
        meta={"request_id": _request_id()},
    )


# ---------------------------------------------------------------------------
# DELETE /{webhook_id} -- Delete webhook
# ---------------------------------------------------------------------------


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Delete a webhook configuration."""
    config = await db.get(WebhookConfig, webhook_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook {webhook_id} not found",
        )

    await db.delete(config)
    await db.commit()
