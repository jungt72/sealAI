"""Add inert MAT-EVID-01C factual evidence-review persistence.

Revision ID: 20260718_0016
Revises: 20260718_0015

The migration is additive and empty.  It creates no evidence, seed, backfill,
runtime binding, pointer, activation, deployment, or public API state.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from sealai_v2.db.migrations.adoption_fingerprint import require_schema_fingerprint


revision = "20260718_0016"
down_revision = "20260718_0015"
branch_labels = None
depends_on = None

_TABLES = (
    "v2_material_evidence_review_dossiers",
    "v2_material_evidence_review_snapshots",
    "v2_material_evidence_review_validation_events",
    "v2_material_evidence_review_lifecycle_events",
    "v2_material_evidence_review_audit_events",
)
_ADOPTION_FINGERPRINTS: dict[str, frozenset[str]] = {
    "postgresql": frozenset(
        {"269d59428325f3d50c668be5f88700e5c28ea0fb52c39b088bd6e1da7774098b"}
    ),
    "sqlite": frozenset(
        {"e9c4f9d442d71ee2a200c6c40db36e03f6dc59b76460186f64b3b6833dfed0ab"}
    ),
}
_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def _create_tables() -> None:
    op.create_table(
        "v2_material_evidence_review_dossiers",
        sa.Column("review_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(68), nullable=False),
        sa.Column("creator_subject", sa.String(255), nullable=False),
        sa.Column("creator_identity_kind", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(review_id) = 36 AND review_id LIKE 'mer_%'",
            name="ck_v2_mat_evid_review_id",
        ),
        sa.CheckConstraint(
            "creator_identity_kind = 'verified_human'",
            name="ck_v2_mat_evid_review_creator_human",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["v2_material_evidence_snapshots.snapshot_id"],
            name="fk_v2_mat_evid_review_evidence",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("review_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "evidence_snapshot_id",
            name="uq_v2_mat_evid_review_tenant_evidence",
        ),
    )
    op.create_index(
        "ix_v2_mat_evid_review_dossiers_tenant",
        "v2_material_evidence_review_dossiers",
        ["tenant_id"],
    )
    op.create_index(
        "ix_v2_mat_evid_review_dossiers_evidence",
        "v2_material_evidence_review_dossiers",
        ["evidence_snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_review_snapshots",
        sa.Column("review_snapshot_id", sa.String(68), nullable=False),
        sa.Column("review_id", sa.String(36), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(68), nullable=False),
        sa.Column("evidence_content_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_manifest_schema_version", sa.Integer(), nullable=False),
        sa.Column("evidence_contract_version", sa.String(32), nullable=False),
        sa.Column("review_schema_version", sa.Integer(), nullable=False),
        sa.Column("canonicalization_version", sa.Integer(), nullable=False),
        sa.Column("mat_evid_review_contract_version", sa.String(32), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_payload_json", _JSON, nullable=False),
        sa.Column("canonical_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("runtime_authority", sa.String(32), nullable=False),
        sa.Column("positive_statement_allowed", sa.Boolean(), nullable=False),
        sa.Column("created_by_subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(review_snapshot_id) = 68 AND review_snapshot_id LIKE 'mrv_%'",
            name="ck_v2_mat_evid_review_snapshot_id",
        ),
        sa.CheckConstraint(
            "review_schema_version = 1 AND canonicalization_version = 1 AND "
            "mat_evid_review_contract_version = 'MAT-EVID-01C.v1'",
            name="ck_v2_mat_evid_review_snapshot_contract",
        ),
        sa.CheckConstraint(
            "evidence_manifest_schema_version = 1 AND "
            "evidence_contract_version = 'MAT-EVID-01A.v1'",
            name="ck_v2_mat_evid_review_evidence_contract",
        ),
        sa.CheckConstraint(
            "length(content_sha256) = 64 AND length(evidence_content_sha256) = 64",
            name="ck_v2_mat_evid_review_snapshot_hashes",
        ),
        sa.CheckConstraint(
            "runtime_authority = 'FACTUAL_REVIEW_ONLY' AND "
            "positive_statement_allowed IS FALSE",
            name="ck_v2_mat_evid_review_no_runtime_authority",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["v2_material_evidence_review_dossiers.review_id"],
            name="fk_v2_mat_evid_review_snapshot_dossier",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["v2_material_evidence_snapshots.snapshot_id"],
            name="fk_v2_mat_evid_review_snapshot_evidence",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("review_snapshot_id"),
        sa.UniqueConstraint(
            "review_id",
            "content_sha256",
            name="uq_v2_mat_evid_review_snapshot_content",
        ),
    )
    op.create_index(
        "ix_v2_mat_evid_review_snapshots_review",
        "v2_material_evidence_review_snapshots",
        ["review_id"],
    )
    op.create_index(
        "ix_v2_mat_evid_review_snapshots_evidence",
        "v2_material_evidence_review_snapshots",
        ["evidence_snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_review_validation_events",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("review_snapshot_id", sa.String(68), nullable=False),
        sa.Column("validator_contract_version", sa.String(32), nullable=False),
        sa.Column("validation_state", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("validation_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mvv_%'",
            name="ck_v2_mat_evid_review_validation_id",
        ),
        sa.CheckConstraint(
            "validation_state = 'valid' AND error_code = 'none'",
            name="ck_v2_mat_evid_review_validation_state",
        ),
        sa.CheckConstraint(
            "length(validation_sha256) = 64",
            name="ck_v2_mat_evid_review_validation_hash",
        ),
        sa.ForeignKeyConstraint(
            ["review_snapshot_id"],
            ["v2_material_evidence_review_snapshots.review_snapshot_id"],
            name="fk_v2_mat_evid_review_validation_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_mat_evid_review_validation_snapshot",
        "v2_material_evidence_review_validation_events",
        ["review_snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_review_lifecycle_events",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("review_snapshot_id", sa.String(68), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("review_state", sa.String(16), nullable=False),
        sa.Column("approval_state", sa.String(16), nullable=False),
        sa.Column("actor_tenant_id", sa.String(255), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column("actor_identity_kind", sa.String(32), nullable=False),
        sa.Column("previous_event_sha256", sa.String(64), nullable=False),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mrl_%'",
            name="ck_v2_mat_evid_review_lifecycle_id",
        ),
        sa.CheckConstraint(
            "event_type IN ('reviewed','rejected','approved','revoked','quarantined')",
            name="ck_v2_mat_evid_review_lifecycle_type",
        ),
        sa.CheckConstraint(
            "review_state IN ('draft','reviewed','rejected','revoked','quarantined')",
            name="ck_v2_mat_evid_review_state",
        ),
        sa.CheckConstraint(
            "approval_state IN ('not_approved','approved','revoked','quarantined')",
            name="ck_v2_mat_evid_approval_state",
        ),
        sa.CheckConstraint(
            "actor_role IN ('material_evidence:review','material_evidence:approve')",
            name="ck_v2_mat_evid_review_actor_role",
        ),
        sa.CheckConstraint(
            "actor_identity_kind = 'verified_human'",
            name="ck_v2_mat_evid_review_actor_human",
        ),
        sa.CheckConstraint(
            "sequence_no > 0 AND length(previous_event_sha256) = 64 AND "
            "length(event_sha256) = 64",
            name="ck_v2_mat_evid_review_lifecycle_hashes",
        ),
        sa.ForeignKeyConstraint(
            ["review_snapshot_id"],
            ["v2_material_evidence_review_snapshots.review_snapshot_id"],
            name="fk_v2_mat_evid_review_lifecycle_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "review_snapshot_id",
            "sequence_no",
            name="uq_v2_mat_evid_review_lifecycle_sequence",
        ),
    )
    op.create_index(
        "ix_v2_mat_evid_review_lifecycle_snapshot",
        "v2_material_evidence_review_lifecycle_events",
        ["review_snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_review_audit_events",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("review_snapshot_id", sa.String(68), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor_tenant_id", sa.String(255), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("event_payload_json", _JSON, nullable=False),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mra_%'",
            name="ck_v2_mat_evid_review_audit_id",
        ),
        sa.CheckConstraint(
            "event_type = 'review_snapshot_created'",
            name="ck_v2_mat_evid_review_audit_type",
        ),
        sa.CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_mat_evid_review_audit_hash",
        ),
        sa.ForeignKeyConstraint(
            ["review_snapshot_id"],
            ["v2_material_evidence_review_snapshots.review_snapshot_id"],
            name="fk_v2_mat_evid_review_audit_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_mat_evid_review_audit_snapshot",
        "v2_material_evidence_review_audit_events",
        ["review_snapshot_id"],
    )


def _install_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION sealai_mat_evid_01c_reject_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'MAT-EVID-01C immutable table % rejects %',
                    TG_TABLE_NAME, TG_OP USING ERRCODE = '55000';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        for table in _TABLES:
            trigger = f"trg_{table}_immutable"
            op.execute(f'DROP TRIGGER IF EXISTS "{trigger}" ON "{table}"')
            op.execute(
                f'CREATE TRIGGER "{trigger}" BEFORE UPDATE OR DELETE ON "{table}" '
                "FOR EACH ROW EXECUTE FUNCTION sealai_mat_evid_01c_reject_mutation()"
            )
        return
    if dialect == "sqlite":
        for table in _TABLES:
            for operation in ("UPDATE", "DELETE"):
                trigger = f"trg_{table}_{operation.lower()}_immutable"
                op.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
                op.execute(
                    f'CREATE TRIGGER "{trigger}" BEFORE {operation} ON "{table}" '
                    "BEGIN SELECT RAISE(ABORT, 'MAT-EVID-01C immutable table'); END"
                )
        return
    raise RuntimeError(f"MAT-EVID-01C immutability unsupported on {dialect!r}")


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present and present != expected:
        raise RuntimeError(
            "partial MAT-EVID-01C schema; refusing adoption: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    if present:
        require_schema_fingerprint(
            bind, _TABLES, _ADOPTION_FINGERPRINTS, contract="MAT-EVID-01C"
        )
        return
    _create_tables()
    _install_immutability_triggers()
    require_schema_fingerprint(
        bind, _TABLES, _ADOPTION_FINGERPRINTS, contract="MAT-EVID-01C post-install"
    )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present != expected:
        raise RuntimeError(
            "partial MAT-EVID-01C schema; refusing destructive downgrade: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    populated = [
        table
        for table in _TABLES
        if bind.execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
    ]
    if populated:
        raise RuntimeError(
            "MAT-EVID-01C tables contain data; refusing destructive downgrade: "
            f"{populated}"
        )
    for table in reversed(_TABLES):
        op.drop_table(table)
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS sealai_mat_evid_01c_reject_mutation()")
