from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, String, func

from app.database import Base


class CaseRecord(Base):
    __tablename__ = "cases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_number = Column(String(50), nullable=False, unique=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    subsegment = Column(String(100), nullable=True)
    status = Column(String(50), nullable=False, server_default="active", default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
