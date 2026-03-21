import json
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.agent.graph import app, final_response_node, _GRAPH_MODEL_ID, VISIBLE_REPLY_PROMPT_HASH, VISIBLE_REPLY_PROMPT_VERSION
from app.agent.api.sse_runtime import agent_sse_generator
from app.agent.agent.prompts import REASONING_PROMPT_HASH, REASONING_PROMPT_VERSION
from app.agent.agent.state import AgentState
from app.agent.api.models import ChatRequest, ChatResponse, ReviewRequest, ReviewResponse, ReviewSeedResponse
from app.agent.case_state import (
    CASE_STATE_BUILDER_VERSION,
    DETERMINISTIC_DATA_VERSION,
    DETERMINISTIC_SERVICE_VERSION,
    PROJECTION_VERSION,
    build_visible_case_narrative,
    resolve_next_step_contract,
)
from app.agent.cli import create_initial_state
from app.agent.agent.interaction_policy import evaluate_policy as evaluate_interaction_policy
from app.services.auth.dependencies import RequestUser, canonical_user_id, get_current_request_user
from app.services.history.persist import ConcurrencyConflictError, load_structured_case, save_structured_case

router = APIRouter()
SESSION_STORE: Dict[str, AgentState] = {}


async def execute_agent(state: AgentState) -> AgentState:
    return await app.ainvoke(state)


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
    """SSE stream with Phase 0A.4 node filter.

    Only fast_guidance_node and final_response_node tokens reach the client.
    Internal nodes (reasoning_node, evidence_tool_node, selection_node) are
    silently filtered by agent_sse_generator.
    """
    session_id = request.session_id
    if session_id not in SESSION_STORE:
        initial_sealing_state = create_initial_state()
        initial_sealing_state["cycle"]["analysis_cycle_id"] = f"session_{session_id}_1"
        SESSION_STORE[session_id] = {"messages": [], "sealing_state": initial_sealing_state, "working_profile": {}}
    current_state = SESSION_STORE[session_id]
    current_state["messages"].append(HumanMessage(content=request.message))
    async for frame in agent_sse_generator(current_state, graph=app):
        yield frame


async def chat_endpoint(request: ChatRequest, current_user: RequestUser | None = None):
    if current_user is None:
        session_id = request.session_id
        if session_id not in SESSION_STORE:
            initial_sealing_state = create_initial_state()
            initial_sealing_state["cycle"]["analysis_cycle_id"] = f"session_{session_id}_1"
            SESSION_STORE[session_id] = {"messages": [], "sealing_state": initial_sealing_state}
        current_state = SESSION_STORE[session_id]
        current_state["messages"].append(HumanMessage(content=request.message))
        current_state["inquiry_id"] = session_id
        current_state.setdefault("turn_count", 0)
        current_state.setdefault("max_turns", 12)
        updated_state = await execute_agent(current_state)
        SESSION_STORE[session_id] = updated_state
        last_msg = [m for m in updated_state["messages"] if isinstance(m, AIMessage)][-1]
        return ChatResponse(reply=last_msg.content, session_id=session_id, sealing_state=updated_state["sealing_state"])

    decision = evaluate_interaction_policy(request.message)

    if not decision.has_case_state:
        session_id = request.session_id
        owner_id = canonical_user_id(current_user)
        tenant_id = current_user.tenant_id or owner_id
        cache_key = _case_cache_key(tenant_id, owner_id, session_id)
        if cache_key not in SESSION_STORE:
            initial_sealing_state = create_initial_state()
            initial_sealing_state["cycle"]["analysis_cycle_id"] = f"session_{session_id}_1"
            SESSION_STORE[cache_key] = {"messages": [], "sealing_state": initial_sealing_state, "working_profile": {}, "owner_id": owner_id, "tenant_id": tenant_id}
        current_state = SESSION_STORE[cache_key]
        current_state["messages"].append(HumanMessage(content=request.message))
        # Phase 0A.3: inject policy signals so the graph entry switch can route correctly
        current_state["policy_path"] = decision.path.value
        current_state["result_form"] = decision.result_form.value
        # Phase 0A QW-4: V3 spec fields
        current_state["inquiry_id"] = session_id
        current_state.setdefault("turn_count", 0)
        current_state.setdefault("max_turns", 12)
        updated_state = await execute_agent(current_state)
        SESSION_STORE[cache_key] = updated_state
        last_msg = [m for m in updated_state["messages"] if isinstance(m, AIMessage)][-1]
        payload = _build_guidance_response_payload(decision, session_id=session_id, reply=last_msg.content, state=updated_state, working_profile=updated_state.get("working_profile"))
        return ChatResponse(sealing_state=updated_state["sealing_state"], **payload)

    state = await prepare_structured_state(request, current_user=current_user)
    # Phase 0A.3: structured path — inject policy signals into state
    state["policy_path"] = decision.path.value
    state["result_form"] = decision.result_form.value
    # Phase 0A QW-4: V3 spec fields
    state["inquiry_id"] = request.session_id
    state.setdefault("turn_count", 0)
    state.setdefault("max_turns", 12)
    updated_state = await execute_agent(state)
    last_msg = [m for m in updated_state["messages"] if isinstance(m, AIMessage)][-1]
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
async def chat_route(request: ChatRequest, current_user: RequestUser = Depends(get_current_request_user)):
    return await chat_endpoint(request, current_user=current_user)


@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    return StreamingResponse(event_generator(request), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# HITL Review — Blueprint Sections 08 & 12
# ---------------------------------------------------------------------------

def _find_session(session_id: str) -> AgentState | None:
    """Look up a session from SESSION_STORE by plain or composite key."""
    if session_id in SESSION_STORE:
        return SESSION_STORE[session_id]
    # Composite key used by authenticated path: "tenant_id:owner_id:session_id"
    for key, state in SESSION_STORE.items():
        if key.endswith(f":{session_id}"):
            return state
    return None


def _save_session(session_id: str, state: AgentState) -> None:
    """Write back into the same SESSION_STORE slot the state was loaded from."""
    if session_id in SESSION_STORE:
        SESSION_STORE[session_id] = state
        return
    for key in list(SESSION_STORE.keys()):
        if key.endswith(f":{session_id}"):
            SESSION_STORE[key] = state
            return
    SESSION_STORE[session_id] = state


def _apply_review_decision(state: AgentState, request: ReviewRequest) -> AgentState:
    """Return a deep-copied state with governance, review and selection layers patched.

    Does NOT call the LLM or any external service — purely deterministic.
    The cycle revision is advanced so concurrent writes are detectable.
    """
    patched = deepcopy(state)
    sealing_state: dict = patched["sealing_state"]

    governance = dict(sealing_state.get("governance") or {})
    review = dict(sealing_state.get("review") or {})
    selection = dict(sealing_state.get("selection") or {})
    now_iso = datetime.now(timezone.utc).isoformat()

    if request.action == "approve":
        # Governance
        governance["release_status"] = "rfq_ready"
        governance["rfq_admissibility"] = "ready"
        # Review lifecycle
        review["review_required"] = False
        review["review_state"] = "approved"
        review["reviewed_by"] = "reviewer"
        review["review_decision"] = "approved"
        review["review_note"] = request.reviewer_notes or ""
        review["reviewed_at"] = now_iso
        # Selection projection — keep aligned with governance so build_final_reply
        # can produce a meaningful response (not just SAFEGUARDED_WITHHELD_REPLY).
        selection["release_status"] = "rfq_ready"
        selection["rfq_admissibility"] = "ready"
        selection["output_blocked"] = False
        selection.setdefault("specificity_level", "compound_required")
        artifact = dict(selection.get("recommendation_artifact") or {})
        if artifact:
            artifact["release_status"] = "rfq_ready"
            artifact["rfq_admissibility"] = "ready"
            artifact["output_blocked"] = False
            selection["recommendation_artifact"] = artifact

    elif request.action == "reject":
        governance["release_status"] = "inadmissible"
        governance["rfq_admissibility"] = "inadmissible"
        review["review_required"] = False
        review["review_state"] = "rejected"
        review["reviewed_by"] = "reviewer"
        review["review_decision"] = "rejected"
        review["review_note"] = request.reviewer_notes or ""
        review["reviewed_at"] = now_iso

    sealing_state["governance"] = governance
    sealing_state["review"] = review
    sealing_state["selection"] = selection

    # Advance revision so optimistic-locking checks remain valid
    cycle = dict(sealing_state.get("cycle") or {})
    current_rev = int(cycle.get("state_revision", 0) or 0)
    cycle["state_revision"] = current_rev + 1
    cycle["snapshot_parent_revision"] = current_rev
    cycle["analysis_cycle_id"] = (
        f"{cycle.get('analysis_cycle_id') or request.session_id}"
        f"::review::{request.action}::{uuid.uuid4().hex[:8]}"
    )
    sealing_state["cycle"] = cycle
    patched["sealing_state"] = sealing_state
    return patched


@router.post("/review", response_model=ReviewResponse)
async def review_endpoint(request: ReviewRequest) -> ReviewResponse:
    """HITL resume — apply a reviewer decision to a pending review session.

    Blueprint Section 08 & 12: the graph is NOT re-invoked end-to-end.
    Instead the state is patched deterministically and then routed through
    final_response_node only, so the handover object is computed and the
    audit log is written without re-running LLM reasoning.
    """
    # 1. Load session
    state = _find_session(request.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Session '{request.session_id}' not found")

    # 2. Guard: only process sessions that have a pending review
    sealing_state: dict = state.get("sealing_state") or {}
    review_layer: dict = sealing_state.get("review") or {}
    if not review_layer.get("review_required"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"No pending review for session '{request.session_id}'. "
                f"Current review_state='{review_layer.get('review_state', 'none')}'"
            ),
        )

    # 3. Patch state with reviewer decision (deterministic, no LLM)
    patched_state = _apply_review_decision(state, request)

    # 4. Run final_response_node directly — computes handover + fires audit log
    node_result = await final_response_node(patched_state)

    # 5. Merge node output back into state and persist to SESSION_STORE
    patched_state["sealing_state"] = node_result["sealing_state"]
    existing_msgs = list(patched_state.get("messages") or [])
    patched_state["messages"] = existing_msgs + list(node_result.get("messages") or [])
    _save_session(request.session_id, patched_state)

    # 6. Build response
    final_sealing: dict = patched_state["sealing_state"]
    final_governance: dict = final_sealing.get("governance") or {}
    final_review: dict = final_sealing.get("review") or {}
    handover: dict | None = final_sealing.get("handover")
    last_ai_msgs = [m for m in node_result.get("messages") or [] if isinstance(m, AIMessage)]
    reply_text = last_ai_msgs[-1].content if last_ai_msgs else ""

    return ReviewResponse(
        session_id=request.session_id,
        action=request.action,
        review_state=str(final_review.get("review_state", "")),
        release_status=str(final_governance.get("release_status", "")),
        is_handover_ready=bool((handover or {}).get("is_handover_ready", False)),
        handover=handover,
        reply=reply_text,
    )


@router.post("/review/seed", response_model=ReviewSeedResponse)
async def review_seed_endpoint() -> ReviewSeedResponse:
    """Test-only: inject a review-pending session into SESSION_STORE.

    Creates a deterministic AgentState with:
    - governance.release_status = "manufacturer_validation_required"
    - review.review_required = True / review_state = "pending"
    - A minimal but valid selection layer

    Returns the generated session_id so the test script can call POST /review.
    """
    from app.agent.agent.review import REASON_MANUFACTURER_VALIDATION
    from app.agent.cli import create_initial_state

    session_id = f"hitl-test-{uuid.uuid4().hex[:12]}"
    sealing_state = create_initial_state()

    # Asserted signal so governance does not fall back to "precheck_only"
    sealing_state["asserted"] = {
        "medium_profile": {"medium": "water", "medium_raw": "Wasser"},
        "machine_profile": {"shaft_diameter_mm": 50.0, "rpm": 3000},
        "installation_profile": {},
        "operating_conditions": {"pressure_bar": 8.0, "temperature_c": 60.0},
        "sealing_requirement_spec": {},
    }

    # Governance: manufacturer validation required (unknowns present but not blocking)
    sealing_state["governance"] = {
        "release_status": "manufacturer_validation_required",
        "rfq_admissibility": "provisional",
        "specificity_level": "compound_required",
        "scope_of_validity": ["manufacturer_validation_scope"],
        "assumptions_active": [],
        "gate_failures": [],
        "unknowns_release_blocking": [],
        "unknowns_manufacturer_validation": ["Compound-Validierung durch Hersteller erforderlich"],
        "conflicts": [],
    }

    # Review layer: pending
    sealing_state["review"] = {
        "review_required": True,
        "review_state": "pending",
        "review_reason": REASON_MANUFACTURER_VALIDATION,
        "reviewed_by": None,
        "review_decision": None,
        "review_note": None,
    }

    # Selection layer aligned with governance (needed by build_final_reply)
    candidate_id = "candidate_FKM_compound_required"
    artifact = {
        "selection_status": "viable_candidate_found",
        "winner_candidate_id": candidate_id,
        "candidate_ids": [candidate_id],
        "viable_candidate_ids": [candidate_id],
        "blocked_candidates": [],
        "evidence_basis": ["seed_data"],
        "release_status": "manufacturer_validation_required",
        "rfq_admissibility": "provisional",
        "specificity_level": "compound_required",
        "output_blocked": True,
        "trace_provenance_refs": [],
    }
    sealing_state["selection"] = {
        "selection_status": "viable_candidate_found",
        "candidates": [],
        "viable_candidate_ids": [candidate_id],
        "blocked_candidates": [],
        "winner_candidate_id": candidate_id,
        "recommendation_artifact": artifact,
        "release_status": "manufacturer_validation_required",
        "rfq_admissibility": "provisional",
        "specificity_level": "compound_required",
        "output_blocked": True,
    }

    sealing_state["cycle"]["analysis_cycle_id"] = f"session_{session_id}_1"

    agent_state: AgentState = {
        "messages": [HumanMessage(content="Ich brauche eine Dichtung: Welle 50mm, 3000 rpm, Wasser, 8 bar.")],
        "sealing_state": sealing_state,
        "working_profile": {
            "shaft_diameter_mm": 50.0,
            "rpm": 3000,
            "medium": "water",
            "pressure_bar": 8.0,
        },
        "relevant_fact_cards": [],
        "tenant_id": None,
        "turn_count": 1,
        "max_turns": 12,
        "inquiry_id": session_id,
    }
    SESSION_STORE[session_id] = agent_state

    return ReviewSeedResponse(
        session_id=session_id,
        review_state="pending",
        release_status="manufacturer_validation_required",
        review_reason=REASON_MANUFACTURER_VALIDATION,
    )


app_api = FastAPI(title="SealAI LangGraph PoC API")
app_api.include_router(router)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app_api.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
