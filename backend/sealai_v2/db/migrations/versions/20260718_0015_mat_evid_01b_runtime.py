"""Add immutable MAT-EVID-01B runtime-binding companions.

Revision ID: 20260718_0015
Revises: 20260718_0014

The migration is additive and empty. It creates no binding, pin, evaluation,
seed, backfill, active pointer, review, approval, or deployment state.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from sealai_v2.db.migrations.adoption_fingerprint import require_schema_fingerprint


revision = "20260718_0015"
down_revision = "20260718_0014"
branch_labels = None
depends_on = None

_TABLES = (
    "v2_material_evidence_runtime_bindings",
    "v2_material_evidence_runtime_pins",
    "v2_material_evidence_runtime_evaluations",
    "v2_material_evidence_runtime_evaluation_refs",
    "v2_material_evidence_runtime_audit_events",
)
_ADOPTION_FINGERPRINTS: dict[str, frozenset[str]] = {
    "postgresql": frozenset(
        {"5e039f6971fdd2ec1f286105d4854ac5c4801745265d425d78d6e1c7025bab1d"}
    ),
    "sqlite": frozenset(
        {"a094cabdae90113486e97471b451189e3fd83eb3d80061f9f1859d41b5975c66"}
    ),
}
_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def _create_tables() -> None:
    op.create_table(
        "v2_material_evidence_runtime_bindings",
        sa.Column("binding_id", sa.String(37), nullable=False),
        sa.Column("binding_schema_version", sa.Integer(), nullable=False),
        sa.Column("binding_contract_version", sa.String(32), nullable=False),
        sa.Column("binding_state", sa.String(24), nullable=False),
        sa.Column("ruleset_snapshot_id", sa.String(68), nullable=False),
        sa.Column("ruleset_content_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(68), nullable=True),
        sa.Column("evidence_content_sha256", sa.String(64), nullable=True),
        sa.Column("evidence_manifest_schema_version", sa.Integer(), nullable=True),
        sa.Column("evidence_canonicalization_version", sa.Integer(), nullable=True),
        sa.Column("evidence_contract_version", sa.String(32), nullable=True),
        sa.Column("domain_pack_id", sa.String(128), nullable=False),
        sa.Column("domain_pack_version", sa.String(128), nullable=False),
        sa.Column("evaluator_version", sa.String(128), nullable=False),
        sa.Column("kernel_version", sa.String(128), nullable=False),
        sa.Column("authority", sa.String(32), nullable=False),
        sa.Column("positive_statement_allowed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "binding_state IN ('unbound','bound_unreviewed')",
            name="ck_v2_mat_evid_runtime_binding_state",
        ),
        sa.CheckConstraint(
            "binding_schema_version = 1 AND "
            "binding_contract_version = 'MAT-EVID-01B.v1'",
            name="ck_v2_mat_evid_runtime_binding_contract",
        ),
        sa.CheckConstraint(
            "length(ruleset_content_sha256) = 64",
            name="ck_v2_mat_evid_runtime_binding_ruleset_hash",
        ),
        sa.CheckConstraint(
            "(binding_state = 'unbound' AND evidence_snapshot_id IS NULL AND "
            "evidence_content_sha256 IS NULL AND "
            "evidence_manifest_schema_version IS NULL AND "
            "evidence_canonicalization_version IS NULL AND "
            "evidence_contract_version IS NULL AND authority = 'NONE') OR "
            "(binding_state = 'bound_unreviewed' AND "
            "evidence_snapshot_id IS NOT NULL AND "
            "length(evidence_content_sha256) = 64 AND "
            "evidence_manifest_schema_version = 1 AND "
            "evidence_canonicalization_version = 1 AND "
            "evidence_contract_version = 'MAT-EVID-01A.v1' AND "
            "authority = 'TECHNICAL_UNREVIEWED')",
            name="ck_v2_mat_evid_runtime_binding_evidence_identity",
        ),
        sa.CheckConstraint(
            "positive_statement_allowed IS FALSE",
            name="ck_v2_mat_evid_runtime_binding_no_positive",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["v2_material_shadow_bindings.binding_id"],
            name="fk_v2_mat_evid_runtime_binding_shadow",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ruleset_snapshot_id"],
            ["v2_material_ruleset_snapshots.snapshot_id"],
            name="fk_v2_mat_evid_runtime_binding_ruleset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["v2_material_evidence_snapshots.snapshot_id"],
            name="fk_v2_mat_evid_runtime_binding_evidence",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("binding_id"),
    )
    op.create_index(
        "ix_v2_mat_evid_runtime_bindings_ruleset",
        "v2_material_evidence_runtime_bindings",
        ["ruleset_snapshot_id"],
    )
    op.create_index(
        "ix_v2_mat_evid_runtime_bindings_evidence",
        "v2_material_evidence_runtime_bindings",
        ["evidence_snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_runtime_pins",
        sa.Column("pin_id", sa.String(37), nullable=False),
        sa.Column("pin_schema_version", sa.Integer(), nullable=False),
        sa.Column("binding_id", sa.String(37), nullable=False),
        sa.Column("binding_state", sa.String(24), nullable=False),
        sa.Column("ruleset_snapshot_id", sa.String(68), nullable=False),
        sa.Column("ruleset_content_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(68), nullable=True),
        sa.Column("evidence_content_sha256", sa.String(64), nullable=True),
        sa.Column("authority", sa.String(32), nullable=False),
        sa.Column("positive_statement_allowed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "pin_schema_version = 1",
            name="ck_v2_mat_evid_runtime_pin_schema",
        ),
        sa.CheckConstraint(
            "binding_state IN ('unbound','bound_unreviewed')",
            name="ck_v2_mat_evid_runtime_pin_state",
        ),
        sa.CheckConstraint(
            "length(ruleset_content_sha256) = 64",
            name="ck_v2_mat_evid_runtime_pin_ruleset_hash",
        ),
        sa.CheckConstraint(
            "(binding_state = 'unbound' AND evidence_snapshot_id IS NULL AND "
            "evidence_content_sha256 IS NULL AND authority = 'NONE') OR "
            "(binding_state = 'bound_unreviewed' AND "
            "evidence_snapshot_id IS NOT NULL AND "
            "length(evidence_content_sha256) = 64 AND "
            "authority = 'TECHNICAL_UNREVIEWED')",
            name="ck_v2_mat_evid_runtime_pin_evidence_identity",
        ),
        sa.CheckConstraint(
            "positive_statement_allowed IS FALSE",
            name="ck_v2_mat_evid_runtime_pin_no_positive",
        ),
        sa.ForeignKeyConstraint(
            ["pin_id"],
            ["v2_material_shadow_pins.pin_id"],
            name="fk_v2_mat_evid_runtime_pin_shadow",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["v2_material_evidence_runtime_bindings.binding_id"],
            name="fk_v2_mat_evid_runtime_pin_binding",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("pin_id"),
    )
    op.create_index(
        "ix_v2_material_evidence_runtime_pins_binding_id",
        "v2_material_evidence_runtime_pins",
        ["binding_id"],
    )
    op.create_table(
        "v2_material_evidence_runtime_evaluations",
        sa.Column("evaluation_id", sa.String(37), nullable=False),
        sa.Column("pin_id", sa.String(37), nullable=False),
        sa.Column("binding_state", sa.String(24), nullable=False),
        sa.Column("ruleset_snapshot_id", sa.String(68), nullable=False),
        sa.Column("ruleset_content_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(68), nullable=True),
        sa.Column("evidence_content_sha256", sa.String(64), nullable=True),
        sa.Column("result_sha256", sa.String(64), nullable=False),
        sa.Column("stable_error_code", sa.String(64), nullable=False),
        sa.Column("authority", sa.String(32), nullable=False),
        sa.Column("positive_statement_allowed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "binding_state IN ('unbound','bound_unreviewed')",
            name="ck_v2_mat_evid_runtime_eval_state",
        ),
        sa.CheckConstraint(
            "length(result_sha256) = 64",
            name="ck_v2_mat_evid_runtime_eval_hash",
        ),
        sa.CheckConstraint(
            "positive_statement_allowed IS FALSE",
            name="ck_v2_mat_evid_runtime_eval_no_positive",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["v2_material_shadow_evaluations.evaluation_id"],
            name="fk_v2_mat_evid_runtime_eval_shadow",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pin_id"],
            ["v2_material_evidence_runtime_pins.pin_id"],
            name="fk_v2_mat_evid_runtime_eval_pin",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("evaluation_id"),
    )
    op.create_index(
        "ix_v2_material_evidence_runtime_evaluations_pin_id",
        "v2_material_evidence_runtime_evaluations",
        ["pin_id"],
    )
    op.create_table(
        "v2_material_evidence_runtime_evaluation_refs",
        sa.Column("ref_id", sa.String(37), nullable=False),
        sa.Column("evaluation_id", sa.String(37), nullable=False),
        sa.Column("rule_ref", sa.String(128), nullable=False),
        sa.Column("claim_ref", sa.String(68), nullable=False),
        sa.Column("source_ref", sa.String(68), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["v2_material_evidence_runtime_evaluations.evaluation_id"],
            name="fk_v2_mat_evid_runtime_eval_ref_evaluation",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("ref_id"),
        sa.UniqueConstraint(
            "evaluation_id",
            "rule_ref",
            "claim_ref",
            "source_ref",
            name="uq_v2_mat_evid_runtime_eval_ref",
        ),
    )
    op.create_index(
        "ix_v2_material_evidence_runtime_evaluation_refs_evaluation_id",
        "v2_material_evidence_runtime_evaluation_refs",
        ["evaluation_id"],
    )
    op.create_table(
        "v2_material_evidence_runtime_audit_events",
        sa.Column("event_id", sa.String(37), nullable=False),
        sa.Column("binding_id", sa.String(37), nullable=False),
        sa.Column("pin_id", sa.String(37), nullable=True),
        sa.Column("evaluation_id", sa.String(37), nullable=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("event_payload_json", _JSON, nullable=False),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('binding_created','pin_created',"
            "'evaluation_created','integrity_blocked')",
            name="ck_v2_mat_evid_runtime_audit_type",
        ),
        sa.CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_mat_evid_runtime_audit_hash",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["v2_material_evidence_runtime_bindings.binding_id"],
            name="fk_v2_mat_evid_runtime_audit_binding",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pin_id"],
            ["v2_material_evidence_runtime_pins.pin_id"],
            name="fk_v2_mat_evid_runtime_audit_pin",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["v2_material_evidence_runtime_evaluations.evaluation_id"],
            name="fk_v2_mat_evid_runtime_audit_evaluation",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_material_evidence_runtime_audit_events_binding_id",
        "v2_material_evidence_runtime_audit_events",
        ["binding_id"],
    )


def _install_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION sealai_mat_evid_01b_reject_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'MAT-EVID-01B immutable table % rejects %',
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
                "FOR EACH ROW EXECUTE FUNCTION sealai_mat_evid_01b_reject_mutation()"
            )
        return
    if dialect == "sqlite":
        for table in _TABLES:
            for operation in ("UPDATE", "DELETE"):
                trigger = f"trg_{table}_{operation.lower()}_immutable"
                op.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
                op.execute(
                    f'CREATE TRIGGER "{trigger}" BEFORE {operation} ON "{table}" '
                    "BEGIN SELECT RAISE(ABORT, 'MAT-EVID-01B immutable table'); END"
                )
        return
    raise RuntimeError(
        f"MAT-EVID-01B immutability is unsupported on dialect {dialect!r}"
    )


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present and present != expected:
        raise RuntimeError(
            "partial MAT-EVID-01B schema; refusing adoption: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    if present:
        require_schema_fingerprint(
            bind,
            _TABLES,
            _ADOPTION_FINGERPRINTS,
            contract="MAT-EVID-01B",
        )
        return
    _create_tables()
    _install_immutability_triggers()
    require_schema_fingerprint(
        bind,
        _TABLES,
        _ADOPTION_FINGERPRINTS,
        contract="MAT-EVID-01B post-install",
    )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present != expected:
        raise RuntimeError(
            "partial MAT-EVID-01B schema; refusing destructive downgrade: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    populated = [
        table
        for table in _TABLES
        if bind.execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
    ]
    if populated:
        raise RuntimeError(
            "MAT-EVID-01B tables contain data; refusing destructive downgrade: "
            f"{populated}"
        )
    for table in reversed(_TABLES):
        op.drop_table(table)
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS sealai_mat_evid_01b_reject_mutation()")
