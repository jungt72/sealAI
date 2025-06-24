# 📁 backend/app/services/memory/postgres_logger.py

from app.models.chat_message import ChatMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Literal

async def log_message_to_db(
    db: AsyncSession,
    username: str,
    session_id: str,
    role: Literal["user", "assistant"],
    content: str,
):
    message = ChatMessage(
        username=username,
        session_id=session_id,
        role=role,
        content=content
    )
    db.add(message)
    await db.commit()

async def get_messages_for_session(
    db: AsyncSession,
    username: str,
    session_id: str
):
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.username == username)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.timestamp)
    )
    return result.scalars().all()
