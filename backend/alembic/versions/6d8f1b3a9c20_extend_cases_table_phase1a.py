"""extend cases table for Phase 1a persistence foundation

Revision ID: 6d8f1b3a9c20
Revises: a1b2c3d4e5f6
Create Date: 2026-04-19

Purpose
-------
Adds 16 new columns to the cases table per Founder Decision #1 and
Implementation Plan Sprint 1 Patch 1.1. These columns support:
- Optimistic locking (case_revision) per Supplement v1 §34
- Version tracking per Supplement v1 §36.3 (schema_version, ruleset_version,
  calc_library_version, risk_engine_version)
- Workflow state (phase, routing_path transitional, pre_gate_classification)
- Domain classification (request_type, engineering_path,
  sealing_material_family) per AGENTS §5.1 and Supplement v2 §39
- Forward-link to application patterns (application_pattern_id; FK target
  in Sprint 4)
- Readiness flags (rfq_ready, inquiry_admissible)
- Structured payload (payload JSONB)
- Tenant scope (tenant_id) per Founder Decision #6

Data migration
--------------
Existing cases and dependent rows are preserved. This migration is additive:
it extends the existing cases table without purging case history. Pre-migration
row counts are logged for the audit trail.

Preserved
---------
Pre-existing columns: id, case_number, user_id, subsegment, status,
created_at, updated_at, session_id — all untouched.

Pre-existing indexes: cases_pkey, ix_cases_case_number,
ix_cases_session_id, ix_cases_user_id — all preserved, never dropped.

Type deviation from plan
------------------------
Implementation Plan §Patch 1.1 specifies tenant_id as UUID. Current
schema uses VARCHAR for cases.id (36) and cases.user_id (255). For
consistency, tenant_id is VARCHAR(255) matching user_id convention;
application_pattern_id is VARCHAR(36) matching cases.id convention.

A dedicated schema-typing sprint may later consolidate these to UUID.
Not in Phase 1a scope.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "6d8f1b3a9c20"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Keep this migration non-destructive on real databases. Counts are logged
    # so operators can verify that existing case history was preserved.
    before_cases = conn.execute(sa.text("SELECT COUNT(*) FROM cases")).scalar()
    before_snapshots = conn.execute(
        sa.text("SELECT COUNT(*) FROM case_state_snapshots")
    ).scalar()
    before_audit = conn.execute(sa.text("SELECT COUNT(*) FROM inquiry_audit")).scalar()
    before_deliveries = conn.execute(
        sa.text("SELECT COUNT(*) FROM inquiry_deliveries")
    ).scalar()
    print(
        f"[phase1a_extend_cases] Pre-migration counts: "
        f"cases={before_cases}, case_state_snapshots={before_snapshots}, "
        f"inquiry_audit={before_audit}, inquiry_deliveries={before_deliveries}"
    )

    op.add_column("cases", sa.Column("tenant_id", sa.String(255), nullable=True))
    op.add_column(
        "cases",
        sa.Column("case_revision", sa.Integer(), nullable=False, server_default="0"),
    )

    op.add_column("cases", sa.Column("schema_version", sa.String(32), nullable=True))
    op.add_column("cases", sa.Column("ruleset_version", sa.String(32), nullable=True))
    op.add_column(
        "cases", sa.Column("calc_library_version", sa.String(32), nullable=True)
    )
    op.add_column(
        "cases", sa.Column("risk_engine_version", sa.String(32), nullable=True)
    )

    op.add_column("cases", sa.Column("phase", sa.String(32), nullable=True))
    op.add_column("cases", sa.Column("routing_path", sa.String(32), nullable=True))
    op.add_column(
        "cases", sa.Column("pre_gate_classification", sa.String(32), nullable=True)
    )

    op.add_column("cases", sa.Column("request_type", sa.String(32), nullable=True))
    op.add_column("cases", sa.Column("engineering_path", sa.String(32), nullable=True))
    op.add_column(
        "cases", sa.Column("sealing_material_family", sa.String(64), nullable=True)
    )

    op.add_column(
        "cases", sa.Column("application_pattern_id", sa.String(36), nullable=True)
    )

    op.add_column(
        "cases",
        sa.Column(
            "rfq_ready", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "inquiry_admissible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.add_column(
        "cases",
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_index("idx_cases_tenant_id", "cases", ["tenant_id"])
    op.create_index("idx_cases_engineering_path", "cases", ["engineering_path"])
    op.create_index("idx_cases_request_type", "cases", ["request_type"])
    op.create_index("idx_cases_updated_at", "cases", [sa.text("updated_at DESC")])
    op.create_index(
        "idx_cases_payload_sealing_family",
        "cases",
        [sa.text("(payload->>'sealing_material_family')")],
    )


def downgrade() -> None:
    op.drop_index("idx_cases_payload_sealing_family", table_name="cases")
    op.drop_index("idx_cases_updated_at", table_name="cases")
    op.drop_index("idx_cases_request_type", table_name="cases")
    op.drop_index("idx_cases_engineering_path", table_name="cases")
    op.drop_index("idx_cases_tenant_id", table_name="cases")

    op.drop_column("cases", "payload")
    op.drop_column("cases", "inquiry_admissible")
    op.drop_column("cases", "rfq_ready")
    op.drop_column("cases", "application_pattern_id")
    op.drop_column("cases", "sealing_material_family")
    op.drop_column("cases", "engineering_path")
    op.drop_column("cases", "request_type")
    op.drop_column("cases", "pre_gate_classification")
    op.drop_column("cases", "routing_path")
    op.drop_column("cases", "phase")
    op.drop_column("cases", "risk_engine_version")
    op.drop_column("cases", "calc_library_version")
    op.drop_column("cases", "ruleset_version")
    op.drop_column("cases", "schema_version")
    op.drop_column("cases", "case_revision")
    op.drop_column("cases", "tenant_id")

    # Existing case data is intentionally preserved by upgrade and downgrade.
