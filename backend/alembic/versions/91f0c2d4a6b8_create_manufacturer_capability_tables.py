"""create manufacturer capability tables

Revision ID: 91f0c2d4a6b8
Revises: e3a9c7d1f0b2
Create Date: 2026-04-20

Purpose
-------
Sprint 3 Patch 3.2 creates the database foundation for the Manufacturer
Capability Model from Supplement v2 Chapter 41. The capability service,
CRUD/API surfaces, seed import, and matching behavior are intentionally
left to later Sprint 3/4 patches.

Small-quantity fields from Supplement v3 Chapter 47 are stored as
relational columns on claims, not only inside capability_payload, so the
future capability_service can implement the hard <=10 pieces filter
without JSONB-specific query logic.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "91f0c2d4a6b8"
down_revision = "e3a9c7d1f0b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manufacturer_profiles",
        sa.Column("manufacturer_id", sa.String(36), primary_key=True),
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("size_category", sa.String(32), nullable=False),
        sa.Column(
            "account_status",
            sa.String(32),
            nullable=False,
            server_default="pending_verification",
        ),
        sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("slug", name="uq_manufacturer_profiles_slug"),
        sa.UniqueConstraint(
            "legal_name",
            "country",
            name="uq_manufacturer_profiles_legal_name_country",
        ),
        sa.CheckConstraint(
            "country = upper(country) AND country ~ '^[A-Z]{2}$'",
            name="ck_manufacturer_profiles_country_iso2",
        ),
        sa.CheckConstraint(
            "size_category IN ('micro', 'small', 'medium', 'large', 'enterprise')",
            name="ck_manufacturer_profiles_size_category",
        ),
        sa.CheckConstraint(
            "account_status IN ("
            "'pending_verification', 'active', 'suspended', 'withdrawn'"
            ")",
            name="ck_manufacturer_profiles_account_status",
        ),
    )
    op.create_index(
        "ix_manufacturer_profiles_country",
        "manufacturer_profiles",
        ["country"],
    )
    op.create_index(
        "ix_manufacturer_profiles_account_status",
        "manufacturer_profiles",
        ["account_status"],
    )

    op.create_table(
        "manufacturer_capability_claims",
        sa.Column("claim_id", sa.String(36), primary_key=True),
        sa.Column("manufacturer_id", sa.String(36), nullable=False),
        sa.Column("capability_type", sa.String(64), nullable=False),
        sa.Column("engineering_path", sa.String(64), nullable=True),
        sa.Column("sealing_material_family", sa.String(64), nullable=True),
        sa.Column(
            "capability_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("confidence", sa.SmallInteger(), nullable=False),
        sa.Column("validity_from", sa.Date(), nullable=False),
        sa.Column("validity_to", sa.Date(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.String(36), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("minimum_order_pieces", sa.Integer(), nullable=True),
        sa.Column("typical_minimum_pieces", sa.Integer(), nullable=True),
        sa.Column("maximum_order_pieces", sa.Integer(), nullable=True),
        sa.Column("preferred_batch_min_pieces", sa.Integer(), nullable=True),
        sa.Column("preferred_batch_max_pieces", sa.Integer(), nullable=True),
        sa.Column("accepts_single_pieces", sa.Boolean(), nullable=True),
        sa.Column("rapid_manufacturing_available", sa.Boolean(), nullable=True),
        sa.Column(
            "rapid_manufacturing_surcharge_percent",
            sa.SmallInteger(),
            nullable=True,
        ),
        sa.Column(
            "rapid_manufacturing_leadtime_hours",
            sa.SmallInteger(),
            nullable=True,
        ),
        sa.Column("standard_leadtime_weeks", sa.SmallInteger(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["manufacturer_id"],
            ["manufacturer_profiles.manufacturer_id"],
            ondelete="CASCADE",
            name="fk_manufacturer_capability_claims_manufacturer_id",
        ),
        sa.CheckConstraint(
            "capability_type IN ("
            "'product_family', 'operating_envelope', 'material_expertise', "
            "'geometry_range', 'norm_capability', 'medium_experience', "
            "'lot_size_capability', 'certification'"
            ")",
            name="ck_manufacturer_capability_claims_capability_type",
        ),
        sa.CheckConstraint(
            "source_type IN ("
            "'self_declared', 'datasheet_extracted', 'third_party_verified', "
            "'customer_reference'"
            ")",
            name="ck_manufacturer_capability_claims_source_type",
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 1 AND 5",
            name="ck_manufacturer_capability_claims_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'expired', 'withdrawn')",
            name="ck_manufacturer_capability_claims_status",
        ),
        sa.CheckConstraint(
            "validity_to IS NULL OR validity_to >= validity_from",
            name="ck_manufacturer_capability_claims_validity_window",
        ),
        sa.CheckConstraint(
            "minimum_order_pieces IS NULL OR minimum_order_pieces > 0",
            name="ck_manufacturer_capability_claims_minimum_order_positive",
        ),
        sa.CheckConstraint(
            "typical_minimum_pieces IS NULL OR typical_minimum_pieces > 0",
            name="ck_manufacturer_capability_claims_typical_minimum_positive",
        ),
        sa.CheckConstraint(
            "maximum_order_pieces IS NULL OR maximum_order_pieces > 0",
            name="ck_manufacturer_capability_claims_maximum_order_positive",
        ),
        sa.CheckConstraint(
            "preferred_batch_min_pieces IS NULL OR preferred_batch_min_pieces > 0",
            name="ck_manufacturer_capability_claims_preferred_min_positive",
        ),
        sa.CheckConstraint(
            "preferred_batch_max_pieces IS NULL OR preferred_batch_max_pieces > 0",
            name="ck_manufacturer_capability_claims_preferred_max_positive",
        ),
        sa.CheckConstraint(
            "typical_minimum_pieces IS NULL OR minimum_order_pieces IS NULL "
            "OR typical_minimum_pieces >= minimum_order_pieces",
            name="ck_manufacturer_capability_claims_typical_ge_minimum",
        ),
        sa.CheckConstraint(
            "maximum_order_pieces IS NULL OR typical_minimum_pieces IS NULL "
            "OR maximum_order_pieces >= typical_minimum_pieces",
            name="ck_manufacturer_capability_claims_maximum_ge_typical",
        ),
        sa.CheckConstraint(
            "preferred_batch_min_pieces IS NULL OR preferred_batch_max_pieces IS NULL "
            "OR preferred_batch_max_pieces >= preferred_batch_min_pieces",
            name="ck_manufacturer_capability_claims_preferred_range",
        ),
        sa.CheckConstraint(
            "accepts_single_pieces IS NOT TRUE OR minimum_order_pieces <= 1",
            name="ck_manufacturer_capability_claims_single_piece_minimum",
        ),
        sa.CheckConstraint(
            "capability_type <> 'lot_size_capability' OR ("
            "minimum_order_pieces IS NOT NULL "
            "AND typical_minimum_pieces IS NOT NULL "
            "AND maximum_order_pieces IS NOT NULL "
            "AND accepts_single_pieces IS NOT NULL"
            ")",
            name="ck_manufacturer_capability_claims_lot_size_required_fields",
        ),
        sa.CheckConstraint(
            "rapid_manufacturing_surcharge_percent IS NULL OR "
            "rapid_manufacturing_surcharge_percent BETWEEN 0 AND 500",
            name="ck_manufacturer_capability_claims_rapid_surcharge_range",
        ),
        sa.CheckConstraint(
            "rapid_manufacturing_leadtime_hours IS NULL OR "
            "rapid_manufacturing_leadtime_hours > 0",
            name="ck_manufacturer_capability_claims_rapid_leadtime_positive",
        ),
        sa.CheckConstraint(
            "standard_leadtime_weeks IS NULL OR standard_leadtime_weeks > 0",
            name="ck_manufacturer_capability_claims_standard_leadtime_positive",
        ),
        sa.CheckConstraint(
            "rapid_manufacturing_available IS NOT TRUE OR ("
            "rapid_manufacturing_surcharge_percent IS NOT NULL "
            "AND rapid_manufacturing_leadtime_hours IS NOT NULL"
            ")",
            name="ck_manufacturer_capability_claims_rapid_required_fields",
        ),
    )
    op.create_index(
        "uq_manufacturer_capability_claims_source_window",
        "manufacturer_capability_claims",
        [
            "manufacturer_id",
            "capability_type",
            "source_type",
            "source_reference",
            "validity_from",
        ],
        unique=True,
    )
    op.create_index(
        "ix_manufacturer_capability_claims_manufacturer_id",
        "manufacturer_capability_claims",
        ["manufacturer_id"],
    )
    op.create_index(
        "ix_manufacturer_capability_claims_capability_type",
        "manufacturer_capability_claims",
        ["capability_type"],
    )
    op.create_index(
        "ix_manufacturer_capability_claims_status",
        "manufacturer_capability_claims",
        ["status"],
    )
    op.create_index(
        "ix_manufacturer_capability_claims_path_material",
        "manufacturer_capability_claims",
        ["engineering_path", "sealing_material_family"],
    )
    op.create_index(
        "ix_manufacturer_capability_claims_small_quantity",
        "manufacturer_capability_claims",
        ["accepts_single_pieces", "minimum_order_pieces"],
    )
    op.create_index(
        "ix_manufacturer_capability_claims_rapid_manufacturing",
        "manufacturer_capability_claims",
        ["rapid_manufacturing_available"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_manufacturer_capability_claims_rapid_manufacturing",
        table_name="manufacturer_capability_claims",
    )
    op.drop_index(
        "ix_manufacturer_capability_claims_small_quantity",
        table_name="manufacturer_capability_claims",
    )
    op.drop_index(
        "ix_manufacturer_capability_claims_path_material",
        table_name="manufacturer_capability_claims",
    )
    op.drop_index(
        "ix_manufacturer_capability_claims_status",
        table_name="manufacturer_capability_claims",
    )
    op.drop_index(
        "ix_manufacturer_capability_claims_capability_type",
        table_name="manufacturer_capability_claims",
    )
    op.drop_index(
        "ix_manufacturer_capability_claims_manufacturer_id",
        table_name="manufacturer_capability_claims",
    )
    op.drop_index(
        "uq_manufacturer_capability_claims_source_window",
        table_name="manufacturer_capability_claims",
    )
    op.drop_table("manufacturer_capability_claims")

    op.drop_index(
        "ix_manufacturer_profiles_account_status",
        table_name="manufacturer_profiles",
    )
    op.drop_index("ix_manufacturer_profiles_country", table_name="manufacturer_profiles")
    op.drop_table("manufacturer_profiles")
