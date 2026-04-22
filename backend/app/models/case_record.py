from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, false, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import validates
from sqlalchemy.types import JSON

from app.database import Base


class CaseRecord(Base):
    __tablename__ = "cases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_number = Column(String(50), nullable=False, unique=True, index=True)
    session_id = Column(String(255), nullable=True, unique=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    subsegment = Column(String(100), nullable=True)
    status = Column(String(50), nullable=False, server_default="active", default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    tenant_id = Column(String(255), nullable=False)
    case_revision = Column(Integer, nullable=False, server_default="0", default=0)
    schema_version = Column(String(32), nullable=True)
    ruleset_version = Column(String(32), nullable=True)
    calc_library_version = Column(String(32), nullable=True)
    risk_engine_version = Column(String(32), nullable=True)
    phase = Column(String(32), nullable=True)
    routing_path = Column(String(32), nullable=True)
    pre_gate_classification = Column(String(32), nullable=True)
    request_type = Column(String(32), nullable=True)
    engineering_path = Column(String(32), nullable=True)
    sealing_material_family = Column(String(64), nullable=True)
    application_pattern_id = Column(String(36), nullable=True)
    rfq_ready = Column(Boolean, nullable=False, server_default=false(), default=False)
    inquiry_admissible = Column(Boolean, nullable=False, server_default=false(), default=False)
    payload = Column(
        JSON().with_variant(JSONB(astext_type=Text()), "postgresql"),
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    @validates("tenant_id")
    def _validate_tenant_id(self, _key: str, value: Any) -> str:
        if value is None:
            raise ValueError("tenant_id is required")
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("tenant_id is required")
        return normalized

    @validates("case_revision")
    def _validate_case_revision(self, _key: str, value: Any) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("case_revision must be an integer")
        if value < 0:
            raise ValueError("case_revision must be non-negative")
        return value

    @validates("payload")
    def _validate_payload(self, _key: str, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("payload must be a dict")
        return value
