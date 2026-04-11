"""ORM model for inquiry_deliveries — Phase H1.4/H1.5."""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.types import JSON

from app.database import Base


class InquiryDelivery(Base):
    """Stores every inquiry payload that was created/sent to a manufacturer.

    Phase H1 status values:
      "logged"  — payload written to DB; no external delivery yet (H1 pilot)
      "sent"    — delivered via API/e-mail (future phases)
      "failed"  — delivery attempt failed
    """

    __tablename__ = "inquiry_deliveries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_inquiry_deliveries_idempotency_key"),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    case_id = Column(
        String(36),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    manufacturer_id = Column(String(100), nullable=False, index=True)
    payload_json = Column(JSON, nullable=False)
    idempotency_key = Column(String(255), nullable=False, unique=True)
    status = Column(String(50), nullable=False, default="logged")
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
