"""add user_profiles table

Revision ID: 8b7f4c21d3ab
Revises: 70968fe4c62e
Create Date: 2025-09-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql

# revision identifiers, used by Alembic.
revision = "8b7f4c21d3ab"
down_revision = "70968fe4c62e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("prefs", psql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("params_patch", psql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="public",
    )


def downgrade():
    op.drop_table("user_profiles", schema="public")

