"""Template auth: cookie-based JWT and one-time token deep link route."""

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.core.auth import consume_review_token, create_jwt, decode_jwt, AuthenticationError
from app.core.config import get_settings
from app.core.dependencies import get_redis

router = APIRouter()


async def get_template_user(
    access_token: str | None = Cookie(None),
) -> str:
    """FastAPI dependency: read JWT from httpOnly cookie, return client identity."""
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    settings = get_settings()
    try:
        payload = decode_jwt(access_token, settings.jwt_secret)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload.get("client", "unknown")


@router.get("/t/{token}")
async def token_deep_link(token: str, request: Request):
    """One-time token deep link: validate token, set JWT cookie, redirect to dashboard.

    If token is valid: create JWT, set httpOnly cookie, redirect to /?detail={review_id}.
    If token is invalid/expired: redirect to /?toast=token_expired.
    """
    settings = get_settings()
    redis = get_redis(request)

    if redis is None:
        return RedirectResponse(url="/?toast_error=Service+unavailable", status_code=303)

    review_id = await consume_review_token(redis, token)

    if review_id is None:
        # Token expired or already used
        return RedirectResponse(url="/?toast=token_expired", status_code=303)

    # Create JWT and set as httpOnly cookie
    jwt_token = create_jwt("reviewer", settings.jwt_secret, expires_minutes=15)
    response = RedirectResponse(
        url=f"/?detail={review_id}",
        status_code=303,
    )
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        max_age=900,  # 15 minutes
        samesite="lax",
    )
    return response
