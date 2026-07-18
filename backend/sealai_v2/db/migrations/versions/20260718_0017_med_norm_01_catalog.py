"""Add inert MED-NORM-01 closed media-catalog persistence.

Revision ID: 20260718_0017
Revises: 20260718_0016

The migration is additive and empty.  It creates no catalog entries, seed,
backfill, active pointer, runtime binding, public API, sampling, or deployment
state.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from sealai_v2.db.migrations.adoption_fingerprint import require_schema_fingerprint


revision = "20260718_0017"
down_revision = "20260718_0016"
branch_labels = None
depends_on = None

_TABLES = (
    "v2_medium_catalogs",
    "v2_medium_catalog_snapshots",
    "v2_medium_catalog_validation_events",
    "v2_medium_catalog_audit_events",
)
_ADOPTION_FINGERPRINTS: dict[str, frozenset[str]] = {
    "postgresql": frozenset(
        {"3ec4852fa84151737b101e711ceb064bb1bd443d8c1dec1685288e2cbc900ed3"}
    ),
    "sqlite": frozenset(
        {"6bd79741ab9c46ac4e176fb06b87ad2674316a27dce21d38061fd0dc11dc1af6"}
    ),
}
_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def _create_tables() -> None:
    op.create_table(
        "v2_medium_catalogs",
        sa.Column("catalog_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("domain_pack_id", sa.String(128), nullable=False),
        sa.Column("created_by_subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(catalog_id) = 36 AND catalog_id LIKE 'mcf_%'",
            name="ck_v2_medium_catalog_id",
        ),
        sa.PrimaryKeyConstraint("catalog_id"),
    )
    op.create_index(
        "ix_v2_medium_catalogs_tenant_id", "v2_medium_catalogs", ["tenant_id"]
    )
    op.create_table(
        "v2_medium_catalog_snapshots",
        sa.Column("snapshot_id", sa.String(68), nullable=False),
        sa.Column("catalog_id", sa.String(36), nullable=False),
        sa.Column("media_catalog_schema_version", sa.Integer(), nullable=False),
        sa.Column("canonicalization_version", sa.Integer(), nullable=False),
        sa.Column("med_norm_contract_version", sa.String(32), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_payload_json", _JSON, nullable=False),
        sa.Column("canonical_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("runtime_authority", sa.String(32), nullable=False),
        sa.Column("positive_statement_allowed", sa.Boolean(), nullable=False),
        sa.Column("created_by_subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(snapshot_id) = 68 AND snapshot_id LIKE 'mcs_%'",
            name="ck_v2_medium_catalog_snapshot_id",
        ),
        sa.CheckConstraint(
            "media_catalog_schema_version = 1 AND canonicalization_version = 1 "
            "AND med_norm_contract_version = 'MED-NORM-01.v1'",
            name="ck_v2_medium_catalog_snapshot_contract",
        ),
        sa.CheckConstraint(
            "length(content_sha256) = 64",
            name="ck_v2_medium_catalog_snapshot_hash",
        ),
        sa.CheckConstraint(
            "runtime_authority = 'NORMALIZATION_ONLY' "
            "AND positive_statement_allowed IS FALSE",
            name="ck_v2_medium_catalog_no_positive_authority",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_id"],
            ["v2_medium_catalogs.catalog_id"],
            name="fk_v2_medium_catalog_snapshot_catalog",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("snapshot_id"),
        sa.UniqueConstraint(
            "catalog_id",
            "content_sha256",
            name="uq_v2_medium_catalog_snapshot_content",
        ),
    )
    op.create_index(
        "ix_v2_medium_catalog_snapshots_catalog_id",
        "v2_medium_catalog_snapshots",
        ["catalog_id"],
    )
    op.create_table(
        "v2_medium_catalog_validation_events",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(68), nullable=False),
        sa.Column("validator_contract_version", sa.String(32), nullable=False),
        sa.Column("validation_state", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("validation_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mcv_%'",
            name="ck_v2_medium_catalog_validation_id",
        ),
        sa.CheckConstraint(
            "validation_state = 'valid' AND error_code = 'none'",
            name="ck_v2_medium_catalog_validation_state",
        ),
        sa.CheckConstraint(
            "length(validation_sha256) = 64",
            name="ck_v2_medium_catalog_validation_hash",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["v2_medium_catalog_snapshots.snapshot_id"],
            name="fk_v2_medium_catalog_validation_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_medium_catalog_validation_events_snapshot_id",
        "v2_medium_catalog_validation_events",
        ["snapshot_id"],
    )
    op.create_table(
        "v2_medium_catalog_audit_events",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(68), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("event_payload_json", _JSON, nullable=False),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mca_%'",
            name="ck_v2_medium_catalog_audit_id",
        ),
        sa.CheckConstraint(
            "event_type = 'catalog_snapshot_created'",
            name="ck_v2_medium_catalog_audit_type",
        ),
        sa.CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_medium_catalog_audit_hash",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["v2_medium_catalog_snapshots.snapshot_id"],
            name="fk_v2_medium_catalog_audit_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_medium_catalog_audit_events_snapshot_id",
        "v2_medium_catalog_audit_events",
        ["snapshot_id"],
    )


def _install_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION sealai_med_norm_01_reject_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'MED-NORM-01 immutable table % rejects %',
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
                "FOR EACH ROW EXECUTE FUNCTION sealai_med_norm_01_reject_mutation()"
            )
        return
    if dialect == "sqlite":
        for table in _TABLES:
            for operation in ("UPDATE", "DELETE"):
                trigger = f"trg_{table}_{operation.lower()}_immutable"
                op.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
                op.execute(
                    f'CREATE TRIGGER "{trigger}" BEFORE {operation} ON "{table}" '
                    "BEGIN SELECT RAISE(ABORT, 'MED-NORM-01 immutable table'); END"
                )
        return
    raise RuntimeError(f"MED-NORM-01 immutability unsupported on {dialect!r}")


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present and present != expected:
        raise RuntimeError(
            "partial MED-NORM-01 schema; refusing adoption: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    if present:
        require_schema_fingerprint(
            bind, _TABLES, _ADOPTION_FINGERPRINTS, contract="MED-NORM-01"
        )
        return
    _create_tables()
    _install_immutability_triggers()
    require_schema_fingerprint(
        bind, _TABLES, _ADOPTION_FINGERPRINTS, contract="MED-NORM-01 post-install"
    )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present != expected:
        raise RuntimeError(
            "partial MED-NORM-01 schema; refusing destructive downgrade: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    populated = [
        table
        for table in _TABLES
        if bind.execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
    ]
    if populated:
        raise RuntimeError(
            "MED-NORM-01 tables contain data; refusing destructive downgrade: "
            f"{populated}"
        )
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(
            "DROP FUNCTION IF EXISTS sealai_med_norm_01_reject_mutation() CASCADE"
        )
    elif dialect != "sqlite":
        raise RuntimeError(f"MED-NORM-01 downgrade unsupported on {dialect!r}")
    for table in reversed(_TABLES):
        op.drop_table(table)
