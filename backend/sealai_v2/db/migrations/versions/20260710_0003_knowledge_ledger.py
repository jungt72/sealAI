"""Add the authoritative technical-knowledge ledger and derived-index outbox.

Revision ID: 20260710_0003
Revises: 20260710_0002
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260710_0003"
down_revision = "20260710_0002"
branch_labels = None
depends_on = None

_EXPECTED_COLUMNS = {
    "v2_knowledge_documents": {
        "id",
        "tenant_id",
        "source_type",
        "source_id",
        "source_uri",
        "object_key",
        "title",
        "content_sha256",
        "version",
        "authority",
        "status",
        "valid_from",
        "valid_to",
        "created_at",
    },
    "v2_knowledge_claims": {
        "id",
        "tenant_id",
        "card_id",
        "card_version",
        "document_id",
        "claim_order",
        "text",
        "content_sha256",
        "kind",
        "review_status",
        "scope_json",
        "sources_json",
        "provenance_json",
        "active",
        "version",
        "qdrant_sync_state",
        "qdrant_synced_version",
        "qdrant_synced_at",
        "created_at",
        "updated_at",
        "reviewed_at",
        "reviewed_by",
    },
    "v2_knowledge_reviews": {
        "id",
        "claim_id",
        "tenant_id",
        "from_status",
        "to_status",
        "actor",
        "note",
        "evidence_json",
        "created_at",
    },
    "v2_knowledge_outbox": {
        "id",
        "claim_id",
        "tenant_id",
        "event_type",
        "payload",
        "status",
        "attempts",
        "last_error",
        "created_at",
        "processed_at",
        "next_attempt_at",
    },
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    knowledge_tables = set(_EXPECTED_COLUMNS)
    present = existing_tables & knowledge_tables
    if present:
        if present != knowledge_tables:
            raise RuntimeError(
                "partial technical-knowledge ledger schema; refusing adoption: "
                f"present={sorted(present)} missing={sorted(knowledge_tables - present)}"
            )
        missing_columns = {
            table: sorted(
                expected - {column["name"] for column in inspector.get_columns(table)}
            )
            for table, expected in _EXPECTED_COLUMNS.items()
        }
        missing_columns = {
            table: columns for table, columns in missing_columns.items() if columns
        }
        if missing_columns:
            raise RuntimeError(
                "incomplete technical-knowledge ledger schema; refusing adoption: "
                f"{missing_columns}"
            )
        return

    op.create_table(
        "v2_knowledge_documents",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("source_uri", sa.String(1000), nullable=False),
        sa.Column("object_key", sa.String(1000), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("authority", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.String(32), nullable=True),
        sa.Column("valid_to", sa.String(32), nullable=True),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_type",
            "source_id",
            "content_sha256",
            name="uq_v2_knowledge_document_content",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "source_type",
            "source_id",
            "version",
            name="uq_v2_knowledge_document_version",
        ),
    )
    op.create_index(
        "ix_v2_knowledge_documents_tenant_id",
        "v2_knowledge_documents",
        ["tenant_id"],
    )
    op.create_table(
        "v2_knowledge_claims",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("card_id", sa.String(255), nullable=False),
        sa.Column("card_version", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("claim_order", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("sources_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("qdrant_sync_state", sa.String(32), nullable=False),
        sa.Column("qdrant_synced_version", sa.Integer(), nullable=True),
        sa.Column("qdrant_synced_at", sa.String(32), nullable=True),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("reviewed_at", sa.String(32), nullable=True),
        sa.Column("reviewed_by", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("active", "card_id", "document_id", "review_status", "tenant_id"):
        op.create_index(
            f"ix_v2_knowledge_claims_{column}",
            "v2_knowledge_claims",
            [column],
        )
    op.create_table(
        "v2_knowledge_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("claim_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=False),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_v2_knowledge_reviews_claim_id",
        "v2_knowledge_reviews",
        ["claim_id"],
    )
    op.create_index(
        "ix_v2_knowledge_reviews_tenant_id",
        "v2_knowledge_reviews",
        ["tenant_id"],
    )
    op.create_table(
        "v2_knowledge_outbox",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("claim_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("processed_at", sa.String(32), nullable=True),
        sa.Column("next_attempt_at", sa.String(32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("claim_id", "next_attempt_at", "status", "tenant_id"):
        op.create_index(
            f"ix_v2_knowledge_outbox_{column}",
            "v2_knowledge_outbox",
            [column],
        )


def downgrade() -> None:
    op.drop_table("v2_knowledge_outbox")
    op.drop_table("v2_knowledge_reviews")
    op.drop_table("v2_knowledge_claims")
    op.drop_table("v2_knowledge_documents")
