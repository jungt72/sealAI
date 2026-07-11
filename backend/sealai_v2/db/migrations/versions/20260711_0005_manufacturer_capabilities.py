"""Separate technical manufacturer capabilities from commercial partners.

Revision ID: 20260711_0005
Revises: 20260711_0004
"""

from __future__ import annotations

from alembic import op
from datetime import datetime, timezone
import sqlalchemy as sa

revision = "20260711_0005"
down_revision = "20260711_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    expected = {
        "v2_manufacturer_capability_profiles",
        "v2_manufacturer_capability_reviews",
    }
    present = existing & expected
    if present:
        if present != expected:
            raise RuntimeError(
                "partial manufacturer-capability schema; refusing adoption: "
                f"present={sorted(present)} missing={sorted(expected - present)}"
            )
        return
    if "v2_manufacturer_capability_profiles" not in existing:
        op.create_table(
            "v2_manufacturer_capability_profiles",
            sa.Column("manufacturer_id", sa.String(255), nullable=False),
            sa.Column("company_name", sa.String(255), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("regions_json", sa.JSON(), nullable=False),
            sa.Column("contacts_json", sa.JSON(), nullable=False),
            sa.Column("seal_types_json", sa.JSON(), nullable=False),
            sa.Column("materials_json", sa.JSON(), nullable=False),
            sa.Column("compounds_json", sa.JSON(), nullable=False),
            sa.Column("size_ranges_json", sa.JSON(), nullable=False),
            sa.Column("manufacturing_processes_json", sa.JSON(), nullable=False),
            sa.Column("tolerances_json", sa.JSON(), nullable=False),
            sa.Column("special_capabilities_json", sa.JSON(), nullable=False),
            sa.Column("industries_json", sa.JSON(), nullable=False),
            sa.Column("certificates_json", sa.JSON(), nullable=False),
            sa.Column("test_capabilities_json", sa.JSON(), nullable=False),
            sa.Column("approvals_json", sa.JSON(), nullable=False),
            sa.Column("documents_json", sa.JSON(), nullable=False),
            sa.Column("services_json", sa.JSON(), nullable=False),
            sa.Column("application_limits_json", sa.JSON(), nullable=False),
            sa.Column("exclusions_json", sa.JSON(), nullable=False),
            sa.Column("evidence_json", sa.JSON(), nullable=False),
            sa.Column("submitted_at", sa.String(32), nullable=True),
            sa.Column("updated_at", sa.String(32), nullable=False),
            sa.Column("verified_at", sa.String(32), nullable=True),
            sa.Column("verified_by", sa.String(255), nullable=True),
            sa.Column("review_expires_at", sa.String(32), nullable=True),
            sa.Column("change_reason", sa.Text(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("manufacturer_id"),
        )
    if "v2_manufacturer_capability_reviews" not in existing:
        op.create_table(
            "v2_manufacturer_capability_reviews",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("manufacturer_id", sa.String(255), nullable=False),
            sa.Column("from_status", sa.String(32), nullable=False),
            sa.Column("to_status", sa.String(32), nullable=False),
            sa.Column("actor", sa.String(255), nullable=False),
            sa.Column("actor_relation", sa.String(64), nullable=False),
            sa.Column("conflict_of_interest", sa.String(32), nullable=False),
            sa.Column("note", sa.Text(), nullable=False),
            sa.Column("evidence_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.String(32), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_v2_manufacturer_capability_reviews_manufacturer_id",
            "v2_manufacturer_capability_reviews",
            ["manufacturer_id"],
        )
    _backfill_legacy_partner_capabilities(op.get_bind())


def _backfill_legacy_partner_capabilities(bind) -> None:
    if "v2_hersteller_partner" not in set(sa.inspect(bind).get_table_names()):
        return
    partner = sa.table(
        "v2_hersteller_partner",
        sa.column("hersteller", sa.String()),
        sa.column("firmenname", sa.String()),
        sa.column("werkstoffe", sa.JSON()),
        sa.column("bauformen", sa.JSON()),
        sa.column("groessen", sa.String()),
        sa.column("zertifikate", sa.JSON()),
    )
    profiles = sa.table(
        "v2_manufacturer_capability_profiles",
        sa.column("manufacturer_id", sa.String()),
        sa.column("company_name", sa.String()),
        sa.column("status", sa.String()),
        sa.column("regions_json", sa.JSON()),
        sa.column("contacts_json", sa.JSON()),
        sa.column("seal_types_json", sa.JSON()),
        sa.column("materials_json", sa.JSON()),
        sa.column("compounds_json", sa.JSON()),
        sa.column("size_ranges_json", sa.JSON()),
        sa.column("manufacturing_processes_json", sa.JSON()),
        sa.column("tolerances_json", sa.JSON()),
        sa.column("special_capabilities_json", sa.JSON()),
        sa.column("industries_json", sa.JSON()),
        sa.column("certificates_json", sa.JSON()),
        sa.column("test_capabilities_json", sa.JSON()),
        sa.column("approvals_json", sa.JSON()),
        sa.column("documents_json", sa.JSON()),
        sa.column("services_json", sa.JSON()),
        sa.column("application_limits_json", sa.JSON()),
        sa.column("exclusions_json", sa.JSON()),
        sa.column("evidence_json", sa.JSON()),
        sa.column("submitted_at", sa.String()),
        sa.column("updated_at", sa.String()),
        sa.column("verified_at", sa.String()),
        sa.column("verified_by", sa.String()),
        sa.column("review_expires_at", sa.String()),
        sa.column("change_reason", sa.Text()),
        sa.column("version", sa.Integer()),
    )
    reviews = sa.table(
        "v2_manufacturer_capability_reviews",
        sa.column("manufacturer_id", sa.String()),
        sa.column("from_status", sa.String()),
        sa.column("to_status", sa.String()),
        sa.column("actor", sa.String()),
        sa.column("actor_relation", sa.String()),
        sa.column("conflict_of_interest", sa.String()),
        sa.column("note", sa.Text()),
        sa.column("evidence_json", sa.JSON()),
        sa.column("created_at", sa.String()),
    )
    migrated_at = datetime.now(timezone.utc).isoformat()
    reason = (
        "Migrated from legacy commercial partner capability fields; "
        "independent review required"
    )
    for row in bind.execute(sa.select(partner)).mappings():
        bind.execute(
            profiles.insert().values(
                manufacturer_id=row["hersteller"],
                company_name=row["firmenname"] or row["hersteller"],
                status="submitted",
                regions_json=[],
                contacts_json=[],
                seal_types_json=row["bauformen"] or [],
                materials_json=row["werkstoffe"] or [],
                compounds_json=[],
                size_ranges_json=[row["groessen"]] if row["groessen"] else [],
                manufacturing_processes_json=[],
                tolerances_json=[],
                special_capabilities_json=[],
                industries_json=[],
                certificates_json=row["zertifikate"] or [],
                test_capabilities_json=[],
                approvals_json=[],
                documents_json=[],
                services_json=[],
                application_limits_json=[],
                exclusions_json=[],
                evidence_json=[],
                submitted_at=migrated_at,
                updated_at=migrated_at,
                verified_at=None,
                verified_by=None,
                review_expires_at=None,
                change_reason=reason,
                version=1,
            )
        )
        bind.execute(
            reviews.insert().values(
                manufacturer_id=row["hersteller"],
                from_status="legacy_partner_metadata",
                to_status="submitted",
                actor="migration:20260711_0005",
                actor_relation="migration",
                conflict_of_interest="not_assessed",
                note=reason,
                evidence_json=[],
                created_at=migrated_at,
            )
        )


def downgrade() -> None:
    op.drop_table("v2_manufacturer_capability_reviews")
    op.drop_table("v2_manufacturer_capability_profiles")
