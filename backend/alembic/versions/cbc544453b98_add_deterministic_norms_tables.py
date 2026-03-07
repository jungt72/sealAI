"""add deterministic norms tables

Revision ID: cbc544453b98
Revises: d5a1e0f76c22
Create Date: 2026-03-06

Creates:
  - deterministic_din_norms
  - deterministic_material_limits
"""

revision = "cbc544453b98"
down_revision = "d5a1e0f76c22"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        "deterministic_din_norms",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("norm_code", sa.String(), nullable=False),
        sa.Column("material", sa.String(), nullable=False),
        sa.Column("medium", sa.String(), nullable=True),
        sa.Column("pressure_min_bar", sa.Float(), nullable=True),
        sa.Column("pressure_max_bar", sa.Float(), nullable=True),
        sa.Column("temperature_min_c", sa.Float(), nullable=True),
        sa.Column("temperature_max_c", sa.Float(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_ref", sa.String(), nullable=False),
        sa.Column("revision", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "norm_code", "material", "version", "effective_date",
            name="uq_deterministic_din_norms_version",
        ),
    )
    op.create_index("ix_deterministic_din_norms_tenant_id", "deterministic_din_norms", ["tenant_id"])
    op.create_index("ix_deterministic_din_norms_norm_code", "deterministic_din_norms", ["norm_code"])
    op.create_index("ix_deterministic_din_norms_material", "deterministic_din_norms", ["material"])
    op.create_index("ix_deterministic_din_norms_medium", "deterministic_din_norms", ["medium"])
    op.create_index("ix_deterministic_din_norms_effective_date", "deterministic_din_norms", ["effective_date"])
    op.create_index("ix_deterministic_din_norms_valid_until", "deterministic_din_norms", ["valid_until"])
    op.create_index(
        "ix_deterministic_din_norms_material_effective",
        "deterministic_din_norms", ["material", "effective_date"],
    )

    op.create_table(
        "deterministic_material_limits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("material", sa.String(), nullable=False),
        sa.Column("medium", sa.String(), nullable=True),
        sa.Column("limit_kind", sa.String(), nullable=False),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("conditions_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_ref", sa.String(), nullable=False),
        sa.Column("revision", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "material", "limit_kind", "version", "effective_date",
            name="uq_deterministic_material_limits_version",
        ),
    )
    op.create_index("ix_deterministic_material_limits_tenant_id", "deterministic_material_limits", ["tenant_id"])
    op.create_index("ix_deterministic_material_limits_material", "deterministic_material_limits", ["material"])
    op.create_index("ix_deterministic_material_limits_medium", "deterministic_material_limits", ["medium"])
    op.create_index("ix_deterministic_material_limits_limit_kind", "deterministic_material_limits", ["limit_kind"])
    op.create_index("ix_deterministic_material_limits_effective_date", "deterministic_material_limits", ["effective_date"])
    op.create_index("ix_deterministic_material_limits_valid_until", "deterministic_material_limits", ["valid_until"])
    op.create_index(
        "ix_deterministic_material_limits_material_effective",
        "deterministic_material_limits", ["material", "effective_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_deterministic_material_limits_material_effective", table_name="deterministic_material_limits")
    op.drop_index("ix_deterministic_material_limits_valid_until", table_name="deterministic_material_limits")
    op.drop_index("ix_deterministic_material_limits_effective_date", table_name="deterministic_material_limits")
    op.drop_index("ix_deterministic_material_limits_limit_kind", table_name="deterministic_material_limits")
    op.drop_index("ix_deterministic_material_limits_medium", table_name="deterministic_material_limits")
    op.drop_index("ix_deterministic_material_limits_material", table_name="deterministic_material_limits")
    op.drop_index("ix_deterministic_material_limits_tenant_id", table_name="deterministic_material_limits")
    op.drop_table("deterministic_material_limits")

    op.drop_index("ix_deterministic_din_norms_material_effective", table_name="deterministic_din_norms")
    op.drop_index("ix_deterministic_din_norms_valid_until", table_name="deterministic_din_norms")
    op.drop_index("ix_deterministic_din_norms_effective_date", table_name="deterministic_din_norms")
    op.drop_index("ix_deterministic_din_norms_medium", table_name="deterministic_din_norms")
    op.drop_index("ix_deterministic_din_norms_material", table_name="deterministic_din_norms")
    op.drop_index("ix_deterministic_din_norms_norm_code", table_name="deterministic_din_norms")
    op.drop_index("ix_deterministic_din_norms_tenant_id", table_name="deterministic_din_norms")
    op.drop_table("deterministic_din_norms")
