"""Policy CRUD API with version tracking and audit logging.

Endpoints for creating, reading, updating, and deleting YAML policies.
All mutations are validated via JSON Schema and logged to the audit trail.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import append_audit
from app.core.database import get_db
from app.core.policy import PolicyEngine, PolicyValidationError, get_policy_engine
from app.models.schema import PolicyVersion
from app.models.schemas import (
    ApiResponse,
    PolicyCreateRequest,
    PolicyResponse,
    PolicyUpdateRequest,
)

router = APIRouter(prefix="/api/v1/policies", tags=["policies"])


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def get_policy_engine_dependency() -> PolicyEngine:
    """FastAPI dependency that returns the global PolicyEngine."""
    return get_policy_engine()


async def get_current_client() -> str:
    """Placeholder auth dependency -- returns client identity.

    Will be replaced with proper JWT validation once the auth module
    is implemented (Plan 02).
    """
    return "system"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _policy_response(pv: PolicyVersion) -> PolicyResponse:
    """Convert a PolicyVersion ORM object to a PolicyResponse."""
    return PolicyResponse(
        name=pv.name,
        version=pv.version,
        is_active=pv.is_active,
        created_at=pv.created_at,
        updated_at=pv.updated_at,
    )


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def _increment_version(version: str) -> str:
    """Increment a 'X.Y' version string to 'X.(Y+1)'."""
    parts = version.split(".")
    major = int(parts[0]) if len(parts) > 0 else 1
    minor = int(parts[1]) if len(parts) > 1 else 0
    return f"{major}.{minor + 1}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", response_model=ApiResponse[list[PolicyResponse]])
async def list_policies(
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """List all active policies."""
    stmt = (
        select(PolicyVersion)
        .where(PolicyVersion.is_active == True)  # noqa: E712
        .order_by(PolicyVersion.name)
    )
    result = await db.execute(stmt)
    policies = result.scalars().all()

    return ApiResponse(
        data=[_policy_response(pv).model_dump() for pv in policies],
        meta={"request_id": _request_id()},
    )


@router.get("/{name}", response_model=ApiResponse[PolicyResponse])
async def get_policy(
    name: str,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
):
    """Get a specific active policy by name."""
    stmt = select(PolicyVersion).where(
        PolicyVersion.name == name,
        PolicyVersion.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    pv = result.scalar_one_or_none()

    if pv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy '{name}' not found",
        )

    return ApiResponse(
        data=_policy_response(pv).model_dump(),
        meta={"request_id": _request_id()},
    )


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[PolicyResponse],
)
async def create_policy(
    request: PolicyCreateRequest,
    db: AsyncSession = Depends(get_db),
    engine: PolicyEngine = Depends(get_policy_engine_dependency),
    client: str = Depends(get_current_client),
):
    """Create a new policy after JSON Schema validation."""
    # Validate the YAML content
    try:
        engine.validate_policy(request.content)
    except PolicyValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # Check for existing active policy with same name
    stmt = select(PolicyVersion).where(
        PolicyVersion.name == request.name,
        PolicyVersion.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Policy '{request.name}' already exists",
        )

    # Create PolicyVersion record
    pv = PolicyVersion(
        name=request.name,
        version="1.0",
        content=request.content,
        is_active=True,
    )
    db.add(pv)
    await db.commit()
    await db.refresh(pv)

    # Load into in-memory engine
    engine.load_policy(request.name, request.content)

    # Audit trail
    await append_audit(
        db,
        review_id=0,
        action="policy_create",
        actor=f"client:{client}",
        payload={"policy_name": request.name},
    )

    return ApiResponse(
        data=_policy_response(pv).model_dump(),
        meta={"request_id": _request_id()},
    )


@router.put("/{name}", response_model=ApiResponse[PolicyResponse])
async def update_policy(
    name: str,
    request: PolicyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    engine: PolicyEngine = Depends(get_policy_engine_dependency),
    client: str = Depends(get_current_client),
):
    """Update an existing policy with version increment."""
    # Validate new content
    try:
        engine.validate_policy(request.content)
    except PolicyValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # Find current active policy
    stmt = select(PolicyVersion).where(
        PolicyVersion.name == name,
        PolicyVersion.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    old = result.scalar_one_or_none()

    if old is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy '{name}' not found",
        )

    new_version = _increment_version(old.version)

    # Deactivate old record
    old.is_active = False
    await db.flush()

    # Create new versioned record
    pv = PolicyVersion(
        name=name,
        version=new_version,
        content=request.content,
        is_active=True,
    )
    db.add(pv)
    await db.commit()
    await db.refresh(pv)

    # Reload in-memory engine
    engine.load_policy(name, request.content)

    # Audit trail
    await append_audit(
        db,
        review_id=0,
        action="policy_update",
        actor=f"client:{client}",
        payload={
            "policy_name": name,
            "old_version": old.version,
            "new_version": new_version,
        },
    )

    return ApiResponse(
        data=_policy_response(pv).model_dump(),
        meta={"request_id": _request_id()},
    )


@router.delete("/{name}", response_model=ApiResponse[dict])
async def delete_policy(
    name: str,
    db: AsyncSession = Depends(get_db),
    engine: PolicyEngine = Depends(get_policy_engine_dependency),
    client: str = Depends(get_current_client),
):
    """Deactivate (soft-delete) a policy."""
    stmt = select(PolicyVersion).where(
        PolicyVersion.name == name,
        PolicyVersion.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    pv = result.scalar_one_or_none()

    if pv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy '{name}' not found",
        )

    pv.is_active = False
    await db.commit()

    # Remove from in-memory engine
    engine.remove_policy(name)

    # Audit trail
    await append_audit(
        db,
        review_id=0,
        action="policy_delete",
        actor=f"client:{client}",
        payload={"policy_name": name},
    )

    return ApiResponse(
        data={"deleted": name},
        meta={"request_id": _request_id()},
    )
