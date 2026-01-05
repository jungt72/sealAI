"""add rag_documents table

Revision ID: c3f1a9b3f2e4
Revises: b9404c037af5
Create Date: 2025-02-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c3f1a9b3f2e4"
down_revision = "b9404c037af5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_documents",
        sa.Column("document_id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("ingest_stats", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_rag_documents_document_id", "rag_documents", ["document_id"])
    op.create_index("ix_rag_documents_tenant_id", "rag_documents", ["tenant_id"])
    op.create_index("ix_rag_documents_status", "rag_documents", ["status"])


def downgrade() -> None:
    op.drop_index("ix_rag_documents_status", table_name="rag_documents")
    op.drop_index("ix_rag_documents_tenant_id", table_name="rag_documents")
    op.drop_index("ix_rag_documents_document_id", table_name="rag_documents")
    op.drop_table("rag_documents")
