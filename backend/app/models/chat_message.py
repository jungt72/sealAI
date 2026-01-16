from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)

    # Tenant scoping (NOT NULL in DB)
    tenant_id = Column(String, nullable=False, index=True)

    # We store canonical Keycloak user id here (historical name "username" kept to avoid migrations)
    username = Column(String, nullable=True, index=True)

    # We store the chat/thread id here (historical name "session_id" kept to avoid migrations)
    session_id = Column(String, nullable=True, index=True)

    # "user" | "assistant" | "system"
    role = Column(String, nullable=True)

    content = Column(Text, nullable=True)

    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
