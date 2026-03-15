import json
import os
import asyncio
from datetime import datetime, timezone
from typing import Dict, AsyncGenerator, Any
from fastapi import APIRouter, HTTPException, FastAPI, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from app.agent.api.models import CaseActionRequest, CaseActionResponse, ChatRequest, ChatResponse
from app.agent.agent.rwdr_orchestration import merge_rwdr_patch
from app.agent.agent.state import AgentState
from app.agent.agent.sync import project_rwdr_output, project_rwdr_read_model, sync_working_profile_to_state
from app.agent.agent.prompts import REASONING_PROMPT_VERSION, REASONING_PROMPT_HASH
from app.agent.case_state import (
    CASE_STATE_BUILDER_VERSION,
    PROJECTION_VERSION,
    QUALIFIED_ACTION_AUDIT_EVENT,
    QUALIFIED_ACTION_DOWNLOAD_RFQ,
    QUALIFIED_ACTION_STATUS_BLOCKED,
    QUALIFIED_ACTION_STATUS_EXECUTED,
    QualifiedActionAuditEvent,
    QualifiedActionId,
    QualifiedActionLifecycleStatus,
    VersionProvenance,
    get_material_input_snapshot_and_fingerprint,
    get_material_provider_snapshot_and_fingerprint,
    build_visible_case_narrative,
    build_conversation_guidance_contract,
    normalize_qualified_action_id,
    sync_case_state_to_state,
    sync_material_cycle_control,
)
from app.agent.cli import create_initial_state
from app.agent.runtime import (
    INTERACTION_POLICY_VERSION,
    RuntimeDecision,
    execute_fast_calculation,
    execute_fast_knowledge,
    route_interaction,
    evaluate_interaction_policy,
    InteractionPolicyDecision,
)
from app.services.auth.dependencies import RequestUser, canonical_user_id, get_current_request_user
from app.services.history.persist import load_structured_case, save_structured_case
from langchain_core.messages import HumanMessage, AIMessage

router = APIRouter()
QUALIFIED_ACTION_HISTORY_LIMIT = 5

# 0A.4: Only tokens from these nodes are forwarded to the client SSE stream.
# All other on_chat_model_stream events (reasoning, unknown, missing metadata)
# are silently suppressed.
_VISIBLE_STREAM_NODES: frozenset[str] = frozenset({"final_response_node"})

# Secondary in-process cache only. Structured source of truth is persisted state.
SESSION_STORE: Dict[str, AgentState] = {}
_GRAPH_APP = None


def _build_structured_version_provenance(
    *,
    decision: Any,
    rwdr_config_version: str | None = None,
) -> VersionProvenance:
    """0A.5: Provenance for structured paths where final_response_node uses an LLM.

    Accesses graph-level constants via a lazy import to avoid circular imports.
    """
    from app.agent.agent.graph import (  # noqa: PLC0415 — lazy to avoid circular import
        _GRAPH_MODEL_ID,
        VISIBLE_REPLY_PROMPT_VERSION,
        VISIBLE_REPLY_PROMPT_HASH,
    )
    vp: VersionProvenance = {
        "model_id": _GRAPH_MODEL_ID,
        "prompt_version": REASONING_PROMPT_VERSION,
        "prompt_hash": REASONING_PROMPT_HASH,
        "visible_reply_prompt_version": VISIBLE_REPLY_PROMPT_VERSION,
        "visible_reply_prompt_hash": VISIBLE_REPLY_PROMPT_HASH,
        "policy_version": getattr(decision, "policy_version", INTERACTION_POLICY_VERSION),
        "projection_version": PROJECTION_VERSION,
        "case_state_builder_version": CASE_STATE_BUILDER_VERSION,
        "data_version_note": "not_yet_governed",
    }
    if rwdr_config_version is not None:
        vp["rwdr_config_version"] = rwdr_config_version
    return vp


def _build_fast_path_version_provenance(*, decision: Any) -> VersionProvenance:
    """0A.5: Provenance for fast paths — no LLM used for visible output.

    model_id is intentionally None: fast calculation and fast knowledge paths
    do not run an LLM to generate the visible answer. Recording a model_id here
    would be false attribution.
    """
    return {
        "model_id": None,
        "policy_version": getattr(decision, "policy_version", INTERACTION_POLICY_VERSION),
        "projection_version": PROJECTION_VERSION,
        "case_state_builder_version": CASE_STATE_BUILDER_VERSION,
        "data_version_note": "not_yet_governed",
    }


def get_agent_graph():
    global _GRAPH_APP
    if _GRAPH_APP is None:
        from app.agent.agent.graph import app as graph_app

        _GRAPH_APP = graph_app
    return _GRAPH_APP

async def execute_agent(state: AgentState) -> AgentState:
    """Kapselt den Aufruf des LangGraph-Agenten.

    Router bleibt reiner Transport-Layer. RWDR-Fachlogik darf hier nicht
    nachgebildet werden; der Router delegiert nur an Graph/Orchestrierung.
    """
    graph_app = get_agent_graph()
    state = await asyncio.to_thread(graph_app.invoke, state)
    return sync_working_profile_to_state(state)


def build_runtime_payload(
    decision: Any,  # RuntimeDecision | InteractionPolicyDecision
    *,
    session_id: str,
    reply: str,
    case_state: Any = None,
    visible_case_narrative: Any = None,
    working_profile: Any = None,
    rwdr_output: Any = None,
    version_provenance: Any = None,
    next_step_contract: Any = None,
) -> Dict[str, Any]:
    qualified_action_gate = None
    result_contract = None
    rfq_ready = False
    payload_binding_level = decision.binding_level
    if case_state is not None:
        qualified_action_gate = case_state.get("qualified_action_gate")
        result_contract = case_state.get("result_contract")
        rfq_ready = bool((qualified_action_gate or {}).get("allowed", False))
        payload_binding_level = _resolve_payload_binding_level(
            decision.binding_level,
            case_state=case_state,
        )
    payload: Dict[str, Any] = {
        "reply": reply,
        "session_id": session_id,
        "interaction_class": decision.interaction_class,
        "runtime_path": decision.runtime_path,
        "binding_level": payload_binding_level,
        "has_case_state": decision.has_case_state,
        "case_id": session_id if decision.has_case_state else None,
        "qualified_action_gate": qualified_action_gate,
        "result_contract": result_contract,
        "rfq_ready": rfq_ready,
        "visible_case_narrative": visible_case_narrative,
        # 0A.2: Interaction Policy V1 fields — present when decision is InteractionPolicyDecision
        "result_form": getattr(decision, "result_form", None),
        "coverage_status": getattr(decision, "coverage_status", None),
        "boundary_flags": list(getattr(decision, "boundary_flags", ())),
        "escalation_reason": getattr(decision, "escalation_reason", None),
    }
    if case_state is not None:
        payload["case_state"] = jsonable_encoder(case_state)
    if working_profile is not None:
        payload["working_profile"] = jsonable_encoder(working_profile)
    if rwdr_output is not None:
        payload["rwdr_output"] = jsonable_encoder(rwdr_output)
    # 0A.5: additive version provenance
    if version_provenance is not None:
        payload["version_provenance"] = version_provenance
    # 0B.2a: next-step contract — present on structured paths, None on fast paths
    if next_step_contract is not None:
        payload["next_step_contract"] = next_step_contract
    return payload


def _case_cache_key(owner_id: str, case_id: str) -> str:
    return f"{owner_id}:{case_id}"


def _resolve_payload_binding_level(
    default_binding_level: str,
    *,
    case_state: Dict[str, Any] | None,
) -> str:
    if not case_state:
        return default_binding_level
    result_contract = case_state.get("result_contract") or {}
    if isinstance(result_contract.get("binding_level"), str):
        return str(result_contract["binding_level"])
    case_meta = case_state.get("case_meta") or {}
    if isinstance(case_meta.get("binding_level"), str):
        return str(case_meta["binding_level"])
    gate = case_state.get("qualified_action_gate") or {}
    if isinstance(gate.get("binding_level"), str):
        return str(gate["binding_level"])
    return default_binding_level


def _build_case_action_audit_event(
    *,
    action: QualifiedActionId,
    status: QualifiedActionLifecycleStatus,
    block_reasons: list[str],
) -> QualifiedActionAuditEvent:
    executed = status == QUALIFIED_ACTION_STATUS_EXECUTED
    return {
        "event_type": QUALIFIED_ACTION_AUDIT_EVENT,
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_ref": "api.agent.actions",
        "details": {
            "action": action,
            "status": status,
            "executed": executed,
            "block_reasons": list(block_reasons),
        },
    }


def _create_initial_agent_state(case_id: str, *, owner_id: str, tenant_id: str | None) -> AgentState:
    initial_sealing_state = create_initial_state()
    initial_sealing_state["cycle"]["analysis_cycle_id"] = f"session_{case_id}_1"
    state: AgentState = {
        "messages": [],
        "sealing_state": initial_sealing_state,
        "working_profile": {},
        "relevant_fact_cards": [],
        "tenant_id": tenant_id or owner_id,
        "owner_id": owner_id,
    }
    return state


async def prepare_structured_state(request: ChatRequest, *, current_user: RequestUser) -> AgentState:
    owner_id = canonical_user_id(current_user)
    cache_key = _case_cache_key(owner_id, request.session_id)
    current_state = await load_structured_case(owner_id=owner_id, case_id=request.session_id)
    if current_state is None:
        current_state = _create_initial_agent_state(
            request.session_id,
            owner_id=owner_id,
            tenant_id=current_user.tenant_id,
        )
    current_state["tenant_id"] = current_user.tenant_id or owner_id
    current_state["owner_id"] = owner_id
    if request.rwdr_input is not None or request.rwdr_input_patch is not None:
        merge_rwdr_patch(
            current_state["sealing_state"],
            rwdr_input=request.rwdr_input,
            rwdr_input_patch=request.rwdr_input_patch,
        )
    current_state["messages"].append(HumanMessage(content=request.message))
    SESSION_STORE[cache_key] = current_state
    return current_state


async def persist_structured_state(
    *,
    current_user: RequestUser,
    session_id: str,
    state: AgentState,
    decision: RuntimeDecision,
) -> None:
    owner_id = canonical_user_id(current_user)
    cache_key = _case_cache_key(owner_id, session_id)
    await save_structured_case(
        owner_id=owner_id,
        case_id=session_id,
        state=state,
        runtime_path=decision.runtime_path,
        binding_level=_resolve_payload_binding_level(
            decision.binding_level,
            case_state=state.get("case_state"),
        ),
    )
    SESSION_STORE[cache_key] = state


async def load_and_refresh_structured_case(
    *,
    current_user: RequestUser,
    case_id: str,
) -> tuple[AgentState, str, str]:
    owner_id = canonical_user_id(current_user)
    state = await load_structured_case(owner_id=owner_id, case_id=case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Structured case not found")

    existing_case_state = state.get("case_state") or {}
    case_meta = existing_case_state.get("case_meta") or {}
    runtime_path = str(case_meta.get("runtime_path") or "STRUCTURED_QUALIFICATION")
    binding_level = str(case_meta.get("binding_level") or "QUALIFIED_PRESELECTION")
    refreshed_state = sync_case_state_to_state(
        state,
        session_id=case_id,
        runtime_path=runtime_path,
        binding_level=binding_level,
    )
    return refreshed_state, runtime_path, binding_level


def _build_qualified_action_status_payload(
    *,
    action: QualifiedActionId,
    executed: bool,
    block_reasons: list[str],
    runtime_path: str,
    binding_level: str,
    action_payload: Dict[str, Any] | None,
    source_ref: str = "api.agent.actions.download_rfq_action",
) -> Dict[str, Any]:
    render_artifact = ((action_payload or {}).get("render_artifact") or {})
    artifact_provenance = None
    if render_artifact:
        artifact_provenance = {
            "artifact_type": str(render_artifact.get("artifact_type") or ""),
            "artifact_version": str(render_artifact.get("artifact_version") or ""),
            "filename": str(render_artifact.get("filename") or ""),
            "mime_type": str(render_artifact.get("mime_type") or ""),
            "source_ref": str(render_artifact.get("source_ref") or ""),
        }
    return {
        "action": normalize_qualified_action_id(action),
        "last_status": QUALIFIED_ACTION_STATUS_EXECUTED if executed else QUALIFIED_ACTION_STATUS_BLOCKED,
        "allowed_at_execution_time": executed,
        "executed": executed,
        "block_reasons": list(block_reasons),
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "binding_level": binding_level,
        "runtime_path": runtime_path,
        "source_ref": source_ref,
        "action_payload_stub": (
            (action_payload or {}).get("contract_version")
            or (action_payload or {}).get("artifact_stub")
        ),
        "current_gate_allows_action": executed,
        "artifact_provenance": artifact_provenance,
    }


def _carry_forward_case_read_models(
    previous_state: AgentState,
    next_state: AgentState,
) -> AgentState:
    previous_case_state = previous_state.get("case_state") or {}
    previous_action_status = previous_case_state.get("qualified_action_status")
    previous_action_history = previous_case_state.get("qualified_action_history")
    if not previous_action_status and not previous_action_history:
        return next_state

    updated_state = dict(next_state)
    next_case_state = dict(updated_state.get("case_state") or {})
    if previous_action_status and not next_case_state.get("qualified_action_status"):
        next_case_state["qualified_action_status"] = previous_action_status
    if previous_action_history and not next_case_state.get("qualified_action_history"):
        next_case_state["qualified_action_history"] = previous_action_history
    if next_case_state:
        updated_state["case_state"] = next_case_state
    return updated_state


def _append_qualified_action_history_entry(
    state: AgentState,
    *,
    entry: Dict[str, Any],
) -> AgentState:
    updated_state = dict(state)
    case_state = dict(updated_state.get("case_state") or {})
    existing_history = case_state.get("qualified_action_history") or []
    history = [entry, *[item for item in existing_history if isinstance(item, dict)]]
    case_state["qualified_action_history"] = history[:QUALIFIED_ACTION_HISTORY_LIMIT]
    case_state["qualified_action_status"] = entry
    updated_state["case_state"] = case_state
    return updated_state


def _build_guidance_response_payload(
    decision: Any,
    *,
    session_id: str,
    reply: str,
    state: AgentState,
    working_profile: Any = None,
    version_provenance: Any = None,
) -> Dict[str, Any]:
    """0A.3: Orientation-level payload for guided paths.

    Explicitly excludes qualification artifacts (case_state, result_contract,
    qualified_action_gate). Reuses deterministic visible narrative projection
    at ORIENTATION binding level without modification.
    0B.2: policy_context threaded into narrative builder for coverage_scope.
    0B.2a: next_step_contract wired from live post-run guidance_contract.
    """
    policy_context: Dict[str, Any] | None = None
    if hasattr(decision, "coverage_status"):
        policy_context = {
            "coverage_status": getattr(decision, "coverage_status", None),
            "boundary_flags": list(getattr(decision, "boundary_flags", ())),
            "escalation_reason": getattr(decision, "escalation_reason", None),
            "required_fields": list(getattr(decision, "required_fields", ())),
        }
    visible_case_narrative = build_visible_case_narrative(
        state=state,
        case_state=None,
        binding_level="ORIENTATION",
        policy_context=policy_context,
    )
    # 0B.2a: derive next_step_contract from post-run live state
    next_step_contract = build_conversation_guidance_contract(state)
    payload: Dict[str, Any] = {
        "reply": reply,
        "session_id": session_id,
        "interaction_class": decision.interaction_class,
        "runtime_path": decision.runtime_path,
        "binding_level": "ORIENTATION",
        "has_case_state": True,
        "case_id": session_id,
        "rfq_ready": False,
        "result_form": getattr(decision, "result_form", "guided"),
        "coverage_status": getattr(decision, "coverage_status", None),
        "boundary_flags": list(getattr(decision, "boundary_flags", ())),
        "escalation_reason": getattr(decision, "escalation_reason", None),
        "visible_case_narrative": visible_case_narrative,
        "next_step_contract": next_step_contract,
    }
    if working_profile is not None:
        payload["working_profile"] = jsonable_encoder(working_profile)
    # 0A.5: additive version provenance
    if version_provenance is not None:
        payload["version_provenance"] = version_provenance
    return payload


async def execute_fast_path(
    request: ChatRequest,
    decision: RuntimeDecision,
    version_provenance: Any = None,
) -> Dict[str, Any]:
    if decision.runtime_path == "FAST_CALCULATION":
        result = await execute_fast_calculation(request.message)
    else:
        result = await execute_fast_knowledge(request.message)
    return build_runtime_payload(
        decision,
        session_id=request.session_id,
        reply=result.reply,
        working_profile=result.working_profile,
        version_provenance=version_provenance,
    )

async def event_generator(
    request: ChatRequest,
    *,
    current_user: RequestUser,
) -> AsyncGenerator[str, None]:
    """
    Asynchroner Generator für SSE-Streaming (Phase F3).
    Extrahiert Chunks aus dem LLM-Stream und sendet sie an das Frontend.
    """
    from app.services.auth.dependencies import canonical_user_id as _cuid
    session_id = request.session_id
    _owner_id = _cuid(current_user)
    _cache_key = _case_cache_key(_owner_id, session_id)
    _cached_state = SESSION_STORE.get(_cache_key)
    decision = evaluate_interaction_policy(
        request.message,
        has_rwdr_payload=request.rwdr_input is not None or request.rwdr_input_patch is not None,
        existing_state=_cached_state,
    )

    if not decision.has_case_state:
        try:
            vp_fast = _build_fast_path_version_provenance(decision=decision)
            fast_payload = await execute_fast_path(request, decision, version_provenance=vp_fast)
            yield f"data: {json.dumps({'chunk': fast_payload['reply']})}\n\n"
            yield f"data: {json.dumps(fast_payload)}\n\n"
            yield "data: [DONE]\n\n"
            return
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

    # 0A.5: build structured provenance once for this request
    _rwdr_config_version = (
        ((_cached_state or {}).get("sealing_state") or {})
        .get("rwdr", {})
        .get("config_version")
    )
    vp_structured = _build_structured_version_provenance(
        decision=decision,
        rwdr_config_version=_rwdr_config_version,
    )

    current_state = await prepare_structured_state(request, current_user=current_user)
    final_state = current_state
    cycle = current_state.get("sealing_state", {}).get("cycle", {})
    previous_material_snapshot = cycle.get("material_input_snapshot")
    previous_material_fingerprint = cycle.get("material_input_fingerprint")
    if previous_material_snapshot is None or previous_material_fingerprint is None:
        previous_material_snapshot, previous_material_fingerprint = get_material_input_snapshot_and_fingerprint(current_state)
    previous_provider_snapshot = cycle.get("provider_contract_snapshot")
    previous_provider_fingerprint = cycle.get("provider_contract_fingerprint")
    if previous_provider_snapshot is None or previous_provider_fingerprint is None:
        previous_provider_snapshot, previous_provider_fingerprint = get_material_provider_snapshot_and_fingerprint(current_state)

    try:
        # 2. Über LangGraph Events iterieren (Version v2)
        graph_app = get_agent_graph()
        async for event in graph_app.astream_events(current_state, version="v2"):
            kind = event["event"]
            
            # Token-Streaming vom Chat-Modell — 0A.4: only visible answer nodes
            if kind == "on_chat_model_stream":
                node = event.get("metadata", {}).get("langgraph_node")
                if node in _VISIBLE_STREAM_NODES:
                    chunk = event["data"].get("chunk")
                    if chunk and chunk.content:
                        yield f"data: {json.dumps({'chunk': chunk.content})}\n\n"
            
            # Finalen State am Ende der Kette abgreifen
            elif kind == "on_chain_end" and event["name"] == "LangGraph":
                final_state = event["data"].get("output")

        # 3. Session-Store aktualisieren
        if final_state:
            # Wave 1: Sync aufrufen
            final_state = sync_working_profile_to_state(final_state)
            final_state = _carry_forward_case_read_models(current_state, final_state)

            # 0A.3: Split guided vs qualified post-graph execution
            if decision.result_form == "guided":
                guided_state = dict(final_state)
                guided_state.pop("case_state", None)  # strip stale case_state from prior qualified turns
                last_msg = [m for m in guided_state["messages"] if isinstance(m, AIMessage)][-1]
                await persist_structured_state(
                    current_user=current_user,
                    session_id=session_id,
                    state=guided_state,
                    decision=decision,
                )
                payload = _build_guidance_response_payload(
                    decision,
                    session_id=session_id,
                    reply=last_msg.content,
                    state=guided_state,
                    working_profile=guided_state.get("working_profile"),
                    version_provenance=vp_structured,
                )
                yield f"data: {json.dumps(payload)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Qualified path — unchanged
            final_state = sync_material_cycle_control(
                final_state,
                previous_material_snapshot=previous_material_snapshot,
                previous_material_fingerprint=previous_material_fingerprint,
                previous_provider_snapshot=previous_provider_snapshot,
                previous_provider_fingerprint=previous_provider_fingerprint,
            )
            final_state = sync_case_state_to_state(
                final_state,
                session_id=session_id,
                runtime_path=decision.runtime_path,
                binding_level=decision.binding_level,
                version_provenance=vp_structured,
            )
            await persist_structured_state(
                current_user=current_user,
                session_id=session_id,
                state=final_state,
                decision=decision,
            )
            last_msg = [m for m in final_state["messages"] if isinstance(m, AIMessage)][-1]
            payload = build_runtime_payload(
                decision,
                session_id=session_id,
                reply=last_msg.content,
                case_state=final_state.get("case_state"),
                visible_case_narrative=build_visible_case_narrative(
                    state=final_state,
                    case_state=final_state.get("case_state"),
                    binding_level=_resolve_payload_binding_level(
                        decision.binding_level,
                        case_state=final_state.get("case_state"),
                    ),
                    policy_context={"coverage_status": getattr(decision, "coverage_status", None), "boundary_flags": list(getattr(decision, "boundary_flags", ())), "escalation_reason": getattr(decision, "escalation_reason", None), "required_fields": list(getattr(decision, "required_fields", ()))},
                ),
                working_profile=final_state.get("working_profile", {}),
                rwdr_output=project_rwdr_output(final_state.get("sealing_state", {}).get("rwdr")),
                version_provenance=vp_structured,
                # 0B.2a: post-run live next-step contract
                next_step_contract=build_conversation_guidance_contract(final_state),
            )
            payload["rwdr"] = project_rwdr_read_model(final_state.get("sealing_state", {}).get("rwdr"))

            # 4. Finalen technischen State senden
            yield f"data: {json.dumps(payload)}\n\n"
        
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    current_user: RequestUser = Depends(get_current_request_user),
):
    """REST-Endpunkt für Chat-Anfragen (Phase F2)."""
    session_id = request.session_id
    owner_id = canonical_user_id(current_user)
    cache_key = _case_cache_key(owner_id, session_id)
    cached_state = SESSION_STORE.get(cache_key)
    decision = evaluate_interaction_policy(
        request.message,
        has_rwdr_payload=request.rwdr_input is not None or request.rwdr_input_patch is not None,
        existing_state=cached_state,
    )
    
    try:
        if not decision.has_case_state:
            vp_fast = _build_fast_path_version_provenance(decision=decision)
            fast_payload = await execute_fast_path(request, decision, version_provenance=vp_fast)
            return ChatResponse(**fast_payload)

        # 0A.5: build structured provenance once for this request
        _rwdr_config_version = (
            (cached_state or {})
            .get("sealing_state", {})
            .get("rwdr", {})
            .get("config_version")
        )
        vp_structured = _build_structured_version_provenance(
            decision=decision,
            rwdr_config_version=_rwdr_config_version,
        )

        current_state = await prepare_structured_state(request, current_user=current_user)
        cycle = current_state.get("sealing_state", {}).get("cycle", {})
        previous_material_snapshot = cycle.get("material_input_snapshot")
        previous_material_fingerprint = cycle.get("material_input_fingerprint")
        if previous_material_snapshot is None or previous_material_fingerprint is None:
            previous_material_snapshot, previous_material_fingerprint = get_material_input_snapshot_and_fingerprint(current_state)
        previous_provider_snapshot = cycle.get("provider_contract_snapshot")
        previous_provider_fingerprint = cycle.get("provider_contract_fingerprint")
        if previous_provider_snapshot is None or previous_provider_fingerprint is None:
            previous_provider_snapshot, previous_provider_fingerprint = get_material_provider_snapshot_and_fingerprint(current_state)
        updated_state = await execute_agent(current_state)
        updated_state = _carry_forward_case_read_models(current_state, updated_state)

        # 0A.3: Split guided vs qualified post-graph execution
        if decision.result_form == "guided":
            guided_state = dict(updated_state)
            guided_state.pop("case_state", None)  # strip stale case_state from prior qualified turns
            last_msg = [m for m in guided_state["messages"] if isinstance(m, AIMessage)][-1]
            await persist_structured_state(
                current_user=current_user,
                session_id=session_id,
                state=guided_state,
                decision=decision,
            )
            return ChatResponse(**_build_guidance_response_payload(
                decision,
                session_id=session_id,
                reply=last_msg.content,
                state=guided_state,
                working_profile=guided_state.get("working_profile"),
                version_provenance=vp_structured,
            ))

        # Qualified path — unchanged
        updated_state = sync_material_cycle_control(
            updated_state,
            previous_material_snapshot=previous_material_snapshot,
            previous_material_fingerprint=previous_material_fingerprint,
            previous_provider_snapshot=previous_provider_snapshot,
            previous_provider_fingerprint=previous_provider_fingerprint,
        )
        updated_state = sync_case_state_to_state(
            updated_state,
            session_id=session_id,
            runtime_path=decision.runtime_path,
            binding_level=decision.binding_level,
            version_provenance=vp_structured,
        )
        await persist_structured_state(
            current_user=current_user,
            session_id=session_id,
            state=updated_state,
            decision=decision,
        )
        last_msg = [m for m in updated_state["messages"] if isinstance(m, AIMessage)][-1]
        rwdr_output = updated_state.get("sealing_state", {}).get("rwdr", {}).get("output")
        return ChatResponse(**build_runtime_payload(
            decision,
            session_id=session_id,
            reply=last_msg.content,
            case_state=updated_state.get("case_state"),
            visible_case_narrative=build_visible_case_narrative(
                state=updated_state,
                case_state=updated_state.get("case_state"),
                binding_level=_resolve_payload_binding_level(
                    decision.binding_level,
                    case_state=updated_state.get("case_state"),
                ),
                policy_context={"coverage_status": getattr(decision, "coverage_status", None), "boundary_flags": list(getattr(decision, "boundary_flags", ())), "escalation_reason": getattr(decision, "escalation_reason", None), "required_fields": list(getattr(decision, "required_fields", ()))},
            ),
            working_profile=updated_state.get("working_profile", {}),
            rwdr_output=rwdr_output,
            version_provenance=vp_structured,
            # 0B.2a: post-run live next-step contract
            next_step_contract=build_conversation_guidance_contract(updated_state),
        ))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cases/{case_id}/actions/download-rfq", response_model=CaseActionResponse)
async def download_rfq_action(
    case_id: str,
    body: CaseActionRequest,
    current_user: RequestUser = Depends(get_current_request_user),
):
    if body.action != "download_rfq":
        raise HTTPException(status_code=400, detail="Unsupported action")

    state, runtime_path, binding_level = await load_and_refresh_structured_case(
        current_user=current_user,
        case_id=case_id,
    )
    gate = (state.get("case_state") or {}).get("qualified_action_gate") or {}
    allowed = bool(gate.get("allowed"))
    block_reasons = list(gate.get("block_reasons", []))
    executed = allowed
    action_payload = None
    if executed:
        sealing_requirement_spec = (state.get("case_state") or {}).get("sealing_requirement_spec") or {}
        action_payload = {
            "sealing_requirement_spec": sealing_requirement_spec,
            "contract_version": sealing_requirement_spec.get("contract_version"),
            "rendering_status": sealing_requirement_spec.get("rendering_status"),
            "message": sealing_requirement_spec.get("rendering_message"),
            "render_artifact": sealing_requirement_spec.get("render_artifact"),
        }
    qualified_action_status = _build_qualified_action_status_payload(
        action=body.action,
        executed=executed,
        block_reasons=block_reasons,
        runtime_path=runtime_path,
        binding_level=binding_level,
        action_payload=action_payload,
        source_ref="api.agent.actions.download_rfq_action",
    )
    audit_event = _build_case_action_audit_event(
        action=body.action,
        status=QUALIFIED_ACTION_STATUS_EXECUTED if executed else QUALIFIED_ACTION_STATUS_BLOCKED,
        block_reasons=block_reasons,
    )
    state = _append_qualified_action_history_entry(
        state,
        entry=qualified_action_status,
    )
    state.setdefault("case_state", {}).setdefault("audit_trail", []).append(audit_event)
    await save_structured_case(
        owner_id=canonical_user_id(current_user),
        case_id=case_id,
        state=state,
        runtime_path=runtime_path,
        binding_level=binding_level,
    )
    SESSION_STORE[_case_cache_key(canonical_user_id(current_user), case_id)] = state

    return CaseActionResponse(
        case_id=case_id,
        action=body.action,
        allowed=allowed,
        executed=executed,
        block_reasons=block_reasons,
        runtime_path=runtime_path,
        binding_level=binding_level,
        qualified_action_gate=gate,
        result_contract=(state.get("case_state") or {}).get("result_contract"),
        case_state=state.get("case_state"),
        visible_case_narrative=build_visible_case_narrative(
            state=state,
            case_state=state.get("case_state"),
            binding_level=binding_level,
        ),
        action_payload=action_payload,
        audit_event=audit_event,
    )


@router.get("/cases/{case_id}/actions/download-rfq/artifact")
async def download_rfq_artifact(
    case_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
):
    state, runtime_path, binding_level = await load_and_refresh_structured_case(
        current_user=current_user,
        case_id=case_id,
    )
    gate = (state.get("case_state") or {}).get("qualified_action_gate") or {}
    allowed = bool(gate.get("allowed"))
    block_reasons = list(gate.get("block_reasons", []))
    if not allowed:
        qualified_action_status = _build_qualified_action_status_payload(
            action=QUALIFIED_ACTION_DOWNLOAD_RFQ,
            executed=False,
            block_reasons=block_reasons,
            runtime_path=runtime_path,
            binding_level=binding_level,
            action_payload=None,
            source_ref="api.agent.actions.download_rfq_artifact",
        )
        audit_event = _build_case_action_audit_event(
            action=QUALIFIED_ACTION_DOWNLOAD_RFQ,
            status=QUALIFIED_ACTION_STATUS_BLOCKED,
            block_reasons=block_reasons,
        )
        state = _append_qualified_action_history_entry(
            state,
            entry=qualified_action_status,
        )
        state.setdefault("case_state", {}).setdefault("audit_trail", []).append(audit_event)
        await save_structured_case(
            owner_id=canonical_user_id(current_user),
            case_id=case_id,
            state=state,
            runtime_path=runtime_path,
            binding_level=binding_level,
        )
        SESSION_STORE[_case_cache_key(canonical_user_id(current_user), case_id)] = state
        raise HTTPException(
            status_code=409,
            detail={
                "code": "rfq_action_blocked",
                "block_reasons": block_reasons,
            },
        )

    sealing_requirement_spec = (state.get("case_state") or {}).get("sealing_requirement_spec") or {}
    render_artifact = sealing_requirement_spec.get("render_artifact") or {}
    if not render_artifact:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "render_artifact_missing",
                "source_ref": sealing_requirement_spec.get("source_ref"),
            },
        )

    filename = str(render_artifact.get("filename") or "sealing-requirement-spec.md")
    mime_type = str(render_artifact.get("mime_type") or "text/plain")
    content = str(render_artifact.get("content") or "")
    action_payload = {
        "sealing_requirement_spec": sealing_requirement_spec,
        "contract_version": sealing_requirement_spec.get("contract_version"),
        "rendering_status": sealing_requirement_spec.get("rendering_status"),
        "message": sealing_requirement_spec.get("rendering_message"),
        "render_artifact": render_artifact,
    }
    qualified_action_status = _build_qualified_action_status_payload(
        action=QUALIFIED_ACTION_DOWNLOAD_RFQ,
        executed=True,
        block_reasons=[],
        runtime_path=runtime_path,
        binding_level=binding_level,
        action_payload=action_payload,
        source_ref="api.agent.actions.download_rfq_artifact",
    )
    audit_event = _build_case_action_audit_event(
        action=QUALIFIED_ACTION_DOWNLOAD_RFQ,
        status=QUALIFIED_ACTION_STATUS_EXECUTED,
        block_reasons=[],
    )
    state = _append_qualified_action_history_entry(
        state,
        entry=qualified_action_status,
    )
    state.setdefault("case_state", {}).setdefault("audit_trail", []).append(audit_event)
    await save_structured_case(
        owner_id=canonical_user_id(current_user),
        case_id=case_id,
        state=state,
        runtime_path=runtime_path,
        binding_level=binding_level,
    )
    SESSION_STORE[_case_cache_key(canonical_user_id(current_user), case_id)] = state
    return Response(
        content=content.encode("utf-8"),
        media_type=mime_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.post("/chat/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    current_user: RequestUser = Depends(get_current_request_user),
):
    """Streaming-Endpunkt für Echtzeit-Antworten (Phase F3)."""
    return StreamingResponse(
        event_generator(request, current_user=current_user),
        media_type="text/event-stream"
    )

# FastAPI App Instanz für Phase G1
app_api = FastAPI(title="SealAI LangGraph PoC API")
app_api.include_router(router)

# Statische Dateien ausliefern
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app_api.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    print(f"WARNUNG: Statisches Verzeichnis nicht gefunden: {static_dir}")
