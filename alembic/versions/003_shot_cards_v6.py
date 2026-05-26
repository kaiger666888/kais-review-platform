"""Add shot_cards_v6 table for V6.0 minimal review API.

Revision ID: 003_shot_cards_v6
Revises: 002_shadow_and_ab_tables
Create Date: 2026-05-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_shot_cards_v6"
down_revision = "002_shadow_and_ab_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enums
    shot_card_status_v6 = postgresql.ENUM(
        "pending", "approved", "rejected", "expired",
        name="shot_card_status_v6",
        create_type=True,
    )
    pipeline_phase_v6 = postgresql.ENUM(
        "storyboard", "character", "image", "video", "audio", "compose",
        name="pipeline_phase_v6",
        create_type=True,
    )
    priority_v6 = postgresql.ENUM(
        "normal", "urgent",
        name="priority_v6",
        create_type=True,
    )

    shot_card_status_v6.create(op.get_bind(), checkfirst=True)
    pipeline_phase_v6.create(op.get_bind(), checkfirst=True)
    priority_v6.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "shot_cards_v6",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(100), nullable=False),
        sa.Column("shot_id", sa.String(100), nullable=False),
        sa.Column("phase", pipeline_phase_v6, nullable=False),
        sa.Column("priority", priority_v6, nullable=False, server_default="normal"),
        sa.Column("asset_url", sa.String(500), nullable=False),
        sa.Column("thumbnail_url", sa.String(500), nullable=True),
        sa.Column("status", shot_card_status_v6, nullable=False, server_default="pending"),
        sa.Column("narrative_context", postgresql.JSONB(), nullable=True),
        sa.Column("score_aesthetics", sa.Float(), nullable=True),
        sa.Column("score_consistency", sa.Float(), nullable=True),
        sa.Column("score_compliance", sa.Float(), nullable=True),
        sa.Column("score_technical_quality", sa.Float(), nullable=True),
        sa.Column("score_audio_match", sa.Float(), nullable=True),
        sa.Column("reviewer_id", sa.String(100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reject_reason", sa.String(100), nullable=True),
        sa.Column("reject_comment", sa.String(500), nullable=True),
        sa.Column("callback_url", sa.String(500), nullable=True),
        sa.Column("callback_sent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_sc_v6_project_status", "shot_cards_v6", ["project_id", "status"])
    op.create_index("ix_sc_v6_phase_status", "shot_cards_v6", ["phase", "status"])
    op.create_index("ix_sc_v6_project_created", "shot_cards_v6", ["project_id", "created_at"])
    op.create_index(op.f("ix_shot_cards_v6_project_id"), "shot_cards_v6", ["project_id"])
    op.create_index(op.f("ix_shot_cards_v6_shot_id"), "shot_cards_v6", ["shot_id"])


def downgrade() -> None:
    op.drop_table("shot_cards_v6")

    op.execute("DROP TYPE IF EXISTS shot_card_status_v6")
    op.execute("DROP TYPE IF EXISTS pipeline_phase_v6")
    op.execute("DROP TYPE IF EXISTS priority_v6")
