"""Deterministic norms/material limits schema for hybrid knowledge stack."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)

from app.database import Base


class DeterministicDINNorm(Base):
    """Versioned DIN/ISO/EN norm limits with deterministic numeric boundaries."""

    __tablename__ = "deterministic_din_norms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, nullable=True, index=True)
    norm_code = Column(String, nullable=False, index=True)  # e.g., DIN 3770
    material = Column(String, nullable=False, index=True)  # e.g., FKM, NBR, PTFE
    medium = Column(String, nullable=True, index=True)

    pressure_min_bar = Column(Float, nullable=True)
    pressure_max_bar = Column(Float, nullable=True)
    temperature_min_c = Column(Float, nullable=True)
    temperature_max_c = Column(Float, nullable=True)

    payload_json = Column(JSON, nullable=False, default=dict)
    source_ref = Column(String, nullable=False)
    revision = Column(String, nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default=text("1"))

    effective_date = Column(Date, nullable=False, index=True)
    valid_until = Column(Date, nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "norm_code",
            "material",
            "version",
            "effective_date",
            name="uq_deterministic_din_norms_version",
        ),
        Index("ix_deterministic_din_norms_material_effective", "material", "effective_date"),
    )


class DeterministicMaterialLimit(Base):
    """Versioned deterministic material operating limits."""

    __tablename__ = "deterministic_material_limits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, nullable=True, index=True)
    material = Column(String, nullable=False, index=True)
    medium = Column(String, nullable=True, index=True)
    limit_kind = Column(String, nullable=False, index=True)  # pressure, temperature, lifecycle, etc.

    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    unit = Column(String, nullable=False, default="", server_default=text("''"))

    conditions_json = Column(JSON, nullable=False, default=dict)
    source_ref = Column(String, nullable=False)
    revision = Column(String, nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default=text("1"))

    effective_date = Column(Date, nullable=False, index=True)
    valid_until = Column(Date, nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "material",
            "limit_kind",
            "version",
            "effective_date",
            name="uq_deterministic_material_limits_version",
        ),
        Index("ix_deterministic_material_limits_material_effective", "material", "effective_date"),
    )


__all__ = ["DeterministicDINNorm", "DeterministicMaterialLimit"]
