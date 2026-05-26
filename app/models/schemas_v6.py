"""V6.0 Pydantic schemas for ShotCard minimal review API.

Aligned with review-platform.openapi.yaml V6.0.0 spec.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ─── ScoreVector ──────────────────────────────────────

class ScoreVector(BaseModel):
    """Five-dimension quality scores (0-100)."""
    aesthetics: float | None = Field(None, ge=0, le=100, description="美学")
    consistency: float | None = Field(None, ge=0, le=100, description="一致性")
    compliance: float | None = Field(None, ge=0, le=100, description="合规")
    technical_quality: float | None = Field(None, ge=0, le=100, description="技术质量")
    audio_match: float | None = Field(None, ge=0, le=100, description="音画匹配")


# ─── Create ───────────────────────────────────────────

class CreateShotCardRequest(BaseModel):
    """POST /api/v1/shot-cards — create a review card."""
    project_id: str = Field(..., min_length=1, max_length=100)
    shot_id: str = Field(..., min_length=1, max_length=100)
    phase: Literal["storyboard", "character", "image", "video", "audio", "compose"]
    asset_url: str = Field(..., min_length=1, max_length=500)
    thumbnail_url: str | None = Field(None, max_length=500)
    narrative_context: dict | None = None
    ai_scores: ScoreVector | None = None
    priority: Literal["normal", "urgent"] = "normal"
    metadata: dict | None = None
    callback_url: str | None = Field(None, max_length=500)


# ─── Response ─────────────────────────────────────────

class ShotCardResponse(BaseModel):
    """Full ShotCard detail response."""
    id: int
    project_id: str
    shot_id: str
    phase: str
    status: str
    asset_url: str
    thumbnail_url: str | None = None
    narrative_context: dict | None = None
    ai_scores: ScoreVector | None = None
    priority: str = "normal"
    reviewer_id: str | None = None
    reviewed_at: datetime | None = None
    reject_reason: str | None = None
    reject_comment: str | None = None
    metadata: dict | None = None
    callback_sent: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShotCardSummary(BaseModel):
    """Lightweight summary for list queries — includes thumbnail for mobile."""
    id: int
    project_id: str
    shot_id: str
    phase: str
    status: str
    thumbnail_url: str | None = None
    priority: str = "normal"
    ai_score_overall: float | None = Field(None, description="五维均分")
    created_at: datetime

    model_config = {"from_attributes": True}


class ShotCardListResponse(BaseModel):
    """Paginated list response."""
    items: list[ShotCardSummary]
    total: int
    limit: int
    offset: int


# ─── Approval / Rejection ────────────────────────────

class ApprovalRequest(BaseModel):
    """POST /api/v1/shot-cards/{id}/approve — mobile-friendly."""
    comment: str | None = None
    scores_override: dict[str, float] | None = Field(
        None, description="治理端覆盖评分（可选）"
    )
    tags: list[str] | None = None


class RejectionRequest(BaseModel):
    """POST /api/v1/shot-cards/{id}/reject — reason is required."""
    reason: Literal[
        "character_drift", "quality_issue", "continuity_error", "compliance", "other"
    ]
    comment: str | None = None
    suggested_action: Literal[
        "regenerate", "adjust_params", "use_alternate"
    ] | None = None
    reject_dimensions: list[
        Literal[
            "aesthetics", "consistency", "compliance",
            "technical_quality", "audio_match"
        ]
    ] | None = None
    priority: Literal["normal", "urgent"] = "normal"


class ReviewResult(BaseModel):
    """Response for approve/reject actions."""
    id: str
    status: str
    reviewer_id: str | None = None
    reviewed_at: datetime | None = None
    callback_sent: bool = False
    audit_entry_id: str | None = None


# ─── Batch ────────────────────────────────────────────

class BatchApprovalRequest(BaseModel):
    """POST /api/v1/shot-cards/batch/approve."""
    card_ids: list[int] = Field(..., min_length=1, max_length=100)
    comment: str | None = None


class BatchRejectionRequest(BaseModel):
    """POST /api/v1/shot-cards/batch/reject."""
    card_ids: list[int] = Field(..., min_length=1, max_length=100)
    reason: Literal[
        "character_drift", "quality_issue", "continuity_error", "compliance", "other"
    ]
    comment: str | None = None
    suggested_action: Literal[
        "regenerate", "adjust_params", "use_alternate"
    ] | None = None


class BatchItemResult(BaseModel):
    """Single item result in batch response."""
    card_id: int
    status: Literal["approved", "rejected", "error"]
    error: str | None = None


class BatchReviewResult(BaseModel):
    """Batch operation response."""
    total: int
    succeeded: int
    failed: int
    results: list[BatchItemResult]


# ─── Callback ─────────────────────────────────────────

class ReviewCallbackItem(BaseModel):
    """Per-shot callback payload."""
    shot_id: str
    decision: Literal["approved", "rejected"]
    reviewer: str | None = None
    reviewer_role: str | None = None
    reviewed_at: datetime | None = None
    scores: ScoreVector | None = None
    reject_reason: str | None = None
    reject_dimensions: list[str] | None = None
    suggested_action: str | None = None


class ReviewCallbackPayload(BaseModel):
    """POST callback_url payload — aligns with callback-schemas.json ReviewCallback."""
    review_id: str
    pipeline_id: str | None = None
    phase: str
    decision: Literal["approved", "rejected", "needs_revision", "auto_approved"]
    items: list[ReviewCallbackItem]
    audit_entry_ids: list[str] | None = None
    merkle_leaf_hash: str | None = None
    signature: str | None = None
    timestamp: datetime
