"""Add inert, non-authoritative MAT-EVID AI cross-review persistence.

Revision ID: 20260718_0019
Revises: 20260718_0018

The migration is additive and initially empty.  It creates no claim, rule,
review approval, active pointer, sampling configuration, public payload or
deployment state.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from sealai_v2.db.migrations.adoption_fingerprint import require_schema_fingerprint


revision = "20260718_0019"
down_revision = "20260718_0018"
branch_labels = None
depends_on = None

_TABLES = (
    "v2_material_evidence_ai_review_batches",
    "v2_material_evidence_ai_review_snapshots",
    "v2_material_evidence_ai_challenges",
    "v2_material_evidence_ai_adjudications",
    "v2_material_evidence_ai_validation_events",
    "v2_material_evidence_ai_lifecycle_events",
    "v2_material_evidence_ai_audit_events",
)
_ADOPTION_FINGERPRINTS: dict[str, frozenset[str]] = {
    "postgresql": frozenset(
        {"6ba5005602612356bd79765e87fa530e882e9f492e52cde987b7b6b61b467489"}
    ),
    "sqlite": frozenset(
        {"ddcaaa402f6971cafd12344b77f31a6b535e0be9826f4e8d02a1042e6726281a"}
    ),
}
_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def _create_batch_and_snapshot_tables() -> None:
    op.create_table(
        "v2_material_evidence_ai_review_batches",
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("domain_pack_id", sa.String(128), nullable=False),
        sa.Column("ruleset_snapshot_id", sa.String(68), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(68), nullable=False),
        sa.Column("creator_identity_kind", sa.String(32), nullable=False),
        sa.Column("creator_provider", sa.String(32), nullable=False),
        sa.Column("creator_model", sa.String(128), nullable=False),
        sa.Column("creator_version", sa.String(128), nullable=False),
        sa.Column("creator_run_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(batch_id) = 36 AND batch_id LIKE 'mai_%'",
            name="ck_v2_mat_evid_ai_batch_id",
        ),
        sa.CheckConstraint(
            "environment IN ('development','test','dark_staging')",
            name="ck_v2_mat_evid_ai_batch_nonprod",
        ),
        sa.CheckConstraint(
            "creator_identity_kind = 'ai_agent' AND creator_provider = 'openai'",
            name="ck_v2_mat_evid_ai_batch_creator",
        ),
        sa.ForeignKeyConstraint(
            ["ruleset_snapshot_id"],
            ["v2_material_ruleset_snapshots.snapshot_id"],
            name="fk_v2_mat_evid_ai_batch_ruleset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["v2_material_evidence_snapshots_v2.snapshot_id"],
            name="fk_v2_mat_evid_ai_batch_evidence",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("batch_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "environment",
            "ruleset_snapshot_id",
            "evidence_snapshot_id",
            "creator_run_id",
            name="uq_v2_mat_evid_ai_batch_run",
        ),
    )
    op.create_index(
        "ix_v2_material_evidence_ai_review_batches_tenant_id",
        "v2_material_evidence_ai_review_batches",
        ["tenant_id"],
    )
    op.create_index(
        "ix_v2_mat_evid_ai_batch_ruleset",
        "v2_material_evidence_ai_review_batches",
        ["ruleset_snapshot_id"],
    )
    op.create_index(
        "ix_v2_mat_evid_ai_batch_evidence",
        "v2_material_evidence_ai_review_batches",
        ["evidence_snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_ai_review_snapshots",
        sa.Column("review_snapshot_id", sa.String(68), nullable=False),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("ruleset_snapshot_id", sa.String(68), nullable=False),
        sa.Column("ruleset_content_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(68), nullable=False),
        sa.Column("evidence_content_sha256", sa.String(64), nullable=False),
        sa.Column("ai_review_schema_version", sa.Integer(), nullable=False),
        sa.Column("canonicalization_version", sa.Integer(), nullable=False),
        sa.Column("ai_review_contract_version", sa.String(40), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_payload_json", _JSON, nullable=False),
        sa.Column("canonical_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("authority", sa.String(48), nullable=False),
        sa.Column("positive_statement_allowed", sa.Boolean(), nullable=False),
        sa.Column("creator_input_sha256", sa.String(64), nullable=False),
        sa.Column("creator_output_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(review_snapshot_id) = 68 AND review_snapshot_id LIKE 'mas_%'",
            name="ck_v2_mat_evid_ai_snapshot_id",
        ),
        sa.CheckConstraint(
            "ai_review_schema_version = 1 AND canonicalization_version = 1 AND "
            "ai_review_contract_version = 'MAT-EVID-AI-REVIEW.v1'",
            name="ck_v2_mat_evid_ai_snapshot_contract",
        ),
        sa.CheckConstraint(
            "length(content_sha256) = 64 AND "
            "length(ruleset_content_sha256) = 64 AND "
            "length(evidence_content_sha256) = 64 AND "
            "length(creator_input_sha256) = 64 AND "
            "length(creator_output_sha256) = 64",
            name="ck_v2_mat_evid_ai_snapshot_hashes",
        ),
        sa.CheckConstraint(
            "authority = 'AI_CROSS_REVIEW_NON_AUTHORITATIVE' AND "
            "positive_statement_allowed IS FALSE",
            name="ck_v2_mat_evid_ai_snapshot_no_authority",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["v2_material_evidence_ai_review_batches.batch_id"],
            name="fk_v2_mat_evid_ai_snapshot_batch",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("review_snapshot_id"),
        sa.UniqueConstraint(
            "batch_id",
            "content_sha256",
            name="uq_v2_mat_evid_ai_snapshot_content",
        ),
    )
    op.create_index(
        "ix_v2_material_evidence_ai_review_snapshots_batch_id",
        "v2_material_evidence_ai_review_snapshots",
        ["batch_id"],
    )


def _create_run_tables() -> None:
    op.create_table(
        "v2_material_evidence_ai_challenges",
        sa.Column("challenge_id", sa.String(68), nullable=False),
        sa.Column("review_snapshot_id", sa.String(68), nullable=False),
        sa.Column("challenger_identity_kind", sa.String(32), nullable=False),
        sa.Column("challenger_provider", sa.String(32), nullable=False),
        sa.Column("challenger_model", sa.String(64), nullable=False),
        sa.Column("challenger_version", sa.String(128), nullable=False),
        sa.Column("challenger_run_id", sa.String(255), nullable=False),
        sa.Column("challenger_prompt_version", sa.String(128), nullable=False),
        sa.Column("challenger_prompt_sha256", sa.String(64), nullable=False),
        sa.Column("audit_input_sha256", sa.String(64), nullable=False),
        sa.Column("audit_input_file_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_audit_input_json", _JSON, nullable=False),
        sa.Column("audit_output_sha256", sa.String(64), nullable=False),
        sa.Column("cli_result_file_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_cli_receipt_json", _JSON, nullable=False),
        sa.Column("claude_executable_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_executable_attestation_json", _JSON, nullable=False),
        sa.Column(
            "claude_executable_attestation_sha256", sa.String(64), nullable=False
        ),
        sa.Column("report_sha256", sa.String(64), nullable=False),
        sa.Column("process_returncode", sa.Integer(), nullable=False),
        sa.Column("session_id_sha256", sa.String(64), nullable=False),
        sa.Column("runner_receipt_sha256", sa.String(64), nullable=False),
        sa.Column("tools_enabled", sa.Boolean(), nullable=False),
        sa.Column("mcp_enabled", sa.Boolean(), nullable=False),
        sa.Column("hooks_enabled", sa.Boolean(), nullable=False),
        sa.Column("session_persistence_enabled", sa.Boolean(), nullable=False),
        sa.Column("web_search_requests", sa.Integer(), nullable=False),
        sa.Column("web_fetch_requests", sa.Integer(), nullable=False),
        sa.Column("canonical_report_json", _JSON, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(challenge_id) = 68 AND challenge_id LIKE 'mac_%'",
            name="ck_v2_mat_evid_ai_challenge_id",
        ),
        sa.CheckConstraint(
            "challenger_identity_kind = 'ai_agent' AND "
            "challenger_provider = 'anthropic' AND "
            "challenger_model = 'claude-sonnet-5'",
            name="ck_v2_mat_evid_ai_challenger",
        ),
        sa.CheckConstraint(
            "tools_enabled IS FALSE AND mcp_enabled IS FALSE AND "
            "hooks_enabled IS FALSE AND session_persistence_enabled IS FALSE AND "
            "web_search_requests = 0 AND web_fetch_requests = 0",
            name="ck_v2_mat_evid_ai_challenge_isolation",
        ),
        sa.CheckConstraint(
            "length(challenger_prompt_sha256) = 64 AND "
            "length(audit_input_sha256) = 64 AND "
            "length(audit_input_file_sha256) = 64 AND "
            "length(audit_output_sha256) = 64 AND "
            "length(cli_result_file_sha256) = 64 AND "
            "length(claude_executable_sha256) = 64 AND "
            "length(claude_executable_attestation_sha256) = 64 AND "
            "length(report_sha256) = 64 AND "
            "length(session_id_sha256) = 64 AND "
            "length(runner_receipt_sha256) = 64 AND process_returncode = 0",
            name="ck_v2_mat_evid_ai_challenge_hashes",
        ),
        sa.ForeignKeyConstraint(
            ["review_snapshot_id"],
            ["v2_material_evidence_ai_review_snapshots.review_snapshot_id"],
            name="fk_v2_mat_evid_ai_challenge_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("challenge_id"),
        sa.UniqueConstraint(
            "review_snapshot_id",
            "challenger_run_id",
            name="uq_v2_mat_evid_ai_challenge_run",
        ),
    )
    op.create_index(
        "ix_v2_material_evidence_ai_challenges_review_snapshot_id",
        "v2_material_evidence_ai_challenges",
        ["review_snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_ai_adjudications",
        sa.Column("adjudication_id", sa.String(68), nullable=False),
        sa.Column("review_snapshot_id", sa.String(68), nullable=False),
        sa.Column("challenge_id", sa.String(68), nullable=False),
        sa.Column("adjudicator_identity_kind", sa.String(32), nullable=False),
        sa.Column("adjudicator_provider", sa.String(32), nullable=False),
        sa.Column("adjudicator_model", sa.String(128), nullable=False),
        sa.Column("adjudicator_version", sa.String(128), nullable=False),
        sa.Column("adjudicator_run_id", sa.String(255), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("output_sha256", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(48), nullable=False),
        sa.Column("replacement_ruleset_snapshot_id", sa.String(68), nullable=True),
        sa.Column("replacement_evidence_snapshot_id", sa.String(68), nullable=True),
        sa.Column("canonical_adjudication_json", _JSON, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(adjudication_id) = 68 AND adjudication_id LIKE 'maa_%'",
            name="ck_v2_mat_evid_ai_adjudication_id",
        ),
        sa.CheckConstraint(
            "adjudicator_identity_kind = 'ai_agent' AND "
            "adjudicator_provider = 'openai'",
            name="ck_v2_mat_evid_ai_adjudicator",
        ),
        sa.CheckConstraint(
            "outcome IN ('ai_cross_reviewed_non_authoritative',"
            "'changes_required','quarantined')",
            name="ck_v2_mat_evid_ai_adjudication_outcome",
        ),
        sa.CheckConstraint(
            "((replacement_ruleset_snapshot_id IS NULL AND "
            "replacement_evidence_snapshot_id IS NULL) OR "
            "(replacement_ruleset_snapshot_id IS NOT NULL AND "
            "replacement_evidence_snapshot_id IS NOT NULL)) AND "
            "(outcome = 'changes_required' OR "
            "(replacement_ruleset_snapshot_id IS NULL AND "
            "replacement_evidence_snapshot_id IS NULL))",
            name="ck_v2_mat_evid_ai_adjudication_replacements",
        ),
        sa.CheckConstraint(
            "length(input_sha256) = 64 AND length(output_sha256) = 64",
            name="ck_v2_mat_evid_ai_adjudication_hashes",
        ),
        sa.ForeignKeyConstraint(
            ["review_snapshot_id"],
            ["v2_material_evidence_ai_review_snapshots.review_snapshot_id"],
            name="fk_v2_mat_evid_ai_adjudication_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["challenge_id"],
            ["v2_material_evidence_ai_challenges.challenge_id"],
            name="fk_v2_mat_evid_ai_adjudication_challenge",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replacement_ruleset_snapshot_id"],
            ["v2_material_ruleset_snapshots.snapshot_id"],
            name="fk_v2_mat_evid_ai_adjudication_ruleset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replacement_evidence_snapshot_id"],
            ["v2_material_evidence_snapshots_v2.snapshot_id"],
            name="fk_v2_mat_evid_ai_adjudication_evidence",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("adjudication_id"),
        sa.UniqueConstraint(
            "review_snapshot_id",
            "challenge_id",
            "adjudicator_run_id",
            name="uq_v2_mat_evid_ai_adjudication_run",
        ),
    )
    op.create_index(
        "ix_v2_material_evidence_ai_adjudications_review_snapshot_id",
        "v2_material_evidence_ai_adjudications",
        ["review_snapshot_id"],
    )
    op.create_index(
        "ix_v2_material_evidence_ai_adjudications_challenge_id",
        "v2_material_evidence_ai_adjudications",
        ["challenge_id"],
    )


def _create_event_tables() -> None:
    op.create_table(
        "v2_material_evidence_ai_validation_events",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("review_snapshot_id", sa.String(68), nullable=False),
        sa.Column("validator_contract_version", sa.String(40), nullable=False),
        sa.Column("validation_state", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("validation_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mav_%'",
            name="ck_v2_mat_evid_ai_validation_id",
        ),
        sa.CheckConstraint(
            "validation_state = 'valid' AND error_code = 'none'",
            name="ck_v2_mat_evid_ai_validation_state",
        ),
        sa.CheckConstraint(
            "length(validation_sha256) = 64",
            name="ck_v2_mat_evid_ai_validation_hash",
        ),
        sa.ForeignKeyConstraint(
            ["review_snapshot_id"],
            ["v2_material_evidence_ai_review_snapshots.review_snapshot_id"],
            name="fk_v2_mat_evid_ai_validation_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_material_evidence_ai_validation_events_review_snapshot_id",
        "v2_material_evidence_ai_validation_events",
        ["review_snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_ai_lifecycle_events",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("review_snapshot_id", sa.String(68), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("state", sa.String(48), nullable=False),
        sa.Column("actor_identity_kind", sa.String(32), nullable=False),
        sa.Column("actor_provider", sa.String(32), nullable=False),
        sa.Column("actor_run_id", sa.String(255), nullable=False),
        sa.Column("artifact_ref", sa.String(68), nullable=False),
        sa.Column("previous_event_sha256", sa.String(64), nullable=False),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mal_%'",
            name="ck_v2_mat_evid_ai_lifecycle_id",
        ),
        sa.CheckConstraint(
            "event_type IN ('challenged','cross_reviewed_non_authoritative',"
            "'changes_required','quarantined','revoked')",
            name="ck_v2_mat_evid_ai_lifecycle_type",
        ),
        sa.CheckConstraint(
            "state IN ('ai_draft','ai_challenged',"
            "'ai_cross_reviewed_non_authoritative','changes_required',"
            "'quarantined','revoked')",
            name="ck_v2_mat_evid_ai_lifecycle_state",
        ),
        sa.CheckConstraint(
            "actor_identity_kind = 'ai_agent' AND "
            "actor_provider IN ('openai','anthropic')",
            name="ck_v2_mat_evid_ai_lifecycle_actor",
        ),
        sa.CheckConstraint(
            "sequence_no > 0 AND length(previous_event_sha256) = 64 AND "
            "length(event_sha256) = 64",
            name="ck_v2_mat_evid_ai_lifecycle_hashes",
        ),
        sa.ForeignKeyConstraint(
            ["review_snapshot_id"],
            ["v2_material_evidence_ai_review_snapshots.review_snapshot_id"],
            name="fk_v2_mat_evid_ai_lifecycle_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "review_snapshot_id",
            "sequence_no",
            name="uq_v2_mat_evid_ai_lifecycle_sequence",
        ),
    )
    op.create_index(
        "ix_v2_material_evidence_ai_lifecycle_events_review_snapshot_id",
        "v2_material_evidence_ai_lifecycle_events",
        ["review_snapshot_id"],
    )
    op.create_table(
        "v2_material_evidence_ai_audit_events",
        sa.Column("event_id", sa.String(38), nullable=False),
        sa.Column("review_snapshot_id", sa.String(68), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("actor_identity_kind", sa.String(32), nullable=False),
        sa.Column("actor_provider", sa.String(32), nullable=False),
        sa.Column("actor_run_id", sa.String(255), nullable=False),
        sa.Column("event_payload_json", _JSON, nullable=False),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "length(event_id) = 38 AND event_id LIKE 'maaev_%'",
            name="ck_v2_mat_evid_ai_audit_id",
        ),
        sa.CheckConstraint(
            "event_type IN ('review_snapshot_created','challenge_recorded',"
            "'adjudication_recorded','quarantine_recorded','revocation_recorded')",
            name="ck_v2_mat_evid_ai_audit_type",
        ),
        sa.CheckConstraint(
            "actor_identity_kind = 'ai_agent' AND "
            "actor_provider IN ('openai','anthropic')",
            name="ck_v2_mat_evid_ai_audit_actor",
        ),
        sa.CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_mat_evid_ai_audit_hash",
        ),
        sa.ForeignKeyConstraint(
            ["review_snapshot_id"],
            ["v2_material_evidence_ai_review_snapshots.review_snapshot_id"],
            name="fk_v2_mat_evid_ai_audit_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_v2_material_evidence_ai_audit_events_review_snapshot_id",
        "v2_material_evidence_ai_audit_events",
        ["review_snapshot_id"],
    )


def _install_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION sealai_mat_evid_ai_review_reject_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'MAT-EVID AI immutable table % rejects %',
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
                "FOR EACH ROW EXECUTE FUNCTION "
                "sealai_mat_evid_ai_review_reject_mutation()"
            )
        return
    if dialect == "sqlite":
        for table in _TABLES:
            for operation in ("UPDATE", "DELETE"):
                trigger = f"trg_{table}_{operation.lower()}_immutable"
                op.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
                op.execute(
                    f'CREATE TRIGGER "{trigger}" BEFORE {operation} ON "{table}" '
                    "BEGIN SELECT RAISE(ABORT, 'MAT-EVID AI immutable table'); END"
                )
        return
    raise RuntimeError(f"MAT-EVID AI immutability unsupported on {dialect!r}")


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present and present != expected:
        raise RuntimeError(
            "partial MAT-EVID AI schema; refusing adoption: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    if present:
        require_schema_fingerprint(
            bind,
            _TABLES,
            _ADOPTION_FINGERPRINTS,
            contract="MAT-EVID-AI-REVIEW.v1",
        )
        return
    _create_batch_and_snapshot_tables()
    _create_run_tables()
    _create_event_tables()
    _install_immutability_triggers()
    require_schema_fingerprint(
        bind,
        _TABLES,
        _ADOPTION_FINGERPRINTS,
        contract="MAT-EVID-AI-REVIEW.v1 post-install",
    )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    expected = set(_TABLES)
    present = existing & expected
    if present != expected:
        raise RuntimeError(
            "partial MAT-EVID AI schema; refusing destructive downgrade: "
            f"present={sorted(present)} missing={sorted(expected - present)}"
        )
    populated = [
        table
        for table in _TABLES
        if bind.execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
    ]
    if populated:
        raise RuntimeError(
            "MAT-EVID AI tables contain data; refusing destructive downgrade: "
            f"{populated}"
        )
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP FUNCTION IF EXISTS "
            "sealai_mat_evid_ai_review_reject_mutation() CASCADE"
        )
    elif bind.dialect.name != "sqlite":
        raise RuntimeError(
            f"MAT-EVID AI downgrade unsupported on {bind.dialect.name!r}"
        )
    for table in reversed(_TABLES):
        op.drop_table(table)
