"""Capability token verification endpoint.

POST /api/v1/tokens/verify -- Verify a capability token for downstream execution gating.
"""

from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request

from app.core.auth import verify_capability_token
from app.core.config import Settings, get_settings
from app.models.schemas import ApiResponse

router = APIRouter(prefix="/api/v1/tokens", tags=["tokens"])


class TokenVerifyRequest(BaseModel):
    """Request body for token verification."""

    token: str


class TokenVerifyResponse(BaseModel):
    """Response for capability token verification."""

    valid: bool
    shot_id: str | None = None
    node_scope: list[str] | None = None
    expires_at: str | None = None
    reason: str | None = None


@router.post("/verify", response_model=ApiResponse[TokenVerifyResponse])
async def verify_token(
    request: TokenVerifyRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
):
    """Verify a capability token.

    Validates the JWT signature, checks expiration, and enforces
    single-use semantics via Redis key deletion. Returns structured
    response indicating whether the token is valid.
    """
    redis = getattr(http_request.app.state, "redis", None)
    if redis is None:
        return ApiResponse(
            data=TokenVerifyResponse(
                valid=False,
                reason="service_unavailable",
            )
        )

    result = await verify_capability_token(
        redis=redis,
        token=request.token,
        secret=settings.capability_token_secret,
    )
    return ApiResponse(data=TokenVerifyResponse(**result))
