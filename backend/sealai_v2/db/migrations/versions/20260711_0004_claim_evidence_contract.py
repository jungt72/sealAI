"""Add the SSoT v2 evidence and applicability contract to knowledge claims.

Revision ID: 20260711_0004
Revises: 20260710_0003
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260711_0004"
down_revision = "20260710_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {
        column["name"] for column in inspector.get_columns("v2_knowledge_claims")
    }
    additions = (
        sa.Column(
            "evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column(
            "applicability_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "uncertainty",
            sa.String(64),
            nullable=False,
            server_default="not_sufficiently_supported",
        ),
        sa.Column(
            "transferability",
            sa.String(64),
            nullable=False,
            server_default="not_assessed",
        ),
        sa.Column(
            "conflicts_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("review_expires_at", sa.String(32), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=False, server_default=""),
    )
    missing = [column for column in additions if column.name not in existing]
    if missing:
        with op.batch_alter_table("v2_knowledge_claims") as batch:
            for column in missing:
                batch.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("v2_knowledge_claims") as batch:
        for column in (
            "change_reason",
            "review_expires_at",
            "conflicts_json",
            "transferability",
            "uncertainty",
            "applicability_json",
            "evidence_json",
        ):
            batch.drop_column(column)
