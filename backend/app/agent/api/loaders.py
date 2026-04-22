import logging
import os
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

_log = logging.getLogger(__name__)

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
) -> tuple[GovernedSessionState, list[BaseMessage], dict[str, Any]]:
    governed = governed_state_override
    if governed is None:
        governed = await _load_live_governed_state(
            current_user=current_user,
            session_id=request.session_id,
            create_if_missing=True,
        )

    history = _governed_messages_as_langchain(governed)
    case_summary = _build_light_case_summary(governed)
    return governed, history, {"topic": case_summary} if case_summary else {}

def _build_light_runtime_context_from_request_only(
    request: Any, # ChatRequest
) -> tuple[list[BaseMessage], dict[str, Any]]:
    from langchain_core.messages import HumanMessage # noqa: PLC0415
    return [HumanMessage(content=request.message)], {}
