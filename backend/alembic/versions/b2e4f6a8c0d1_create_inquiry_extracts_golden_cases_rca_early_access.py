"""create inquiry extracts, golden cases, and RCA early access tables

Revision ID: b2e4f6a8c0d1
Revises: 91f0c2d4a6b8
Create Date: 2026-04-20

Purpose
-------
Sprint 3 Patch 3.3 creates the database foundation for three later service
surfaces without implementing those services:
- inquiry_extracts: structured manufacturer-facing extract artifacts
- golden_cases: anonymized curated regression/training references
- rca_early_access: MVP RCA-degrade interest/failure-case capture

No inquiry_extract_service, anonymization_service, RCA pipeline, workflow,
API, seed import, or matching behavior is introduced here.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b2e4f6a8c0d1"
down_revision = "91f0c2d4a6b8"
branch_labels = None
depends_on = None


REQUEST_TYPES = (
    "'new_design', 'retrofit', 'rca_failure_analysis', 'validation_check', "
    "'spare_part_identification', 'quick_engineering_check'"
)

ENGINEERING_PATHS = (
    "'ms_pump', 'rwdr', 'static', 'labyrinth', 'hyd_pneu', 'unclear_rotary'"
)

SEALING_MATERIAL_FAMILIES = (
    "'ptfe_virgin', 'ptfe_glass_filled', 'ptfe_carbon_filled', "
    "'ptfe_bronze_filled', 'ptfe_mos2_filled', 'ptfe_graphite_filled', "
    "'ptfe_peek_filled', 'ptfe_mixed_filled', 'elastomer_nbr', "
    "'elastomer_fkm', 'elastomer_epdm', 'elastomer_hnbr', "
    "'elastomer_ffkm', 'elastomer_silicone', 'unknown'"
)

OUTPUT_CLASSES = (
    "'conversational_answer', 'structured_clarification', "
    "'governed_state_update', 'technical_preselection', 'rca_hypothesis', "
    "'candidate_shortlist', 'inquiry_ready'"
)


def upgrade() -> None:
    op.create_table(
        "inquiry_extracts",
        sa.Column("extract_id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("case_revision", sa.Integer(), nullable=False),
        sa.Column(
            "artifact_type",
            sa.String(64),
            nullable=False,
            server_default="manufacturer_inquiry",
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "source_kind",
            sa.String(32),
            nullable=False,
            server_default="case_revision",
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            ondelete="CASCADE",
            name="fk_inquiry_extracts_case_id",
        ),
        sa.UniqueConstraint(
            "case_id",
            "case_revision",
            "artifact_type",
            name="uq_inquiry_extracts_case_revision_type",
        ),
        sa.CheckConstraint(
            "case_revision >= 0",
            name="ck_inquiry_extracts_case_revision_nonnegative",
        ),
        sa.CheckConstraint(
            "artifact_type IN ('manufacturer_inquiry', 'technical_summary')",
            name="ck_inquiry_extracts_artifact_type",
        ),
        sa.CheckConstraint(
            "source_kind IN ('case_revision', 'manual', 'migration')",
            name="ck_inquiry_extracts_source_kind",
        ),
    )
    op.create_index("ix_inquiry_extracts_case_id", "inquiry_extracts", ["case_id"])
    op.create_index(
        "ix_inquiry_extracts_tenant_id",
        "inquiry_extracts",
        ["tenant_id"],
    )
    op.create_index(
        "ix_inquiry_extracts_artifact_type",
        "inquiry_extracts",
        ["artifact_type"],
    )
    op.create_index(
        "ix_inquiry_extracts_created_at",
        "inquiry_extracts",
        [sa.text("created_at DESC")],
    )

    op.create_table(
        "golden_cases",
        sa.Column("golden_case_id", sa.String(36), primary_key=True),
        sa.Column("stable_key", sa.String(128), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("request_type", sa.String(32), nullable=False),
        sa.Column("engineering_path", sa.String(32), nullable=False),
        sa.Column(
            "sealing_material_family",
            sa.String(64),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("expected_output_class", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "stable_key",
            "version",
            name="uq_golden_cases_stable_key_version",
        ),
        sa.CheckConstraint(
            f"request_type IN ({REQUEST_TYPES})",
            name="ck_golden_cases_request_type",
        ),
        sa.CheckConstraint(
            f"engineering_path IN ({ENGINEERING_PATHS})",
            name="ck_golden_cases_engineering_path",
        ),
        sa.CheckConstraint(
            f"sealing_material_family IN ({SEALING_MATERIAL_FAMILIES})",
            name="ck_golden_cases_sealing_material_family",
        ),
        sa.CheckConstraint(
            f"expected_output_class IS NULL OR expected_output_class IN ({OUTPUT_CLASSES})",
            name="ck_golden_cases_expected_output_class",
        ),
        sa.CheckConstraint("version > 0", name="ck_golden_cases_version_positive"),
    )
    op.create_index("ix_golden_cases_stable_key", "golden_cases", ["stable_key"])
    op.create_index(
        "ix_golden_cases_request_path_material",
        "golden_cases",
        ["request_type", "engineering_path", "sealing_material_family"],
    )
    op.create_index("ix_golden_cases_active", "golden_cases", ["active"])

    op.create_table(
        "rca_early_access",
        sa.Column("entry_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=True),
        sa.Column("contact_identifier", sa.Text(), nullable=True),
        sa.Column(
            "contact_consent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("submission_text", sa.Text(), nullable=False),
        sa.Column(
            "structured_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="new",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(submission_text)) > 0",
            name="ck_rca_early_access_submission_text_not_blank",
        ),
        sa.CheckConstraint(
            "contact_identifier IS NULL OR contact_consent IS TRUE",
            name="ck_rca_early_access_contact_requires_consent",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'contacted', 'closed', 'withdrawn')",
            name="ck_rca_early_access_status",
        ),
    )
    op.create_index(
        "ix_rca_early_access_tenant_id",
        "rca_early_access",
        ["tenant_id"],
    )
    op.create_index("ix_rca_early_access_status", "rca_early_access", ["status"])
    op.create_index(
        "ix_rca_early_access_created_at",
        "rca_early_access",
        [sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_rca_early_access_created_at", table_name="rca_early_access")
    op.drop_index("ix_rca_early_access_status", table_name="rca_early_access")
    op.drop_index("ix_rca_early_access_tenant_id", table_name="rca_early_access")
    op.drop_table("rca_early_access")

    op.drop_index("ix_golden_cases_active", table_name="golden_cases")
    op.drop_index(
        "ix_golden_cases_request_path_material",
        table_name="golden_cases",
    )
    op.drop_index("ix_golden_cases_stable_key", table_name="golden_cases")
    op.drop_table("golden_cases")

    op.drop_index("ix_inquiry_extracts_created_at", table_name="inquiry_extracts")
    op.drop_index("ix_inquiry_extracts_artifact_type", table_name="inquiry_extracts")
    op.drop_index("ix_inquiry_extracts_tenant_id", table_name="inquiry_extracts")
    op.drop_index("ix_inquiry_extracts_case_id", table_name="inquiry_extracts")
    op.drop_table("inquiry_extracts")
