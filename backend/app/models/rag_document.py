# backend/app/models/rag_document.py
from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text, func

from app.database import Base


class RagDocument(Base):
    __tablename__ = "rag_documents"

    document_id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    status = Column(String, index=True, nullable=False, default="queued")
    visibility = Column(String, nullable=False, default="private")
    filename = Column(String, nullable=True)
    content_type = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    category = Column(String, nullable=True)
    tags = Column(JSON, nullable=True)
    sha256 = Column(String, nullable=False)
    path = Column(Text, nullable=False)
    error = Column(Text, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    ingest_stats = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
