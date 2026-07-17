"""Add empty, pointerless MAT-GOV-03B shadow persistence.

Revision ID: 20260717_0012
Revises: 20260717_0011

No binding, snapshot selection, seed, backfill, activation, approval, deployment
state, cohort, or public management surface is created by this migration.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260717_0012"
down_revision = "20260717_0011"
branch_labels = None
depends_on = None

_TABLES = (
    "v2_material_shadow_bindings",
    "v2_material_shadow_binding_events",
    "v2_material_shadow_pins",
    "v2_material_shadow_session_versions",
    "v2_material_shadow_session_upgrade_events",
    "v2_material_shadow_outbox",
    "v2_material_shadow_evaluations",
    "v2_material_shadow_evaluation_matches",
    "v2_material_shadow_evaluation_refs",
)
_IMMUTABLE = tuple(table for table in _TABLES if table != "v2_material_shadow_outbox")

_EXPECTED_COLUMNS = {
    "v2_material_shadow_bindings": {
        "binding_id",
        "binding_schema_version",
        "snapshot_id",
        "content_sha256",
        "environment",
        "purpose",
        "scope_kind",
        "tenant_ref_hmac",
        "hmac_key_id",
        "domain_pack_id",
        "domain_pack_version",
        "evaluator_version",
        "kernel_version",
        "runtime_profile_sha256",
        "build_git_sha",
        "build_tree_hash",
        "valid_from",
        "valid_until",
        "creator_subject",
        "reason",
        "sampling_policy_version",
        "sampling_basis_points",
        "created_at",
    },
    "v2_material_shadow_binding_events": {
        "event_id",
        "event_schema_version",
        "binding_id",
        "event_type",
        "actor_subject",
        "reason",
        "effective_at",
        "created_at",
        "event_sha256",
    },
    "v2_material_shadow_pins": {
        "pin_id",
        "pin_schema_version",
        "binding_id",
        "snapshot_id",
        "content_sha256",
        "environment",
        "purpose",
        "scope_kind",
        "tenant_ref_hmac",
        "hmac_key_id",
        "domain_pack_id",
        "domain_pack_version",
        "evaluator_version",
        "kernel_version",
        "runtime_profile_sha256",
        "build_git_sha",
        "build_tree_hash",
        "sampling_policy_version",
        "sampled",
        "authority",
        "positive_statement_allowed",
        "acquired_at",
        "binding_valid_until",
    },
    "v2_material_shadow_session_versions": {
        "session_version_id",
        "session_ref_hmac",
        "hmac_key_id",
        "version_no",
        "pin_id",
        "created_at",
    },
    "v2_material_shadow_session_upgrade_events": {
        "event_id",
        "from_session_version_id",
        "to_session_version_id",
        "actor_subject",
        "reason",
        "created_at",
    },
    "v2_material_shadow_outbox": {
        "job_id",
        "pin_id",
        "session_version_id",
        "sequence_no",
        "hmac_key_id",
        "correlation_hmac",
        "case_ref_hmac",
        "decision_ref_hmac",
        "material_id",
        "medium_id",
        "material_state",
        "medium_state",
        "medium_cardinality",
        "relation_state",
        "domain_pack_id",
        "domain_pack_version",
        "input_fingerprint",
        "idempotency_key",
        "status",
        "attempts",
        "stable_error_code",
        "created_at",
        "claimed_at",
        "next_attempt_at",
        "completed_at",
    },
    "v2_material_shadow_evaluations": {
        "evaluation_id",
        "job_id",
        "pin_id",
        "hmac_key_id",
        "evaluation_state",
        "verdict",
        "decisive_ref",
        "result_sha256",
        "stable_error_code",
        "cache_hit",
        "authority",
        "positive_statement_allowed",
        "created_at",
        "expires_at",
    },
    "v2_material_shadow_evaluation_matches": {
        "match_id",
        "evaluation_id",
        "rule_ref",
        "verdict",
        "source_ref",
    },
    "v2_material_shadow_evaluation_refs": {
        "ref_id",
        "evaluation_id",
        "ref_kind",
        "ref_hmac",
        "hmac_key_id",
        "authority",
    },
}

_EXPECTED_PRIMARY_KEYS = {
    "v2_material_shadow_bindings": "binding_id",
    "v2_material_shadow_binding_events": "event_id",
    "v2_material_shadow_pins": "pin_id",
    "v2_material_shadow_session_versions": "session_version_id",
    "v2_material_shadow_session_upgrade_events": "event_id",
    "v2_material_shadow_outbox": "job_id",
    "v2_material_shadow_evaluations": "evaluation_id",
    "v2_material_shadow_evaluation_matches": "match_id",
    "v2_material_shadow_evaluation_refs": "ref_id",
}

_EXPECTED_NULLABLE = {
    "v2_material_shadow_bindings": {"tenant_ref_hmac", "hmac_key_id"},
    "v2_material_shadow_binding_events": set(),
    "v2_material_shadow_pins": set(),
    "v2_material_shadow_session_versions": set(),
    "v2_material_shadow_session_upgrade_events": set(),
    "v2_material_shadow_outbox": {
        "case_ref_hmac",
        "decision_ref_hmac",
        "claimed_at",
        "next_attempt_at",
        "completed_at",
    },
    "v2_material_shadow_evaluations": {"verdict", "decisive_ref"},
    "v2_material_shadow_evaluation_matches": set(),
    "v2_material_shadow_evaluation_refs": set(),
}

_EXPECTED_FKS = {
    (
        "v2_material_shadow_bindings",
        "snapshot_id",
        "v2_material_ruleset_snapshots",
        "snapshot_id",
    ),
    (
        "v2_material_shadow_binding_events",
        "binding_id",
        "v2_material_shadow_bindings",
        "binding_id",
    ),
    (
        "v2_material_shadow_pins",
        "binding_id",
        "v2_material_shadow_bindings",
        "binding_id",
    ),
    (
        "v2_material_shadow_pins",
        "snapshot_id",
        "v2_material_ruleset_snapshots",
        "snapshot_id",
    ),
    (
        "v2_material_shadow_session_versions",
        "pin_id",
        "v2_material_shadow_pins",
        "pin_id",
    ),
    (
        "v2_material_shadow_session_upgrade_events",
        "from_session_version_id",
        "v2_material_shadow_session_versions",
        "session_version_id",
    ),
    (
        "v2_material_shadow_session_upgrade_events",
        "to_session_version_id",
        "v2_material_shadow_session_versions",
        "session_version_id",
    ),
    ("v2_material_shadow_outbox", "pin_id", "v2_material_shadow_pins", "pin_id"),
    (
        "v2_material_shadow_outbox",
        "session_version_id",
        "v2_material_shadow_session_versions",
        "session_version_id",
    ),
    ("v2_material_shadow_evaluations", "job_id", "v2_material_shadow_outbox", "job_id"),
    ("v2_material_shadow_evaluations", "pin_id", "v2_material_shadow_pins", "pin_id"),
    (
        "v2_material_shadow_evaluation_matches",
        "evaluation_id",
        "v2_material_shadow_evaluations",
        "evaluation_id",
    ),
    (
        "v2_material_shadow_evaluation_refs",
        "evaluation_id",
        "v2_material_shadow_evaluations",
        "evaluation_id",
    ),
}

_EXPECTED_CHECKS = {
    "v2_material_shadow_bindings": {
        "ck_v2_material_shadow_binding_id",
        "ck_v2_material_shadow_binding_schema_v1",
        "ck_v2_material_shadow_purpose",
        "ck_v2_material_shadow_environment",
        "ck_v2_material_shadow_scope_kind",
        "ck_v2_material_shadow_scope_tenant",
        "ck_v2_material_shadow_content_hash",
        "ck_v2_material_shadow_runtime_hash",
        "ck_v2_material_shadow_valid_interval",
        "ck_v2_material_shadow_sampling_zero",
    },
    "v2_material_shadow_binding_events": {
        "ck_v2_material_shadow_binding_event_type",
        "ck_v2_material_shadow_binding_event_schema_v1",
        "ck_v2_material_shadow_binding_event_hash",
    },
    "v2_material_shadow_pins": {
        "ck_v2_material_shadow_pin_authority",
        "ck_v2_material_shadow_pin_no_positive",
        "ck_v2_material_shadow_pin_unsampled",
        "ck_v2_material_shadow_pin_schema_v1",
        "ck_v2_material_shadow_pin_hashes",
    },
    "v2_material_shadow_session_versions": {
        "ck_v2_material_shadow_session_version",
        "ck_v2_material_shadow_session_hmac",
    },
    "v2_material_shadow_outbox": {
        "ck_v2_material_shadow_sequence",
        "ck_v2_material_shadow_job_status",
        "ck_v2_material_shadow_job_eligible_input",
        "ck_v2_material_shadow_job_integrity",
    },
    "v2_material_shadow_evaluations": {
        "ck_v2_material_shadow_eval_authority",
        "ck_v2_material_shadow_eval_no_positive",
        "ck_v2_material_shadow_eval_state",
        "ck_v2_material_shadow_eval_verdict",
        "ck_v2_material_shadow_eval_hash",
    },
    "v2_material_shadow_evaluation_matches": {
        "ck_v2_material_shadow_match_verdict",
        "ck_v2_material_shadow_match_source",
    },
    "v2_material_shadow_evaluation_refs": {
        "ck_v2_material_shadow_ref_kind",
        "ck_v2_material_shadow_ref_authority",
        "ck_v2_material_shadow_ref_hmac",
    },
}

_EXPECTED_UNIQUES = {
    "v2_material_shadow_session_versions": {"uq_v2_material_shadow_session_version"},
    "v2_material_shadow_session_upgrade_events": {
        "uq_v2_material_shadow_session_upgrade_from",
        "uq_v2_material_shadow_session_upgrade_to",
    },
    "v2_material_shadow_outbox": {
        "uq_v2_material_shadow_outbox_idem",
        "uq_v2_material_shadow_session_sequence",
    },
    "v2_material_shadow_evaluations": {"uq_v2_material_shadow_evaluation_job"},
    "v2_material_shadow_evaluation_matches": {"uq_v2_material_shadow_eval_match"},
    "v2_material_shadow_evaluation_refs": {"uq_v2_material_shadow_ref"},
}


def _create_tables() -> None:
    op.create_table(
        "v2_material_shadow_bindings",
        sa.Column("binding_id", sa.String(37), primary_key=True),
        sa.Column("binding_schema_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.String(68), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("scope_kind", sa.String(16), nullable=False),
        sa.Column("tenant_ref_hmac", sa.String(64), nullable=True),
        sa.Column("hmac_key_id", sa.String(64), nullable=True),
        sa.Column("domain_pack_id", sa.String(128), nullable=False),
        sa.Column("domain_pack_version", sa.String(128), nullable=False),
        sa.Column("evaluator_version", sa.String(128), nullable=False),
        sa.Column("kernel_version", sa.String(128), nullable=False),
        sa.Column("runtime_profile_sha256", sa.String(64), nullable=False),
        sa.Column("build_git_sha", sa.String(40), nullable=False),
        sa.Column("build_tree_hash", sa.String(40), nullable=False),
        sa.Column("valid_from", sa.String(32), nullable=False),
        sa.Column("valid_until", sa.String(32), nullable=False),
        sa.Column("creator_subject", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("sampling_policy_version", sa.String(128), nullable=False),
        sa.Column("sampling_basis_points", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "length(binding_id)=37 AND binding_id LIKE 'mshb_%'",
            name="ck_v2_material_shadow_binding_id",
        ),
        sa.CheckConstraint(
            "binding_schema_version=1",
            name="ck_v2_material_shadow_binding_schema_v1",
        ),
        sa.CheckConstraint(
            "purpose='MATERIAL_RULESET_SHADOW'",
            name="ck_v2_material_shadow_purpose",
        ),
        sa.CheckConstraint(
            "environment IN ('development','staging','production')",
            name="ck_v2_material_shadow_environment",
        ),
        sa.CheckConstraint(
            "scope_kind IN ('GLOBAL','TENANT_CANARY')",
            name="ck_v2_material_shadow_scope_kind",
        ),
        sa.CheckConstraint(
            "(scope_kind='GLOBAL' AND tenant_ref_hmac IS NULL AND "
            "hmac_key_id IS NULL) OR "
            "(scope_kind='TENANT_CANARY' AND length(tenant_ref_hmac)=64 "
            "AND hmac_key_id IS NOT NULL AND length(hmac_key_id)>0)",
            name="ck_v2_material_shadow_scope_tenant",
        ),
        sa.CheckConstraint(
            "length(content_sha256)=64 AND content_sha256=lower(content_sha256)",
            name="ck_v2_material_shadow_content_hash",
        ),
        sa.CheckConstraint(
            "length(runtime_profile_sha256)=64",
            name="ck_v2_material_shadow_runtime_hash",
        ),
        sa.CheckConstraint(
            "valid_until > valid_from",
            name="ck_v2_material_shadow_valid_interval",
        ),
        sa.CheckConstraint(
            "sampling_basis_points=0",
            name="ck_v2_material_shadow_sampling_zero",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["v2_material_ruleset_snapshots.snapshot_id"],
            name="fk_v2_material_shadow_binding_snapshot",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_v2_material_shadow_binding_lookup",
        "v2_material_shadow_bindings",
        [
            "environment",
            "purpose",
            "scope_kind",
            "tenant_ref_hmac",
            "hmac_key_id",
            "domain_pack_id",
        ],
    )
    op.create_index(
        "ix_v2_material_shadow_binding_snapshot",
        "v2_material_shadow_bindings",
        ["snapshot_id"],
    )

    op.create_table(
        "v2_material_shadow_binding_events",
        sa.Column("event_id", sa.String(37), primary_key=True),
        sa.Column("event_schema_version", sa.Integer(), nullable=False),
        sa.Column("binding_id", sa.String(37), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("effective_at", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('CREATED','REVOKED','TERMINATED')",
            name="ck_v2_material_shadow_binding_event_type",
        ),
        sa.CheckConstraint(
            "event_schema_version=1",
            name="ck_v2_material_shadow_binding_event_schema_v1",
        ),
        sa.CheckConstraint(
            "length(event_sha256)=64",
            name="ck_v2_material_shadow_binding_event_hash",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["v2_material_shadow_bindings.binding_id"],
            name="fk_v2_material_shadow_event_binding",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_v2_material_shadow_event_binding",
        "v2_material_shadow_binding_events",
        ["binding_id"],
    )
    op.create_index(
        "uq_v2_material_shadow_event_created",
        "v2_material_shadow_binding_events",
        ["binding_id"],
        unique=True,
        postgresql_where=sa.text("event_type='CREATED'"),
        sqlite_where=sa.text("event_type='CREATED'"),
    )
    op.create_index(
        "uq_v2_material_shadow_event_terminal",
        "v2_material_shadow_binding_events",
        ["binding_id"],
        unique=True,
        postgresql_where=sa.text("event_type IN ('REVOKED','TERMINATED')"),
        sqlite_where=sa.text("event_type IN ('REVOKED','TERMINATED')"),
    )

    op.create_table(
        "v2_material_shadow_pins",
        sa.Column("pin_id", sa.String(37), primary_key=True),
        sa.Column("pin_schema_version", sa.Integer(), nullable=False),
        sa.Column("binding_id", sa.String(37), nullable=False),
        sa.Column("snapshot_id", sa.String(68), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("scope_kind", sa.String(16), nullable=False),
        sa.Column("tenant_ref_hmac", sa.String(64), nullable=False),
        sa.Column("hmac_key_id", sa.String(64), nullable=False),
        sa.Column("domain_pack_id", sa.String(128), nullable=False),
        sa.Column("domain_pack_version", sa.String(128), nullable=False),
        sa.Column("evaluator_version", sa.String(128), nullable=False),
        sa.Column("kernel_version", sa.String(128), nullable=False),
        sa.Column("runtime_profile_sha256", sa.String(64), nullable=False),
        sa.Column("build_git_sha", sa.String(40), nullable=False),
        sa.Column("build_tree_hash", sa.String(40), nullable=False),
        sa.Column("sampling_policy_version", sa.String(128), nullable=False),
        sa.Column("sampled", sa.Boolean(), nullable=False),
        sa.Column("authority", sa.String(32), nullable=False),
        sa.Column("positive_statement_allowed", sa.Boolean(), nullable=False),
        sa.Column("acquired_at", sa.String(32), nullable=False),
        sa.Column("binding_valid_until", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "authority='SHADOW_NON_AUTHORITATIVE'",
            name="ck_v2_material_shadow_pin_authority",
        ),
        sa.CheckConstraint(
            "positive_statement_allowed IS FALSE",
            name="ck_v2_material_shadow_pin_no_positive",
        ),
        sa.CheckConstraint(
            "sampled IS FALSE", name="ck_v2_material_shadow_pin_unsampled"
        ),
        sa.CheckConstraint(
            "pin_schema_version=1", name="ck_v2_material_shadow_pin_schema_v1"
        ),
        sa.CheckConstraint(
            "length(content_sha256)=64 AND "
            "length(runtime_profile_sha256)=64 AND "
            "length(tenant_ref_hmac)=64",
            name="ck_v2_material_shadow_pin_hashes",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["v2_material_shadow_bindings.binding_id"],
            name="fk_v2_material_shadow_pin_binding",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["v2_material_ruleset_snapshots.snapshot_id"],
            name="fk_v2_material_shadow_pin_snapshot",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_v2_material_shadow_pin_binding",
        "v2_material_shadow_pins",
        ["binding_id"],
    )
    op.create_index(
        "ix_v2_material_shadow_pin_tenant",
        "v2_material_shadow_pins",
        ["tenant_ref_hmac"],
    )

    op.create_table(
        "v2_material_shadow_session_versions",
        sa.Column("session_version_id", sa.String(37), primary_key=True),
        sa.Column("session_ref_hmac", sa.String(64), nullable=False),
        sa.Column("hmac_key_id", sa.String(64), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("pin_id", sa.String(37), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "version_no>0", name="ck_v2_material_shadow_session_version"
        ),
        sa.CheckConstraint(
            "length(session_ref_hmac)=64",
            name="ck_v2_material_shadow_session_hmac",
        ),
        sa.ForeignKeyConstraint(
            ["pin_id"],
            ["v2_material_shadow_pins.pin_id"],
            name="fk_v2_material_shadow_session_pin",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "session_ref_hmac",
            "version_no",
            name="uq_v2_material_shadow_session_version",
        ),
    )
    op.create_index(
        "ix_v2_material_shadow_session_ref",
        "v2_material_shadow_session_versions",
        ["session_ref_hmac"],
    )

    op.create_table(
        "v2_material_shadow_session_upgrade_events",
        sa.Column("event_id", sa.String(37), primary_key=True),
        sa.Column("from_session_version_id", sa.String(37), nullable=False),
        sa.Column("to_session_version_id", sa.String(37), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["from_session_version_id"],
            ["v2_material_shadow_session_versions.session_version_id"],
            name="fk_v2_material_shadow_upgrade_from",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_session_version_id"],
            ["v2_material_shadow_session_versions.session_version_id"],
            name="fk_v2_material_shadow_upgrade_to",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "from_session_version_id",
            name="uq_v2_material_shadow_session_upgrade_from",
        ),
        sa.UniqueConstraint(
            "to_session_version_id",
            name="uq_v2_material_shadow_session_upgrade_to",
        ),
    )

    op.create_table(
        "v2_material_shadow_outbox",
        sa.Column("job_id", sa.String(37), primary_key=True),
        sa.Column("pin_id", sa.String(37), nullable=False),
        sa.Column("session_version_id", sa.String(37), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("hmac_key_id", sa.String(64), nullable=False),
        sa.Column("correlation_hmac", sa.String(64), nullable=False),
        sa.Column("case_ref_hmac", sa.String(64), nullable=True),
        sa.Column("decision_ref_hmac", sa.String(64), nullable=True),
        sa.Column("material_id", sa.String(128), nullable=False),
        sa.Column("medium_id", sa.String(128), nullable=False),
        sa.Column("material_state", sa.String(16), nullable=False),
        sa.Column("medium_state", sa.String(16), nullable=False),
        sa.Column("medium_cardinality", sa.String(16), nullable=False),
        sa.Column("relation_state", sa.String(24), nullable=False),
        sa.Column("domain_pack_id", sa.String(128), nullable=False),
        sa.Column("domain_pack_version", sa.String(128), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("stable_error_code", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("claimed_at", sa.String(32), nullable=True),
        sa.Column("next_attempt_at", sa.String(32), nullable=True),
        sa.Column("completed_at", sa.String(32), nullable=True),
        sa.CheckConstraint("sequence_no>0", name="ck_v2_material_shadow_sequence"),
        sa.CheckConstraint(
            "status IN ('pending','processing','done','failed')",
            name="ck_v2_material_shadow_job_status",
        ),
        sa.CheckConstraint(
            "material_state='known' AND medium_state='known' AND "
            "medium_cardinality='single' AND relation_state='not_applicable'",
            name="ck_v2_material_shadow_job_eligible_input",
        ),
        sa.CheckConstraint(
            "attempts>=0 AND length(correlation_hmac)=64 AND "
            "length(input_fingerprint)=64 AND length(idempotency_key)=64 AND "
            "(case_ref_hmac IS NULL OR length(case_ref_hmac)=64) AND "
            "(decision_ref_hmac IS NULL OR length(decision_ref_hmac)=64)",
            name="ck_v2_material_shadow_job_integrity",
        ),
        sa.ForeignKeyConstraint(
            ["pin_id"],
            ["v2_material_shadow_pins.pin_id"],
            name="fk_v2_material_shadow_job_pin",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_version_id"],
            ["v2_material_shadow_session_versions.session_version_id"],
            name="fk_v2_material_shadow_job_session",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_v2_material_shadow_outbox_idem"
        ),
        sa.UniqueConstraint(
            "session_version_id",
            "sequence_no",
            name="uq_v2_material_shadow_session_sequence",
        ),
    )
    op.create_index(
        "ix_v2_material_shadow_outbox_status",
        "v2_material_shadow_outbox",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "ix_v2_material_shadow_outbox_session",
        "v2_material_shadow_outbox",
        ["session_version_id", "sequence_no"],
    )

    op.create_table(
        "v2_material_shadow_evaluations",
        sa.Column("evaluation_id", sa.String(37), primary_key=True),
        sa.Column("job_id", sa.String(37), nullable=False),
        sa.Column("pin_id", sa.String(37), nullable=False),
        sa.Column("hmac_key_id", sa.String(64), nullable=False),
        sa.Column("evaluation_state", sa.String(40), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=True),
        sa.Column("decisive_ref", sa.String(128), nullable=True),
        sa.Column("result_sha256", sa.String(64), nullable=False),
        sa.Column("stable_error_code", sa.String(64), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("authority", sa.String(32), nullable=False),
        sa.Column("positive_statement_allowed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "authority='SHADOW_NON_AUTHORITATIVE'",
            name="ck_v2_material_shadow_eval_authority",
        ),
        sa.CheckConstraint(
            "positive_statement_allowed IS FALSE",
            name="ck_v2_material_shadow_eval_no_positive",
        ),
        sa.CheckConstraint(
            "evaluation_state IN ('evaluated','blocked','no_rule_data',"
            "'ineligible_unresolved_input','revoked','integrity_blocked',"
            "'cache_unavailable','retry_exhausted')",
            name="ck_v2_material_shadow_eval_state",
        ),
        sa.CheckConstraint(
            "(evaluation_state='evaluated' AND "
            "verdict IN ('vertraeglich','unvertraeglich','bedingt') AND "
            "decisive_ref IS NOT NULL) OR "
            "(evaluation_state<>'evaluated' AND verdict IS NULL AND "
            "decisive_ref IS NULL)",
            name="ck_v2_material_shadow_eval_verdict",
        ),
        sa.CheckConstraint(
            "length(result_sha256)=64",
            name="ck_v2_material_shadow_eval_hash",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["v2_material_shadow_outbox.job_id"],
            name="fk_v2_material_shadow_eval_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pin_id"],
            ["v2_material_shadow_pins.pin_id"],
            name="fk_v2_material_shadow_eval_pin",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("job_id", name="uq_v2_material_shadow_evaluation_job"),
    )

    op.create_table(
        "v2_material_shadow_evaluation_matches",
        sa.Column("match_id", sa.String(37), primary_key=True),
        sa.Column("evaluation_id", sa.String(37), nullable=False),
        sa.Column("rule_ref", sa.String(128), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(256), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["v2_material_shadow_evaluations.evaluation_id"],
            name="fk_v2_material_shadow_match_eval",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "evaluation_id", "rule_ref", name="uq_v2_material_shadow_eval_match"
        ),
        sa.CheckConstraint(
            "verdict IN ('vertraeglich','unvertraeglich','bedingt')",
            name="ck_v2_material_shadow_match_verdict",
        ),
        sa.CheckConstraint(
            "source_ref='matrix-cell:' || rule_ref",
            name="ck_v2_material_shadow_match_source",
        ),
    )
    op.create_index(
        "ix_v2_material_shadow_match_eval",
        "v2_material_shadow_evaluation_matches",
        ["evaluation_id"],
    )

    op.create_table(
        "v2_material_shadow_evaluation_refs",
        sa.Column("ref_id", sa.String(37), primary_key=True),
        sa.Column("evaluation_id", sa.String(37), nullable=False),
        sa.Column("ref_kind", sa.String(16), nullable=False),
        sa.Column("ref_hmac", sa.String(64), nullable=False),
        sa.Column("hmac_key_id", sa.String(64), nullable=False),
        sa.Column("authority", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "ref_kind IN ('REQUEST','SESSION','CASE','DECISION')",
            name="ck_v2_material_shadow_ref_kind",
        ),
        sa.CheckConstraint(
            "authority='SHADOW_NON_AUTHORITATIVE'",
            name="ck_v2_material_shadow_ref_authority",
        ),
        sa.CheckConstraint(
            "length(ref_hmac)=64",
            name="ck_v2_material_shadow_ref_hmac",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["v2_material_shadow_evaluations.evaluation_id"],
            name="fk_v2_material_shadow_ref_eval",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "evaluation_id", "ref_kind", "ref_hmac", name="uq_v2_material_shadow_ref"
        ),
    )
    op.create_index(
        "ix_v2_material_shadow_ref_eval",
        "v2_material_shadow_evaluation_refs",
        ["evaluation_id"],
    )


def _install_guards() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION sealai_mat_gov_03b_reject_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'MAT-GOV-03B immutable table % rejects %',
                    TG_TABLE_NAME, TG_OP USING ERRCODE='55000';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        for table in _IMMUTABLE:
            trigger = f"trg_{table}_immutable"
            op.execute(f'DROP TRIGGER IF EXISTS "{trigger}" ON "{table}"')
            op.execute(
                f'CREATE TRIGGER "{trigger}" BEFORE UPDATE OR DELETE ON "{table}" '
                "FOR EACH ROW EXECUTE FUNCTION sealai_mat_gov_03b_reject_mutation()"
            )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION sealai_mat_gov_03b_binding_insert_guard()
            RETURNS trigger AS $$
            DECLARE
                partition_key text;
                stored_hash text;
                max_lifetime interval;
            BEGIN
                partition_key := concat_ws(E'\\x1f', NEW.environment, NEW.purpose,
                    NEW.scope_kind, coalesce(NEW.tenant_ref_hmac, '<GLOBAL>'),
                    coalesce(NEW.hmac_key_id, '<NO_KEY>'),
                    NEW.domain_pack_id);
                PERFORM pg_advisory_xact_lock(hashtextextended(partition_key, 73003));
                SELECT content_sha256 INTO stored_hash
                  FROM v2_material_ruleset_snapshots
                 WHERE snapshot_id=NEW.snapshot_id;
                IF stored_hash IS NULL OR stored_hash <> NEW.content_sha256 THEN
                    RAISE EXCEPTION 'MAT-GOV-03B snapshot/hash mismatch'
                        USING ERRCODE='23514';
                END IF;
                max_lifetime := CASE WHEN NEW.environment='production'
                    THEN interval '4 hours' ELSE interval '24 hours' END;
                IF NEW.valid_until::timestamptz - NEW.valid_from::timestamptz
                    > max_lifetime THEN
                    RAISE EXCEPTION 'MAT-GOV-03B binding lifetime exceeded'
                        USING ERRCODE='23514';
                END IF;
                IF EXISTS (
                    SELECT 1 FROM v2_material_shadow_bindings existing
                     WHERE existing.environment=NEW.environment
                       AND existing.purpose=NEW.purpose
                       AND existing.scope_kind=NEW.scope_kind
                       AND coalesce(existing.tenant_ref_hmac, '<GLOBAL>')=
                           coalesce(NEW.tenant_ref_hmac, '<GLOBAL>')
                       AND coalesce(existing.hmac_key_id, '<NO_KEY>')=
                           coalesce(NEW.hmac_key_id, '<NO_KEY>')
                       AND existing.domain_pack_id=NEW.domain_pack_id
                       AND existing.valid_from < NEW.valid_until
                       AND NEW.valid_from < existing.valid_until
                ) THEN
                    RAISE EXCEPTION 'MAT-GOV-03B overlapping binding'
                        USING ERRCODE='23P01';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_v2_material_shadow_binding_insert_guard
            BEFORE INSERT ON v2_material_shadow_bindings
            FOR EACH ROW EXECUTE FUNCTION sealai_mat_gov_03b_binding_insert_guard()
            """
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
            """
            CREATE TRIGGER trg_v2_material_shadow_outbox_update_guard
            BEFORE UPDATE ON v2_material_shadow_outbox
            FOR EACH ROW EXECUTE FUNCTION sealai_mat_gov_03b_outbox_guard()
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_v2_material_shadow_outbox_delete_guard
            BEFORE DELETE ON v2_material_shadow_outbox
            FOR EACH ROW EXECUTE FUNCTION sealai_mat_gov_03b_reject_mutation()
            """
        )
        return
    if dialect == "sqlite":
        for table in _IMMUTABLE:
            for operation in ("UPDATE", "DELETE"):
                trigger = f"trg_{table}_{operation.lower()}_immutable"
                op.execute(
                    f'CREATE TRIGGER "{trigger}" BEFORE {operation} ON "{table}" '
                    "BEGIN SELECT RAISE(ABORT, 'MAT-GOV-03B immutable table'); END"
                )
        op.execute(
            """
            CREATE TRIGGER trg_v2_material_shadow_binding_insert_guard
            BEFORE INSERT ON v2_material_shadow_bindings
            BEGIN
                SELECT CASE WHEN NOT EXISTS (
                    SELECT 1 FROM v2_material_ruleset_snapshots s
                     WHERE s.snapshot_id=NEW.snapshot_id
                       AND s.content_sha256=NEW.content_sha256
                ) THEN RAISE(ABORT, 'MAT-GOV-03B snapshot/hash mismatch') END;
                SELECT CASE WHEN EXISTS (
                    SELECT 1 FROM v2_material_shadow_bindings existing
                     WHERE existing.environment=NEW.environment
                       AND existing.purpose=NEW.purpose
                       AND existing.scope_kind=NEW.scope_kind
                       AND coalesce(existing.tenant_ref_hmac, '<GLOBAL>')=
                           coalesce(NEW.tenant_ref_hmac, '<GLOBAL>')
                       AND coalesce(existing.hmac_key_id, '<NO_KEY>')=
                           coalesce(NEW.hmac_key_id, '<NO_KEY>')
                       AND existing.domain_pack_id=NEW.domain_pack_id
                       AND existing.valid_from < NEW.valid_until
                       AND NEW.valid_from < existing.valid_until
                ) THEN RAISE(ABORT, 'MAT-GOV-03B overlapping binding') END;
            END
            """
        )
        immutable_cols = (
            "job_id,pin_id,session_version_id,sequence_no,hmac_key_id,"
            "correlation_hmac,case_ref_hmac,decision_ref_hmac,material_id,medium_id,"
            "material_state,medium_state,"
            "medium_cardinality,relation_state,domain_pack_id,domain_pack_version,"
            "input_fingerprint,idempotency_key,created_at"
        ).split(",")
        changed = " OR ".join(f"OLD.{col} IS NOT NEW.{col}" for col in immutable_cols)
        op.execute(
            "CREATE TRIGGER trg_v2_material_shadow_outbox_update_guard "
            "BEFORE UPDATE ON v2_material_shadow_outbox "
            f"WHEN {changed} BEGIN SELECT RAISE(ABORT, "
            "'MAT-GOV-03B outbox payload is immutable'); END"
        )
        op.execute(
            "CREATE TRIGGER trg_v2_material_shadow_outbox_delete_guard "
            "BEFORE DELETE ON v2_material_shadow_outbox "
            "BEGIN SELECT RAISE(ABORT, 'MAT-GOV-03B outbox is immutable'); END"
        )
        return
    raise RuntimeError(f"MAT-GOV-03B unsupported database dialect {dialect!r}")


def _validate_adopted_schema() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, expected_columns in _EXPECTED_COLUMNS.items():
        columns = inspector.get_columns(table)
        actual_columns = {column["name"] for column in columns}
        allowed_columns = {frozenset(expected_columns)}
        if table == "v2_material_shadow_outbox":
            allowed_columns.add(
                frozenset(expected_columns | {"lease_owner", "lease_expires_at"})
            )
        if frozenset(actual_columns) not in allowed_columns:
            raise RuntimeError(
                "invalid MAT-GOV-03B adoption columns: "
                f"table={table} actual={sorted(actual_columns)} "
                f"expected={sorted(expected_columns)}"
            )
        actual_nullable = {column["name"] for column in columns if column["nullable"]}
        allowed_nullable = {frozenset(_EXPECTED_NULLABLE[table])}
        if table == "v2_material_shadow_outbox":
            allowed_nullable.add(
                frozenset(
                    _EXPECTED_NULLABLE[table] | {"lease_owner", "lease_expires_at"}
                )
            )
        if frozenset(actual_nullable) not in allowed_nullable:
            raise RuntimeError(
                "invalid MAT-GOV-03B adoption nullability: "
                f"table={table} actual={sorted(actual_nullable)} "
                f"expected={sorted(_EXPECTED_NULLABLE[table])}"
            )
        primary_key = inspector.get_pk_constraint(table)["constrained_columns"]
        if primary_key != [_EXPECTED_PRIMARY_KEYS[table]]:
            raise RuntimeError(
                "invalid MAT-GOV-03B adoption primary key: "
                f"table={table} actual={primary_key} "
                f"expected={[_EXPECTED_PRIMARY_KEYS[table]]}"
            )

    actual_fks: set[tuple[str, str, str, str]] = set()
    for table in _TABLES:
        for foreign_key in inspector.get_foreign_keys(table):
            if (
                len(foreign_key["constrained_columns"]) != 1
                or len(foreign_key["referred_columns"]) != 1
            ):
                raise RuntimeError(
                    f"invalid MAT-GOV-03B composite foreign key in {table}"
                )
            if str(foreign_key.get("options", {}).get("ondelete", "")).upper() != (
                "RESTRICT"
            ):
                raise RuntimeError(
                    f"invalid MAT-GOV-03B foreign-key deletion policy in {table}"
                )
            actual_fks.add(
                (
                    table,
                    foreign_key["constrained_columns"][0],
                    foreign_key["referred_table"],
                    foreign_key["referred_columns"][0],
                )
            )
    if actual_fks != _EXPECTED_FKS:
        raise RuntimeError(
            "invalid MAT-GOV-03B adoption foreign keys: "
            f"actual={sorted(actual_fks)} expected={sorted(_EXPECTED_FKS)}"
        )

    for table, expected in _EXPECTED_CHECKS.items():
        actual = {
            constraint["name"] for constraint in inspector.get_check_constraints(table)
        }
        if not expected <= actual:
            raise RuntimeError(
                "invalid MAT-GOV-03B adoption checks: "
                f"table={table} missing={sorted(expected - actual)}"
            )
    for table, expected in _EXPECTED_UNIQUES.items():
        actual = {
            constraint["name"] for constraint in inspector.get_unique_constraints(table)
        }
        if not expected <= actual:
            raise RuntimeError(
                "invalid MAT-GOV-03B adoption unique constraints: "
                f"table={table} missing={sorted(expected - actual)}"
            )


def _ensure_adoption_indexes() -> None:
    inspector = sa.inspect(op.get_bind())

    def create_if_missing(
        name: str,
        table: str,
        columns: list[str],
        *,
        unique: bool = False,
        where: str | None = None,
    ) -> None:
        existing = {index["name"] for index in inspector.get_indexes(table)}
        if name in existing:
            return
        kwargs: dict[str, object] = {}
        if where is not None:
            kwargs["postgresql_where"] = sa.text(where)
            kwargs["sqlite_where"] = sa.text(where)
        op.create_index(name, table, columns, unique=unique, **kwargs)

    create_if_missing(
        "ix_v2_material_shadow_binding_lookup",
        "v2_material_shadow_bindings",
        [
            "environment",
            "purpose",
            "scope_kind",
            "tenant_ref_hmac",
            "hmac_key_id",
            "domain_pack_id",
        ],
    )
    create_if_missing(
        "uq_v2_material_shadow_event_created",
        "v2_material_shadow_binding_events",
        ["binding_id"],
        unique=True,
        where="event_type='CREATED'",
    )
    create_if_missing(
        "uq_v2_material_shadow_event_terminal",
        "v2_material_shadow_binding_events",
        ["binding_id"],
        unique=True,
        where="event_type IN ('REVOKED','TERMINATED')",
    )
    create_if_missing(
        "ix_v2_material_shadow_outbox_status",
        "v2_material_shadow_outbox",
        ["status", "next_attempt_at"],
    )
    create_if_missing(
        "ix_v2_material_shadow_outbox_session",
        "v2_material_shadow_outbox",
        ["session_version_id", "sequence_no"],
    )


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present and present != expected:
        raise RuntimeError(
            "partial MAT-GOV-03B schema; refusing adoption: "
            f"present={sorted(present)} missing={sorted(expected-present)}"
        )
    if present:
        _validate_adopted_schema()
        _ensure_adoption_indexes()
    else:
        _create_tables()
    _install_guards()


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present != expected:
        raise RuntimeError(
            "partial MAT-GOV-03B schema; refusing destructive downgrade: "
            f"present={sorted(present)} missing={sorted(expected-present)}"
        )
    populated = [
        table
        for table in _TABLES
        if bind.execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
    ]
    if populated:
        raise RuntimeError(
            "MAT-GOV-03B tables contain data; refusing destructive downgrade: "
            f"{populated}"
        )
    for table in reversed(_TABLES):
        op.drop_table(table)
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS sealai_mat_gov_03b_outbox_guard()")
        op.execute("DROP FUNCTION IF EXISTS sealai_mat_gov_03b_binding_insert_guard()")
        op.execute("DROP FUNCTION IF EXISTS sealai_mat_gov_03b_reject_mutation()")
