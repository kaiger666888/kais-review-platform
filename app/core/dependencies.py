"""Shared FastAPI dependencies.

Provides Redis and arq pool accessors from app state without
creating circular imports between main.py and route modules.
"""

from fastapi import Request


def get_redis(request: Request):
    """Return the Redis connection from app state."""
    return request.app.state.redis


def get_arq_pool(request: Request):
    """Return the arq connection pool from app state."""
    return request.app.state.arq_pool
