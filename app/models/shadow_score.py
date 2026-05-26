"""ShadowScore SQLAlchemy model.

Records AI scores alongside human decisions for shadow mode evaluation.
Phase 0: scores come from NullScoringPlugin (all None dimensions).
"""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ShadowScore(Base):
    __tablename__ = "shadow_scores"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    shot_card_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shot_cards.id"), nullable=False
    )
    shot_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    score_vector: Mapped[dict] = mapped_column(JSON, nullable=False)
    human_decision: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_shadow_shot_created", "shot_card_id", created_at.desc()),
        Index("ix_shadow_shot_id", "shot_id"),
    )
