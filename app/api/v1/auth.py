"""Auth API endpoints: API key to JWT token exchange."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import create_jwt, Role
from app.core.config import Settings, get_settings
from app.models.schemas import TokenRequest

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token")
async def exchange_api_key(
    request: TokenRequest,
    settings: Settings = Depends(get_settings),
):
    """Exchange a static API key for a short-lived JWT token with role claim."""
    if request.api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Validate requested role against Role enum
    valid_roles = {r.value for r in Role}
    if request.role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{request.role}'. Must be one of: {sorted(valid_roles)}",
        )

    token = create_jwt(request.client_id, settings.jwt_secret, role=request.role)

    return {
        "data": {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": 900,
        }
    }
