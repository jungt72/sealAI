"""Add the API lifecycle, quota, receipt, and quarantine foundation.

Revision ID: 20260715_0014
Revises: 20260715_0013

All legacy contribution/lead columns are nullable. This revision never infers consent, rights,
ownership, retention, or review state and never rewrites or deletes an existing row. Profiling,
mapping, validation, RLS, role grants, and activation remain separate GATE-07/GATE-08 work.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260715_0014"
down_revision = "20260715_0013"
branch_labels = None
depends_on = None

_CONTRIBUTION_COLUMNS = {
    "admission_request_id": sa.String(36),
    "owner_subject_ref": sa.String(64),
    "policy_authority_ref": sa.String(128),
    "purpose_version": sa.String(128),
    "consent_version": sa.String(128),
    "rights_basis": sa.String(32),
    "license_id": sa.String(64),
    "provenance": sa.String(255),
    "document_type": sa.String(64),
    "pii_classification": sa.String(32),
    "prompt_trust": sa.String(32),
    "prompt_injection_signal": sa.Boolean(),
    "lifecycle_state": sa.String(32),
    "quarantine_reason": sa.Text(),
    "content_bytes": sa.BigInteger(),
    "retention_review_after": sa.String(32),
    "withdrawn_at": sa.String(32),
}
_LEAD_COLUMNS = {
    "admission_request_id": sa.String(36),
    "briefing_provenance_json": sa.JSON(),
    "briefing_wissensstand": sa.Text(),
    "briefing_risk_flags_json": sa.JSON(),
    "policy_authority_ref": sa.String(128),
    "purpose_version": sa.String(128),
    "consent_version": sa.String(128),
    "handoff_confirmed": sa.Boolean(),
    "pii_classification": sa.String(32),
    "prompt_trust": sa.String(32),
    "prompt_injection_signal": sa.Boolean(),
    "lifecycle_state": sa.String(32),
    "content_bytes": sa.BigInteger(),
    "retention_review_after": sa.String(32),
    "cancelled_at": sa.String(32),
    "cancellation_reason": sa.String(64),
}


def _add_nullable_columns(
    inspector: sa.Inspector, table: str, columns: dict[str, sa.types.TypeEngine]
) -> None:
    if table not in inspector.get_table_names():
        raise RuntimeError(f"required API lifecycle source table is missing: {table}")
    existing = {item["name"] for item in inspector.get_columns(table)}
    for name, column_type in columns.items():
        if name not in existing:
            op.add_column(table, sa.Column(name, column_type, nullable=True))


def _create_tables(tables: set[str]) -> None:
    if "v2_api_lifecycle_windows" not in tables:
        op.create_table(
            "v2_api_lifecycle_windows",
            sa.Column("quota_group", sa.String(32), nullable=False),
            sa.Column("scope_kind", sa.String(16), nullable=False),
            sa.Column("scope_ref", sa.String(64), nullable=False),
            sa.Column("window_kind", sa.String(16), nullable=False),
            sa.Column("window_start", sa.String(32), nullable=False),
            sa.Column(
                "admitted_count", sa.BigInteger(), nullable=False, server_default="0"
            ),
            sa.Column(
                "denied_count", sa.BigInteger(), nullable=False, server_default="0"
            ),
            sa.Column(
                "reserved_bytes", sa.BigInteger(), nullable=False, server_default="0"
            ),
            sa.Column("updated_at", sa.String(32), nullable=False),
            sa.PrimaryKeyConstraint(
                "quota_group", "scope_kind", "scope_ref", "window_kind", "window_start"
            ),
        )
    if "v2_api_lifecycle_admissions" not in tables:
        op.create_table(
            "v2_api_lifecycle_admissions",
            sa.Column("request_id", sa.String(36), nullable=False),
            sa.Column("quota_group", sa.String(32), nullable=False),
            sa.Column("action", sa.String(32), nullable=False),
            sa.Column("tenant_ref", sa.String(64), nullable=False),
            sa.Column("actor_ref", sa.String(64), nullable=False),
            sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
            sa.Column("request_digest", sa.String(64), nullable=False),
            sa.Column("estimated_bytes", sa.BigInteger(), nullable=False),
            sa.Column("started_at", sa.String(32), nullable=False),
            sa.Column("expires_at", sa.String(32), nullable=False),
            sa.Column("released_at", sa.String(32), nullable=True),
            sa.Column(
                "outcome", sa.String(16), nullable=False, server_default="active"
            ),
            sa.Column("resource_type", sa.String(32), nullable=True),
            sa.Column("resource_id", sa.String(64), nullable=True),
            sa.PrimaryKeyConstraint("request_id"),
            sa.UniqueConstraint(
                "action",
                "tenant_ref",
                "actor_ref",
                "idempotency_key_hash",
                name="uq_v2_api_lifecycle_admission_idempotency",
            ),
        )
        op.create_index(
            "ix_v2_api_lifecycle_admissions_started_at",
            "v2_api_lifecycle_admissions",
            ["started_at"],
        )
        op.create_index(
            "ix_v2_api_lifecycle_admission_actor_active",
            "v2_api_lifecycle_admissions",
            ["actor_ref", "released_at", "expires_at"],
        )
        op.create_index(
            "ix_v2_api_lifecycle_admission_tenant_active",
            "v2_api_lifecycle_admissions",
            ["tenant_ref", "released_at", "expires_at"],
        )
    if "v2_api_lifecycle_receipts" not in tables:
        op.create_table(
            "v2_api_lifecycle_receipts",
            sa.Column("receipt_id", sa.String(36), nullable=False),
            sa.Column("resource_type", sa.String(32), nullable=False),
            sa.Column("resource_id", sa.String(64), nullable=False),
            sa.Column("tenant_ref", sa.String(64), nullable=False),
            sa.Column("actor_ref", sa.String(64), nullable=False),
            sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
            sa.Column("reason_code", sa.String(64), nullable=False),
            sa.Column("policy_authority_ref", sa.String(128), nullable=False),
            sa.Column("lifecycle_state", sa.String(32), nullable=False),
            sa.Column("issued_at", sa.String(32), nullable=False),
            sa.Column("receipt_digest", sa.String(64), nullable=False),
            sa.PrimaryKeyConstraint("receipt_id"),
            sa.UniqueConstraint("receipt_digest"),
            sa.UniqueConstraint(
                "resource_type",
                "resource_id",
                "idempotency_key_hash",
                name="uq_v2_api_lifecycle_receipt_idempotency",
            ),
        )
    if "v2_api_lifecycle_events" not in tables:
        op.create_table(
            "v2_api_lifecycle_events",
            sa.Column("event_id", sa.String(36), nullable=False),
            sa.Column("receipt_id", sa.String(36), nullable=False),
            sa.Column("resource_type", sa.String(32), nullable=False),
            sa.Column("resource_id", sa.String(64), nullable=False),
            sa.Column("tenant_id", sa.String(255), nullable=False),
            sa.Column("actor_ref", sa.String(64), nullable=False),
            sa.Column("event_type", sa.String(32), nullable=False),
            sa.Column("from_state", sa.String(32), nullable=False),
            sa.Column("to_state", sa.String(32), nullable=False),
            sa.Column("reason_code", sa.String(64), nullable=False),
            sa.Column("policy_authority_ref", sa.String(128), nullable=False),
            sa.Column("created_at", sa.String(32), nullable=False),
            sa.Column("event_digest", sa.String(64), nullable=False),
            sa.PrimaryKeyConstraint("event_id"),
            sa.UniqueConstraint("receipt_id"),
            sa.UniqueConstraint("event_digest"),
        )
        op.create_index(
            "ix_v2_api_lifecycle_events_tenant_id",
            "v2_api_lifecycle_events",
            ["tenant_id"],
        )


def _create_source_indexes(inspector: sa.Inspector) -> None:
    contribution_indexes = {
        item["name"] for item in inspector.get_indexes("v2_contributions")
    }
    if "ix_v2_contributions_owner_subject_ref" not in contribution_indexes:
        op.create_index(
            "ix_v2_contributions_owner_subject_ref",
            "v2_contributions",
            ["owner_subject_ref"],
        )
    if "ux_v2_contributions_admission_request_id" not in contribution_indexes:
        op.create_index(
            "ux_v2_contributions_admission_request_id",
            "v2_contributions",
            ["admission_request_id"],
            unique=True,
        )
    if "ix_v2_contributions_retention_review_after" not in contribution_indexes:
        op.create_index(
            "ix_v2_contributions_retention_review_after",
            "v2_contributions",
            ["retention_review_after"],
        )
    lead_indexes = {item["name"] for item in inspector.get_indexes("v2_leads")}
    if "ux_v2_leads_admission_request_id" not in lead_indexes:
        op.create_index(
            "ux_v2_leads_admission_request_id",
            "v2_leads",
            ["admission_request_id"],
            unique=True,
        )
    if "ix_v2_leads_retention_review_after" not in lead_indexes:
        op.create_index(
            "ix_v2_leads_retention_review_after",
            "v2_leads",
            ["retention_review_after"],
        )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    _add_nullable_columns(inspector, "v2_contributions", _CONTRIBUTION_COLUMNS)
    _add_nullable_columns(inspector, "v2_leads", _LEAD_COLUMNS)
    _create_tables(tables)
    # Re-inspect because additive columns/tables may have been created above.
    _create_source_indexes(sa.inspect(op.get_bind()))


def downgrade() -> None:
    op.drop_index(
        "ix_v2_api_lifecycle_events_tenant_id", table_name="v2_api_lifecycle_events"
    )
    op.drop_table("v2_api_lifecycle_events")
    op.drop_table("v2_api_lifecycle_receipts")
    op.drop_index(
        "ix_v2_api_lifecycle_admission_tenant_active",
        table_name="v2_api_lifecycle_admissions",
    )
    op.drop_index(
        "ix_v2_api_lifecycle_admission_actor_active",
        table_name="v2_api_lifecycle_admissions",
    )
    op.drop_index(
        "ix_v2_api_lifecycle_admissions_started_at",
        table_name="v2_api_lifecycle_admissions",
    )
    op.drop_table("v2_api_lifecycle_admissions")
    op.drop_table("v2_api_lifecycle_windows")
    op.drop_index(
        "ix_v2_contributions_retention_review_after", table_name="v2_contributions"
    )
    op.drop_index(
        "ix_v2_contributions_owner_subject_ref", table_name="v2_contributions"
    )
    op.drop_index(
        "ux_v2_contributions_admission_request_id", table_name="v2_contributions"
    )
    op.drop_index("ux_v2_leads_admission_request_id", table_name="v2_leads")
    op.drop_index("ix_v2_leads_retention_review_after", table_name="v2_leads")
    for name in reversed(tuple(_CONTRIBUTION_COLUMNS)):
        op.drop_column("v2_contributions", name)
    for name in reversed(tuple(_LEAD_COLUMNS)):
        op.drop_column("v2_leads", name)
