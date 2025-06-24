# 📁 backend/app/models/chat_message.py

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.database import Base

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    session_id = Column(String, index=True)
    role = Column(String)  # "user" oder "assistant"
    content = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
