"""Initial V2 schema with shot_cards and audit_entries tables.

Revision ID: 001_v2_initial
Revises: None
Create Date: 2026-05-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "001_v2_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# PostgreSQL ENUM types
audit_status_enum = sa.Enum(
    "awaiting_audit",
    "approved",
    "rejected",
    "pending_audio",
    name="audit_status",
    create_constraint=True,
)
routing_decision_enum = sa.Enum(
    "AUTO",
    "HUMAN",
    "AI_AUDIT",
    "BLOCK",
    name="routing_decision",
    create_constraint=True,
)


def upgrade() -> None:
    # Create ENUM types
    audit_status_enum.create(op.get_bind(), checkfirst=True)
    routing_decision_enum.create(op.get_bind(), checkfirst=True)

    # Create shot_cards table
    op.create_table(
        "shot_cards",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shot_id", sa.String(100), nullable=False),
        sa.Column("project_id", sa.String(100), nullable=False),
        sa.Column("narrative_context", JSONB, nullable=False, server_default="{}"),
        sa.Column("visual_bundle", JSONB, nullable=True),
        sa.Column("audio_bundle", JSONB, nullable=True),
        sa.Column("audit_status", audit_status_enum, nullable=False),
        sa.Column("routing_decision", routing_decision_enum, nullable=True),
        sa.Column("min_audit_set", JSONB, nullable=True),
        sa.Column("blocking_reason", sa.String(500), nullable=True),
        sa.Column("workflow_version", sa.String(64), nullable=True),
        sa.Column("policy_commit_sha", sa.String(64), nullable=True),
        sa.Column("execution_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shot_id"),
    )

    # Create indexes for shot_cards
    op.create_index(
        "ix_shot_cards_project_id", "shot_cards", ["project_id"], unique=False
    )
    op.create_index(
        "ix_shot_cards_project_created",
        "shot_cards",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_shot_cards_status_created",
        "shot_cards",
        ["audit_status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_shot_cards_narrative_gin",
        "shot_cards",
        ["narrative_context"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_shot_cards_visual_gin",
        "shot_cards",
        ["visual_bundle"],
        unique=False,
        postgresql_using="gin",
    )

    # Create audit_entries table
    op.create_table(
        "audit_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shot_card_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("from_state", sa.String(50), nullable=True),
        sa.Column("to_state", sa.String(50), nullable=True),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("own_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("created_at", "id"),
        sa.ForeignKeyConstraint(["shot_card_id"], ["shot_cards.id"]),
    )

    # Create indexes for audit_entries
    op.create_index(
        "ix_audit_shot_created",
        "audit_entries",
        ["shot_card_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_audit_action_created",
        "audit_entries",
        ["action", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_audit_actor_created",
        "audit_entries",
        ["actor", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    # Drop tables
    op.drop_table("audit_entries")
    op.drop_table("shot_cards")

    # Drop ENUM types
    audit_status_enum.drop(op.get_bind(), checkfirst=True)
    routing_decision_enum.drop(op.get_bind(), checkfirst=True)
