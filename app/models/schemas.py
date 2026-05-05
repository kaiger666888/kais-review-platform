from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field


# --- Enums ---


class ReviewState(str, Enum):
    PENDING = "PENDING"
    POLICY_EVAL = "POLICY_EVAL"
    APPROVING = "APPROVING"
    COMPLETE = "COMPLETE"


class Disposition(str, Enum):
    AUTO = "AUTO"
    HUMAN = "HUMAN"
    AI_AUDIT = "AI_AUDIT"
    BLOCK = "BLOCK"


# --- Request Models ---


class ReviewCreateRequest(BaseModel):
    type: str = Field(min_length=1, max_length=50)
    content_ref: str = Field(min_length=1)
    metadata: dict | None = None
    source_system: str = Field(min_length=1)
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|critical)$")
    risk_score: float | None = Field(default=None, ge=0.0, le=1.0)


class ApproveRequest(BaseModel):
    comment: str | None = None


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class TokenRequest(BaseModel):
    api_key: str
    client_id: str


class PolicyCreateRequest(BaseModel):
    name: str
    content: str


class PolicyUpdateRequest(BaseModel):
    content: str


class WebhookCreateRequest(BaseModel):
    url: str = Field(min_length=1)
    secret: str = Field(min_length=1)
    source_system: str = Field(min_length=1)


class WebhookUpdateRequest(BaseModel):
    url: str | None = None
    secret: str | None = None
    source_system: str | None = None
    is_active: bool | None = None


class WebhookResponse(BaseModel):
    id: int
    url: str
    secret: str
    source_system: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Response Models ---


class ReviewResponse(BaseModel):
    id: int
    type: str
    content_ref: str
    metadata: dict | None
    source_system: str
    priority: str
    risk_score: float | None
    state: str
    disposition: str | None
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewSubmitResponse(BaseModel):
    review_id: int
    state: str
    routing: str | None


class AuditEntryResponse(BaseModel):
    id: int
    review_id: int
    action: str
    actor: str
    from_state: str | None
    to_state: str | None
    payload: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PolicyResponse(BaseModel):
    name: str
    version: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


# --- Generic Envelope Models ---

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: int | None
    has_more: bool


class ApiResponse(BaseModel, Generic[T]):
    data: T | None = None
    meta: dict | None = None
    error: ErrorResponse | None = None
