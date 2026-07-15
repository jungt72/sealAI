"""Add versioned affiliation authority, immutable snapshots, and COI audit.

Revision ID: 20260715_0014
Revises: 20260715_0013

This migration creates empty additive structures only. It does not infer an
affiliation, rewrite a review, assign a role, or activate a feature. Human
authority import and legacy quarantine are separate GATE-07 operations.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260715_0014"
down_revision = "20260715_0013"
branch_labels = None
depends_on = None

_EXPECTED_COLUMNS = {
    "v2_identity_affiliation_revisions": {
        "id",
        "subject_ref",
        "organization_ref",
        "relationship",
        "authority_source",
        "authority_reference",
        "authority_version",
        "effective_from",
        "effective_to",
        "status",
        "revision",
        "recorded_at",
        "recorded_by",
        "record_sha256",
    },
    "v2_governance_snapshots": {
        "id",
        "subject_ref",
        "purpose",
        "resource_type",
        "resource_ref",
        "resource_version",
        "snapshot_json",
        "created_at",
    },
    "v2_governance_decisions": {
        "id",
        "decision_type",
        "resource_type",
        "resource_ref",
        "resource_version",
        "first_snapshot_id",
        "second_snapshot_id",
        "outcome",
        "reason_code",
        "decision_json",
        "created_at",
    },
    "v2_governance_quarantine": {
        "id",
        "resource_type",
        "record_fingerprint",
        "reason_code",
        "detected_at",
        "resolution_status",
        "resolution_note",
    },
}

_EXPECTED_UNIQUES = {
    "v2_identity_affiliation_revisions": {
        frozenset({"subject_ref", "organization_ref", "relationship", "revision"})
    },
    "v2_governance_snapshots": {
        frozenset({"resource_type", "resource_ref", "resource_version", "purpose"})
    },
    "v2_governance_decisions": {
        frozenset(
            {"decision_type", "resource_type", "resource_ref", "resource_version"}
        )
    },
    "v2_governance_quarantine": {
        frozenset({"resource_type", "record_fingerprint", "reason_code"})
    },
}

_EXPECTED_INDEX_COLUMNS = {
    "v2_identity_affiliation_revisions": {
        ("subject_ref",),
        ("organization_ref",),
        ("status",),
    },
    "v2_governance_snapshots": {
        ("subject_ref",),
        ("resource_type",),
        ("resource_ref",),
    },
    "v2_governance_decisions": {
        ("decision_type",),
        ("resource_type",),
        ("resource_ref",),
    },
    "v2_governance_quarantine": set(),
}


def _adopt_complete_precreated_schema(inspector: sa.Inspector) -> bool:
    tables = set(inspector.get_table_names())
    present = set(_EXPECTED_COLUMNS) & tables
    if not present:
        return False
    if present != set(_EXPECTED_COLUMNS):
        raise RuntimeError("partial reviewer-governance schema already exists")
    for table, expected in _EXPECTED_COLUMNS.items():
        actual = {item["name"] for item in inspector.get_columns(table)}
        if actual != expected:
            raise RuntimeError(
                f"reviewer-governance column drift in {table}: "
                f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
            )
        primary_key = set(
            inspector.get_pk_constraint(table).get("constrained_columns") or ()
        )
        if primary_key != {"id"}:
            raise RuntimeError(f"reviewer-governance primary-key drift in {table}")
        actual_uniques = {
            frozenset(item.get("column_names") or ())
            for item in inspector.get_unique_constraints(table)
        }
        if not _EXPECTED_UNIQUES[table] <= actual_uniques:
            raise RuntimeError(
                f"reviewer-governance unique-constraint drift in {table}"
            )
        actual_indexes = {
            tuple(item.get("column_names") or ())
            for item in inspector.get_indexes(table)
        }
        if not _EXPECTED_INDEX_COLUMNS[table] <= actual_indexes:
            raise RuntimeError(f"reviewer-governance index drift in {table}")
    return True


def upgrade() -> None:
    if _adopt_complete_precreated_schema(sa.inspect(op.get_bind())):
        return
    op.create_table(
        "v2_identity_affiliation_revisions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("subject_ref", sa.String(255), nullable=False),
        sa.Column("organization_ref", sa.String(255), nullable=False),
        sa.Column("relationship", sa.String(32), nullable=False),
        sa.Column("authority_source", sa.String(64), nullable=False),
        sa.Column("authority_reference", sa.String(255), nullable=False),
        sa.Column("authority_version", sa.String(64), nullable=False),
        sa.Column("effective_from", sa.String(32), nullable=False),
        sa.Column("effective_to", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        sa.Column("record_sha256", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subject_ref",
            "organization_ref",
            "relationship",
            "revision",
            name="uq_v2_affiliation_subject_org_relation_revision",
        ),
    )
    op.create_index(
        "ix_v2_identity_affiliation_revisions_subject_ref",
        "v2_identity_affiliation_revisions",
        ["subject_ref"],
    )
    op.create_index(
        "ix_v2_identity_affiliation_revisions_organization_ref",
        "v2_identity_affiliation_revisions",
        ["organization_ref"],
    )
    op.create_index(
        "ix_v2_identity_affiliation_revisions_status",
        "v2_identity_affiliation_revisions",
        ["status"],
    )
    op.create_table(
        "v2_governance_snapshots",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("subject_ref", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_ref", sa.String(255), nullable=False),
        sa.Column("resource_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resource_type",
            "resource_ref",
            "resource_version",
            "purpose",
            name="uq_v2_governance_snapshot_resource_purpose",
        ),
    )
    op.create_index(
        "ix_v2_governance_snapshots_subject_ref",
        "v2_governance_snapshots",
        ["subject_ref"],
    )
    op.create_index(
        "ix_v2_governance_snapshots_resource_type",
        "v2_governance_snapshots",
        ["resource_type"],
    )
    op.create_index(
        "ix_v2_governance_snapshots_resource_ref",
        "v2_governance_snapshots",
        ["resource_ref"],
    )
    op.create_table(
        "v2_governance_decisions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("decision_type", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_ref", sa.String(255), nullable=False),
        sa.Column("resource_version", sa.Integer(), nullable=False),
        sa.Column("first_snapshot_id", sa.String(64), nullable=False),
        sa.Column("second_snapshot_id", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("decision_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "decision_type",
            "resource_type",
            "resource_ref",
            "resource_version",
            name="uq_v2_governance_decision_resource_version",
        ),
    )
    op.create_index(
        "ix_v2_governance_decisions_decision_type",
        "v2_governance_decisions",
        ["decision_type"],
    )
    op.create_index(
        "ix_v2_governance_decisions_resource_type",
        "v2_governance_decisions",
        ["resource_type"],
    )
    op.create_index(
        "ix_v2_governance_decisions_resource_ref",
        "v2_governance_decisions",
        ["resource_ref"],
    )
    op.create_table(
        "v2_governance_quarantine",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
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
            "resource_type",
            "record_fingerprint",
            "reason_code",
            name="uq_v2_governance_quarantine_record_reason",
        ),
    )


def downgrade() -> None:
    op.drop_table("v2_governance_quarantine")
    op.drop_index(
        "ix_v2_governance_decisions_resource_ref",
        table_name="v2_governance_decisions",
    )
    op.drop_index(
        "ix_v2_governance_decisions_resource_type",
        table_name="v2_governance_decisions",
    )
    op.drop_index(
        "ix_v2_governance_decisions_decision_type",
        table_name="v2_governance_decisions",
    )
    op.drop_table("v2_governance_decisions")
    op.drop_index(
        "ix_v2_governance_snapshots_resource_ref",
        table_name="v2_governance_snapshots",
    )
    op.drop_index(
        "ix_v2_governance_snapshots_resource_type",
        table_name="v2_governance_snapshots",
    )
    op.drop_index(
        "ix_v2_governance_snapshots_subject_ref",
        table_name="v2_governance_snapshots",
    )
    op.drop_table("v2_governance_snapshots")
    op.drop_index(
        "ix_v2_identity_affiliation_revisions_status",
        table_name="v2_identity_affiliation_revisions",
    )
    op.drop_index(
        "ix_v2_identity_affiliation_revisions_organization_ref",
        table_name="v2_identity_affiliation_revisions",
    )
    op.drop_index(
        "ix_v2_identity_affiliation_revisions_subject_ref",
        table_name="v2_identity_affiliation_revisions",
    )
    op.drop_table("v2_identity_affiliation_revisions")
