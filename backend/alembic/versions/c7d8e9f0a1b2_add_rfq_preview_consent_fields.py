"""add rfq preview consent fields

Revision ID: c7d8e9f0a1b2
Revises: b6d7e8f9a1c2
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c7d8e9f0a1b2"
down_revision = "b6d7e8f9a1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_inquiry_extracts_artifact_type", "inquiry_extracts", type_="check")
    op.create_check_constraint(
        "ck_inquiry_extracts_artifact_type",
        "inquiry_extracts",
        "artifact_type IN ('manufacturer_inquiry', 'technical_summary', 'rfq_preview')",
    )
    op.add_column(
        "inquiry_extracts",
        sa.Column(
            "consent_status",
            sa.String(32),
            nullable=False,
            server_default="not_requested",
        ),
    )
    op.add_column(
        "inquiry_extracts",
        sa.Column("consent_granted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "inquiry_extracts",
        sa.Column("consent_granted_by", sa.String(255), nullable=True),
    )
    op.add_column(
        "inquiry_extracts",
        sa.Column(
            "consent_scope",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "inquiry_extracts",
        sa.Column(
            "dispatch_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_check_constraint(
        "ck_inquiry_extracts_consent_status",
        "inquiry_extracts",
        "consent_status IN ('not_requested', 'granted', 'revoked')",
    )
    op.create_index(
        "ix_inquiry_extracts_consent_status",
        "inquiry_extracts",
        ["consent_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_inquiry_extracts_consent_status", table_name="inquiry_extracts")
    op.drop_constraint("ck_inquiry_extracts_consent_status", "inquiry_extracts", type_="check")
    op.drop_column("inquiry_extracts", "dispatch_enabled")
    op.drop_column("inquiry_extracts", "consent_scope")
    op.drop_column("inquiry_extracts", "consent_granted_by")
    op.drop_column("inquiry_extracts", "consent_granted_at")
    op.drop_column("inquiry_extracts", "consent_status")
    op.drop_constraint("ck_inquiry_extracts_artifact_type", "inquiry_extracts", type_="check")
    op.create_check_constraint(
        "ck_inquiry_extracts_artifact_type",
        "inquiry_extracts",
        "artifact_type IN ('manufacturer_inquiry', 'technical_summary')",
    )
