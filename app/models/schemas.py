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


# --- Review State Machine Enum (V1 compatibility) ---


class ReviewState(str, enum.Enum):
    """Review lifecycle states for the V1 state machine.

    Used by state_machine.py, approval_router.py, and API endpoints
    that still operate on the Review model.
    """

    PENDING = "PENDING"
    POLICY_EVAL = "POLICY_EVAL"
    APPROVING = "APPROVING"
    COMPLETE = "COMPLETE"


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


# --- V1 Legacy Request Models (backward compat) ---


class ReviewCreateRequest(BaseModel):
    type: str = Field(min_length=1, max_length=50)
    content_ref: str = Field(min_length=1)
    metadata: dict | None = None
    source_system: str = Field(min_length=1)
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|critical)$")
    risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    callback_url: str | None = Field(default=None, min_length=1)
    callback_secret: str | None = Field(default=None, min_length=1)


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


class PolicyResponse(BaseModel):
    name: str
    version: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- V2 Request Models ---


class ShotCardCreate(BaseModel):
    shot_id: str = Field(min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    narrative_context: NarrativeContext
    visual_bundle: VisualBundle | None = None
    audio_bundle: AudioBundle | None = None
    audit_state: AuditStatePydantic | None = None
    provenance: Provenance | None = None


# --- V1 Legacy Response Models (backward compat) ---


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
    callback_url: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewSubmitResponse(BaseModel):
    review_id: int
    state: str
    routing: str | None


class ReviewTokenResponse(BaseModel):
    token: str
    review_url: str
    expires_at: datetime


# --- V2 Response Models ---


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
    shot_card_id: int | None = None
    review_id: int | None = None
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


# --- A/B Test Models ---


class ABTestCreateRequest(BaseModel):
    """Request body for creating an A/B test batch."""

    shot_ids: list[str] = Field(min_length=1, max_length=100)


class ABTestCreateResponse(BaseModel):
    """Response for A/B test batch creation."""

    batch_id: str
    total: int


class ABTestPairResponse(BaseModel):
    """Response for a single A/B test pair."""

    id: int
    batch_id: str
    shot_id: str
    ai_score: dict | None
    human_decision: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Shot Card Action Models ---


class ApproveRequest(BaseModel):
    """V1 legacy approve request — kept for backward compat with actions.py."""
    comment: str | None = None


class RejectRequest(BaseModel):
    """V1 legacy reject request — kept for backward compat with actions.py."""
    reason: str = Field(min_length=1, max_length=500)


class ShotCardApproveRequest(BaseModel):
    comment: str | None = None


class ShotCardRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


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


# --- Mobile Bundle Models ---


class MobileShotCardBundle(BaseModel):
    """Mobile-optimized Shot Card bundle with flat fields extracted from nested JSONB.

    Denormalizes narrative_context, visual_bundle, and audio_bundle into
    flat fields for easy consumption by mobile clients (no nested traversal).
    """

    id: int
    shot_id: str
    project_id: str
    scene: str
    shot_number: int
    emotion_curve: str
    continuity_tags: list[str]
    first_frame_url: str | None = None
    last_frame_url: str | None = None
    video_url: str | None = None
    visual_prompt: str | None = None
    candidates: list[dict] | None = None
    audio_status: str = "pending"
    bgm_prompt: str | None = None
    sfx_prompt: str | None = None
    audit_status: str
    routing_decision: str | None = None

    model_config = {"from_attributes": True}


class MobileAudioBundle(BaseModel):
    """Audio bundle data for async progressive loading on mobile.

    Mobile clients load visual content first, then fetch audio data
    via a separate endpoint to reduce initial payload size.
    """

    shot_card_id: int
    audio_status: str
    bgm_prompt: str | None = None
    sfx_prompt: str | None = None

    model_config = {"from_attributes": True}


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
