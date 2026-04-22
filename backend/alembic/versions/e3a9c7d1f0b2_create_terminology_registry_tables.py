"""create terminology registry tables

Revision ID: e3a9c7d1f0b2
Revises: b8c4d6e2f901
Create Date: 2026-04-20

Purpose
-------
Sprint 3 Patch 3.1 creates the database foundation for the Terminology
Mapping Registry from Supplement v2 Chapter 40. The service layer, seed
import, normalization behavior, and CRUD surfaces are intentionally left
to later Sprint 3 patches.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e3a9c7d1f0b2"
down_revision = "b8c4d6e2f901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generic_concepts",
        sa.Column("concept_id", sa.String(36), primary_key=True),
        sa.Column("canonical_name", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column(
            "standards_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("engineering_path", sa.String(64), nullable=False),
        sa.Column(
            "sealing_material_family",
            sa.String(64),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "structural_parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
            "canonical_name",
            name="uq_generic_concepts_canonical_name",
        ),
    )
    op.create_index(
        "ix_generic_concepts_engineering_path",
        "generic_concepts",
        ["engineering_path"],
    )
    op.create_index(
        "ix_generic_concepts_sealing_material_family",
        "generic_concepts",
        ["sealing_material_family"],
    )

    op.create_table(
        "product_terms",
        sa.Column("term_id", sa.String(36), primary_key=True),
        sa.Column("term_text", sa.String(255), nullable=False),
        sa.Column("normalized_term", sa.String(255), nullable=False),
        sa.Column("term_language", sa.String(8), nullable=False, server_default="de"),
        sa.Column("term_type", sa.String(32), nullable=False),
        sa.Column("originating_manufacturer_id", sa.String(36), nullable=True),
        sa.Column(
            "is_trademark",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "term_type IN ("
            "'brand_name', 'series_name', 'generic_term', "
            "'abbreviation', 'colloquial'"
            ")",
            name="ck_product_terms_term_type",
        ),
    )
    op.create_index(
        "uq_product_terms_normalized_scope",
        "product_terms",
        [
            "normalized_term",
            "term_language",
            "term_type",
            sa.text("COALESCE(originating_manufacturer_id, '')"),
        ],
        unique=True,
    )
    op.create_index(
        "ix_product_terms_normalized_term",
        "product_terms",
        ["normalized_term"],
    )
    op.create_index(
        "ix_product_terms_originating_manufacturer_id",
        "product_terms",
        ["originating_manufacturer_id"],
    )

    op.create_table(
        "term_mappings",
        sa.Column("mapping_id", sa.String(36), primary_key=True),
        sa.Column("term_id", sa.String(36), nullable=False),
        sa.Column("concept_id", sa.String(36), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("confidence", sa.SmallInteger(), nullable=False),
        sa.Column("validity_from", sa.Date(), nullable=True),
        sa.Column("validity_to", sa.Date(), nullable=True),
        sa.Column(
            "reviewer_status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewer_id", sa.String(36), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["term_id"],
            ["product_terms.term_id"],
            name="fk_term_mappings_term_id",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["generic_concepts.concept_id"],
            name="fk_term_mappings_concept_id",
        ),
        sa.CheckConstraint(
            "source_type IN ("
            "'standards', 'manufacturer_datasheet', 'manufacturer_website', "
            "'public_reference', 'community_contribution', 'expert_judgment'"
            ")",
            name="ck_term_mappings_source_type",
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 1 AND 5",
            name="ck_term_mappings_confidence",
        ),
        sa.CheckConstraint(
            "reviewer_status IN ('pending', 'reviewed', 'published', 'deprecated')",
            name="ck_term_mappings_reviewer_status",
        ),
        sa.CheckConstraint(
            "validity_to IS NULL OR validity_from IS NULL OR validity_to >= validity_from",
            name="ck_term_mappings_validity_window",
        ),
    )
    op.create_index(
        "uq_term_mappings_source_window",
        "term_mappings",
        [
            "term_id",
            "concept_id",
            "source_type",
            "source_reference",
            sa.text("COALESCE(validity_from, DATE '0001-01-01')"),
        ],
        unique=True,
    )
    op.create_index("ix_term_mappings_term_id", "term_mappings", ["term_id"])
    op.create_index("ix_term_mappings_concept_id", "term_mappings", ["concept_id"])
    op.create_index(
        "ix_term_mappings_reviewer_status",
        "term_mappings",
        ["reviewer_status"],
    )
    op.create_index("ix_term_mappings_is_active", "term_mappings", ["is_active"])

    op.create_table(
        "term_audit_log",
        sa.Column("audit_id", sa.String(36), primary_key=True),
        sa.Column("mapping_id", sa.String(36), nullable=True),
        sa.Column("concept_id", sa.String(36), nullable=True),
        sa.Column("term_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=True),
        sa.Column(
            "actor_type",
            sa.String(32),
            nullable=False,
            server_default="system",
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["mapping_id"],
            ["term_mappings.mapping_id"],
            ondelete="SET NULL",
            name="fk_term_audit_log_mapping_id",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["generic_concepts.concept_id"],
            ondelete="SET NULL",
            name="fk_term_audit_log_concept_id",
        ),
        sa.ForeignKeyConstraint(
            ["term_id"],
            ["product_terms.term_id"],
            ondelete="SET NULL",
            name="fk_term_audit_log_term_id",
        ),
        sa.CheckConstraint(
            "mapping_id IS NOT NULL OR concept_id IS NOT NULL OR term_id IS NOT NULL",
            name="ck_term_audit_log_has_target",
        ),
    )
    op.create_index("ix_term_audit_log_mapping_id", "term_audit_log", ["mapping_id"])
    op.create_index("ix_term_audit_log_concept_id", "term_audit_log", ["concept_id"])
    op.create_index("ix_term_audit_log_term_id", "term_audit_log", ["term_id"])
    op.create_index("ix_term_audit_log_created_at", "term_audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_term_audit_log_created_at", table_name="term_audit_log")
    op.drop_index("ix_term_audit_log_term_id", table_name="term_audit_log")
    op.drop_index("ix_term_audit_log_concept_id", table_name="term_audit_log")
    op.drop_index("ix_term_audit_log_mapping_id", table_name="term_audit_log")
    op.drop_table("term_audit_log")

    op.drop_index("ix_term_mappings_is_active", table_name="term_mappings")
    op.drop_index("ix_term_mappings_reviewer_status", table_name="term_mappings")
    op.drop_index("ix_term_mappings_concept_id", table_name="term_mappings")
    op.drop_index("ix_term_mappings_term_id", table_name="term_mappings")
    op.drop_index("uq_term_mappings_source_window", table_name="term_mappings")
    op.drop_table("term_mappings")

    op.drop_index(
        "ix_product_terms_originating_manufacturer_id",
        table_name="product_terms",
    )
    op.drop_index("ix_product_terms_normalized_term", table_name="product_terms")
    op.drop_index("uq_product_terms_normalized_scope", table_name="product_terms")
    op.drop_table("product_terms")

    op.drop_index(
        "ix_generic_concepts_sealing_material_family",
        table_name="generic_concepts",
    )
    op.drop_index("ix_generic_concepts_engineering_path", table_name="generic_concepts")
    op.drop_table("generic_concepts")
