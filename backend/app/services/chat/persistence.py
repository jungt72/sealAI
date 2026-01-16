from __future__ import annotations

import logging
from typing import Any, Sequence

from sqlalchemy import select

logger = logging.getLogger(__name__)

try:  # pragma: no cover - allow importing without full app settings in tests
    from app.models.chat_transcript import ChatTranscript
except Exception:  # pragma: no cover
    ChatTranscript = None

try:  # pragma: no cover - allow importing without full app settings in tests
    from app.models.chat_message import ChatMessage
except Exception:  # pragma: no cover
    ChatMessage = None

try:  # pragma: no cover - allow importing without full app settings in tests
    from app.database import AsyncSessionLocal
except Exception:  # pragma: no cover
    AsyncSessionLocal = None


def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool, list, dict)):
            safe[str(key)] = value
        else:
            safe[str(key)] = str(value)
    return safe


async def persist_chat_transcript(
    *,
    chat_id: str,
    user_id: str,
    tenant_id: str,
    summary: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist chat summary/metadata (tenant scoped), without message history."""
    chat_id = (chat_id or "").strip()
    user_id = (user_id or "").strip()
    tenant_id = (tenant_id or "").strip()
    if not chat_id or not user_id or not tenant_id:
        return

    safe_summary = (summary or "").strip() or "New Conversation"
    safe_meta = _sanitize_metadata(metadata)

    if AsyncSessionLocal is None or ChatTranscript is None:  # pragma: no cover
        raise RuntimeError("Persistence dependencies unavailable")

    async with AsyncSessionLocal() as session:
        stmt = select(ChatTranscript).where(
            ChatTranscript.chat_id == chat_id,
            ChatTranscript.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.user_id = user_id
            existing.summary = safe_summary
            # IMPORTANT: Column is named "metadata" in DB, but mapped as metadata_json in the model.
            existing.metadata_json = safe_meta
            session.add(existing)
        else:
            transcript = ChatTranscript(
                chat_id=chat_id,
                user_id=user_id,
                tenant_id=tenant_id,
                summary=safe_summary,
                # IMPORTANT: Column is named "metadata" in DB, but mapped as metadata_json in the model.
                metadata_json=safe_meta,
            )
            session.add(transcript)

        await session.commit()

    logger.info(
        "persisted_chat_transcript",
        extra={"chat_id": chat_id, "tenant_id": tenant_id},
    )


async def persist_chat_messages(
    *,
    chat_id: str,
    user_id: str,
    tenant_id: str,
    messages: Sequence[tuple[str, str]],
    request_id: str | None = None,
    client_msg_id: str | None = None,
) -> None:
    """
    Persist the last user+assistant messages into Postgres (long-term history).

    Storage mapping to existing table `chat_messages`:
      - tenant_id  -> tenant_id
      - username   -> user_id (canonical Keycloak user id)
      - session_id -> chat_id (thread id)
      - role       -> "user" | "assistant" | "system"
      - content    -> message text
    """
    chat_id = (chat_id or "").strip()
    user_id = (user_id or "").strip()
    tenant_id = (tenant_id or "").strip()
    if not chat_id or not user_id or not tenant_id:
        return
    if not messages:
        return

    if AsyncSessionLocal is None or ChatMessage is None:  # pragma: no cover
        raise RuntimeError("Persistence dependencies unavailable")

    normalized: list[tuple[str, str]] = []
    for role, content in messages:
        r = (role or "").strip().lower() or "assistant"
        c = (content or "").strip()
        if not c:
            continue
        if r not in {"user", "assistant", "system"}:
            r = "assistant"
        normalized.append((r, c))

    if not normalized:
        return

    async with AsyncSessionLocal() as session:
        for role, content in normalized:
            row = ChatMessage(
                tenant_id=tenant_id,
                username=user_id,
                session_id=chat_id,
                role=role,
                content=content,
            )
            session.add(row)
        await session.commit()

    logger.info(
        "persisted_chat_messages",
        extra={
            "tenant_id": tenant_id,
            "chat_id": chat_id,
            "user_id": user_id,
            "count": len(normalized),
            "request_id": request_id,
            "client_msg_id": client_msg_id,
        },
    )


__all__ = ["persist_chat_transcript", "persist_chat_messages"]
