"""Add the default-off adaptive interview state and shadow decision log.

Revision ID: 20260713_0009
Revises: 20260713_0008
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260713_0009"
down_revision = "20260713_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "v2_interview_state" not in tables:
        op.create_table(
            "v2_interview_state",
            sa.Column("tenant_id", sa.String(255), nullable=False),
            sa.Column("session_id", sa.String(255), nullable=False),
            sa.Column("topic_id", sa.String(128), nullable=False),
            sa.Column("pack_id", sa.String(128), nullable=False),
            sa.Column("pack_version", sa.String(64), nullable=False),
            sa.Column("policy_version", sa.String(128), nullable=False),
            sa.Column("question_catalog_version", sa.String(128), nullable=False),
            sa.Column("case_schema_version", sa.Integer(), nullable=False),
            sa.Column("state_revision", sa.Integer(), nullable=False),
            sa.Column("pending_questions_json", sa.JSON(), nullable=False),
            sa.Column("need_status_overrides_json", sa.JSON(), nullable=False),
            sa.Column("conflicts_json", sa.JSON(), nullable=False),
            sa.Column("fact_snapshots_json", sa.JSON(), nullable=False),
            sa.Column("calculator_version_refs_json", sa.JSON(), nullable=False),
            sa.Column("updated_at", sa.String(32), nullable=False),
            sa.PrimaryKeyConstraint("tenant_id", "session_id", "topic_id"),
        )
    if "v2_interview_shadow_decisions" not in tables:
        op.create_table(
            "v2_interview_shadow_decisions",
            sa.Column("id", sa.String(64), nullable=False),
            sa.Column("tenant_id", sa.String(255), nullable=False),
            sa.Column("case_reference", sa.String(64), nullable=False),
            sa.Column("state_revision", sa.Integer(), nullable=False),
            sa.Column("pack_id", sa.String(128), nullable=False),
            sa.Column("pack_version", sa.String(64), nullable=False),
            sa.Column("policy_version", sa.String(128), nullable=False),
            sa.Column("legacy_question_present", sa.Boolean(), nullable=False),
            sa.Column("legacy_question_fingerprint", sa.String(64), nullable=True),
            sa.Column("controller_directive", sa.String(64), nullable=False),
            sa.Column("controller_question_id", sa.String(128), nullable=True),
            sa.Column("rule_refs_json", sa.JSON(), nullable=False),
            sa.Column("divergence_type", sa.String(64), nullable=False),
            sa.Column("decision_duration_ms", sa.Float(), nullable=False),
            sa.Column("completeness_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.String(32), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_v2_interview_shadow_decisions_tenant_id",
            "v2_interview_shadow_decisions",
            ["tenant_id"],
        )
        op.create_index(
            "ix_v2_interview_shadow_decisions_case_reference",
            "v2_interview_shadow_decisions",
            ["case_reference"],
        )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "v2_interview_shadow_decisions" in tables:
        op.drop_table("v2_interview_shadow_decisions")
    if "v2_interview_state" in tables:
        op.drop_table("v2_interview_state")
