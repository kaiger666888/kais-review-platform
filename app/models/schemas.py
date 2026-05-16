import enum
from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field


# --- Legacy Enum (kept for backward compat with app/core/policy.py) ---


class Disposition(str, enum.Enum):
    """Routing disposition for review decisions.

    Mirrors RoutingDecision in shot_card.py. Kept here for backward
    compatibility with the V1 policy engine (app/core/policy.py).
    """

    AUTO = "AUTO"
    HUMAN = "HUMAN"
    AI_AUDIT = "AI_AUDIT"
    BLOCK = "BLOCK"


# --- Nested Structure Models (JSONB validation) ---


class Keyframe(BaseModel):
    url: str
    hash: str
    node: str


class Keyframes(BaseModel):
    first: Keyframe | None = None
    last: Keyframe | None = None


class VideoClip(BaseModel):
    url: str
    duration: float
    node: str


class Candidate(BaseModel):
    candidate_id: str
    keyframes: Keyframes
    score: float | None = None


class VisualBundle(BaseModel):
    keyframes: Keyframes | None = None
    video_clip: VideoClip | None = None
    prompt: str | None = None
    candidates: list[Candidate] = Field(default_factory=list)


class AudioBundle(BaseModel):
    bgm_prompt: str | None = None
    sfx_prompt: str | None = None
    status: Literal["pending", "ready", "failed"] = "pending"


class NarrativeContext(BaseModel):
    scene: str
    shot_number: int
    emotion_curve: str
    continuity_tags: list[str] = Field(default_factory=list)


class AuditStatePydantic(BaseModel):
    status: Literal["awaiting_audit", "approved", "rejected", "pending_audio"]
    routing_decision: Literal["AUTO", "HUMAN", "AI_AUDIT", "BLOCK"] | None = None
    min_audit_set: list[str] = Field(default_factory=lambda: ["visual_bundle"])
    blocking_reason: str | None = None


class Provenance(BaseModel):
    workflow_version: str | None = None
    policy_commit_sha: str | None = None
    execution_id: str | None = None


# --- Request Models ---


class ShotCardCreate(BaseModel):
    shot_id: str = Field(min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    narrative_context: NarrativeContext
    visual_bundle: VisualBundle | None = None
    audio_bundle: AudioBundle | None = None
    audit_state: AuditStatePydantic | None = None
    provenance: Provenance | None = None


# --- Response Models ---


class ShotCardResponse(BaseModel):
    id: int
    shot_id: str
    project_id: str
    narrative_context: dict
    visual_bundle: dict | None
    audio_bundle: dict | None
    audit_status: str
    routing_decision: str | None
    min_audit_set: list | None
    blocking_reason: str | None
    workflow_version: str | None
    policy_commit_sha: str | None
    execution_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AuditEntryResponse(BaseModel):
    id: int
    shot_card_id: int
    action: str
    actor: str
    from_state: str | None
    to_state: str | None
    payload: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


# --- Batch Operation Models ---


class BatchApproveRequest(BaseModel):
    review_ids: list[int] = Field(min_length=1, max_length=100)
    comment: str | None = None


class BatchRejectRequest(BaseModel):
    review_ids: list[int] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)


class BatchItemResult(BaseModel):
    review_id: int
    status: str  # "success" or "failed"
    error: str | None = None


class BatchResponse(BaseModel):
    total: int
    success_count: int
    failure_count: int
    items: list[BatchItemResult]


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
