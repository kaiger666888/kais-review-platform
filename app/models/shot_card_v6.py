"""V6.0 ShotCard model — minimal review API.

Extends the V2 ShotCard with:
- Five-dimension ScoreVector (aesthetics/consistency/compliance/technical_quality/audio_match)
- Pipeline phase tracking
- File-path asset_url / thumbnail_url (non-HTTP references)
- Flexible metadata JSONB for pipeline context
- callback_url for movie-agent notification
"""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ShotCardStatus(str, enum.Enum):
    """V6.0 card status lifecycle."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PipelinePhase(str, enum.Enum):
    """Pipeline phases for the V6.0 quality-gate."""
    STORYBOARD = "storyboard"
    CHARACTER = "character"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    COMPOSE = "compose"


class Priority(str, enum.Enum):
    NORMAL = "normal"
    URGENT = "urgent"


class ShotCardV6(Base):
    """V6.0 ShotCard — lightweight review card for card-flow governance."""
    __tablename__ = "shot_cards_v6"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Natural keys
    project_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    shot_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Pipeline context
    phase: Mapped[str] = mapped_column(
        SAEnum(PipelinePhase, name="pipeline_phase_v6", create_constraint=True),
        nullable=False,
    )
    priority: Mapped[str] = mapped_column(
        SAEnum(Priority, name="priority_v6", create_constraint=True),
        nullable=False,
        default=Priority.NORMAL,
    )

    # Asset references (file paths, not HTTP URLs)
    asset_url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        SAEnum(ShotCardStatus, name="shot_card_status_v6", create_constraint=True),
        nullable=False,
        default=ShotCardStatus.PENDING,
        index=True,
    )

    # Narrative context (flexible JSON)
    narrative_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Five-dimension AI scores (nullable until AI scoring runs)
    score_aesthetics: Mapped[float | None] = mapped_column(nullable=True)
    score_consistency: Mapped[float | None] = mapped_column(nullable=True)
    score_compliance: Mapped[float | None] = mapped_column(nullable=True)
    score_technical_quality: Mapped[float | None] = mapped_column(nullable=True)
    score_audio_match: Mapped[float | None] = mapped_column(nullable=True)

    # Review metadata
    reviewer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reject_comment: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Callback for movie-agent notification
    callback_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    callback_sent: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Flexible pipeline context
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_sc_v6_project_status", "project_id", "status"),
        Index("ix_sc_v6_phase_status", "phase", "status"),
        Index("ix_sc_v6_project_created", "project_id", "created_at"),
    )
