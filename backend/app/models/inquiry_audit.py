"""ORM model for inquiry_audit — Phase H1.5.

Append-only audit log: every inquiry creation is recorded here.
No UPDATE rights — rows are immutable after INSERT.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.types import JSON

from app.database import Base


class InquiryAudit(Base):
    """Immutable audit record for each inquiry payload creation.

    Fields:
      case_id            — FK → cases.id
      idempotency_key    — mirrors inquiry_deliveries.idempotency_key
      state_snapshot_id  — FK → case_state_snapshots.id (optional)
      decision_basis_hash — 16-char hash from GovernedSessionState
      pdf_url            — URL if PDF was generated (nullable)
      disclaimer_text    — verbatim disclaimer included in the payload
      payload_json       — full payload at audit time
      created_at         — immutable timestamp (no updated_at by design)
    """

    __tablename__ = "inquiry_audit"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_inquiry_audit_idempotency_key"),
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
    idempotency_key = Column(String(255), nullable=False, unique=True)
    state_snapshot_id = Column(
        String(36),
        ForeignKey("case_state_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision_basis_hash = Column(String(32), nullable=False)
    pdf_url = Column(String(500), nullable=True)
    disclaimer_text = Column(String(1000), nullable=True)
    payload_json = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # Intentionally NO updated_at — this table is append-only.
