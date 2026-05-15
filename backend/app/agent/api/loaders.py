import logging
import os
import json
from typing import Any, Optional

from fastapi import HTTPException
from langchain_core.messages import BaseMessage

from app.agent.state.agent_state import AgentState
from app.agent.state.models import GovernedSessionState, ConversationMessage
from app.agent.graph import GraphState
from app.agent.state.persistence import (
    get_or_create_governed_state_async,
    load_governed_state_async,
    save_governed_state_async,
    save_governed_state_snapshot_async,
    get_governed_case_snapshot_by_revision_async,
    get_latest_governed_case_snapshot_async,
    with_snapshot_persistence_marker,
)
from app.services.auth.dependencies import RequestUser
from app.services.history.persist import load_structured_case, save_structured_case, ConcurrencyConflictError
from app.agent.api.deps import _canonical_scope, _cache_loaded_state
from app.agent.api.utils import (
    _governed_messages_as_langchain,
    _build_light_case_summary,
    _sync_governed_state_from_review_outcome,
)
from app.services.knowledge_case_bridge_service import (
    KnowledgeCaseBridgeService,
    KnowledgeConversationTurn,
    KnowledgeSessionContext,
    ParameterSeed,
)

_log = logging.getLogger(__name__)
_KNOWLEDGE_SESSION_TTL_SECONDS = 86_400

_PRE_GATE_CLASSIFICATIONS = {
    "GREETING",
    "META_QUESTION",
    "KNOWLEDGE_QUERY",
    "BLOCKED",
    "DOMAIN_INQUIRY",
}


def _snapshot_pre_gate_classification(value: str | None) -> str | None:
    if value in _PRE_GATE_CLASSIFICATIONS:
        return value
    return None


def _knowledge_session_key(*, tenant_id: str, owner_id: str, session_id: str) -> str:
    return f"knowledge_session:{tenant_id}:{owner_id}:{session_id}"


def _serialize_knowledge_session_context(context: KnowledgeSessionContext) -> str:
    payload = {
        "session_id": context.session_id,
        "mentioned_parameters": {
            field_name: {
                "field_name": seed.field_name,
                "raw_value": seed.raw_value,
                "raw_unit": seed.raw_unit,
                "confidence": seed.confidence,
                "source_turn_index": seed.source_turn_index,
            }
            for field_name, seed in dict(context.mentioned_parameters).items()
        },
        "explored_concepts": list(context.explored_concepts),
        "detected_intent": context.detected_intent,
        "transition_offered": context.transition_offered,
        "conversation_turns": [
            {"role": turn.role, "content": turn.content}
            for turn in context.conversation_turns
        ],
        "user_turn_index": context.user_turn_index,
    }
    return json.dumps(payload, ensure_ascii=True)


def _deserialize_knowledge_session_context(raw: str) -> KnowledgeSessionContext | None:
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    parameter_payload = data.get("mentioned_parameters") or {}
    mentioned_parameters = {
        str(field_name): ParameterSeed(**value)
        for field_name, value in dict(parameter_payload).items()
        if isinstance(value, dict)
    }
    conversation_turns = tuple(
        KnowledgeConversationTurn(
            role=str(turn.get("role") or "assistant"),
            content=str(turn.get("content") or ""),
        )
        for turn in list(data.get("conversation_turns") or [])
        if isinstance(turn, dict) and str(turn.get("content") or "").strip()
    )
    return KnowledgeSessionContext(
        session_id=str(data.get("session_id") or "default"),
        mentioned_parameters=mentioned_parameters,
        explored_concepts=tuple(str(item) for item in list(data.get("explored_concepts") or []) if str(item).strip()),
        detected_intent=str(data.get("detected_intent") or "").strip() or None,
        transition_offered=bool(data.get("transition_offered")),
        conversation_turns=conversation_turns,
        user_turn_index=int(data.get("user_turn_index") or 0),
    )

async def _load_live_governed_state(
    *,
    current_user: RequestUser,
    session_id: str,
    create_if_missing: bool = False,
) -> GovernedSessionState | None:
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=session_id)
    redis_url = os.getenv("REDIS_URL", "")
    from redis.asyncio import Redis as AsyncRedis # noqa: PLC0415
    async with AsyncRedis.from_url(redis_url, decode_responses=True) as redis_client:
        if create_if_missing:
            return await get_or_create_governed_state_async(
                tenant_id=tenant_id,
                session_id=session_id,
                redis_client=redis_client,
            )
        return await load_governed_state_async(
            tenant_id=tenant_id,
            session_id=session_id,
            redis_client=redis_client,
        )


async def _load_live_knowledge_session_context(
    *,
    current_user: RequestUser,
    session_id: str,
) -> KnowledgeSessionContext | None:
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=session_id)
    redis_url = os.getenv("REDIS_URL", "")
    from redis.asyncio import Redis as AsyncRedis  # noqa: PLC0415

    async with AsyncRedis.from_url(redis_url, decode_responses=True) as redis_client:
        raw = await redis_client.get(
            _knowledge_session_key(
                tenant_id=tenant_id,
                owner_id=owner_id,
                session_id=session_id,
            )
        )
    if raw is None:
        return None
    return _deserialize_knowledge_session_context(raw)


async def _persist_live_knowledge_session_context(
    *,
    current_user: RequestUser,
    session_id: str,
    context: KnowledgeSessionContext,
) -> None:
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=session_id)
    redis_url = os.getenv("REDIS_URL", "")
    from redis.asyncio import Redis as AsyncRedis  # noqa: PLC0415

    async with AsyncRedis.from_url(redis_url, decode_responses=True) as redis_client:
        await redis_client.set(
            _knowledge_session_key(
                tenant_id=tenant_id,
                owner_id=owner_id,
                session_id=session_id,
            ),
            _serialize_knowledge_session_context(context),
            ex=_KNOWLEDGE_SESSION_TTL_SECONDS,
        )


async def _clear_live_knowledge_session_context(
    *,
    current_user: RequestUser,
    session_id: str,
) -> None:
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=session_id)
    redis_url = os.getenv("REDIS_URL", "")
    from redis.asyncio import Redis as AsyncRedis  # noqa: PLC0415

    async with AsyncRedis.from_url(redis_url, decode_responses=True) as redis_client:
        await redis_client.delete(
            _knowledge_session_key(
                tenant_id=tenant_id,
                owner_id=owner_id,
                session_id=session_id,
            )
        )

async def _persist_live_governed_state(
    *,
    current_user: RequestUser,
    session_id: str,
    state: GovernedSessionState,
    pre_gate_classification: str | None = None,
) -> None:
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=session_id)
    redis_url = os.getenv("REDIS_URL", "")
    unmarked_state = state.model_copy(update={"persistence_marker": None})
    from redis.asyncio import Redis as AsyncRedis # noqa: PLC0415
    async with AsyncRedis.from_url(redis_url, decode_responses=True) as redis_client:
        await save_governed_state_async(
            tenant_id=tenant_id,
            session_id=session_id,
            state=unmarked_state,
            redis_client=redis_client,
        )
    try:
        snapshot_result = await save_governed_state_snapshot_async(
            unmarked_state,
            case_number=session_id,
            user_id=owner_id,
            tenant_id=tenant_id,
            pre_gate_classification=_snapshot_pre_gate_classification(pre_gate_classification),
            status="active",
        )
        if snapshot_result is not None:
            marked_state = with_snapshot_persistence_marker(unmarked_state, snapshot_result)
            async with AsyncRedis.from_url(redis_url, decode_responses=True) as redis_client:
                await save_governed_state_async(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    state=marked_state,
                    redis_client=redis_client,
                )
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "[loaders] governed snapshot persistence failed case=%s user=%s: %s",
            session_id,
            owner_id,
            exc,
            exc_info=True,
        )


async def persist_visible_governed_turn(
    *,
    current_user: RequestUser,
    session_id: str,
    user_message: str,
    assistant_message: str,
    governed_state: GovernedSessionState | None = None,
    pre_gate_classification: str | None = None,
    create_if_missing: bool = True,
) -> GovernedSessionState | None:
    """Persist visible non-graph turns into the governed transcript canon."""

    if not session_id or not str(assistant_message or "").strip():
        return None
    state = governed_state
    if state is None:
        state = await _load_live_governed_state(
            current_user=current_user,
            session_id=session_id,
            create_if_missing=create_if_missing,
        )
    if state is None:
        return None

    from app.agent.api.utils import _with_governed_conversation_turn  # noqa: PLC0415

    updated = state
    user_text = str(user_message or "").strip()
    assistant_text = str(assistant_message or "").strip()
    existing_messages = list(updated.conversation_messages)
    if user_text and not (
        existing_messages
        and existing_messages[-1].role == "user"
        and existing_messages[-1].content == user_text
    ):
        updated = _with_governed_conversation_turn(
            updated,
            role="user",
            content=user_text,
        )
        existing_messages = list(updated.conversation_messages)
    if assistant_text and not (
        existing_messages
        and existing_messages[-1].role == "assistant"
        and existing_messages[-1].content == assistant_text
    ):
        updated = _with_governed_conversation_turn(
            updated,
            role="assistant",
            content=assistant_text,
        )
    await _persist_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        state=updated,
        pre_gate_classification=pre_gate_classification,
    )
    return updated


def _merge_seed_into_governed_state(
    *,
    governed_state: GovernedSessionState,
    context: KnowledgeSessionContext,
) -> GovernedSessionState:
    seed = KnowledgeCaseBridgeService().build_governed_seed(context)

    conversation_messages = list(governed_state.conversation_messages)
    seen_turns = {(message.role, message.content) for message in conversation_messages}
    for message in seed.conversation_messages:
        key = (message.role, message.content)
        if key in seen_turns:
            continue
        conversation_messages.append(message)
        seen_turns.add(key)

    observed = governed_state.observed
    seen_extractions = {
        (
            extraction.field_name,
            json.dumps(extraction.raw_value, sort_keys=True, default=str),
            extraction.turn_index,
        )
        for extraction in observed.raw_extractions
    }
    for extraction in seed.observed_extractions:
        key = (
            extraction.field_name,
            json.dumps(extraction.raw_value, sort_keys=True, default=str),
            extraction.turn_index,
        )
        if key in seen_extractions:
            continue
        observed = observed.with_extraction(extraction)
        seen_extractions.add(key)

    progress = governed_state.exploration_progress.model_copy(
        update={
            "observed_topic": seed.observed_topic or governed_state.exploration_progress.observed_topic,
            "tentative_domain_signals": list(
                dict.fromkeys(
                    list(governed_state.exploration_progress.tentative_domain_signals)
                    + list(seed.tentative_domain_signals)
                )
            ),
            "case_active": True,
            "last_route": "KNOWLEDGE_BRIDGE",
        }
    )
    return governed_state.model_copy(
        update={
            "observed": observed,
            "conversation_messages": conversation_messages,
            "exploration_progress": progress,
            "user_turn_index": max(governed_state.user_turn_index, seed.user_turn_index),
        }
    )


async def _bridge_knowledge_session_to_governed_state(
    *,
    current_user: RequestUser,
    session_id: str,
    context: KnowledgeSessionContext,
) -> GovernedSessionState:
    governed_state = await _load_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        create_if_missing=True,
    )
    seeded_state = _merge_seed_into_governed_state(
        governed_state=governed_state,
        context=context,
    )
    await _persist_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        state=seeded_state,
        pre_gate_classification="DOMAIN_INQUIRY",
    )
    await _clear_live_knowledge_session_context(
        current_user=current_user,
        session_id=session_id,
    )
    return seeded_state

async def _persist_review_outcome_to_live_governed_state(
    *,
    current_user: RequestUser,
    session_id: str,
    case_state: dict[str, Any] | None,
    sealing_state: dict[str, Any] | None,
    assistant_reply: str | None = None,
) -> None:
    try:
        governed_state = await _load_live_governed_state(
            current_user=current_user,
            session_id=session_id,
            create_if_missing=False,
        )
    except Exception as exc:  # noqa: BLE001
        _log.debug("[loaders] review governed sync load skipped: %s", exc)
        return
    if governed_state is None:
        return
    updated = _sync_governed_state_from_review_outcome(
        governed_state,
        case_state=case_state,
        sealing_state=sealing_state,
    )
    if assistant_reply:
        from app.agent.api.utils import _with_governed_conversation_turn # noqa: PLC0415
        updated = _with_governed_conversation_turn(
            updated,
            role="assistant",
            content=assistant_reply,
        )
    await _persist_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        state=updated,
    )

async def _update_governed_state_post_graph(
    *,
    current_user: RequestUser,
    session_id: str,
    result_state: GraphState,
    pre_gate_classification: str | None = None,
) -> GovernedSessionState:
    from langchain_core.messages import HumanMessage # noqa: PLC0415
    governed = await _load_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        create_if_missing=True,
    )
    if not governed:
        raise HTTPException(status_code=404, detail="Governed state missing during commit")

    new_messages = list(result_state.conversation_messages or governed.conversation_messages)
    conversation = getattr(result_state, "conversation", None)
    for msg in getattr(conversation, "messages", []) or []:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        content = str(msg.content).strip()
        if content:
            new_messages.append(ConversationMessage(role=role, content=content))

    updated = governed.model_copy(
        update={
            "conversation_messages": new_messages,
            "observed": result_state.observed,
            "normalized": result_state.normalized,
            "asserted": result_state.asserted,
            "derived": result_state.derived,
            "evidence": result_state.evidence,
            "governance": result_state.governance,
            "decision": result_state.decision,
            "medium_capture": result_state.medium_capture,
            "medium_classification": result_state.medium_classification,
            "application_hint": result_state.application_hint,
            "motion_hint": result_state.motion_hint,
            "challenge": result_state.challenge,
            "seal_system": result_state.seal_system,
            "engineering": result_state.engineering,
            "calculation": result_state.calculation,
            "standards": result_state.standards,
            "evidence_graph": result_state.evidence_graph,
            "compound_state": result_state.compound_state,
            "document_evidence": result_state.document_evidence,
            "failure_observation": result_state.failure_observation,
            "review_state": result_state.review_state,
            "dossier": result_state.dossier,
            "matching": result_state.matching,
            "rfq": result_state.rfq,
            "dispatch": result_state.dispatch,
            "action_readiness": result_state.action_readiness,
            "case_lifecycle": result_state.case_lifecycle,
            "sealai_norm": result_state.sealai_norm,
            "export_profile": result_state.export_profile,
            "manufacturer_mapping": result_state.manufacturer_mapping,
            "dispatch_contract": result_state.dispatch_contract,
            "medium_context": result_state.medium_context,
            "medium_intelligence": result_state.medium_intelligence,
            "pending_question": result_state.pending_question,
            "last_slot_answer_binding": result_state.last_slot_answer_binding,
            "governed_answer_context": result_state.governed_answer_context,
            "v91_candidate_facts": result_state.v91_candidate_facts,
            "v91_field_governance_decisions": result_state.v91_field_governance_decisions,
            "v91_question_plan": result_state.v91_question_plan,
            "v91_conversation_task": result_state.v91_conversation_task,
            "v91_dialogue_debt": result_state.v91_dialogue_debt,
            "v91_final_answer_context": result_state.v91_final_answer_context,
            "exploration_progress": result_state.exploration_progress,
            "analysis_cycle": result_state.analysis_cycle,
            "user_turn_index": result_state.user_turn_index + 1,
            "max_cycles": result_state.max_cycles,
        }
    )

    await _persist_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        state=updated,
        pre_gate_classification=pre_gate_classification,
    )
    return updated

async def _load_governed_state_snapshot_projection_source(
    *,
    current_user: RequestUser,
    case_id: str,
    revision: int | None = None,
) -> GovernedSessionState | None:
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=case_id)
    if revision is not None:
        snapshot = await get_governed_case_snapshot_by_revision_async(
            case_number=case_id,
            tenant_id=tenant_id,
            user_id=owner_id,
            revision=revision,
        )
        if snapshot and snapshot.state_json:
            return GovernedSessionState.model_validate(snapshot.state_json)
        return None

    redis_url = os.getenv("REDIS_URL", "")
    from redis.asyncio import Redis as AsyncRedis # noqa: PLC0415
    async with AsyncRedis.from_url(redis_url, decode_responses=True) as redis_client:
        return await load_governed_state_async(
            tenant_id=tenant_id,
            session_id=case_id,
            redis_client=redis_client,
        )

async def _load_guarded_workspace_projection_source(
    *,
    current_user: RequestUser,
    case_id: str,
) -> GovernedSessionState | None:
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=case_id)
    redis_url = os.getenv("REDIS_URL", "")
    from redis.asyncio import Redis as AsyncRedis # noqa: PLC0415
    async with AsyncRedis.from_url(redis_url, decode_responses=True) as redis_client:
        redis_state = await load_governed_state_async(
            tenant_id=tenant_id,
            session_id=case_id,
            redis_client=redis_client,
        )

    if redis_state is None:
        snapshot = await get_latest_governed_case_snapshot_async(
            case_number=case_id,
            tenant_id=tenant_id,
            user_id=owner_id,
        )
        if snapshot and snapshot.state_json:
            return GovernedSessionState.model_validate(snapshot.state_json)
        return None

    marker = redis_state.persistence_marker
    if (
        marker is not None
        and marker.snapshot_comparable is True
        and marker.postgres_snapshot_revision is not None
        and marker.postgres_case_revision is not None
        and marker.postgres_case_revision == marker.postgres_snapshot_revision
    ):
        snapshot = await get_latest_governed_case_snapshot_async(
            case_number=case_id,
            tenant_id=tenant_id,
            user_id=owner_id,
        )
        if (
            snapshot
            and snapshot.state_json
            and snapshot.revision == marker.postgres_snapshot_revision
        ):
            return GovernedSessionState.model_validate(snapshot.state_json)

    return redis_state

async def _load_preferred_governed_workspace_source(
    *,
    current_user: RequestUser,
    case_id: str,
) -> GovernedSessionState:
    governed = await _load_governed_state_snapshot_projection_source(
        current_user=current_user,
        case_id=case_id,
    )
    if not governed:
        governed = await _load_live_governed_state(
            current_user=current_user,
            session_id=case_id,
            create_if_missing=True,
        )
    return governed

async def load_structured_residual_state(
    *,
    current_user: RequestUser,
    session_id: str,
) -> AgentState | None:
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=session_id)
    state = await load_structured_case(
        tenant_id=tenant_id,
        owner_id=owner_id,
        case_id=session_id,
    )
    if state:
        _cache_loaded_state(tenant_id, owner_id, session_id, state)
    return state

async def require_structured_residual_state(
    *,
    current_user: RequestUser,
    session_id: str,
) -> AgentState:
    state = await load_structured_residual_state(current_user=current_user, session_id=session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return state

async def load_structured_handover_state(
    *,
    current_user: RequestUser,
    session_id: str,
) -> AgentState | None:
    return await load_structured_residual_state(current_user=current_user, session_id=session_id)

async def require_structured_handover_state(
    *,
    current_user: RequestUser,
    session_id: str,
) -> AgentState:
    return await require_structured_residual_state(current_user=current_user, session_id=session_id)

async def load_structured_review_state(
    *,
    current_user: RequestUser,
    session_id: str,
) -> AgentState | None:
    return await load_structured_residual_state(current_user=current_user, session_id=session_id)

async def require_structured_review_state(
    *,
    current_user: RequestUser,
    session_id: str,
) -> AgentState:
    return await require_structured_residual_state(current_user=current_user, session_id=session_id)

async def persist_structured_residual_commit(
    *,
    current_user: RequestUser,
    session_id: str,
    state: AgentState,
) -> None:
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=session_id)
    try:
        await save_structured_case(
            tenant_id=tenant_id,
            owner_id=owner_id,
            case_id=session_id,
            state=state,
        )
    except ConcurrencyConflictError:
        _log.warning(
            "residual_commit_conflict tenant=%s owner=%s session=%s",
            tenant_id,
            owner_id,
            session_id,
        )
        raise HTTPException(
            status_code=409,
            detail="State collision: someone else modified this case. Please refresh.",
        )

async def persist_structured_review_commit(
    *,
    current_user: RequestUser,
    session_id: str,
    state: AgentState,
) -> None:
    await persist_structured_residual_commit(
        current_user=current_user,
        session_id=session_id,
        state=state,
    )

async def _build_light_runtime_context(
    *,
    request: Any, # ChatRequest
    current_user: RequestUser,
    governed_state_override: GovernedSessionState | None = None,
) -> tuple[GovernedSessionState, list[BaseMessage], str | None]:
    governed = governed_state_override
    if governed is None:
        governed = await _load_live_governed_state(
            current_user=current_user,
            session_id=request.session_id,
            create_if_missing=True,
        )

    history = _governed_messages_as_langchain(governed)
    case_summary = _build_light_case_summary(governed)
    return governed, history, case_summary

def _build_light_runtime_context_from_request_only(
    request: Any, # ChatRequest
) -> tuple[list[BaseMessage], dict[str, Any]]:
    from langchain_core.messages import HumanMessage # noqa: PLC0415
    return [HumanMessage(content=request.message)], {}
