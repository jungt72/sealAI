"""add cases and case_state_snapshots tables

Revision ID: f2d9c4a8b6e1
Revises: 2b7c8d9e0f1a, cbc544453b98
Create Date: 2026-04-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "f2d9c4a8b6e1"
down_revision = ("2b7c8d9e0f1a", "cbc544453b98")
branch_labels = None
depends_on = None


def upgrade():
    state_json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    op.create_table(
        "cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_number", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("subsegment", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cases_case_number", "cases", ["case_number"], unique=True)
    op.create_index("ix_cases_user_id", "cases", ["user_id"], unique=False)

    op.create_table(
        "case_state_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state_json", state_json_type, nullable=False),
        sa.Column("basis_hash", sa.String(length=32), nullable=True),
        sa.Column("ontology_version", sa.String(length=50), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column("model_version", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "revision", name="uq_case_state_snapshots_case_revision"),
    )
    op.create_index("ix_case_state_snapshots_case_id", "case_state_snapshots", ["case_id"], unique=False)


def downgrade():
    op.drop_index("ix_case_state_snapshots_case_id", table_name="case_state_snapshots")
    op.drop_table("case_state_snapshots")
    op.drop_index("ix_cases_user_id", table_name="cases")
    op.drop_index("ix_cases_case_number", table_name="cases")
    op.drop_table("cases")
