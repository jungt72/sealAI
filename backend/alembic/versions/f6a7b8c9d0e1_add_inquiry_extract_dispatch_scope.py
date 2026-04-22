"""add inquiry extract dispatch scope

Revision ID: f6a7b8c9d0e1
Revises: c4d7e8f9a0b1
Create Date: 2026-04-21

Purpose
-------
Minimal Gate 3->4 remediation for Founder Decision #6: inquiry extracts need
an explicit manufacturer dispatch scope. This is intentionally only a nullable
identifier plus lookup index; dispatch workflow and portal access stay out of
Sprint 3.
"""

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "c4d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inquiry_extracts",
        sa.Column("dispatched_to_manufacturer_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_inquiry_extracts_dispatched_to_manufacturer_id",
        "inquiry_extracts",
        ["dispatched_to_manufacturer_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inquiry_extracts_dispatched_to_manufacturer_id",
        table_name="inquiry_extracts",
    )
    op.drop_column("inquiry_extracts", "dispatched_to_manufacturer_id")
