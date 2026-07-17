"""Add inert MAT-GOV-03A immutable material-ruleset snapshots.

Revision ID: 20260717_0011
Revises: 20260714_0010

The migration creates empty technical persistence only.  It imports no matrix
seed, creates no lifecycle/pointer tables, and changes no database roles.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260717_0011"
down_revision = "20260714_0010"
branch_labels = None
depends_on = None

_TABLES = (
    "v2_material_rulesets",
    "v2_material_ruleset_snapshots",
    "v2_material_snapshot_validation_events",
    "v2_material_snapshot_audit_events",
)
_IMMUTABLE_TABLES = _TABLES
_EXPECTED_COLUMNS = {
    "v2_material_rulesets": {
        "ruleset_id",
        "domain_pack_id",
        "created_by_subject",
        "created_at",
    },
    "v2_material_ruleset_snapshots": {
        "snapshot_id",
        "ruleset_id",
        "snapshot_schema_version",
        "canonicalization_version",
        "mat_gov_contract_version",
        "content_sha256",
        "canonical_payload_json",
        "canonical_bytes",
        "created_by_subject",
        "created_at",
    },
    "v2_material_snapshot_validation_events": {
        "event_id",
        "snapshot_id",
        "validator_contract_version",
        "validation_state",
        "error_code",
        "validation_sha256",
        "created_at",
    },
    "v2_material_snapshot_audit_events": {
        "event_id",
        "snapshot_id",
        "event_type",
        "actor_subject",
        "event_payload_json",
        "event_sha256",
        "created_at",
    },
}
_EXPECTED_FOREIGN_KEYS = {
    "v2_material_ruleset_snapshots": {
        ("ruleset_id", "v2_material_rulesets", "ruleset_id")
    },
    "v2_material_snapshot_validation_events": {
        ("snapshot_id", "v2_material_ruleset_snapshots", "snapshot_id")
    },
    "v2_material_snapshot_audit_events": {
        ("snapshot_id", "v2_material_ruleset_snapshots", "snapshot_id")
    },
}
_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def _validate_adopted_schema(inspector: sa.Inspector) -> None:
    missing_columns = {
        table: sorted(
            columns - {column["name"] for column in inspector.get_columns(table)}
        )
        for table, columns in _EXPECTED_COLUMNS.items()
    }
    missing_columns = {
        table: columns for table, columns in missing_columns.items() if columns
    }
    if missing_columns:
        raise RuntimeError(
            "incomplete MAT-GOV-03A schema; refusing adoption: " f"{missing_columns}"
        )
    for table, expected in _EXPECTED_FOREIGN_KEYS.items():
        actual = set()
        for foreign_key in inspector.get_foreign_keys(table):
            constrained = foreign_key.get("constrained_columns") or []
            referred = foreign_key.get("referred_columns") or []
            if len(constrained) == len(referred) == 1:
                actual.add(
                    (
                        constrained[0],
                        foreign_key["referred_table"],
                        referred[0],
                    )
                )
            options = foreign_key.get("options") or {}
            if str(options.get("ondelete", "")).upper() != "RESTRICT":
                raise RuntimeError(
                    f"MAT-GOV-03A foreign key in {table} lacks ON DELETE RESTRICT"
                )
        if expected - actual:
            raise RuntimeError(
                "incomplete MAT-GOV-03A foreign keys; refusing adoption: "
                f"table={table} missing={sorted(expected - actual)}"
            )


def _create_tables() -> None:
    op.create_table(
        "v2_material_rulesets",
        sa.Column("ruleset_id", sa.String(36), nullable=False),
        sa.Column("domain_pack_id", sa.String(128), nullable=False),
        sa.Column("created_by_subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(ruleset_id) = 36 AND ruleset_id LIKE 'mrs_%'",
            name="ck_v2_material_ruleset_id",
        ),
        sa.PrimaryKeyConstraint("ruleset_id"),
    )
    op.create_table(
        "v2_material_ruleset_snapshots",
        sa.Column("snapshot_id", sa.String(68), nullable=False),
        sa.Column("ruleset_id", sa.String(36), nullable=False),
        sa.Column("snapshot_schema_version", sa.Integer(), nullable=False),
        sa.Column("canonicalization_version", sa.Integer(), nullable=False),
        sa.Column("mat_gov_contract_version", sa.String(32), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_payload_json", _JSON, nullable=False),
        sa.Column("canonical_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("created_by_subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(snapshot_id) = 68 AND snapshot_id LIKE 'mss_%'",
            name="ck_v2_material_snapshot_id",
        ),
        sa.CheckConstraint(
            "length(content_sha256) = 64 AND content_sha256 = lower(content_sha256)",
            name="ck_v2_material_snapshot_hash",
        ),
        sa.CheckConstraint(
            "snapshot_schema_version = 1",
            name="ck_v2_material_snapshot_schema_v1",
        ),
        sa.CheckConstraint(
            "canonicalization_version = 1",
            name="ck_v2_material_snapshot_canonicalization_v1",
        ),
        sa.CheckConstraint(
            "mat_gov_contract_version = 'MAT-GOV-03A.v1'",
            name="ck_v2_material_snapshot_contract_v1",
        ),
        sa.ForeignKeyConstraint(
            ["ruleset_id"],
            ["v2_material_rulesets.ruleset_id"],
            name="fk_v2_material_snapshot_ruleset",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("snapshot_id"),
        sa.UniqueConstraint(
            "ruleset_id",
            "content_sha256",
            name="uq_v2_material_ruleset_snapshot_content",
        ),
    )
    op.create_index(
        "ix_v2_material_ruleset_snapshots_ruleset_id",
        "v2_material_ruleset_snapshots",
        ["ruleset_id"],
    )
    op.create_table(
        "v2_material_snapshot_validation_events",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(68), nullable=False),
        sa.Column("validator_contract_version", sa.String(32), nullable=False),
        sa.Column("validation_state", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("validation_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mtv_%'",
            name="ck_v2_material_validation_event_id",
        ),
        sa.CheckConstraint(
            "validation_state = 'valid'",
            name="ck_v2_material_validation_state",
        ),
        sa.CheckConstraint(
            "error_code = 'none'",
            name="ck_v2_material_validation_error_code",
        ),
        sa.CheckConstraint(
            "length(validation_sha256) = 64",
            name="ck_v2_material_validation_hash",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["v2_material_ruleset_snapshots.snapshot_id"],
            name="fk_v2_material_validation_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_material_snapshot_validation_events_snapshot_id",
        "v2_material_snapshot_validation_events",
        ["snapshot_id"],
    )
    op.create_table(
        "v2_material_snapshot_audit_events",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(68), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("event_payload_json", _JSON, nullable=False),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mta_%'",
            name="ck_v2_material_audit_event_id",
        ),
        sa.CheckConstraint(
            "event_type = 'snapshot_created'",
            name="ck_v2_material_audit_event_type",
        ),
        sa.CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_material_audit_event_hash",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["v2_material_ruleset_snapshots.snapshot_id"],
            name="fk_v2_material_audit_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_material_snapshot_audit_events_snapshot_id",
        "v2_material_snapshot_audit_events",
        ["snapshot_id"],
    )


def _install_immutability_triggers() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION sealai_mat_gov_03a_reject_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'MAT-GOV-03A immutable table % rejects %',
                    TG_TABLE_NAME, TG_OP USING ERRCODE = '55000';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        for table in _IMMUTABLE_TABLES:
            trigger = f"trg_{table}_immutable"
            op.execute(f'DROP TRIGGER IF EXISTS "{trigger}" ON "{table}"')
            op.execute(
                f'CREATE TRIGGER "{trigger}" BEFORE UPDATE OR DELETE ON "{table}" '
                "FOR EACH ROW EXECUTE FUNCTION sealai_mat_gov_03a_reject_mutation()"
            )
        return
    if dialect == "sqlite":
        for table in _IMMUTABLE_TABLES:
            for operation in ("UPDATE", "DELETE"):
                trigger = f"trg_{table}_{operation.lower()}_immutable"
                op.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
                op.execute(
                    f'CREATE TRIGGER "{trigger}" BEFORE {operation} ON "{table}" '
                    "BEGIN SELECT RAISE(ABORT, 'MAT-GOV-03A immutable table'); END"
                )
        return
    raise RuntimeError(
        f"MAT-GOV-03A immutability is unsupported on dialect {dialect!r}"
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present and present != expected:
        raise RuntimeError(
            "partial MAT-GOV-03A schema; refusing adoption: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    if present:
        _validate_adopted_schema(inspector)
    else:
        _create_tables()
    _install_immutability_triggers()


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present != expected:
        raise RuntimeError(
            "partial MAT-GOV-03A schema; refusing destructive downgrade: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    populated = [
        table
        for table in _TABLES
        if bind.execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
    ]
    if populated:
        raise RuntimeError(
            "MAT-GOV-03A tables contain data; refusing destructive downgrade: "
            f"{populated}"
        )
    for table in reversed(_TABLES):
        op.drop_table(table)
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS sealai_mat_gov_03a_reject_mutation()")
