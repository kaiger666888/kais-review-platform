"""ABTestPair SQLAlchemy model.

Stores A/B test pairs for comparing AI scoring against human decisions.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Index, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ABTestPair(Base):
    __tablename__ = "ab_test_pairs"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    shot_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ai_score: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    human_decision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_ab_batch_created", "batch_id", created_at.desc()),
        Index("ix_ab_batch_id", "batch_id"),
    )
