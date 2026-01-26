"""add rag_document attempt_count

Revision ID: 5f1c9b2a6d34
Revises: 8f4c1a2d6c9b
Create Date: 2026-01-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "5f1c9b2a6d34"
down_revision = "8f4c1a2d6c9b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rag_documents",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("rag_documents", "attempt_count")
