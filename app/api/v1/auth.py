"""Auth API endpoints — deprecated. Inter-service auth removed."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
