"""Add revisioned, provenance-aware case-state fields.

Revision ID: 20260710_0002
Revises: 20260710_0001
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260710_0002"
down_revision = "20260710_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    session_columns = {
        column["name"] for column in inspector.get_columns("v2_sessions")
    }
    if "case_revision" not in session_columns:
        with op.batch_alter_table("v2_sessions") as batch:
            batch.add_column(
                sa.Column(
                    "case_revision", sa.Integer(), nullable=False, server_default="0"
                )
            )
    fact_columns = {column["name"] for column in inspector.get_columns("v2_facts")}
    additions = (
        sa.Column("unit", sa.String(32), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="stated"),
        sa.Column("source_ref", sa.String(500), nullable=False, server_default=""),
        sa.Column("observed_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("document_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("document_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
    )
    missing = [column for column in additions if column.name not in fact_columns]
    if missing:
        with op.batch_alter_table("v2_facts") as batch:
            for column in missing:
                batch.add_column(column)
    op.execute(
        sa.text(
            "UPDATE v2_facts SET status = 'confirmed' "
            "WHERE provenance IN ('user-edited', 'user-form', 'user-confirmed')"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("v2_facts") as batch:
        for column in (
            "confidence",
            "bbox",
            "page",
            "document_version",
            "document_id",
            "observed_at",
            "source_ref",
            "status",
            "unit",
        ):
            batch.drop_column(column)
    with op.batch_alter_table("v2_sessions") as batch:
        batch.drop_column("case_revision")
