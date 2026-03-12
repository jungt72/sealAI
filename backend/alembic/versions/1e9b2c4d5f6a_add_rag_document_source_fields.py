"""add rag_document source fields

Revision ID: 1e9b2c4d5f6a
Revises: 8f4c1a2d6c9b
Create Date: 2026-03-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "1e9b2c4d5f6a"
down_revision = "8f4c1a2d6c9b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rag_documents", sa.Column("source_system", sa.String(), nullable=True))
    op.add_column("rag_documents", sa.Column("source_document_id", sa.String(), nullable=True))
    op.add_column("rag_documents", sa.Column("source_modified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_rag_documents_source_identity",
        "rag_documents",
        ["tenant_id", "source_system", "source_document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_rag_documents_source_identity", table_name="rag_documents")
    op.drop_column("rag_documents", "source_modified_at")
    op.drop_column("rag_documents", "source_document_id")
    op.drop_column("rag_documents", "source_system")
