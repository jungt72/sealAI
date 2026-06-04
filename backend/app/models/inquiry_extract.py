"""ORM model for governed RFQ preview / inquiry extract artifacts."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import validates

from app.database import Base


class InquiryExtractModel(Base):
    """Frozen manufacturer-facing extract for one case revision.

    Phase-1 RFQ preview/export uses this table as an append-only artifact
    store. Consent fields are explicit and default to non-shareable.
    """

    __tablename__ = "inquiry_extracts"

    extract_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    case_revision = Column(Integer, nullable=False)
    artifact_type = Column(String(64), nullable=False, default="rfq_preview", server_default="manufacturer_inquiry")
    payload = Column(JSONB(astext_type=Text()), nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    source_kind = Column(String(32), nullable=False, default="case_revision", server_default="case_revision")
    dispatched_to_manufacturer_id = Column(String(255), nullable=True, index=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    consent_status = Column(String(32), nullable=False, default="not_requested", server_default="not_requested")
    consent_granted_at = Column(DateTime(timezone=True), nullable=True)
    consent_granted_by = Column(String(255), nullable=True)
    consent_scope = Column(JSONB(astext_type=Text()), nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    dispatch_enabled = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    @validates("tenant_id")
    def _validate_tenant_id(self, _key: str, value: Any) -> str:
        normalized = str(value or "").strip()
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

    @validates("payload", "consent_scope")
    def _validate_json_object(self, key: str, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be a dict")
        return value
