"""add rag_document route key

Revision ID: 2b7c8d9e0f1a
Revises: 1e9b2c4d5f6a
Create Date: 2026-03-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "2b7c8d9e0f1a"
down_revision = "1e9b2c4d5f6a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rag_documents", sa.Column("route_key", sa.String(), nullable=True))
    op.create_index("ix_rag_documents_route_key", "rag_documents", ["route_key"])


def downgrade() -> None:
    op.drop_index("ix_rag_documents_route_key", table_name="rag_documents")
    op.drop_column("rag_documents", "route_key")
