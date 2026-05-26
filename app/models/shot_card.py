import enum
from datetime import datetime

from sqlalchemy import BigInteger, Index, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditStatus(str, enum.Enum):
    AWAITING_AUDIT = "awaiting_audit"
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING_AUDIO = "pending_audio"


class RoutingDecision(str, enum.Enum):
    AUTO = "AUTO"
    HUMAN = "HUMAN"
    AI_AUDIT = "AI_AUDIT"
    BLOCK = "BLOCK"


class ShotCard(Base):
    __tablename__ = "shot_cards"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shot_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    project_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Nested structures as JSON
    narrative_context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    visual_bundle: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    audio_bundle: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Status fields as PostgreSQL ENUMs
    audit_status: Mapped[str] = mapped_column(
        SAEnum(AuditStatus, name="audit_status", create_constraint=True),
        nullable=False,
        default=AuditStatus.AWAITING_AUDIT,
    )
    routing_decision: Mapped[str | None] = mapped_column(
        SAEnum(RoutingDecision, name="routing_decision", create_constraint=True),
        nullable=True,
    )
    min_audit_set: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    blocking_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Provenance fields
    workflow_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_shot_cards_project_created", "project_id", "created_at"),
        Index("ix_shot_cards_status_created", "audit_status", "created_at"),
        Index(
            "ix_shot_cards_narrative_gin",
            "narrative_context",
            postgresql_using="gin",
            postgresql_ops={"narrative_context": "jsonb_path_ops"},
        ),
        Index(
            "ix_shot_cards_visual_gin",
            "visual_bundle",
            postgresql_using="gin",
            postgresql_ops={"visual_bundle": "jsonb_path_ops"},
        ),
    )
