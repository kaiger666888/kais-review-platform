"""Fix timestamps to TIMESTAMPTZ for timezone-aware Python datetime.

Revision ID: 004_fix_timestamps
Revises: 003_shot_cards_v6
"""
from alembic import op

revision = "004_fix_timestamps"
down_revision = "003_shot_cards_v6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
        ALTER TABLE shot_cards_v6 
          ALTER COLUMN reviewed_at TYPE TIMESTAMPTZ USING reviewed_at AT TIME ZONE 'UTC',
          ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC',
          ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING updated_at AT TIME ZONE 'UTC';
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE shot_cards_v6 
          ALTER COLUMN reviewed_at TYPE TIMESTAMP WITHOUT TIME ZONE USING reviewed_at AT TIME ZONE 'UTC',
          ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE USING created_at AT TIME ZONE 'UTC',
          ALTER COLUMN updated_at TYPE TIMESTAMP WITHOUT TIME ZONE USING updated_at AT TIME ZONE 'UTC';
    """)
