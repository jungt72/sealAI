"""make tenant_id mandatory for case write-path tables

Revision ID: b8c4d6e2f901
Revises: 4c2f8a9d1b73
Create Date: 2026-04-20

Purpose
-------
Sprint 1 Patch 1.7 hardens Founder Decision #6 at the database layer:
cases, mutation_events, and outbox rows must always carry tenant_id.

This migration intentionally does not backfill, delete, or default data.
If NULL tenant_id values still exist, upgrade fails before changing
nullability so operators get an explicit data-alignment error.
"""

from alembic import op
import sqlalchemy as sa


revision = "b8c4d6e2f901"
down_revision = "4c2f8a9d1b73"
branch_labels = None
depends_on = None


_TENANT_TABLES = ("cases", "mutation_events", "outbox")


def _assert_no_null_tenant_ids() -> None:
    conn = op.get_bind()
    offenders: list[str] = []
    for table_name in _TENANT_TABLES:
        null_count = conn.execute(
            sa.text(f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id IS NULL")
        ).scalar_one()
        if null_count:
            offenders.append(f"{table_name}.tenant_id={null_count}")

    if offenders:
        joined = ", ".join(offenders)
        raise RuntimeError(
            "Patch 1.7 requires tenant-aligned data before applying NOT NULL; "
            f"found NULL tenant_id rows: {joined}"
        )


def upgrade() -> None:
    _assert_no_null_tenant_ids()

    op.alter_column(
        "cases",
        "tenant_id",
        existing_type=sa.String(255),
        nullable=False,
    )
    op.alter_column(
        "mutation_events",
        "tenant_id",
        existing_type=sa.String(255),
        nullable=False,
    )
    op.alter_column(
        "outbox",
        "tenant_id",
        existing_type=sa.String(255),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "outbox",
        "tenant_id",
        existing_type=sa.String(255),
        nullable=True,
    )
    op.alter_column(
        "mutation_events",
        "tenant_id",
        existing_type=sa.String(255),
        nullable=True,
    )
    op.alter_column(
        "cases",
        "tenant_id",
        existing_type=sa.String(255),
        nullable=True,
    )
