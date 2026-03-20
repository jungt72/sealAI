from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth.dependencies import RequestUser, canonical_user_id, get_current_request_user
from app.services.chat.conversations import ConversationMeta, delete_conversation, list_conversations, upsert_conversation
from app.services.history.persist import delete_structured_case, load_structured_case

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class ConversationTitleUpdate(BaseModel):
    title: str


class ConversationResponse(BaseModel):
    thread_id: str
    title: str | None
    updated_at: str
    last_preview: str | None
    id: str


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
        return datetime.now(timezone.utc).isoformat()

    return {
        "id": uuid.uuid4().hex,
        "role": _determine_role(raw),
        "content": _coerce_text(getattr(raw, "content", raw)),
        "createdAt": _created_at(raw),
        "index": index,
    }


def _resolve_owner_ids(current_user: RequestUser) -> Tuple[str, str | None]:
    owner_id = canonical_user_id(current_user)
    if not owner_id:
        return "", None
    sub = current_user.sub or ""
    legacy_owner_id = sub if sub and sub != owner_id else None
    return owner_id, legacy_owner_id


def _find_conversation(
    owner_id: str,
    conversation_id: str,
    legacy_owner_id: str | None,
    *,
    tenant_id: str | None = None,
) -> ConversationMeta | None:
    for entry in list_conversations(owner_id, legacy_owner_id=legacy_owner_id, tenant_id=tenant_id):
        if entry.id == conversation_id:
            return entry
    return None


def _resolved_conversation_owner(entry: ConversationMeta, fallback_owner_id: str) -> str:
    owner = str(entry.owner_id or "").strip()
    return owner or fallback_owner_id


@router.get("/conversations", response_model=List[ConversationResponse])
async def get_conversations(
    current_user: RequestUser = Depends(get_current_request_user),
) -> List[ConversationResponse]:
    owner_id, legacy_owner_id = _resolve_owner_ids(current_user)
    if not owner_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    tenant_id = current_user.tenant_id or owner_id
    entries = list_conversations(owner_id, legacy_owner_id=legacy_owner_id, tenant_id=tenant_id)
    return [_conversation_to_dict(entry) for entry in entries]


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: str,
    payload: ConversationTitleUpdate,
    current_user: RequestUser = Depends(get_current_request_user),
) -> ConversationResponse:
    owner_id, legacy_owner_id = _resolve_owner_ids(current_user)
    if not owner_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    tenant_id = current_user.tenant_id or owner_id
    entry = _find_conversation(owner_id, conversation_id, legacy_owner_id, tenant_id=tenant_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Conversation not found")
    resolved_owner_id = _resolved_conversation_owner(entry, owner_id)
    upsert_conversation(
        owner_id=resolved_owner_id,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        title=payload.title,
        updated_at=datetime.now(timezone.utc),
    )
    return _conversation_to_dict(entry)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation_endpoint(
    conversation_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, bool]:
    owner_id, legacy_owner_id = _resolve_owner_ids(current_user)
    if not owner_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    tenant_id = current_user.tenant_id or owner_id
    entry = _find_conversation(owner_id, conversation_id, legacy_owner_id, tenant_id=tenant_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Conversation not found")
    resolved_owner_id = _resolved_conversation_owner(entry, owner_id)
    delete_conversation(resolved_owner_id, conversation_id, tenant_id=tenant_id, reason="user_delete")
    try:
        await delete_structured_case(tenant_id=tenant_id, owner_id=resolved_owner_id, case_id=conversation_id)
    except Exception as exc:
        logger.warning("Failed to delete structured case: %s", exc)
    return {"deleted": True}


@router.get("/history/{conversation_id}")
async def get_conversation_history(
    conversation_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    owner_id, legacy_owner_id = _resolve_owner_ids(current_user)
    if not owner_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    tenant_id = current_user.tenant_id or owner_id
    entry = _find_conversation(owner_id, conversation_id, legacy_owner_id, tenant_id=tenant_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Conversation not found")
    resolved_owner_id = _resolved_conversation_owner(entry, owner_id)
    state = await load_structured_case(tenant_id=tenant_id, owner_id=resolved_owner_id, case_id=conversation_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Structured case not found for conversation")
    raw_messages = (state or {}).get("messages") or []
    messages = [_serialize_message(raw, idx) for idx, raw in enumerate(raw_messages or [])]
    return {
        "conversation_id": conversation_id,
        "title": entry.title,
        "updated_at": entry.updated_at.isoformat(),
        "messages": messages,
    }
