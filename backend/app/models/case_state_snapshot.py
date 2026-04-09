from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.types import JSON

from app.database import Base


class CaseStateSnapshot(Base):
    __tablename__ = "case_state_snapshots"
    __table_args__ = (
        UniqueConstraint("case_id", "revision", name="uq_case_state_snapshots_case_revision"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    state_json = Column(JSON, nullable=False)
    basis_hash = Column(String(32), nullable=True)
    ontology_version = Column(String(50), nullable=True)
    prompt_version = Column(String(50), nullable=True)
    model_version = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
