"""add document input fields to rag_documents

Revision ID: b6d7e8f9a1c2
Revises: aa7c1d9e2f43
Create Date: 2026-04-27 19:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b6d7e8f9a1c2"
down_revision = "aa7c1d9e2f43"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rag_documents",
        sa.Column("extraction_status", sa.String(), nullable=False, server_default="not_extracted"),
    )
    op.add_column("rag_documents", sa.Column("extracted_candidates", sa.JSON(), nullable=True))
    op.add_column("rag_documents", sa.Column("evidence_refs", sa.JSON(), nullable=True))
    op.add_column(
        "rag_documents",
        sa.Column("provenance", sa.String(), nullable=False, server_default="documented"),
    )
    op.create_index("ix_rag_documents_extraction_status", "rag_documents", ["extraction_status"])


def downgrade() -> None:
    op.drop_index("ix_rag_documents_extraction_status", table_name="rag_documents")
    op.drop_column("rag_documents", "provenance")
    op.drop_column("rag_documents", "evidence_refs")
    op.drop_column("rag_documents", "extracted_candidates")
    op.drop_column("rag_documents", "extraction_status")
