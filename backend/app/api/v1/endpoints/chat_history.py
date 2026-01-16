from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from app.api.v1.endpoints.state import _build_state_config_with_checkpointer, _state_to_dict
from app.services.auth.dependencies import (
    RequestUser,
    canonical_tenant_id,
    canonical_user_id,
    get_current_request_user,
)
from app.services.chat.conversations import (
    ConversationMeta,
    OwnerIds,
    delete_conversation,
    list_conversations,
    upsert_conversation,
)

# Optional: tenant scoping helper (preferred). Fallback below if not present.
try:  # pragma: no cover
    from app.services.auth.scope import build_scope_id  # type: ignore
except Exception:  # pragma: no cover
    build_scope_id = None  # type: ignore

try:  # pragma: no cover
    from app.database import AsyncSessionLocal
except Exception:  # pragma: no cover
    AsyncSessionLocal = None

try:  # pragma: no cover
    from app.models.chat_message import ChatMessage
except Exception:  # pragma: no cover
    ChatMessage = None

try:  # pragma: no cover
    from app.models.chat_transcript import ChatTranscript
except Exception:  # pragma: no cover
    ChatTranscript = None


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class ConversationTitleUpdate(BaseModel):
    title: str


class ConversationResponse(BaseModel):
    thread_id: str
    title: Optional[str] = None
    updated_at: str
    last_preview: Optional[str] = None
    id: str


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _make_scope_owner_id(*, tenant_id: str, user_id: str) -> str:
    """
    Owner-ID for Redis keys. Prefer build_scope_id if available so we don't
    invent our own format. Fallback is 'tenant:user'.
    """
    if not tenant_id or not user_id:
        return user_id or ""
    if build_scope_id is not None:
        try:
            value = build_scope_id(tenant_id, user_id)
            if isinstance(value, str) and value:
                return value
        except Exception:
            logger.exception("build_scope_id_failed", extra={"tenant_id": tenant_id})
    return f"{tenant_id}:{user_id}"


def _extract_user_id_from_owner(owner_id: str, *, fallback_user_id: str) -> str:
    """
    If owner_id is scoped (e.g. 'tenant:user'), extract the user part.
    """
    if not owner_id:
        return fallback_user_id
    if ":" in owner_id:
        tail = owner_id.split(":")[-1].strip()
        return tail or fallback_user_id
    return owner_id


def _conversation_to_dict(entry: ConversationMeta) -> Dict[str, Any]:
    return {
        "thread_id": entry.id,
        "id": entry.id,
        "title": entry.title,
        "updated_at": entry.updated_at.isoformat(),
        "last_preview": entry.last_preview,
    }


def _serialize_message(raw: Any, index: int) -> Dict[str, Any]:
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

    def _coerce_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, list):
            return "".join(_coerce_text(part) for part in value)
        if isinstance(value, dict):
            for key in ("content", "text", "message"):
                candidate = _coerce_text(value.get(key))
                if candidate:
                    return candidate
            return "".join(_coerce_text(v) for v in value.values())
        return str(value)

    def _determine_role(obj: Any) -> str:
        if isinstance(obj, HumanMessage):
            return "user"
        if isinstance(obj, AIMessage):
            return "assistant"
        if isinstance(obj, SystemMessage):
            return "system"
        if isinstance(obj, dict):
            return obj.get("role") or obj.get("type") or "assistant"
        if isinstance(obj, BaseMessage):
            return "assistant"
        return "assistant"

    def _created_at(obj: Any) -> str:
        if isinstance(obj, dict):
            for key in ("createdAt", "created_at", "timestamp"):
                value = obj.get(key)
                if isinstance(value, str):
                    return value
        if isinstance(obj, BaseMessage):
            extra = getattr(obj, "additional_kwargs", {}) or {}
            for key in ("created_at", "timestamp"):
                candidate = extra.get(key)
                if isinstance(candidate, str):
                    return candidate
        return _now_utc().isoformat()

    content = ""
    role = "assistant"
    if isinstance(raw, dict):
        content = _coerce_text(raw)
        role = _determine_role(raw)
    elif isinstance(raw, BaseMessage):
        value = getattr(raw, "content", "")
        content = _coerce_text(value)
        role = _determine_role(raw)
    else:
        content = _coerce_text(raw)

    return {
        "id": uuid.uuid4().hex,
        "role": role,
        "content": content,
        "createdAt": _created_at(raw),
        "index": index,
    }


def _serialize_db_message(row: Any, index: int) -> Dict[str, Any]:
    role = getattr(row, "role", None) or "assistant"
    content = getattr(row, "content", None) or ""
    ts = getattr(row, "timestamp", None)
    created_at = ts.isoformat() if ts is not None else _now_utc().isoformat()
    return {
        "id": str(getattr(row, "id", uuid.uuid4().hex)),
        "role": role,
        "content": content,
        "createdAt": created_at,
        "index": index,
    }


def _resolve_owner_ids(current_user: RequestUser) -> tuple[OwnerIds, str, str]:
    """
    Returns:
      - OwnerIds for Redis (canonical=tenant-scoped, legacy=old user_id)
      - tenant_id
      - user_id (plain, for DB/graph)
    """
    user_id = canonical_user_id(current_user) or ""
    tenant_id = canonical_tenant_id(current_user) or ""

    if not user_id:
        return OwnerIds(canonical="", legacy=None), tenant_id, user_id

    scoped_owner = _make_scope_owner_id(tenant_id=tenant_id, user_id=user_id)

    # Legacy reads: previously owner_id was just user_id (no tenant).
    legacy_owner = user_id if scoped_owner != user_id else None

    # If you had an older legacy mapping based on sub, keep it as secondary hint.
    # OwnerIds supports only one legacy; prefer old user_id keys.
    return OwnerIds(canonical=scoped_owner, legacy=legacy_owner), tenant_id, user_id


def _find_conversation(owner_ids: OwnerIds, conversation_id: str) -> Optional[ConversationMeta]:
    items = list_conversations(owner_ids=owner_ids, limit=500)
    for it in items:
        if it.id == conversation_id:
            return it
    return None


async def _list_conversations_from_db(*, tenant_id: str, user_id: str, limit: int = 200) -> List[ConversationResponse]:
    if not tenant_id or not user_id:
        return []
    if AsyncSessionLocal is None or ChatTranscript is None:
        return []

    async with AsyncSessionLocal() as session:
        stmt = (
            select(ChatTranscript)
            .where(ChatTranscript.tenant_id == tenant_id, ChatTranscript.user_id == user_id)
            .order_by(desc(ChatTranscript.updated_at))
            .limit(limit)
        )
        res = await session.execute(stmt)
        rows = list(res.scalars().all())

    out: List[ConversationResponse] = []

    # Write-through into Redis: use scoped owner for keys, no tenant leakage.
    scoped_owner_ids = OwnerIds(canonical=_make_scope_owner_id(tenant_id=tenant_id, user_id=user_id), legacy=None)

    for row in rows:
        chat_id = getattr(row, "chat_id", None) or ""
        summary = getattr(row, "summary", None) or "New Conversation"
        updated_at = getattr(row, "updated_at", None) or getattr(row, "created_at", None) or _now_utc()

        meta = getattr(row, "metadata_json", None) or {}
        last_preview = None
        if isinstance(meta, dict):
            last_preview = meta.get("last_assistant_preview") or meta.get("last_user_message")

        try:
            upsert_conversation(
                owner_ids=scoped_owner_ids,
                conversation_id=chat_id,
                title=summary,
                updated_at=updated_at,
                last_preview=last_preview,
            )
        except Exception:
            logger.exception(
                "chat_history_upsert_conversation_failed",
                extra={"tenant_id": tenant_id, "chat_id": chat_id},
            )

        out.append(
            ConversationResponse(
                thread_id=chat_id,
                id=chat_id,
                title=summary,
                updated_at=updated_at.isoformat(),
                last_preview=last_preview,
            )
        )
    return out


@router.get("/conversations")
async def list_conversations_endpoint(
    current_user: RequestUser = Depends(get_current_request_user),
    limit: int = 200,
) -> Dict[str, Any]:
    owner_ids, tenant_id, user_id = _resolve_owner_ids(current_user)
    if not owner_ids.canonical or not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    items = list_conversations(owner_ids=owner_ids, limit=limit)
    if items:
        return {"conversations": [_conversation_to_dict(it) for it in items], "source": "redis"}

    db_items = await _list_conversations_from_db(tenant_id=tenant_id, user_id=user_id, limit=limit)
    return {"conversations": [it.model_dump() for it in db_items], "source": "postgres"}


@router.patch("/conversations/{conversation_id}")
async def rename_conversation_endpoint(
    conversation_id: str,
    payload: ConversationTitleUpdate,
    current_user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    owner_ids, tenant_id, user_id = _resolve_owner_ids(current_user)
    if not owner_ids.canonical or not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    entry = _find_conversation(owner_ids, conversation_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Conversation not found")

    upsert_conversation(
        owner_ids=owner_ids,
        conversation_id=conversation_id,
        title=payload.title,
        updated_at=_now_utc(),
        last_preview=entry.last_preview,
    )
    entry = _find_conversation(owner_ids, conversation_id)
    if not entry:
        raise HTTPException(status_code=500, detail="Failed to update conversation")
    return _conversation_to_dict(entry)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation_endpoint(
    conversation_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, bool]:
    owner_ids, tenant_id, user_id = _resolve_owner_ids(current_user)
    if not owner_ids.canonical or not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    entry = _find_conversation(owner_ids, conversation_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Conversation not found")

    delete_conversation(owner_ids, conversation_id, reason="user_delete")

    # Best-effort delete of LangGraph checkpoint thread
    try:
        # entry.owner_id might be scoped in Redis; always pass plain user_id to graph config.
        resolved_user_id = _extract_user_id_from_owner(entry.owner_id, fallback_user_id=user_id)
        graph, _ = await _build_state_config_with_checkpointer(
            thread_id=conversation_id,
            user_id=resolved_user_id,
            tenant_id=tenant_id,
        )
        try:
            await graph.checkpointer.adelete_thread(conversation_id)
        except AttributeError:
            # some checkpointers may not support delete
            pass
        except Exception as exc:
            logger.warning(
                "Failed to delete checkpointer thread: %s",
                exc,
                extra={"tenant_id": tenant_id, "user_id": resolved_user_id, "conversation_id": conversation_id},
            )
    except Exception as exc:
        logger.warning(
            "Failed to resolve graph for conversation deletion: %s",
            exc,
            extra={"tenant_id": tenant_id, "user_id": user_id, "conversation_id": conversation_id},
        )

    return {"deleted": True}


@router.get("/history/{conversation_id}")
async def get_conversation_history(
    conversation_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    owner_ids, tenant_id, user_id = _resolve_owner_ids(current_user)
    if not owner_ids.canonical or not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    entry = _find_conversation(owner_ids, conversation_id)
    if not entry:
        entry = ConversationMeta(
            id=conversation_id,
            owner_id=user_id,  # plain user id
            title=None,
            updated_at=_now_utc(),
            last_preview=None,
        )

    messages: list[dict[str, Any]] = []
    source = "none"

    # 1) Try LangGraph state first (fast + current)
    try:
        resolved_user_id = _extract_user_id_from_owner(entry.owner_id, fallback_user_id=user_id)
        graph, config = await _build_state_config_with_checkpointer(
            thread_id=conversation_id,
            user_id=resolved_user_id,
            tenant_id=tenant_id,
        )
        snapshot = await graph.aget_state(config)
        state_values = _state_to_dict(snapshot.values)
        raw_messages = state_values.get("messages") or []
        if raw_messages:
            messages = [_serialize_message(raw, idx) for idx, raw in enumerate(raw_messages)]
            source = "langgraph"
    except Exception:
        logger.exception(
            "chat_history_langgraph_read_failed",
            extra={"tenant_id": tenant_id, "user_id": user_id, "conversation_id": conversation_id},
        )
        messages = []
        source = "none"

    # 2) Fallback to Postgres if LangGraph has no messages
    if not messages and AsyncSessionLocal is not None and ChatMessage is not None and tenant_id:
        try:
            resolved_user_id = _extract_user_id_from_owner(entry.owner_id, fallback_user_id=user_id)
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(ChatMessage)
                    .where(
                        ChatMessage.tenant_id == tenant_id,
                        ChatMessage.session_id == conversation_id,
                        ChatMessage.username == resolved_user_id,
                    )
                    .order_by(ChatMessage.id.asc())
                )
                result = await session.execute(stmt)
                rows = list(result.scalars().all())
                messages = [_serialize_db_message(row, idx) for idx, row in enumerate(rows)]
                if messages:
                    source = "postgres"
        except Exception:
            logger.exception(
                "chat_history_db_read_failed",
                extra={"tenant_id": tenant_id, "user_id": user_id, "conversation_id": conversation_id},
            )

    return {
        "conversation_id": conversation_id,
        "title": entry.title,
        "updated_at": entry.updated_at.isoformat(),
        "messages": messages,
        "source": source,
    }


__all__ = ["router"]
