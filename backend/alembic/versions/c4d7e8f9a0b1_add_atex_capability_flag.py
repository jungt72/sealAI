"""add ATEX capability flag

Revision ID: c4d7e8f9a0b1
Revises: b2e4f6a8c0d1
Create Date: 2026-04-20

Purpose
-------
Sprint 3 Patch 3.8 adds only the ATEX manufacturer capability flag from
Founder Decision #7. This is intentionally not a norm module or ATEX
compliance engine. The nullable flag means:

* TRUE  -> a capability claim explicitly declares ATEX-related capability
* FALSE -> a capability claim explicitly declares no ATEX capability
* NULL  -> unknown / not claimed

No backfill or default is applied to avoid inventing manufacturer capability.
"""

from alembic import op
import sqlalchemy as sa


revision = "c4d7e8f9a0b1"
down_revision = "b2e4f6a8c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "manufacturer_capability_claims",
        sa.Column("atex_capable", sa.Boolean(), nullable=True),
    )
    op.create_index(
        "ix_manufacturer_capability_claims_atex_capable",
        "manufacturer_capability_claims",
        ["atex_capable"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_manufacturer_capability_claims_atex_capable",
        table_name="manufacturer_capability_claims",
    )
    op.drop_column("manufacturer_capability_claims", "atex_capable")
