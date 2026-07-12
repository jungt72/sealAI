"""Add stable claim authority and explicit review-origin metadata.

Revision ID: 20260712_0007
Revises: 20260711_0006
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260712_0007"
down_revision = "20260711_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {
        column["name"] for column in inspector.get_columns("v2_knowledge_claims")
    }
    additions = (
        sa.Column(
            "authority_fingerprint",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "review_origin",
            sa.String(32),
            nullable=False,
            server_default="legacy_unverified",
        ),
    )
    missing = [column for column in additions if column.name not in existing]
    if missing:
        with op.batch_alter_table("v2_knowledge_claims") as batch:
            for column in missing:
                batch.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("v2_knowledge_claims") as batch:
        batch.drop_column("review_origin")
        batch.drop_column("authority_fingerprint")
