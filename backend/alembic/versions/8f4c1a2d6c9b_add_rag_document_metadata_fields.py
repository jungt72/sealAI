"""add rag_document metadata fields

Revision ID: 8f4c1a2d6c9b
Revises: c3f1a9b3f2e4
Create Date: 2025-02-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "8f4c1a2d6c9b"
down_revision = "c3f1a9b3f2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rag_documents", sa.Column("filename", sa.String(), nullable=True))
    op.add_column("rag_documents", sa.Column("content_type", sa.String(), nullable=True))
    op.add_column("rag_documents", sa.Column("size_bytes", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("rag_documents", "size_bytes")
    op.drop_column("rag_documents", "content_type")
    op.drop_column("rag_documents", "filename")
