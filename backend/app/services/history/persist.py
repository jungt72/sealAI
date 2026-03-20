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


def build_structured_case_storage_key(tenant_id: str, owner_id: str, case_id: str) -> str:
    return f"agent_case:{tenant_id}:{owner_id}:{case_id}"


def _build_legacy_storage_key(owner_id: str, case_id: str) -> str:
    return f"agent_case:{owner_id}:{case_id}"


def _message_preview(message: BaseMessage | Any) -> str:
    content = getattr(message, "content", "") if isinstance(message, BaseMessage) else ""
    if isinstance(content, str):
        return content.strip()
    return str(content).strip()


def _latest_assistant_preview(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai":
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
    tenant_id: str,
    owner_id: str,
    case_id: str,
    state: AgentState,
    runtime_path: str,
    binding_level: str,
) -> PersistedStructuredCasePayload:
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
        messages=messages_to_dict(state.get("messages", [])),
        tenant_id=tenant_id,
    )


class ConcurrencyConflictError(Exception):
    pass


def _legacy_payload_matches_tenant(
    payload: PersistedStructuredCasePayload,
    *,
    tenant_id: str | None,
) -> bool:
    if tenant_id is None:
        return True
    return payload.tenant_id is not None and payload.tenant_id == tenant_id


async def save_structured_case(
    *,
    tenant_id: str,
    owner_id: str,
    case_id: str,
    state: AgentState,
    runtime_path: str,
    binding_level: str,
) -> None:
    from app.database import AsyncSessionLocal
    from app.models.chat_transcript import ChatTranscript

    payload = _build_structured_case_payload(
        tenant_id=tenant_id,
        owner_id=owner_id,
        case_id=case_id,
        state=state,
        runtime_path=runtime_path,
        binding_level=binding_level,
    )
    storage_key = build_structured_case_storage_key(tenant_id, owner_id, case_id)
    messages = state.get("messages", [])
    summary = _latest_assistant_preview(messages)

    sealing_cycle = state.get("sealing_state", {}).get("cycle", {})
    incoming_rev = sealing_cycle.get("state_revision")
    incoming_parent_rev = sealing_cycle.get("snapshot_parent_revision")
    incoming_cycle_id = sealing_cycle.get("analysis_cycle_id")

    async with AsyncSessionLocal() as session:
        existing = await session.get(ChatTranscript, storage_key, with_for_update=True)
        if existing:
            existing_cycle = ((existing.metadata_json or {}).get("sealing_state") or {}).get("cycle", {})
            db_rev = existing_cycle.get("state_revision")
            db_cycle_id = existing_cycle.get("analysis_cycle_id")
            if db_rev is not None and incoming_rev is not None:
                is_valid = incoming_parent_rev == db_rev if incoming_cycle_id != db_cycle_id else incoming_rev == db_rev
                if not is_valid:
                    raise ConcurrencyConflictError(
                        f"State revision conflict on case {case_id}: DB is at revision {db_rev}, but incoming state expects parent {incoming_parent_rev} or same rev {incoming_rev}."
                    )
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
        tenant_id=tenant_id,
        first_user_message=_first_user_message(messages),
        last_preview=summary,
    )


async def load_structured_case(*, tenant_id: str, owner_id: str, case_id: str) -> AgentState | None:
    from app.database import AsyncSessionLocal
    from app.models.chat_transcript import ChatTranscript

    storage_key = build_structured_case_storage_key(tenant_id, owner_id, case_id)
    loaded_from_legacy = False
    async with AsyncSessionLocal() as session:
        transcript = await session.get(ChatTranscript, storage_key)
        if transcript is None:
            legacy_key = _build_legacy_storage_key(owner_id, case_id)
            transcript = await session.get(ChatTranscript, legacy_key)
            loaded_from_legacy = transcript is not None
        if transcript is None or transcript.user_id != owner_id:
            return None
        metadata = transcript.metadata_json or {}
        if metadata.get("record_type") != STRUCTURED_CASE_RECORD_TYPE:
            return None
        try:
            payload = PersistedStructuredCasePayload.model_validate(metadata)
        except ValidationError as exc:
            logger.warning("Failed to validate structured case payload: %s", exc)
            return None

    if loaded_from_legacy and not _legacy_payload_matches_tenant(payload, tenant_id=tenant_id):
        return None
    if payload.tenant_id is not None and payload.tenant_id != tenant_id:
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


async def delete_structured_case(*, tenant_id: str, owner_id: str, case_id: str) -> None:
    from app.database import AsyncSessionLocal
    from app.models.chat_transcript import ChatTranscript

    storage_key = build_structured_case_storage_key(tenant_id, owner_id, case_id)
    async with AsyncSessionLocal() as session:
        transcript = await session.get(ChatTranscript, storage_key)
        if transcript is None:
            legacy_key = _build_legacy_storage_key(owner_id, case_id)
            transcript = await session.get(ChatTranscript, legacy_key)
            if transcript is not None:
                metadata = transcript.metadata_json or {}
                if metadata.get("record_type") != STRUCTURED_CASE_RECORD_TYPE:
                    return
                try:
                    payload = PersistedStructuredCasePayload.model_validate(metadata)
                except ValidationError:
                    return
                if not _legacy_payload_matches_tenant(payload, tenant_id=tenant_id):
                    return
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
