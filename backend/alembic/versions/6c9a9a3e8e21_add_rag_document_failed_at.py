"""add rag_document failed_at

Revision ID: 6c9a9a3e8e21
Revises: 5f1c9b2a6d34
Create Date: 2026-01-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "6c9a9a3e8e21"
down_revision = "5f1c9b2a6d34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rag_documents", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("rag_documents", "failed_at")
