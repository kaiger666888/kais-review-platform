"""Template auth: cookie-based JWT, login page, and one-time token deep link route."""

from fastapi import APIRouter, Cookie, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.auth import consume_review_token, create_jwt, decode_jwt, AuthenticationError
from app.core.config import get_settings
from app.core.dependencies import get_redis

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


async def get_template_user(
    access_token: str | None = Cookie(None),
) -> dict:
    """Return user info. No auth required for local use."""
    if access_token:
        settings = get_settings()
        try:
            payload = decode_jwt(access_token, settings.jwt_secret)
            return {
                "client": payload.get("client", "unknown"),
                "role": payload.get("role", "reviewer"),
            }
        except AuthenticationError:
            pass
    return {"client": "local", "role": "admin"}


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    """Render login form page."""
    return templates.TemplateResponse(request, "pages/login.html", {
        "error": error,
    })


@router.post("/login")
async def login_submit(request: Request, api_key: str = Form("")):
    """Validate API key, set JWT cookie, redirect to dashboard.

    If api_key is not configured (empty string), any login is accepted.
    If api_key is configured, it must match the submitted value.
    """
    settings = get_settings()
    if settings.api_key and api_key != settings.api_key:
        return templates.TemplateResponse(request, "pages/login.html", {
            "error": "Invalid API key",
        }, status_code=200)
    jwt_token = create_jwt("admin", settings.jwt_secret, expires_minutes=1440, role="admin")
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        max_age=86400,
        samesite="lax",
    )
    return response


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
    jwt_token = create_jwt("reviewer", settings.jwt_secret, expires_minutes=1440, role="reviewer")
    response = RedirectResponse(
        url=f"/?detail={review_id}",
        status_code=303,
    )
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        max_age=86400,
        samesite="lax",
    )
    return response
