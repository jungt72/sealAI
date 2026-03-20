import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.agent.graph import app, _GRAPH_MODEL_ID, VISIBLE_REPLY_PROMPT_HASH, VISIBLE_REPLY_PROMPT_VERSION
from app.agent.agent.prompts import REASONING_PROMPT_HASH, REASONING_PROMPT_VERSION
from app.agent.agent.state import AgentState
from app.agent.api.models import ChatRequest, ChatResponse
from app.agent.case_state import (
    CASE_STATE_BUILDER_VERSION,
    DETERMINISTIC_DATA_VERSION,
    DETERMINISTIC_SERVICE_VERSION,
    PROJECTION_VERSION,
    build_visible_case_narrative,
    resolve_next_step_contract,
)
from app.agent.cli import create_initial_state
from app.services.auth.dependencies import RequestUser, canonical_user_id
from app.services.history.persist import ConcurrencyConflictError, load_structured_case, save_structured_case

router = APIRouter()
SESSION_STORE: Dict[str, AgentState] = {}


def execute_agent(state: AgentState) -> AgentState:
    return app.invoke(state)


def _build_structured_version_provenance(*, decision: Any, rwdr_config_version: str | None = None) -> dict[str, Any]:
    vp = {
        "model_id": _GRAPH_MODEL_ID,
        "model_version": _GRAPH_MODEL_ID,
        "prompt_version": REASONING_PROMPT_VERSION,
        "prompt_hash": REASONING_PROMPT_HASH,
        "visible_reply_prompt_version": VISIBLE_REPLY_PROMPT_VERSION,
        "visible_reply_prompt_hash": VISIBLE_REPLY_PROMPT_HASH,
        "policy_version": getattr(decision, "policy_version", "interaction_policy_v1"),
        "projection_version": PROJECTION_VERSION,
        "case_state_builder_version": CASE_STATE_BUILDER_VERSION,
        "service_version": DETERMINISTIC_SERVICE_VERSION,
        "data_version": DETERMINISTIC_DATA_VERSION,
    }
    if rwdr_config_version is not None:
        vp["rwdr_config_version"] = rwdr_config_version
    return vp


def _build_fast_path_version_provenance(*, decision: Any) -> dict[str, Any]:
    return {
        "model_id": None,
        "model_version": None,
        "policy_version": getattr(decision, "policy_version", "interaction_policy_v1"),
        "projection_version": PROJECTION_VERSION,
        "case_state_builder_version": CASE_STATE_BUILDER_VERSION,
        "service_version": DETERMINISTIC_SERVICE_VERSION,
    }


def _case_cache_key(tenant_id: str, owner_id: str, case_id: str) -> str:
    return f"{tenant_id}:{owner_id}:{case_id}"


def _resolve_payload_binding_level(default_binding_level: str, *, case_state: Dict[str, Any] | None) -> str:
    if not case_state:
        return default_binding_level
    result_contract = case_state.get("result_contract") or {}
    if isinstance(result_contract.get("binding_level"), str):
        return str(result_contract["binding_level"])
    case_meta = case_state.get("case_meta") or {}
    return str(case_meta.get("binding_level") or default_binding_level)


def _advance_case_state_only_revision(
    state: AgentState,
    *,
    case_id: str,
    write_scope: str,
) -> AgentState:
    updated_state = dict(state)
    sealing_state = dict(updated_state.get("sealing_state") or {})
    cycle = dict(sealing_state.get("cycle") or {})
    current_revision = int(cycle.get("state_revision", 0) or 0)
    next_revision = current_revision + 1
    cycle["snapshot_parent_revision"] = current_revision
    cycle["state_revision"] = next_revision
    cycle["analysis_cycle_id"] = f"{cycle.get('analysis_cycle_id') or case_id}::{write_scope}::rev{next_revision}::{uuid.uuid4().hex[:8]}"
    sealing_state["cycle"] = cycle
    updated_state["sealing_state"] = sealing_state
    if updated_state.get("case_state"):
        case_state = dict(updated_state["case_state"])
        for section in ("case_meta", "result_contract", "sealing_requirement_spec"):
            if isinstance(case_state.get(section), dict):
                entry = dict(case_state[section])
                entry["state_revision"] = next_revision
                entry["analysis_cycle_id"] = cycle["analysis_cycle_id"]
                if section == "case_meta":
                    entry["version"] = next_revision
                case_state[section] = entry
        updated_state["case_state"] = case_state
    return updated_state


async def prepare_structured_state(request: ChatRequest, *, current_user: RequestUser) -> AgentState:
    owner_id = canonical_user_id(current_user)
    tenant_id = current_user.tenant_id or owner_id
    cache_key = _case_cache_key(tenant_id, owner_id, request.session_id)
    current_state = await load_structured_case(tenant_id=tenant_id, owner_id=owner_id, case_id=request.session_id)
    if current_state is None:
        initial_sealing_state = create_initial_state()
        initial_sealing_state["cycle"]["analysis_cycle_id"] = f"session_{request.session_id}_1"
        current_state = {
            "messages": [],
            "sealing_state": initial_sealing_state,
            "working_profile": {},
            "relevant_fact_cards": [],
            "tenant_id": tenant_id,
            "owner_id": owner_id,
            "loaded_state_revision": int(initial_sealing_state["cycle"].get("state_revision", 0) or 0),
        }
    current_state["owner_id"] = owner_id
    current_state["tenant_id"] = tenant_id
    current_state["loaded_state_revision"] = int((((current_state.get("sealing_state") or {}).get("cycle") or {}).get("state_revision", 0) or 0))
    current_state["messages"].append(HumanMessage(content=request.message))
    SESSION_STORE[cache_key] = current_state
    return current_state


async def persist_structured_state(
    *,
    current_user: RequestUser,
    session_id: str,
    state: AgentState,
    decision: Any,
) -> None:
    owner_id = canonical_user_id(current_user)
    tenant_id = current_user.tenant_id or owner_id
    cache_key = _case_cache_key(tenant_id, owner_id, session_id)
    current_revision = int((((state.get("sealing_state") or {}).get("cycle") or {}).get("state_revision", 0) or 0))
    loaded_revision = int(state.get("loaded_state_revision", current_revision) or 0)
    if current_revision == loaded_revision:
        state = _advance_case_state_only_revision(state, case_id=session_id, write_scope="structured_persist")
    try:
        await save_structured_case(
            tenant_id=tenant_id,
            owner_id=owner_id,
            case_id=session_id,
            state=state,
            runtime_path=decision.runtime_path,
            binding_level=_resolve_payload_binding_level(decision.binding_level, case_state=state.get("case_state")),
        )
    except ConcurrencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    state["loaded_state_revision"] = int((((state.get("sealing_state") or {}).get("cycle") or {}).get("state_revision", 0) or 0))
    SESSION_STORE[cache_key] = state


def build_runtime_payload(
    decision: Any,
    *,
    session_id: str,
    reply: str,
    case_state: Any = None,
    visible_case_narrative: Any = None,
    working_profile: Any = None,
    version_provenance: Any = None,
    next_step_contract: Any = None,
) -> Dict[str, Any]:
    qualified_action_gate = case_state.get("qualified_action_gate") if case_state else None
    result_contract = case_state.get("result_contract") if case_state else None
    return {
        "reply": reply,
        "session_id": session_id,
        "interaction_class": getattr(decision, "interaction_class", None),
        "runtime_path": getattr(decision, "runtime_path", None),
        "binding_level": _resolve_payload_binding_level(getattr(decision, "binding_level", "ORIENTATION"), case_state=case_state),
        "has_case_state": getattr(decision, "has_case_state", False),
        "case_id": session_id if getattr(decision, "has_case_state", False) else None,
        "qualified_action_gate": qualified_action_gate,
        "result_contract": result_contract,
        "rfq_ready": bool((qualified_action_gate or {}).get("allowed", False)),
        "visible_case_narrative": visible_case_narrative,
        "result_form": getattr(decision, "result_form", None),
        "path": getattr(decision, "path", None),
        "stream_mode": getattr(decision, "stream_mode", None),
        "required_fields": list(getattr(decision, "required_fields", ()) or ()),
        "coverage_status": getattr(decision, "coverage_status", None),
        "boundary_flags": list(getattr(decision, "boundary_flags", ()) or ()),
        "escalation_reason": getattr(decision, "escalation_reason", None),
        "case_state": jsonable_encoder(case_state) if case_state is not None else None,
        "working_profile": jsonable_encoder(working_profile) if working_profile is not None else None,
        "version_provenance": version_provenance,
        "next_step_contract": next_step_contract,
    }


def _build_guidance_response_payload(decision: Any, *, session_id: str, reply: str, state: AgentState, working_profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
    visible_case_narrative = build_visible_case_narrative(state=state, case_state=None, binding_level="ORIENTATION", policy_context={
        "coverage_status": getattr(decision, "coverage_status", None),
        "boundary_flags": list(getattr(decision, "boundary_flags", ()) or ()),
        "escalation_reason": getattr(decision, "escalation_reason", None),
        "required_fields": list(getattr(decision, "required_fields", ()) or ()),
    })
    return build_runtime_payload(
        decision,
        session_id=session_id,
        reply=reply,
        case_state=None,
        visible_case_narrative=visible_case_narrative,
        working_profile=working_profile,
    )


async def event_generator(request: ChatRequest) -> AsyncGenerator[str, None]:
    session_id = request.session_id
    if session_id not in SESSION_STORE:
        initial_sealing_state = create_initial_state()
        initial_sealing_state["cycle"]["analysis_cycle_id"] = f"session_{session_id}_1"
        SESSION_STORE[session_id] = {"messages": [], "sealing_state": initial_sealing_state, "working_profile": {}}
    current_state = SESSION_STORE[session_id]
    current_state["messages"].append(HumanMessage(content=request.message))
    final_state = current_state
    try:
        async for event in app.astream_events(current_state, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and chunk.content:
                    yield f"data: {json.dumps({'chunk': chunk.content})}\n\n"
            elif kind == "on_chain_end" and event["name"] == "LangGraph":
                final_state = event["data"].get("output")
        if final_state:
            SESSION_STORE[session_id] = final_state
            yield f"data: {json.dumps({'state': final_state['sealing_state'], 'working_profile': final_state.get('working_profile', {})})}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


async def chat_endpoint(request: ChatRequest, current_user: RequestUser | None = None):
    if current_user is None:
        session_id = request.session_id
        if session_id not in SESSION_STORE:
            initial_sealing_state = create_initial_state()
            initial_sealing_state["cycle"]["analysis_cycle_id"] = f"session_{session_id}_1"
            SESSION_STORE[session_id] = {"messages": [], "sealing_state": initial_sealing_state}
        current_state = SESSION_STORE[session_id]
        current_state["messages"].append(HumanMessage(content=request.message))
        updated_state = execute_agent(current_state)
        SESSION_STORE[session_id] = updated_state
        last_msg = [m for m in updated_state["messages"] if isinstance(m, AIMessage)][-1]
        return ChatResponse(reply=last_msg.content, session_id=session_id, sealing_state=updated_state["sealing_state"])

    state = await prepare_structured_state(request, current_user=current_user)
    updated_state = execute_agent(state)
    last_msg = [m for m in updated_state["messages"] if isinstance(m, AIMessage)][-1]
    decision = type("Decision", (), {
        "interaction_class": "structured_case",
        "runtime_path": "STRUCTURED_QUALIFICATION",
        "binding_level": "ORIENTATION",
        "has_case_state": True,
        "policy_version": "interaction_policy_v1",
        "result_form": "qualified",
        "path": "structured",
        "stream_mode": "structured_progress_stream",
        "required_fields": (),
        "coverage_status": None,
        "boundary_flags": (),
        "escalation_reason": None,
    })()
    visible_case_narrative = build_visible_case_narrative(state=updated_state, case_state=updated_state.get("case_state"), binding_level="ORIENTATION")
    payload = build_runtime_payload(
        decision,
        session_id=request.session_id,
        reply=last_msg.content,
        case_state=updated_state.get("case_state"),
        visible_case_narrative=visible_case_narrative,
        working_profile=updated_state.get("working_profile"),
        version_provenance=_build_structured_version_provenance(decision=decision),
        next_step_contract=resolve_next_step_contract(updated_state),
    )
    await persist_structured_state(current_user=current_user, session_id=request.session_id, state=updated_state, decision=decision)
    return ChatResponse(sealing_state=updated_state["sealing_state"], **payload)


@router.post("/chat", response_model=ChatResponse)
async def chat_route(request: ChatRequest):
    return await chat_endpoint(request)


@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    return StreamingResponse(event_generator(request), media_type="text/event-stream")


app_api = FastAPI(title="SealAI LangGraph PoC API")
app_api.include_router(router)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app_api.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
