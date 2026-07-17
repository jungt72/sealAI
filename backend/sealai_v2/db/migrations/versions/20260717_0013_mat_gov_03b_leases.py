"""Add bounded, claim-accounted MAT-GOV-03B worker leases.

Revision ID: 20260717_0013
Revises: 20260717_0012

This additive migration contains no binding, pin, job, seed, backfill, active
pointer, approval, deployment, cohort, or public management data.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260717_0013"
down_revision = "20260717_0012"
branch_labels = None
depends_on = None

_TABLE = "v2_material_shadow_outbox"
_LEASE_COLUMNS = {"lease_owner", "lease_expires_at"}


def _postgres_guard() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_v2_material_shadow_outbox_update_guard "
        "ON v2_material_shadow_outbox"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_v2_material_shadow_outbox_insert_lease_guard "
        "ON v2_material_shadow_outbox"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sealai_mat_gov_03b_outbox_guard()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'pending' OR NEW.attempts <> 0
                   OR NEW.claimed_at IS NOT NULL OR NEW.lease_owner IS NOT NULL
                   OR NEW.lease_expires_at IS NOT NULL
                   OR NEW.stable_error_code <> 'none' THEN
                    RAISE EXCEPTION 'MAT-GOV-03B invalid initial lease state'
                        USING ERRCODE='23514';
                END IF;
                RETURN NEW;
            END IF;
            IF ROW(OLD.job_id,OLD.pin_id,OLD.session_version_id,OLD.sequence_no,
                OLD.hmac_key_id,OLD.correlation_hmac,OLD.case_ref_hmac,
                OLD.decision_ref_hmac,OLD.material_id,OLD.medium_id,
                OLD.material_state,OLD.medium_state,OLD.medium_cardinality,
                OLD.relation_state,OLD.domain_pack_id,OLD.domain_pack_version,
                OLD.input_fingerprint,OLD.idempotency_key,OLD.created_at)
               IS DISTINCT FROM
               ROW(NEW.job_id,NEW.pin_id,NEW.session_version_id,NEW.sequence_no,
                NEW.hmac_key_id,NEW.correlation_hmac,NEW.case_ref_hmac,
                NEW.decision_ref_hmac,NEW.material_id,NEW.medium_id,
                NEW.material_state,NEW.medium_state,NEW.medium_cardinality,
                NEW.relation_state,NEW.domain_pack_id,NEW.domain_pack_version,
                NEW.input_fingerprint,NEW.idempotency_key,NEW.created_at) THEN
                RAISE EXCEPTION 'MAT-GOV-03B outbox payload is immutable'
                    USING ERRCODE='55000';
            END IF;
            IF OLD.status IN ('done','failed') AND ROW(
                OLD.status,OLD.attempts,OLD.stable_error_code,OLD.claimed_at,
                OLD.lease_owner,OLD.lease_expires_at,OLD.next_attempt_at,
                OLD.completed_at) IS DISTINCT FROM ROW(
                NEW.status,NEW.attempts,NEW.stable_error_code,NEW.claimed_at,
                NEW.lease_owner,NEW.lease_expires_at,NEW.next_attempt_at,
                NEW.completed_at) THEN
                RAISE EXCEPTION 'MAT-GOV-03B terminal job is immutable'
                    USING ERRCODE='55000';
            END IF;
            IF NEW.attempts < OLD.attempts OR NEW.attempts > OLD.attempts + 1 THEN
                RAISE EXCEPTION 'MAT-GOV-03B invalid attempt transition'
                    USING ERRCODE='23514';
            END IF;
            IF NEW.status = 'processing' THEN
                IF NEW.attempts <> OLD.attempts + 1
                   OR NEW.claimed_at IS NULL OR NEW.lease_owner IS NULL
                   OR NEW.lease_expires_at IS NULL
                   OR NEW.lease_expires_at <= NEW.claimed_at THEN
                    RAISE EXCEPTION 'MAT-GOV-03B claim must consume one attempt'
                        USING ERRCODE='23514';
                END IF;
            ELSIF NEW.lease_owner IS NOT NULL OR NEW.lease_expires_at IS NOT NULL THEN
                RAISE EXCEPTION 'MAT-GOV-03B non-processing job carries a lease'
                    USING ERRCODE='23514';
            ELSIF NEW.attempts <> OLD.attempts THEN
                RAISE EXCEPTION 'MAT-GOV-03B attempt changed outside claim'
                    USING ERRCODE='23514';
            END IF;
            IF NEW.stable_error_code = 'SHADOW_LEASE_ATTEMPTS_EXHAUSTED'
               AND (NEW.status <> 'failed' OR NEW.completed_at IS NULL) THEN
                RAISE EXCEPTION 'MAT-GOV-03B invalid lease exhaustion state'
                    USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_v2_material_shadow_outbox_insert_lease_guard "
        "BEFORE INSERT ON v2_material_shadow_outbox FOR EACH ROW "
        "EXECUTE FUNCTION sealai_mat_gov_03b_outbox_guard()"
    )
    op.execute(
        "CREATE TRIGGER trg_v2_material_shadow_outbox_update_guard "
        "BEFORE UPDATE ON v2_material_shadow_outbox FOR EACH ROW "
        "EXECUTE FUNCTION sealai_mat_gov_03b_outbox_guard()"
    )


def _sqlite_guard() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_v2_material_shadow_outbox_update_guard")
    op.execute(
        """
        CREATE TRIGGER trg_v2_material_shadow_outbox_insert_lease_guard
        BEFORE INSERT ON v2_material_shadow_outbox
        WHEN NEW.status <> 'pending' OR NEW.attempts <> 0
          OR NEW.claimed_at IS NOT NULL OR NEW.lease_owner IS NOT NULL
          OR NEW.lease_expires_at IS NOT NULL OR NEW.stable_error_code <> 'none'
        BEGIN
          SELECT RAISE(ABORT, 'MAT-GOV-03B invalid initial lease state');
        END
        """
    )
    immutable_cols = (
        "job_id,pin_id,session_version_id,sequence_no,hmac_key_id,"
        "correlation_hmac,case_ref_hmac,decision_ref_hmac,material_id,medium_id,"
        "material_state,medium_state,medium_cardinality,relation_state,"
        "domain_pack_id,domain_pack_version,input_fingerprint,idempotency_key,"
        "created_at"
    ).split(",")
    immutable_changed = " OR ".join(
        f"OLD.{column} IS NOT NEW.{column}" for column in immutable_cols
    )
    terminal_changed = " OR ".join(
        f"OLD.{column} IS NOT NEW.{column}"
        for column in (
            "status",
            "attempts",
            "stable_error_code",
            "claimed_at",
            "lease_owner",
            "lease_expires_at",
            "next_attempt_at",
            "completed_at",
        )
    )
    invalid = (
        f"({immutable_changed}) OR "
        f"(OLD.status IN ('done','failed') AND ({terminal_changed})) OR "
        "NEW.attempts < OLD.attempts OR NEW.attempts > OLD.attempts + 1 OR "
        "(NEW.status = 'processing' AND ("
        "NEW.attempts <> OLD.attempts + 1 OR NEW.claimed_at IS NULL OR "
        "NEW.lease_owner IS NULL OR NEW.lease_expires_at IS NULL OR "
        "NEW.lease_expires_at <= NEW.claimed_at)) OR "
        "(NEW.status <> 'processing' AND (NEW.lease_owner IS NOT NULL OR "
        "NEW.lease_expires_at IS NOT NULL)) OR "
        "(NEW.status <> 'processing' AND NEW.attempts <> OLD.attempts) OR "
        "(NEW.stable_error_code = 'SHADOW_LEASE_ATTEMPTS_EXHAUSTED' AND "
        "(NEW.status <> 'failed' OR NEW.completed_at IS NULL))"
    )
    op.execute(
        "CREATE TRIGGER trg_v2_material_shadow_outbox_update_guard "
        "BEFORE UPDATE ON v2_material_shadow_outbox "
        f"WHEN {invalid} BEGIN SELECT RAISE(ABORT, "
        "'MAT-GOV-03B invalid outbox lease transition'); END"
    )


def _install_guard() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        _postgres_guard()
    elif dialect == "sqlite":
        _sqlite_guard()
    else:
        raise RuntimeError(f"MAT-GOV-03B unsupported database dialect {dialect!r}")


def _restore_0012_guard() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_v2_material_shadow_outbox_update_guard "
            "ON v2_material_shadow_outbox"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_v2_material_shadow_outbox_insert_lease_guard "
            "ON v2_material_shadow_outbox"
        )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION sealai_mat_gov_03b_outbox_guard()
            RETURNS trigger AS $$
            BEGIN
                IF ROW(OLD.job_id,OLD.pin_id,OLD.session_version_id,OLD.sequence_no,
                    OLD.hmac_key_id,OLD.correlation_hmac,OLD.case_ref_hmac,
                    OLD.decision_ref_hmac,OLD.material_id,OLD.medium_id,
                    OLD.material_state,OLD.medium_state,OLD.medium_cardinality,
                    OLD.relation_state,OLD.domain_pack_id,OLD.domain_pack_version,
                    OLD.input_fingerprint,OLD.idempotency_key,OLD.created_at)
                   IS DISTINCT FROM
                   ROW(NEW.job_id,NEW.pin_id,NEW.session_version_id,NEW.sequence_no,
                    NEW.hmac_key_id,NEW.correlation_hmac,NEW.case_ref_hmac,
                    NEW.decision_ref_hmac,NEW.material_id,NEW.medium_id,
                    NEW.material_state,NEW.medium_state,NEW.medium_cardinality,
                    NEW.relation_state,NEW.domain_pack_id,NEW.domain_pack_version,
                    NEW.input_fingerprint,NEW.idempotency_key,NEW.created_at) THEN
                    RAISE EXCEPTION 'MAT-GOV-03B outbox payload is immutable'
                        USING ERRCODE='55000';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            "CREATE TRIGGER trg_v2_material_shadow_outbox_update_guard "
            "BEFORE UPDATE ON v2_material_shadow_outbox FOR EACH ROW "
            "EXECUTE FUNCTION sealai_mat_gov_03b_outbox_guard()"
        )
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_v2_material_shadow_outbox_update_guard")
        op.execute(
            "DROP TRIGGER IF EXISTS trg_v2_material_shadow_outbox_insert_lease_guard"
        )
        immutable_cols = (
            "job_id,pin_id,session_version_id,sequence_no,hmac_key_id,"
            "correlation_hmac,case_ref_hmac,decision_ref_hmac,material_id,medium_id,"
            "material_state,medium_state,medium_cardinality,relation_state,"
            "domain_pack_id,domain_pack_version,input_fingerprint,idempotency_key,"
            "created_at"
        ).split(",")
        changed = " OR ".join(
            f"OLD.{column} IS NOT NEW.{column}" for column in immutable_cols
        )
        op.execute(
            "CREATE TRIGGER trg_v2_material_shadow_outbox_update_guard "
            "BEFORE UPDATE ON v2_material_shadow_outbox "
            f"WHEN {changed} BEGIN SELECT RAISE(ABORT, "
            "'MAT-GOV-03B outbox payload is immutable'); END"
        )
    else:
        raise RuntimeError(f"MAT-GOV-03B unsupported database dialect {dialect!r}")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        raise RuntimeError("MAT-GOV-03B outbox table is missing")
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    present = existing & _LEASE_COLUMNS
    if present and present != _LEASE_COLUMNS:
        raise RuntimeError("partial MAT-GOV-03B lease schema; refusing adoption")
    if not present:
        populated = bind.execute(
            sa.text(f'SELECT COUNT(*) FROM "{_TABLE}"')
        ).scalar_one()
        if populated:
            raise RuntimeError(
                "MAT-GOV-03B outbox contains data; refusing lease retrofit"
            )
        op.add_column(_TABLE, sa.Column("lease_owner", sa.String(64), nullable=True))
        op.add_column(
            _TABLE, sa.Column("lease_expires_at", sa.String(32), nullable=True)
        )
    _install_guard()


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(sa.text(f'SELECT COUNT(*) FROM "{_TABLE}"')).scalar_one()
    if populated:
        raise RuntimeError("MAT-GOV-03B outbox contains data; refusing lease downgrade")
    _restore_0012_guard()
    op.drop_column(_TABLE, "lease_expires_at")
    op.drop_column(_TABLE, "lease_owner")
