from __future__ import annotations

from sqlalchemy import Column, DateTime, String, Text, func, JSON

from app.database import Base


class ChatTranscript(Base):
    __tablename__ = "chat_transcripts"

    chat_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    summary = Column(Text, nullable=False)
    contributors = Column(JSON, nullable=True)
    # Column name stays "metadata" to avoid migrations even though attribute name must change.
    metadata_json = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
