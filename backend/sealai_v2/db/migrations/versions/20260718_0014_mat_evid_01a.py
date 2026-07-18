"""Add inert MAT-EVID-01A evidence manifest snapshots.

Revision ID: 20260718_0014
Revises: 20260717_0013

The migration creates empty, immutable technical persistence only. It imports
no matrix text, evidence, seed, backfill, review, approval, pointer, activation,
or deployment data.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from sealai_v2.db.migrations.adoption_fingerprint import require_schema_fingerprint


revision = "20260718_0014"
down_revision = "20260717_0013"
branch_labels = None
depends_on = None

_TABLES = (
    "v2_material_evidence_manifests",
    "v2_material_evidence_snapshots",
    "v2_material_evidence_validation_events",
    "v2_material_evidence_audit_events",
)
_ADOPTION_FINGERPRINTS: dict[str, frozenset[str]] = {
    "postgresql": frozenset(
        {"6152455810e3287776d6dbf545c24aca0d501c0aec207eaa31ec0838081a731d"}
    ),
    "sqlite": frozenset(
        {"02518a6dc365bc9ea79ce6367052fcd3cc68f1a5515d56dae843e2170e8df3ba"}
    ),
}
_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def _create_tables() -> None:
    op.create_table(
        "v2_material_evidence_manifests",
        sa.Column("manifest_id", sa.String(36), nullable=False),
        sa.Column("ruleset_snapshot_id", sa.String(68), nullable=False),
        sa.Column("domain_pack_id", sa.String(128), nullable=False),
        sa.Column("created_by_subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(manifest_id) = 36 AND manifest_id LIKE 'mef_%'",
            name="ck_v2_material_evidence_manifest_id",
        ),
        sa.ForeignKeyConstraint(
            ["ruleset_snapshot_id"],
            ["v2_material_ruleset_snapshots.snapshot_id"],
            name="fk_v2_material_evidence_manifest_ruleset_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("manifest_id"),
        sa.UniqueConstraint(
            "ruleset_snapshot_id",
            name="uq_v2_material_evidence_manifest_ruleset_snapshot",
        ),
    )
    op.create_index(
        "ix_v2_material_evidence_manifests_ruleset_snapshot_id",
        "v2_material_evidence_manifests",
        ["ruleset_snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_snapshots",
        sa.Column("snapshot_id", sa.String(68), nullable=False),
        sa.Column("manifest_id", sa.String(36), nullable=False),
        sa.Column("evidence_manifest_schema_version", sa.Integer(), nullable=False),
        sa.Column("canonicalization_version", sa.Integer(), nullable=False),
        sa.Column("mat_evid_contract_version", sa.String(32), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_payload_json", _JSON, nullable=False),
        sa.Column("canonical_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("created_by_subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(snapshot_id) = 68 AND snapshot_id LIKE 'mes_%'",
            name="ck_v2_material_evidence_snapshot_id",
        ),
        sa.CheckConstraint(
            "length(content_sha256) = 64 AND content_sha256 = lower(content_sha256)",
            name="ck_v2_material_evidence_snapshot_hash",
        ),
        sa.CheckConstraint(
            "evidence_manifest_schema_version = 1",
            name="ck_v2_material_evidence_schema_v1",
        ),
        sa.CheckConstraint(
            "canonicalization_version = 1",
            name="ck_v2_material_evidence_canonicalization_v1",
        ),
        sa.CheckConstraint(
            "mat_evid_contract_version = 'MAT-EVID-01A.v1'",
            name="ck_v2_material_evidence_contract_v1",
        ),
        sa.ForeignKeyConstraint(
            ["manifest_id"],
            ["v2_material_evidence_manifests.manifest_id"],
            name="fk_v2_material_evidence_snapshot_manifest",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("snapshot_id"),
        sa.UniqueConstraint(
            "manifest_id",
            "content_sha256",
            name="uq_v2_material_evidence_snapshot_content",
        ),
    )
    op.create_index(
        "ix_v2_material_evidence_snapshots_manifest_id",
        "v2_material_evidence_snapshots",
        ["manifest_id"],
    )
    op.create_table(
        "v2_material_evidence_validation_events",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(68), nullable=False),
        sa.Column("validator_contract_version", sa.String(32), nullable=False),
        sa.Column("validation_state", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("validation_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mev_%'",
            name="ck_v2_material_evidence_validation_event_id",
        ),
        sa.CheckConstraint(
            "validation_state = 'valid'",
            name="ck_v2_material_evidence_validation_state",
        ),
        sa.CheckConstraint(
            "error_code = 'none'",
            name="ck_v2_material_evidence_validation_error_code",
        ),
        sa.CheckConstraint(
            "length(validation_sha256) = 64",
            name="ck_v2_material_evidence_validation_hash",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["v2_material_evidence_snapshots.snapshot_id"],
            name="fk_v2_material_evidence_validation_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_material_evidence_validation_events_snapshot_id",
        "v2_material_evidence_validation_events",
        ["snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_audit_events",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(68), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("event_payload_json", _JSON, nullable=False),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mea_%'",
            name="ck_v2_material_evidence_audit_event_id",
        ),
        sa.CheckConstraint(
            "event_type = 'snapshot_created'",
            name="ck_v2_material_evidence_audit_event_type",
        ),
        sa.CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_material_evidence_audit_event_hash",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["v2_material_evidence_snapshots.snapshot_id"],
            name="fk_v2_material_evidence_audit_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_material_evidence_audit_events_snapshot_id",
        "v2_material_evidence_audit_events",
        ["snapshot_id"],
    )


def _install_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION sealai_mat_evid_01a_reject_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'MAT-EVID-01A immutable table % rejects %',
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
                "FOR EACH ROW EXECUTE FUNCTION sealai_mat_evid_01a_reject_mutation()"
            )
        return
    if dialect == "sqlite":
        for table in _TABLES:
            for operation in ("UPDATE", "DELETE"):
                trigger = f"trg_{table}_{operation.lower()}_immutable"
                op.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
                op.execute(
                    f'CREATE TRIGGER "{trigger}" BEFORE {operation} ON "{table}" '
                    "BEGIN SELECT RAISE(ABORT, 'MAT-EVID-01A immutable table'); END"
                )
        return
    raise RuntimeError(
        f"MAT-EVID-01A immutability is unsupported on dialect {dialect!r}"
    )


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present and present != expected:
        raise RuntimeError(
            "partial MAT-EVID-01A schema; refusing adoption: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    if present:
        require_schema_fingerprint(
            bind,
            _TABLES,
            _ADOPTION_FINGERPRINTS,
            contract="MAT-EVID-01A",
        )
        return
    _create_tables()
    _install_immutability_triggers()
    require_schema_fingerprint(
        bind,
        _TABLES,
        _ADOPTION_FINGERPRINTS,
        contract="MAT-EVID-01A post-install",
    )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present != expected:
        raise RuntimeError(
            "partial MAT-EVID-01A schema; refusing destructive downgrade: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    populated = [
        table
        for table in _TABLES
        if bind.execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
    ]
    if populated:
        raise RuntimeError(
            "MAT-EVID-01A tables contain data; refusing destructive downgrade: "
            f"{populated}"
        )
    for table in reversed(_TABLES):
        op.drop_table(table)
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS sealai_mat_evid_01a_reject_mutation()")
