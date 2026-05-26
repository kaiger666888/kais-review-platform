from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import PrimaryKeyConstraint

from app.models.base import Base


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(
        BigInteger, autoincrement=True, nullable=False
    )
    shot_card_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shot_cards.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    own_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Composite PK: created_at FIRST for TimescaleDB hypertable partitioning
        PrimaryKeyConstraint("created_at", "id"),
        Index("ix_audit_shot_created", "shot_card_id", created_at.desc()),
        Index("ix_audit_action_created", "action", created_at.desc()),
        Index("ix_audit_actor_created", "actor", created_at.desc()),
    )
