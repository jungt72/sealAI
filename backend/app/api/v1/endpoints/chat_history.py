from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth.dependencies import RequestUser, get_current_request_user  # <-- CurrentUser NICHT importieren
from app.services.chat.conversations import (
    ConversationMeta,
    delete_conversation,
    list_conversations,
    upsert_conversation,
)
from app.services.history.persist import delete_structured_case, load_structured_case

"""Conversation and history endpoints that are scoped to the Keycloak user."""
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


def _resolve_owner_ids(current_user: RequestUser) -> Tuple[str, str | None]:
    owner_id = current_user.sub
    if not owner_id:
        return "", None
    legacy_owner_id = str(current_user.user_id or "")
    if legacy_owner_id == owner_id:
        legacy_owner_id = None
    return owner_id, legacy_owner_id


def _find_conversation(owner_id: str, conversation_id: str, legacy_owner_id: str | None) -> ConversationMeta | None:
    for entry in list_conversations(owner_id, legacy_owner_id=legacy_owner_id):
        if entry.id == conversation_id:
            return entry
    return None


@router.get("/conversations", response_model=List[ConversationResponse])
async def get_conversations(
    current_user: RequestUser = Depends(get_current_request_user),
) -> List[ConversationResponse]:
    """Return the user's conversations ordered by `updated_at` (Keycloak-scoped)."""
    owner_id, legacy_owner_id = _resolve_owner_ids(current_user)
    if not owner_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    entries = list_conversations(owner_id, legacy_owner_id=legacy_owner_id)
    return [_conversation_to_dict(entry) for entry in entries]


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: str,
    payload: ConversationTitleUpdate,
    current_user: RequestUser = Depends(get_current_request_user),
) -> ConversationResponse:
    """Update the title for a single conversation belonging to the authenticated user."""
    owner_id, legacy_owner_id = _resolve_owner_ids(current_user)
    if not owner_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    entry = _find_conversation(owner_id, conversation_id, legacy_owner_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Conversation not found")

    upsert_conversation(
        owner_id=owner_id,
        conversation_id=conversation_id,
        title=payload.title,
        updated_at=datetime.now(timezone.utc),
    )
    entry = _find_conversation(owner_id, conversation_id, legacy_owner_id)
    if not entry:
        raise HTTPException(status_code=500, detail="Failed to update conversation")
    return _conversation_to_dict(entry)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation_endpoint(
    conversation_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, bool]:
    """Delete both the metadata hash and LangGraph state for the user's conversation."""
    owner_id, legacy_owner_id = _resolve_owner_ids(current_user)
    if not owner_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    entry = _find_conversation(owner_id, conversation_id, legacy_owner_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Conversation not found")

    delete_conversation(owner_id, conversation_id, reason="user_delete")

    try:
        await delete_structured_case(owner_id=owner_id, case_id=conversation_id)
    except Exception as exc:
        logger.warning(
            "Failed to delete structured case: %s",
            exc,
            extra={"user_id": owner_id, "conversation_id": conversation_id},
        )

    return {"deleted": True}


@router.get("/history/{conversation_id}")
async def get_conversation_history(
    conversation_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    """Return persisted structured-case messages for the authenticated user's conversation."""

    owner_id, legacy_owner_id = _resolve_owner_ids(current_user)
    if not owner_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    entry = _find_conversation(owner_id, conversation_id, legacy_owner_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Conversation not found")

    state = await load_structured_case(owner_id=owner_id, case_id=conversation_id)
    raw_messages = (state or {}).get("messages") or []
    messages = [_serialize_message(raw, idx) for idx, raw in enumerate(raw_messages or [])]

    return {
        "conversation_id": conversation_id,
        "title": entry.title,
        "updated_at": entry.updated_at.isoformat(),
        "messages": messages,
    }
