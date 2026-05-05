"""JWT authentication and one-time review token management."""

import secrets
from datetime import datetime, timezone, timedelta

import jwt
import redis.asyncio as aioredis
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import Settings, get_settings


class AuthenticationError(Exception):
    """Raised when JWT token validation fails."""
    pass


# --- JWT Functions ---


def create_jwt(client_id: str, jwt_secret: str, expires_minutes: int = 15) -> str:
    """Create a short-lived JWT token with client claim."""
    now = datetime.now(timezone.utc)
    payload = {
        "client": client_id,
        "exp": now + timedelta(minutes=expires_minutes),
        "iat": now,
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


def decode_jwt(token: str, jwt_secret: str) -> dict:
    """Decode and validate a JWT token. Raises AuthenticationError on failure."""
    try:
        return jwt.decode(token, jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token expired")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid token")


# --- FastAPI Auth Dependencies ---


security = HTTPBearer()


async def require_jwt(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
) -> dict:
    """FastAPI dependency that validates Bearer JWT and returns payload dict."""
    try:
        payload = decode_jwt(credentials.credentials, settings.jwt_secret)
    except AuthenticationError as e:
        if "expired" in str(e).lower():
            raise HTTPException(status_code=401, detail="Token expired")
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


async def get_current_client(payload: dict = Depends(require_jwt)) -> str:
    """Extract client identity from validated JWT payload."""
    return payload["client"]


# --- One-Time Review Tokens (Redis-backed) ---


LUA_CONSUME_TOKEN = """
if redis.call("GET", KEYS[1]) then
    local val = redis.call("GET", KEYS[1])
    redis.call("DEL", KEYS[1])
    return val
else
    return nil
end
"""


async def create_review_token(
    redis: aioredis.Redis, review_id: int, ttl: int = 259200
) -> str:
    """Create a one-time review token stored in Redis with TTL.

    Args:
        redis: Async Redis connection.
        review_id: The review ID this token grants access to.
        ttl: Time-to-live in seconds (default 72 hours).

    Returns:
        The generated token string (43+ chars, base64-encoded).
    """
    token = secrets.token_urlsafe(32)
    key = f"review_token:{token}"
    await redis.set(key, str(review_id), ex=ttl)
    return token


async def consume_review_token(
    redis: aioredis.Redis, token: str
) -> str | None:
    """Atomically consume a one-time review token.

    Uses a Lua script to perform GET + DEL atomically, preventing
    double-use race conditions.

    Args:
        redis: Async Redis connection.
        token: The token string to consume.

    Returns:
        The review_id string if token was valid, None if already consumed or expired.
    """
    consume = redis.register_script(LUA_CONSUME_TOKEN)
    result = await consume(keys=[f"review_token:{token}"])
    return result
