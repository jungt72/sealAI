from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi.encoders import jsonable_encoder
from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.agent.state import AgentState
from app.services.chat.conversations import upsert_conversation
from app.services.jobs.queue import enqueue_job

logger = logging.getLogger("app.history.persist")
QUEUE_NAME = "jobs:chat_transcripts"
STRUCTURED_CASE_RECORD_TYPE = "agent_structured_case_v1"


class PersistedStructuredCasePayload(BaseModel):
    """Blueprint v1.2 Section 02: persisted structured case shell for resumable runtime state."""

    case_id: str
    session_id: str
    owner_id: str
    runtime_path: str
    binding_level: str
    record_type: str = Field(default=STRUCTURED_CASE_RECORD_TYPE)
    sealing_state: Dict[str, Any]
    case_state: Optional[Dict[str, Any]] = None
    working_profile: Dict[str, Any] = Field(default_factory=dict)
    relevant_fact_cards: List[Dict[str, Any]] = Field(default_factory=list)
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    tenant_id: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


def build_structured_case_storage_key(owner_id: str, case_id: str) -> str:
    return f"agent_case:{owner_id}:{case_id}"


def _message_preview(message: BaseMessage | Any) -> str:
    content = getattr(message, "content", "") if isinstance(message, BaseMessage) else ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [str(part).strip() for part in content if str(part).strip()]
        return " ".join(parts)
    return str(content).strip()


def _latest_assistant_preview(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai":
            preview = _message_preview(message)
            if preview:
                return preview
    for message in reversed(messages):
        preview = _message_preview(message)
        if preview:
            return preview
    return "Structured case"


def _first_user_message(messages: list[BaseMessage]) -> str | None:
    for message in messages:
        if getattr(message, "type", "") == "human":
            preview = _message_preview(message)
            if preview:
                return preview
    return None


def _build_structured_case_payload(
    *,
    owner_id: str,
    case_id: str,
    state: AgentState,
    runtime_path: str,
    binding_level: str,
) -> PersistedStructuredCasePayload:
    messages = state.get("messages", [])
    return PersistedStructuredCasePayload(
        case_id=case_id,
        session_id=case_id,
        owner_id=owner_id,
        runtime_path=runtime_path,
        binding_level=binding_level,
        sealing_state=jsonable_encoder(state.get("sealing_state", {})),
        case_state=jsonable_encoder(state.get("case_state")),
        working_profile=jsonable_encoder(state.get("working_profile", {})),
        relevant_fact_cards=jsonable_encoder(state.get("relevant_fact_cards", [])),
        messages=messages_to_dict(messages),
        tenant_id=state.get("tenant_id"),
    )


async def save_structured_case(
    *,
    owner_id: str,
    case_id: str,
    state: AgentState,
    runtime_path: str,
    binding_level: str,
) -> None:
    from app.database import AsyncSessionLocal
    from app.models.chat_transcript import ChatTranscript

    payload = _build_structured_case_payload(
        owner_id=owner_id,
        case_id=case_id,
        state=state,
        runtime_path=runtime_path,
        binding_level=binding_level,
    )
    storage_key = build_structured_case_storage_key(owner_id, case_id)
    messages = state.get("messages", [])
    summary = _latest_assistant_preview(messages)

    async with AsyncSessionLocal() as session:
        existing = await session.get(ChatTranscript, storage_key)
        if existing:
            existing.user_id = owner_id
            existing.summary = summary
            existing.contributors = {"runtime_path": runtime_path, "binding_level": binding_level}
            existing.metadata_json = payload.model_dump(mode="python")
        else:
            session.add(
                ChatTranscript(
                    chat_id=storage_key,
                    user_id=owner_id,
                    summary=summary,
                    contributors={"runtime_path": runtime_path, "binding_level": binding_level},
                    metadata_json=payload.model_dump(mode="python"),
                )
            )
        await session.commit()

    upsert_conversation(
        owner_id=owner_id,
        conversation_id=case_id,
        first_user_message=_first_user_message(messages),
        last_preview=summary,
    )


async def load_structured_case(*, owner_id: str, case_id: str) -> AgentState | None:
    from app.database import AsyncSessionLocal
    from app.models.chat_transcript import ChatTranscript

    storage_key = build_structured_case_storage_key(owner_id, case_id)
    async with AsyncSessionLocal() as session:
        transcript = await session.get(ChatTranscript, storage_key)
        if transcript is None or transcript.user_id != owner_id:
            return None
        metadata = transcript.metadata_json or {}
        if metadata.get("record_type") != STRUCTURED_CASE_RECORD_TYPE:
            return None
        try:
            payload = PersistedStructuredCasePayload.model_validate(metadata)
        except ValidationError as exc:
            logger.warning(
                "Failed to validate structured case payload: %s",
                exc,
                extra={"owner_id": owner_id, "case_id": case_id},
            )
            return None

    state: AgentState = {
        "messages": messages_from_dict(payload.messages),
        "sealing_state": payload.sealing_state,
        "working_profile": payload.working_profile,
        "relevant_fact_cards": payload.relevant_fact_cards,
    }
    if payload.tenant_id is not None:
        state["tenant_id"] = payload.tenant_id
    if payload.case_state is not None:
        state["case_state"] = payload.case_state
    return state


async def delete_structured_case(*, owner_id: str, case_id: str) -> None:
    from app.database import AsyncSessionLocal
    from app.models.chat_transcript import ChatTranscript

    storage_key = build_structured_case_storage_key(owner_id, case_id)
    async with AsyncSessionLocal() as session:
        transcript = await session.get(ChatTranscript, storage_key)
        if transcript is None or transcript.user_id != owner_id:
            return
        await session.delete(transcript)
        await session.commit()


async def persist_chat_result(
    *,
    chat_id: str,
    user_id: str,
    summary: str,
    contributors: Any,
    metadata: Dict[str, Any],
) -> None:
    from app.database import AsyncSessionLocal
    from app.models.chat_transcript import ChatTranscript

    if not chat_id or not summary:
        return

    job_payload = {
        "chat_id": chat_id,
        "user_id": user_id,
        "summary": summary,
        "contributors": contributors,
        "metadata": metadata,
    }
    try:
        await enqueue_job(QUEUE_NAME, job_payload)
    except Exception as exc:
        logger.warning("Failed to enqueue transcript job: %s", exc)

    async def _store() -> None:
        try:
            async with AsyncSessionLocal() as session:
                existing = await session.get(ChatTranscript, chat_id)
                if existing:
                    existing.summary = summary
                    existing.contributors = contributors
                    existing.metadata_json = metadata
                else:
                    session.add(
                        ChatTranscript(
                            chat_id=chat_id,
                            user_id=user_id,
                            summary=summary,
                            contributors=contributors,
                            metadata_json=metadata,
                        )
                    )
                await session.commit()
        except Exception as exc:
            logger.error("Persisting chat transcript failed: %s", exc)

    asyncio.create_task(_store())
