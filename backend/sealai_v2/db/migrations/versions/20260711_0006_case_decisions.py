"""Add durable cases, immutable snapshots, decisions, and human reviews.

Revision ID: 20260711_0006
Revises: 20260711_0005
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260711_0006"
down_revision = "20260711_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    expected = {
        "v2_case_records",
        "v2_case_snapshots",
        "v2_decision_records",
        "v2_decision_approvals",
    }
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    present = existing & expected
    if present:
        if present != expected:
            raise RuntimeError(
                "partial case-decision schema; refusing adoption: "
                f"present={sorted(present)} missing={sorted(expected - present)}"
            )
        return
    op.create_table(
        "v2_case_records",
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("risk_class", sa.String(32), nullable=False),
        sa.Column("owner_subject", sa.String(255), nullable=False),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "case_id"),
    )
    op.create_table(
        "v2_case_snapshots",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("open_points_json", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "case_id",
            "revision",
            name="uq_v2_case_snapshot_revision",
        ),
    )
    op.create_index(
        "ix_v2_case_snapshots_tenant_id", "v2_case_snapshots", ["tenant_id"]
    )
    op.create_index("ix_v2_case_snapshots_case_id", "v2_case_snapshots", ["case_id"])
    op.create_table(
        "v2_decision_records",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("decision_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("conclusion", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("uncertainty", sa.String(64), nullable=False),
        sa.Column("responsibilities_json", sa.JSON(), nullable=False),
        sa.Column("approvals_required_json", sa.JSON(), nullable=False),
        sa.Column("supersedes_decision_id", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("tenant_id", "case_id", "snapshot_id"):
        op.create_index(
            f"ix_v2_decision_records_{column}", "v2_decision_records", [column]
        )
    op.create_table(
        "v2_decision_approvals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("decision_id", sa.String(64), nullable=False),
        sa.Column("approval_kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("actor_role", sa.String(64), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_v2_decision_approvals_tenant_id", "v2_decision_approvals", ["tenant_id"]
    )
    op.create_index(
        "ix_v2_decision_approvals_decision_id",
        "v2_decision_approvals",
        ["decision_id"],
    )


def downgrade() -> None:
    op.drop_table("v2_decision_approvals")
    op.drop_table("v2_decision_records")
    op.drop_table("v2_case_snapshots")
    op.drop_table("v2_case_records")
