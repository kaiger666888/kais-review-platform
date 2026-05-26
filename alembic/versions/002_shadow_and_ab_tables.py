"""Add shadow_scores and ab_test_pairs tables for AI audit Phase 0.

Revision ID: 002_shadow_and_ab
Revises: 001_v2_initial
Create Date: 2026-05-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "002_shadow_and_ab"
down_revision: Union[str, None] = "001_v2_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create shadow_scores table
    op.create_table(
        "shadow_scores",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "shot_card_id", sa.BigInteger(), nullable=False
        ),
        sa.Column("shot_id", sa.String(100), nullable=False),
        sa.Column("score_vector", JSONB, nullable=False),
        sa.Column("human_decision", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["shot_card_id"], ["shot_cards.id"]),
    )

    # Create indexes for shadow_scores
    op.create_index(
        "ix_shadow_shot_created",
        "shadow_scores",
        ["shot_card_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_shadow_shot_id",
        "shadow_scores",
        ["shot_id"],
        unique=False,
    )

    # Create ab_test_pairs table
    op.create_table(
        "ab_test_pairs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("shot_id", sa.String(100), nullable=False),
        sa.Column("ai_score", JSONB, nullable=True),
        sa.Column("human_decision", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for ab_test_pairs
    op.create_index(
        "ix_ab_batch_created",
        "ab_test_pairs",
        ["batch_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_ab_batch_id",
        "ab_test_pairs",
        ["batch_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("ab_test_pairs")
    op.drop_table("shadow_scores")
