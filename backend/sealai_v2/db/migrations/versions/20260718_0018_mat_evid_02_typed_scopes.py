"""Add inert MAT-EVID v2 typed-scope persistence.

Revision ID: 20260718_0018
Revises: 20260718_0017

All tables are additive and initially empty.  No v1 row is converted, copied,
rehashed, reinterpreted, or migrated.  The migration creates no claim, source,
rule, catalog entry, approval, runtime activation, API, or deployment state.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from sealai_v2.db.migrations.adoption_fingerprint import require_schema_fingerprint


revision = "20260718_0018"
down_revision = "20260718_0017"
branch_labels = None
depends_on = None

_TABLES = (
    "v2_material_evidence_manifests_v2",
    "v2_material_evidence_snapshots_v2",
    "v2_material_evidence_validation_events_v2",
    "v2_material_evidence_audit_events_v2",
    "v2_material_evidence_runtime_bindings_v2",
    "v2_material_evidence_runtime_pins_v2",
    "v2_material_evidence_runtime_evaluations_v2",
    "v2_material_evidence_runtime_evaluation_refs_v2",
    "v2_material_evidence_runtime_audit_events_v2",
    "v2_material_evidence_review_dossiers_v2",
    "v2_material_evidence_review_snapshots_v2",
    "v2_material_evidence_review_validation_events_v2",
    "v2_material_evidence_review_lifecycle_events_v2",
    "v2_material_evidence_review_audit_events_v2",
)
_ADOPTION_FINGERPRINTS: dict[str, frozenset[str]] = {
    "postgresql": frozenset(
        {"d05a037ad6780689ede880b3eb6c40f1b0c6fadb59a52d872316b9c86f897c07"}
    ),
    "sqlite": frozenset(
        {"b16514d6f60a1a1e9388410896351a4b6688159a6a8a50136e79280332135c5d"}
    ),
}
_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def _create_manifest_tables() -> None:
    op.create_table(
        "v2_material_evidence_manifests_v2",
        sa.Column("manifest_id", sa.String(36), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_ref", sa.String(68), nullable=False),
        sa.Column("ruleset_snapshot_id", sa.String(68), nullable=True),
        sa.Column("media_ref", sa.String(68), nullable=True),
        sa.Column("domain_pack_id", sa.String(128), nullable=False),
        sa.Column("created_by_subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(manifest_id) = 36 AND manifest_id LIKE 'mef_%'",
            name="ck_v2_material_evidence_manifest_v2_id",
        ),
        sa.CheckConstraint(
            "(target_type = 'material_relation' AND "
            "ruleset_snapshot_id IS NOT NULL AND media_ref IS NULL AND "
            "target_ref = ruleset_snapshot_id) OR "
            "(target_type = 'media_identity' AND "
            "ruleset_snapshot_id IS NULL AND length(media_ref) = 68 "
            "AND media_ref LIKE 'med_%' AND target_ref = media_ref)",
            name="ck_v2_material_evidence_manifest_v2_target",
        ),
        sa.ForeignKeyConstraint(
            ["ruleset_snapshot_id"],
            ["v2_material_ruleset_snapshots.snapshot_id"],
            name="fk_v2_material_evidence_manifest_v2_ruleset",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("manifest_id"),
        sa.UniqueConstraint(
            "target_type",
            "target_ref",
            "domain_pack_id",
            name="uq_v2_material_evidence_manifest_v2_target",
        ),
    )
    op.create_index(
        "ix_v2_material_evidence_manifests_v2_ruleset_snapshot_id",
        "v2_material_evidence_manifests_v2",
        ["ruleset_snapshot_id"],
    )
    op.create_index(
        "ix_v2_material_evidence_manifests_v2_media_ref",
        "v2_material_evidence_manifests_v2",
        ["media_ref"],
    )
    op.create_table(
        "v2_material_evidence_snapshots_v2",
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
            name="ck_v2_material_evidence_snapshot_v2_id",
        ),
        sa.CheckConstraint(
            "length(content_sha256) = 64 AND content_sha256 = lower(content_sha256)",
            name="ck_v2_material_evidence_snapshot_v2_hash",
        ),
        sa.CheckConstraint(
            "evidence_manifest_schema_version = 2 AND "
            "canonicalization_version = 2 AND "
            "mat_evid_contract_version = 'MAT-EVID-01A.v2'",
            name="ck_v2_material_evidence_snapshot_v2_contract",
        ),
        sa.ForeignKeyConstraint(
            ["manifest_id"],
            ["v2_material_evidence_manifests_v2.manifest_id"],
            name="fk_v2_material_evidence_snapshot_v2_manifest",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("snapshot_id"),
        sa.UniqueConstraint(
            "manifest_id",
            "content_sha256",
            name="uq_v2_material_evidence_snapshot_v2_content",
        ),
    )
    op.create_index(
        "ix_v2_material_evidence_snapshots_v2_manifest_id",
        "v2_material_evidence_snapshots_v2",
        ["manifest_id"],
    )
    op.create_table(
        "v2_material_evidence_validation_events_v2",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(68), nullable=False),
        sa.Column("validator_contract_version", sa.String(32), nullable=False),
        sa.Column("validation_state", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("validation_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mev_%'",
            name="ck_v2_material_evidence_validation_v2_id",
        ),
        sa.CheckConstraint(
            "validation_state = 'valid' AND error_code = 'none'",
            name="ck_v2_material_evidence_validation_v2_state",
        ),
        sa.CheckConstraint(
            "length(validation_sha256) = 64",
            name="ck_v2_material_evidence_validation_v2_hash",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["v2_material_evidence_snapshots_v2.snapshot_id"],
            name="fk_v2_material_evidence_validation_v2_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_material_evidence_validation_events_v2_snapshot_id",
        "v2_material_evidence_validation_events_v2",
        ["snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_audit_events_v2",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(68), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("event_payload_json", _JSON, nullable=False),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mea_%'",
            name="ck_v2_material_evidence_audit_v2_id",
        ),
        sa.CheckConstraint(
            "event_type = 'snapshot_created'",
            name="ck_v2_material_evidence_audit_v2_type",
        ),
        sa.CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_material_evidence_audit_v2_hash",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["v2_material_evidence_snapshots_v2.snapshot_id"],
            name="fk_v2_material_evidence_audit_v2_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_material_evidence_audit_events_v2_snapshot_id",
        "v2_material_evidence_audit_events_v2",
        ["snapshot_id"],
    )


def _create_review_tables() -> None:
    op.create_table(
        "v2_material_evidence_review_dossiers_v2",
        sa.Column("review_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(68), nullable=False),
        sa.Column("creator_subject", sa.String(255), nullable=False),
        sa.Column("creator_identity_kind", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(review_id) = 36 AND review_id LIKE 'mer_%'",
            name="ck_v2_mat_evid_review_v2_id",
        ),
        sa.CheckConstraint(
            "creator_identity_kind = 'verified_human'",
            name="ck_v2_mat_evid_review_v2_creator_human",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["v2_material_evidence_snapshots_v2.snapshot_id"],
            name="fk_v2_mat_evid_review_v2_evidence",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("review_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "evidence_snapshot_id",
            name="uq_v2_mat_evid_review_v2_tenant_evidence",
        ),
    )
    op.create_index(
        "ix_v2_material_evidence_review_dossiers_v2_tenant_id",
        "v2_material_evidence_review_dossiers_v2",
        ["tenant_id"],
    )
    op.create_index(
        "ix_v2_material_evidence_review_dossiers_v2_evidence_snapshot_id",
        "v2_material_evidence_review_dossiers_v2",
        ["evidence_snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_review_snapshots_v2",
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
            name="ck_v2_mat_evid_review_snapshot_v2_id",
        ),
        sa.CheckConstraint(
            "review_schema_version = 2 AND canonicalization_version = 2 AND "
            "mat_evid_review_contract_version = 'MAT-EVID-01C.v2'",
            name="ck_v2_mat_evid_review_snapshot_v2_contract",
        ),
        sa.CheckConstraint(
            "evidence_manifest_schema_version = 2 AND "
            "evidence_contract_version = 'MAT-EVID-01A.v2'",
            name="ck_v2_mat_evid_review_v2_evidence_contract",
        ),
        sa.CheckConstraint(
            "length(content_sha256) = 64 AND length(evidence_content_sha256) = 64",
            name="ck_v2_mat_evid_review_snapshot_v2_hashes",
        ),
        sa.CheckConstraint(
            "runtime_authority = 'FACTUAL_REVIEW_ONLY' AND "
            "positive_statement_allowed IS FALSE",
            name="ck_v2_mat_evid_review_v2_no_runtime_authority",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["v2_material_evidence_review_dossiers_v2.review_id"],
            name="fk_v2_mat_evid_review_snapshot_v2_dossier",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["v2_material_evidence_snapshots_v2.snapshot_id"],
            name="fk_v2_mat_evid_review_snapshot_v2_evidence",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("review_snapshot_id"),
        sa.UniqueConstraint(
            "review_id",
            "content_sha256",
            name="uq_v2_mat_evid_review_snapshot_v2_content",
        ),
    )
    op.create_index(
        "ix_v2_material_evidence_review_snapshots_v2_review_id",
        "v2_material_evidence_review_snapshots_v2",
        ["review_id"],
    )
    op.create_index(
        "ix_v2_mat_evid_review_snapshot_v2_evidence",
        "v2_material_evidence_review_snapshots_v2",
        ["evidence_snapshot_id"],
    )
    _create_review_event_table(
        "v2_material_evidence_review_validation_events_v2",
        "mvv_%",
        "validation",
    )
    op.create_table(
        "v2_material_evidence_review_lifecycle_events_v2",
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
            name="ck_v2_mat_evid_review_lifecycle_v2_id",
        ),
        sa.CheckConstraint(
            "event_type IN ('reviewed','rejected','approved','revoked','quarantined')",
            name="ck_v2_mat_evid_review_lifecycle_v2_type",
        ),
        sa.CheckConstraint(
            "review_state IN ('draft','reviewed','rejected','revoked','quarantined')",
            name="ck_v2_mat_evid_review_v2_state",
        ),
        sa.CheckConstraint(
            "approval_state IN ('not_approved','approved','revoked','quarantined')",
            name="ck_v2_mat_evid_approval_v2_state",
        ),
        sa.CheckConstraint(
            "actor_role IN ('material_evidence:review','material_evidence:approve')",
            name="ck_v2_mat_evid_review_v2_actor_role",
        ),
        sa.CheckConstraint(
            "actor_identity_kind = 'verified_human'",
            name="ck_v2_mat_evid_review_v2_actor_human",
        ),
        sa.CheckConstraint(
            "sequence_no > 0 AND length(previous_event_sha256) = 64 AND "
            "length(event_sha256) = 64",
            name="ck_v2_mat_evid_review_lifecycle_v2_hashes",
        ),
        sa.ForeignKeyConstraint(
            ["review_snapshot_id"],
            ["v2_material_evidence_review_snapshots_v2.review_snapshot_id"],
            name="fk_v2_mat_evid_review_lifecycle_v2_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "review_snapshot_id",
            "sequence_no",
            name="uq_v2_mat_evid_review_lifecycle_v2_sequence",
        ),
    )
    op.create_index(
        "ix_v2_mat_evid_review_lifecycle_v2_snapshot",
        "v2_material_evidence_review_lifecycle_events_v2",
        ["review_snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_review_audit_events_v2",
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
            name="ck_v2_mat_evid_review_audit_v2_id",
        ),
        sa.CheckConstraint(
            "event_type = 'review_snapshot_created'",
            name="ck_v2_mat_evid_review_audit_v2_type",
        ),
        sa.CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_mat_evid_review_audit_v2_hash",
        ),
        sa.ForeignKeyConstraint(
            ["review_snapshot_id"],
            ["v2_material_evidence_review_snapshots_v2.review_snapshot_id"],
            name="fk_v2_mat_evid_review_audit_v2_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_mat_evid_review_audit_v2_snapshot",
        "v2_material_evidence_review_audit_events_v2",
        ["review_snapshot_id"],
    )


def _create_runtime_tables() -> None:
    op.create_table(
        "v2_material_evidence_runtime_bindings_v2",
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
            name="ck_v2_mat_evid_runtime_binding_v2_state",
        ),
        sa.CheckConstraint(
            "binding_schema_version = 2 AND "
            "binding_contract_version = 'MAT-EVID-01B.v2'",
            name="ck_v2_mat_evid_runtime_binding_v2_contract",
        ),
        sa.CheckConstraint(
            "length(ruleset_content_sha256) = 64",
            name="ck_v2_mat_evid_runtime_binding_v2_ruleset_hash",
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
            "evidence_manifest_schema_version = 2 AND "
            "evidence_canonicalization_version = 2 AND "
            "evidence_contract_version = 'MAT-EVID-01A.v2' AND "
            "authority = 'TECHNICAL_UNREVIEWED')",
            name="ck_v2_mat_evid_runtime_binding_v2_evidence_identity",
        ),
        sa.CheckConstraint(
            "positive_statement_allowed IS FALSE",
            name="ck_v2_mat_evid_runtime_binding_v2_no_positive",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["v2_material_shadow_bindings.binding_id"],
            name="fk_v2_mat_evid_runtime_binding_v2_shadow",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ruleset_snapshot_id"],
            ["v2_material_ruleset_snapshots.snapshot_id"],
            name="fk_v2_mat_evid_runtime_binding_v2_ruleset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["v2_material_evidence_snapshots_v2.snapshot_id"],
            name="fk_v2_mat_evid_runtime_binding_v2_evidence",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("binding_id"),
    )
    op.create_table(
        "v2_material_evidence_runtime_pins_v2",
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
            "pin_schema_version = 2", name="ck_v2_mat_evid_runtime_pin_v2_schema"
        ),
        sa.CheckConstraint(
            "binding_state IN ('unbound','bound_unreviewed')",
            name="ck_v2_mat_evid_runtime_pin_v2_state",
        ),
        sa.CheckConstraint(
            "length(ruleset_content_sha256) = 64",
            name="ck_v2_mat_evid_runtime_pin_v2_ruleset_hash",
        ),
        sa.CheckConstraint(
            "(binding_state = 'unbound' AND evidence_snapshot_id IS NULL AND "
            "evidence_content_sha256 IS NULL AND authority = 'NONE') OR "
            "(binding_state = 'bound_unreviewed' AND "
            "evidence_snapshot_id IS NOT NULL AND "
            "length(evidence_content_sha256) = 64 AND "
            "authority = 'TECHNICAL_UNREVIEWED')",
            name="ck_v2_mat_evid_runtime_pin_v2_evidence_identity",
        ),
        sa.CheckConstraint(
            "positive_statement_allowed IS FALSE",
            name="ck_v2_mat_evid_runtime_pin_v2_no_positive",
        ),
        sa.ForeignKeyConstraint(
            ["pin_id"],
            ["v2_material_shadow_pins.pin_id"],
            name="fk_v2_mat_evid_runtime_pin_v2_shadow",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["v2_material_evidence_runtime_bindings_v2.binding_id"],
            name="fk_v2_mat_evid_runtime_pin_v2_binding",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("pin_id"),
    )
    op.create_index(
        "ix_v2_mat_evid_runtime_pin_v2_binding",
        "v2_material_evidence_runtime_pins_v2",
        ["binding_id"],
    )
    op.create_table(
        "v2_material_evidence_runtime_evaluations_v2",
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
            name="ck_v2_mat_evid_runtime_eval_v2_state",
        ),
        sa.CheckConstraint(
            "length(result_sha256) = 64",
            name="ck_v2_mat_evid_runtime_eval_v2_hash",
        ),
        sa.CheckConstraint(
            "positive_statement_allowed IS FALSE",
            name="ck_v2_mat_evid_runtime_eval_v2_no_positive",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["v2_material_shadow_evaluations.evaluation_id"],
            name="fk_v2_mat_evid_runtime_eval_v2_shadow",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pin_id"],
            ["v2_material_evidence_runtime_pins_v2.pin_id"],
            name="fk_v2_mat_evid_runtime_eval_v2_pin",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("evaluation_id"),
    )
    op.create_index(
        "ix_v2_mat_evid_runtime_eval_v2_pin",
        "v2_material_evidence_runtime_evaluations_v2",
        ["pin_id"],
    )
    op.create_table(
        "v2_material_evidence_runtime_evaluation_refs_v2",
        sa.Column("ref_id", sa.String(37), nullable=False),
        sa.Column("evaluation_id", sa.String(37), nullable=False),
        sa.Column("rule_ref", sa.String(128), nullable=False),
        sa.Column("claim_ref", sa.String(68), nullable=False),
        sa.Column("source_ref", sa.String(68), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["v2_material_evidence_runtime_evaluations_v2.evaluation_id"],
            name="fk_v2_mat_evid_runtime_eval_ref_v2_eval",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("ref_id"),
        sa.UniqueConstraint(
            "evaluation_id",
            "rule_ref",
            "claim_ref",
            "source_ref",
            name="uq_v2_mat_evid_runtime_eval_ref_v2",
        ),
    )
    op.create_index(
        "ix_v2_mat_evid_runtime_eval_ref_v2_eval",
        "v2_material_evidence_runtime_evaluation_refs_v2",
        ["evaluation_id"],
    )
    op.create_table(
        "v2_material_evidence_runtime_audit_events_v2",
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
            name="ck_v2_mat_evid_runtime_audit_v2_type",
        ),
        sa.CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_mat_evid_runtime_audit_v2_hash",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["v2_material_evidence_runtime_bindings_v2.binding_id"],
            name="fk_v2_mat_evid_runtime_audit_v2_binding",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pin_id"],
            ["v2_material_evidence_runtime_pins_v2.pin_id"],
            name="fk_v2_mat_evid_runtime_audit_v2_pin",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["v2_material_evidence_runtime_evaluations_v2.evaluation_id"],
            name="fk_v2_mat_evid_runtime_audit_v2_eval",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_mat_evid_runtime_audit_v2_binding",
        "v2_material_evidence_runtime_audit_events_v2",
        ["binding_id"],
    )


def _create_review_event_table(table: str, prefix: str, kind: str) -> None:
    op.create_table(
        table,
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("review_snapshot_id", sa.String(68), nullable=False),
        sa.Column("validator_contract_version", sa.String(32), nullable=False),
        sa.Column("validation_state", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("validation_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            f"length(event_id) = 36 AND event_id LIKE '{prefix}'",
            name=f"ck_v2_mat_evid_review_{kind}_v2_id",
        ),
        sa.CheckConstraint(
            "validation_state = 'valid' AND error_code = 'none'",
            name=f"ck_v2_mat_evid_review_{kind}_v2_state",
        ),
        sa.CheckConstraint(
            "length(validation_sha256) = 64",
            name=f"ck_v2_mat_evid_review_{kind}_v2_hash",
        ),
        sa.ForeignKeyConstraint(
            ["review_snapshot_id"],
            ["v2_material_evidence_review_snapshots_v2.review_snapshot_id"],
            name=f"fk_v2_mat_evid_review_{kind}_v2_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        f"ix_v2_mat_evid_review_{kind}_v2_snapshot",
        table,
        ["review_snapshot_id"],
    )


def _install_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION sealai_mat_evid_02_reject_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'MAT-EVID-02 immutable table % rejects %',
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
                "FOR EACH ROW EXECUTE FUNCTION sealai_mat_evid_02_reject_mutation()"
            )
        return
    if dialect == "sqlite":
        for table in _TABLES:
            for operation in ("UPDATE", "DELETE"):
                trigger = f"trg_{table}_{operation.lower()}_immutable"
                op.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
                op.execute(
                    f'CREATE TRIGGER "{trigger}" BEFORE {operation} ON "{table}" '
                    "BEGIN SELECT RAISE(ABORT, 'MAT-EVID-02 immutable table'); END"
                )
        return
    raise RuntimeError(f"MAT-EVID-02 immutability unsupported on {dialect!r}")


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present and present != expected:
        raise RuntimeError(
            "partial MAT-EVID-02 schema; refusing adoption: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    if present:
        require_schema_fingerprint(
            bind, _TABLES, _ADOPTION_FINGERPRINTS, contract="MAT-EVID-02"
        )
        return
    _create_manifest_tables()
    _create_runtime_tables()
    _create_review_tables()
    _install_immutability_triggers()
    require_schema_fingerprint(
        bind, _TABLES, _ADOPTION_FINGERPRINTS, contract="MAT-EVID-02 post-install"
    )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present != expected:
        raise RuntimeError(
            "partial MAT-EVID-02 schema; refusing destructive downgrade: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    populated = [
        table
        for table in _TABLES
        if bind.execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
    ]
    if populated:
        raise RuntimeError(
            "MAT-EVID-02 tables contain data; refusing destructive downgrade: "
            f"{populated}"
        )
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP FUNCTION IF EXISTS sealai_mat_evid_02_reject_mutation() CASCADE"
        )
    elif bind.dialect.name != "sqlite":
        raise RuntimeError(
            f"MAT-EVID-02 downgrade unsupported on {bind.dialect.name!r}"
        )
    for table in reversed(_TABLES):
        op.drop_table(table)
