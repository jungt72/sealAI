"""Add safe authority, ownership-quarantine, and RFQ-boundary schema.

Revision ID: 20260715_0012
Revises: 20260714_0011

This revision is deliberately additive. Existing ownerless rows remain unassigned and inaccessible;
profiling, quarantine marking, mapping/backfill, validation, RLS, role cutover, and FORCE RLS are
separate GATE-07 operations documented in the runbook.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260715_0012"
down_revision = "20260714_0011"
branch_labels = None
depends_on = None

_OWNERSHIP_COLUMNS = {
    "v2_sessions": {"ownership_state": sa.String(32)},
    "v2_durable_facts": {"ownership_state": sa.String(32)},
    "v2_memory_items": {"ownership_state": sa.String(32)},
    "v2_leads": {
        "owner_subject": sa.String(255),
        "case_id": sa.String(255),
        "case_revision": sa.Integer(),
        "ownership_state": sa.String(32),
    },
}


def _add_boundary_columns(inspector: sa.Inspector) -> None:
    tables = set(inspector.get_table_names())
    for table, columns in _OWNERSHIP_COLUMNS.items():
        if table not in tables:
            raise RuntimeError(f"required ownership source table is missing: {table}")
        existing = {item["name"] for item in inspector.get_columns(table)}
        for name, column_type in columns.items():
            if name not in existing:
                op.add_column(table, sa.Column(name, column_type, nullable=True))


def _create_authority_table(tables: set[str]) -> None:
    if "v2_knowledge_authority_epochs" not in tables:
        op.create_table(
            "v2_knowledge_authority_epochs",
            sa.Column("scope", sa.String(32), nullable=False),
            sa.Column("sequence", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.String(32), nullable=False),
            sa.PrimaryKeyConstraint("scope"),
        )
    op.execute(
        sa.text(
            "INSERT INTO v2_knowledge_authority_epochs (scope, sequence, updated_at) "
            "SELECT :scope, 0, :updated_at WHERE NOT EXISTS ("
            "SELECT 1 FROM v2_knowledge_authority_epochs WHERE scope = :scope)"
        ).bindparams(scope="knowledge", updated_at="1970-01-01T00:00:00Z")
    )


def _create_quarantine_table(tables: set[str]) -> None:
    if "v2_ownership_quarantine" in tables:
        return
    op.create_table(
        "v2_ownership_quarantine",
        # Integer (rather than BigInteger) keeps SQLite's hermetic migration lane autoincrementing;
        # PostgreSQL still emits a sequence-backed integer identifier.
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("source_table", sa.String(64), nullable=False),
        sa.Column("tenant_fingerprint", sa.String(64), nullable=False),
        sa.Column("record_fingerprint", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("detected_at", sa.String(32), nullable=False),
        sa.Column(
            "resolution_status",
            sa.String(32),
            nullable=False,
            server_default="unresolved",
        ),
        sa.Column("resolution_note", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_table",
            "record_fingerprint",
            "reason_code",
            name="uq_v2_ownership_quarantine_record_reason",
        ),
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    _add_boundary_columns(inspector)
    _create_authority_table(tables)
    _create_quarantine_table(tables)


def downgrade() -> None:
    op.drop_table("v2_ownership_quarantine")
    op.drop_table("v2_knowledge_authority_epochs")
    for table, columns in reversed(tuple(_OWNERSHIP_COLUMNS.items())):
        for name in reversed(tuple(columns)):
            op.drop_column(table, name)
