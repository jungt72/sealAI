"""add inquiry_deliveries and inquiry_audit tables, session_id to cases

Revision ID: a1b2c3d4e5f6
Revises: f2d9c4a8b6e1
Create Date: 2026-04-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "f2d9c4a8b6e1"
branch_labels = None
depends_on = None


def upgrade():
    state_json_type = sa.JSON().with_variant(
        postgresql.JSONB(astext_type=sa.Text()), "postgresql"
    )

    # --- cases: add session_id column (nullable — existing rows have no session) ---
    op.add_column(
        "cases",
        sa.Column("session_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_cases_session_id", "cases", ["session_id"], unique=True
    )

    # --- inquiry_deliveries ---
    op.create_table(
        "inquiry_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "case_id",
            sa.String(length=36),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("manufacturer_id", sa.String(length=100), nullable=False),
        sa.Column("payload_json", state_json_type, nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="logged"
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_inquiry_deliveries_idempotency_key",
        ),
    )
    op.create_index(
        "ix_inquiry_deliveries_case_id",
        "inquiry_deliveries",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        "ix_inquiry_deliveries_manufacturer_id",
        "inquiry_deliveries",
        ["manufacturer_id"],
        unique=False,
    )

    # --- inquiry_audit (append-only) ---
    op.create_table(
        "inquiry_audit",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "case_id",
            sa.String(length=36),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "state_snapshot_id",
            sa.String(length=36),
            sa.ForeignKey("case_state_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decision_basis_hash", sa.String(length=32), nullable=False),
        sa.Column("pdf_url", sa.String(length=500), nullable=True),
        sa.Column("disclaimer_text", sa.String(length=1000), nullable=True),
        sa.Column("payload_json", state_json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # No updated_at — append-only table
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_inquiry_audit_idempotency_key",
        ),
    )
    op.create_index(
        "ix_inquiry_audit_case_id",
        "inquiry_audit",
        ["case_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_inquiry_audit_case_id", table_name="inquiry_audit")
    op.drop_table("inquiry_audit")
    op.drop_index(
        "ix_inquiry_deliveries_manufacturer_id",
        table_name="inquiry_deliveries",
    )
    op.drop_index(
        "ix_inquiry_deliveries_case_id", table_name="inquiry_deliveries"
    )
    op.drop_table("inquiry_deliveries")
    op.drop_index("ix_cases_session_id", table_name="cases")
    op.drop_column("cases", "session_id")
