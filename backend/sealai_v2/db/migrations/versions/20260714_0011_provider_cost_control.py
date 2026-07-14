"""Add shared provider cost-control counters and expiring admissions.

Revision ID: 20260714_0011
Revises: 20260714_0010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260714_0011"
down_revision = "20260714_0010"
branch_labels = None
depends_on = None

_EXPECTED_COLUMNS = {
    "v2_provider_quota_windows": {
        "scope_kind",
        "scope_ref",
        "window_kind",
        "window_start",
        "admitted_count",
        "denied_count",
        "reserved_cost_micros",
        "updated_at",
    },
    "v2_provider_admissions": {
        "request_id",
        "tenant_ref",
        "subject_ref",
        "started_at",
        "expires_at",
        "released_at",
        "outcome",
        "reserved_cost_micros",
    },
}
_EXPECTED_PRIMARY_KEYS = {
    "v2_provider_quota_windows": [
        "scope_kind",
        "scope_ref",
        "window_kind",
        "window_start",
    ],
    "v2_provider_admissions": ["request_id"],
}
_REQUIRED_INDEXES = {
    "v2_provider_admissions": {
        "ix_v2_provider_admissions_started_at": ["started_at"],
        "ix_v2_provider_admission_subject_active": [
            "subject_ref",
            "released_at",
            "expires_at",
        ],
        "ix_v2_provider_admission_tenant_active": [
            "tenant_ref",
            "released_at",
            "expires_at",
        ],
    }
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names()) & set(_EXPECTED_COLUMNS)
    if existing_tables:
        missing_tables = sorted(set(_EXPECTED_COLUMNS) - existing_tables)
        column_drift = {
            table: {
                "missing": sorted(
                    columns - {item["name"] for item in inspector.get_columns(table)}
                ),
                "unexpected": sorted(
                    {item["name"] for item in inspector.get_columns(table)} - columns
                ),
            }
            for table, columns in _EXPECTED_COLUMNS.items()
            if table in existing_tables
            and {item["name"] for item in inspector.get_columns(table)} != columns
        }
        primary_key_drift = {
            table: list(
                inspector.get_pk_constraint(table).get("constrained_columns") or []
            )
            for table, expected in _EXPECTED_PRIMARY_KEYS.items()
            if table in existing_tables
            and list(
                inspector.get_pk_constraint(table).get("constrained_columns") or []
            )
            != expected
        }
        index_drift: dict[str, dict[str, list[str] | None]] = {}
        for table, required in _REQUIRED_INDEXES.items():
            if table not in existing_tables:
                continue
            actual = {
                item["name"]: list(item.get("column_names") or [])
                for item in inspector.get_indexes(table)
            }
            mismatched = {
                name: actual.get(name)
                for name, columns in required.items()
                if actual.get(name) != columns
            }
            if mismatched:
                index_drift[table] = mismatched
        if missing_tables or column_drift or primary_key_drift or index_drift:
            raise RuntimeError(
                "refusing partial provider cost-control schema; "
                f"missing tables={missing_tables}, column drift={column_drift}, "
                f"primary-key drift={primary_key_drift}, index drift={index_drift}"
            )
        # Supports adoption of a complete schema created before this Alembic revision (the same
        # narrow compatibility contract as the immutable baseline migration). Never repairs drift.
        return

    op.create_table(
        "v2_provider_quota_windows",
        sa.Column("scope_kind", sa.String(length=16), nullable=False),
        sa.Column("scope_ref", sa.String(length=64), nullable=False),
        sa.Column("window_kind", sa.String(length=16), nullable=False),
        sa.Column("window_start", sa.String(length=32), nullable=False),
        sa.Column(
            "admitted_count", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("denied_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "reserved_cost_micros", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint(
            "scope_kind", "scope_ref", "window_kind", "window_start"
        ),
    )
    op.create_table(
        "v2_provider_admissions",
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_ref", sa.String(length=64), nullable=False),
        sa.Column("subject_ref", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.String(length=32), nullable=False),
        sa.Column("released_at", sa.String(length=32), nullable=True),
        sa.Column(
            "outcome", sa.String(length=16), nullable=False, server_default="active"
        ),
        sa.Column("reserved_cost_micros", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index(
        "ix_v2_provider_admissions_started_at",
        "v2_provider_admissions",
        ["started_at"],
    )
    op.create_index(
        "ix_v2_provider_admission_subject_active",
        "v2_provider_admissions",
        ["subject_ref", "released_at", "expires_at"],
    )
    op.create_index(
        "ix_v2_provider_admission_tenant_active",
        "v2_provider_admissions",
        ["tenant_ref", "released_at", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_v2_provider_admission_tenant_active", table_name="v2_provider_admissions"
    )
    op.drop_index(
        "ix_v2_provider_admission_subject_active", table_name="v2_provider_admissions"
    )
    op.drop_index(
        "ix_v2_provider_admissions_started_at", table_name="v2_provider_admissions"
    )
    op.drop_table("v2_provider_admissions")
    op.drop_table("v2_provider_quota_windows")
