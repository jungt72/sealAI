import logging
import os
import json
import uuid
from copy import deepcopy
import dataclasses
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Literal, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage
from app.api.v1.projections.case_workspace import (
    project_case_workspace_from_governed_state,
    project_case_workspace_from_ssot,
)
from app.api.v1.renderers.rfq_html import render_rfq_html
from app.api.v1.schemas.case_workspace import CaseWorkspaceProjection

from app.agent.graph.legacy_graph import app, final_response_node, _GRAPH_MODEL_ID, VISIBLE_REPLY_PROMPT_HASH, VISIBLE_REPLY_PROMPT_VERSION
from app.agent.manufacturers.commercial import (
    build_dispatch_bridge,
    build_dispatch_dry_run,
    build_dispatch_event,
    build_dispatch_handoff,
    build_dispatch_transport_envelope,
    build_dispatch_trigger,
    build_handover_payload,
)
from app.agent.api.sse_runtime import agent_sse_generator
from app.agent.runtime.selection import build_final_reply, build_structured_api_exposure
from app.agent.prompts import REASONING_PROMPT_HASH, REASONING_PROMPT_VERSION
from app.agent.state.agent_state import AgentState
from app.agent.api.models import (
    CaseListItemResponse,
    CaseMetadataResponse,
    ChatRequest,
    ChatResponse,
    GovernedSnapshotResponse,
    GovernedSnapshotRevisionListItemResponse,
    OverrideRequest,
    OverrideResponse,
    OverrideGovernanceResult,
    ReviewRequest,
    ReviewResponse,
    ReviewSeedResponse,
    build_public_response_core,
)
from app.agent.graph.nodes.output_contract_node import (
    _determine_response_class,
    build_governed_conversation_strategy_contract,
)
from app.agent.state.models import (
    ConversationMessage,
    GovernedSessionState,
    ObservedExtraction,
    TurnContextContract,
    UserOverride,
)
from app.agent.runtime.reply_composition import (
    GovernedAllowedSurfaceClaims,
    compose_clarification_reply,
    compose_result_reply,
)
from app.agent.runtime.outward_names import (
    build_admissibility_payload,
    normalize_outward_response_class,
)
from app.agent.runtime.surface_claims import get_surface_claims_spec
from app.agent.runtime.turn_context import build_governed_turn_context
from app.agent.runtime.user_facing_reply import (
    assemble_user_facing_reply,
    collect_governed_visible_reply,
)
from app.agent.state.projections import project_for_ui
from app.agent.state.medium_derivation import (
    derive_medium_capture,
    derive_medium_classification,
)
from app.agent.state.persistence import (
    get_case_by_number_async,
    get_governed_case_snapshot_by_revision_async,
    get_latest_governed_case_snapshot_async,
    get_or_create_governed_state_async,
    list_cases_async,
    list_governed_case_snapshots_async,
    load_governed_state_async,
    save_governed_state_snapshot_async,
    save_governed_state_async,
)
from app.agent.state.reducers import (
    determine_changed_parameter_fields,
    invalidate_downstream,
    reduce_observed_to_normalized,
    reduce_normalized_to_asserted,
    reduce_asserted_to_governance,
)
from app.agent.services.medium_context import MediumContext, normalize_medium_context_key, resolve_medium_context
from app.agent.graph import GraphState
from app.agent.graph.topology import GOVERNED_GRAPH
from app.agent.runtime.response_renderer import render_response
from prompts.builder import PromptBuilder

_prompt_builder = PromptBuilder()
from app.agent.state.case_state import (
    CASE_STATE_BUILDER_VERSION,
    DETERMINISTIC_DATA_VERSION,
    DETERMINISTIC_SERVICE_VERSION,
    PROJECTION_VERSION,
    build_dispatch_intent,
    build_visible_case_narrative,
    ensure_case_state,
    resolve_next_step_contract,
)
from app.agent.domain.critical_review import (
    CriticalReviewGovernanceSummary,
    CriticalReviewMatchingPackage,
    CriticalReviewRecommendationPackage,
    CriticalReviewRfqBasis,
    CriticalReviewSpecialistInput,
    critical_review_result_to_dict,
    run_critical_review_specialist,
)
from app.agent.cli import create_initial_state
from app.services.auth.dependencies import RequestUser, canonical_user_id, get_current_request_user
from app.services.history.persist import ConcurrencyConflictError, load_structured_case, save_structured_case

router = APIRouter()
SESSION_STORE: Dict[str, AgentState] = {}

_log = logging.getLogger(__name__)
_RESIDUAL_LEGACY_RUNTIME_LABEL = "residual_legacy_compat_only"
_LIGHT_HISTORY_MESSAGES = 20


@dataclass(frozen=True)
class GovernedReplyAssemblyContext:
    response_class: str
    structured_state: dict[str, Any] | None
    assertions_payload: dict[str, Any]
    conversation_strategy: Any
    turn_context: TurnContextContract
    run_meta: dict[str, Any]
    ui_payload: dict[str, Any]
    deterministic_reply: str
    domain_context: dict[str, Any] = dataclasses.field(default_factory=dict)


def _conversation_message_payload(
    *,
    role: Literal["user", "assistant"],
    content: str,
) -> ConversationMessage | None:
    text = str(content or "").strip()
    if not text:
        return None
    return ConversationMessage(
        role=role,
        content=text,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _with_governed_conversation_turn(
    state: GovernedSessionState,
    *,
    user_message: str,
    assistant_reply: str,
) -> GovernedSessionState:
    additions: list[ConversationMessage] = []
    user_entry = _conversation_message_payload(role="user", content=user_message)
    assistant_entry = _conversation_message_payload(role="assistant", content=assistant_reply)
    if user_entry is not None:
        additions.append(user_entry)
    if assistant_entry is not None:
        additions.append(assistant_entry)
    if not additions:
        return state
    return state.model_copy(update={"conversation_messages": state.conversation_messages + additions})


def _governed_history_slice(
    state: GovernedSessionState,
    *,
    limit: int = _LIGHT_HISTORY_MESSAGES,
) -> list[dict[str, str]]:
    messages = list(state.conversation_messages or [])
    if limit > 0:
        messages = messages[-limit:]
    history: list[dict[str, str]] = []
    for item in messages:
        role = str(item.role or "").strip()
        content = str(item.content or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        history.append({"role": role, "content": content})
    return history


async def _load_live_governed_state(
    *,
    current_user: RequestUser,
    session_id: str,
    create_if_missing: bool = False,
) -> GovernedSessionState | None:
    tenant_id, _, _ = _canonical_scope(current_user, case_id=session_id)
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return GovernedSessionState() if create_if_missing else None
    from redis.asyncio import Redis as AsyncRedis  # noqa: PLC0415

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
    redis_client: object | None = None,
) -> None:
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=session_id)
    if redis_client is not None:
        await save_governed_state_async(
            state,
            tenant_id=tenant_id,
            session_id=session_id,
            redis_client=redis_client,
        )
    else:
        redis_url = os.getenv("REDIS_URL", "")
        if redis_url:
            from redis.asyncio import Redis as AsyncRedis  # noqa: PLC0415

            async with AsyncRedis.from_url(redis_url, decode_responses=True) as managed_redis_client:
                await save_governed_state_async(
                    state,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    redis_client=managed_redis_client,
                )
    await save_governed_state_snapshot_async(
        state,
        case_number=session_id,
        user_id=owner_id,
    )


async def _build_light_runtime_context(
    *,
    request: ChatRequest,
    current_user: RequestUser,
    governed_state_override: GovernedSessionState | None = None,
) -> tuple[GovernedSessionState | None, list[dict[str, str]], Optional[str]]:
    if not request.session_id:
        return None, [], None
    governed = governed_state_override
    if governed is None:
        try:
            governed = await _load_live_governed_state(
                current_user=current_user,
                session_id=request.session_id,
                create_if_missing=True,
            )
        except Exception as exc:  # noqa: BLE001
            _log.debug("[router] live governed context load skipped: %s", exc)
            return None, [], None
    if governed is None:
        return None, [], None
    history = _governed_history_slice(governed)
    case_summary = _build_light_case_summary(governed)
    return governed, history, case_summary


def _serialize_governed_history_payload(
    *,
    conversation_id: str,
    governed_state: GovernedSessionState,
) -> dict[str, Any]:
    messages = []
    for index, item in enumerate(governed_state.conversation_messages):
        role = str(item.role or "").strip()
        content = str(item.content or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        messages.append(
            {
                "id": item.created_at or f"governed-{index}",
                "role": role,
                "content": content,
                "createdAt": item.created_at or datetime.now(timezone.utc).isoformat(),
                "index": index,
            }
        )
    return {
        "conversation_id": conversation_id,
        "title": None,
        "updated_at": (
            messages[-1]["createdAt"] if messages else datetime.now(timezone.utc).isoformat()
        ),
        "messages": messages,
    }


def _governed_working_profile_snapshot(state: GovernedSessionState) -> dict[str, Any]:
    profile: dict[str, Any] = {}
    for field_name, claim in state.asserted.assertions.items():
        if claim.asserted_value is None:
            continue
        profile[field_name] = claim.asserted_value
    motion_label = getattr(state.motion_hint, "label", None)
    if motion_label in {"rotary", "linear", "static"}:
        profile["movement_type"] = motion_label
    application_label = getattr(state.application_hint, "label", None)
    if application_label:
        profile["application_context"] = application_label
    return profile


def _governed_messages_as_langchain(
    state: GovernedSessionState,
) -> list[HumanMessage | AIMessage]:
    messages: list[HumanMessage | AIMessage] = []
    for item in state.conversation_messages:
        role = str(item.role or "").strip()
        content = str(item.content or "").strip()
        if role == "user" and content:
            messages.append(HumanMessage(content=content))
        elif role == "assistant" and content:
            messages.append(AIMessage(content=content))
    return messages


def _governed_release_status_snapshot(state: GovernedSessionState) -> str:
    if state.rfq.rfq_ready or (state.governance.rfq_admissible and state.rfq.critical_review_passed):
        return "inquiry_ready"
    if state.matching.status == "matched_primary_candidate" or state.governance.gov_class == "A":
        return "manufacturer_validation_required"
    if state.governance.gov_class == "B":
        return "precheck_only"
    return "inadmissible"


def _overlay_live_governed_snapshot(
    *,
    state: AgentState,
    governed_state: GovernedSessionState,
) -> AgentState:
    patched: AgentState = deepcopy(state)

    governed_messages = _governed_messages_as_langchain(governed_state)
    if governed_messages:
        patched["messages"] = governed_messages

    governed_profile = _governed_working_profile_snapshot(governed_state)
    if governed_profile:
        patched["working_profile"] = governed_profile

    release_status = _governed_release_status_snapshot(governed_state)
    review_layer = dict(((patched.get("sealing_state") or {}).get("review") or {}))
    review_required = bool(review_layer.get("review_required", False))
    review_state = review_layer.get("review_state")

    case_state = dict(patched.get("case_state") or {})
    governance_state = dict(case_state.get("governance_state") or {})
    governance_state.update(
        {
            "release_status": release_status,
            "rfq_admissibility": "ready" if governed_state.governance.rfq_admissible else "inadmissible",
            "unknowns_release_blocking": list(governed_state.asserted.blocking_unknowns),
            "unknowns_manufacturer_validation": list(governed_state.governance.open_validation_points),
            "scope_of_validity": list(governed_state.governance.validity_limits),
            "critical_review_status": governed_state.rfq.critical_review_status,
            "critical_review_passed": governed_state.rfq.critical_review_passed,
            "blocking_findings": list(governed_state.rfq.blocking_findings),
            "soft_findings": list(governed_state.rfq.soft_findings),
            "required_corrections": list(governed_state.rfq.required_corrections),
        }
    )
    governance_state["review_required"] = review_required
    if review_state is not None:
        governance_state["review_state"] = review_state
    case_state["governance_state"] = governance_state

    rfq_state = dict(case_state.get("rfq_state") or {})
    rfq_state.update(
        {
            "status": governed_state.rfq.status,
            "rfq_admissibility": "ready" if governed_state.rfq.rfq_admissible else "inadmissible",
            "rfq_ready": governed_state.rfq.rfq_ready,
            "handover_ready": governed_state.rfq.rfq_ready,
            "handover_status": governed_state.rfq.handover_status,
            "rfq_object": dict(governed_state.rfq.rfq_object or {}),
            "critical_review_status": governed_state.rfq.critical_review_status,
            "critical_review_passed": governed_state.rfq.critical_review_passed,
            "blocking_findings": list(governed_state.rfq.blocking_findings),
            "soft_findings": list(governed_state.rfq.soft_findings),
            "required_corrections": list(governed_state.rfq.required_corrections),
        }
    )
    case_state["rfq_state"] = rfq_state
    patched["case_state"] = case_state

    sealing_state = dict(patched.get("sealing_state") or {})
    sealing_governance = dict(sealing_state.get("governance") or {})
    sealing_governance.update(
        {
            "release_status": release_status,
            "rfq_admissibility": "ready" if governed_state.governance.rfq_admissible else "inadmissible",
            "scope_of_validity": list(governed_state.governance.validity_limits),
            "unknowns_release_blocking": list(governed_state.asserted.blocking_unknowns),
            "unknowns_manufacturer_validation": list(governed_state.governance.open_validation_points),
        }
    )
    sealing_state["governance"] = sealing_governance
    review_layer.update(
        {
            "critical_review_status": governed_state.rfq.critical_review_status,
            "critical_review_passed": governed_state.rfq.critical_review_passed,
            "blocking_findings": list(governed_state.rfq.blocking_findings),
            "soft_findings": list(governed_state.rfq.soft_findings),
            "required_corrections": list(governed_state.rfq.required_corrections),
        }
    )
    sealing_state["review"] = review_layer
    patched["sealing_state"] = sealing_state
    return patched


def _sync_governed_state_from_review_outcome(
    governed_state: GovernedSessionState,
    *,
    case_state: dict[str, Any] | None,
    sealing_state: dict[str, Any] | None,
) -> GovernedSessionState:
    case_state = dict(case_state or {})
    sealing_state = dict(sealing_state or {})
    governance_state = dict(case_state.get("governance_state") or {})
    rfq_state = dict(case_state.get("rfq_state") or {})
    review_state = dict(sealing_state.get("review") or {})
    handover = dict(sealing_state.get("handover") or {})
    requirement_class_payload = (
        case_state.get("requirement_class")
        or (case_state.get("result_contract") or {}).get("requirement_class")
        or (rfq_state.get("requirement_class") or {})
    )
    selected_manufacturer_ref = (
        rfq_state.get("selected_manufacturer_ref")
        or handover.get("selected_manufacturer_ref")
        or (case_state.get("matching_state") or {}).get("selected_manufacturer_ref")
    )
    dispatch_intent = dict(case_state.get("dispatch_intent") or {})

    updated_governance = governed_state.governance.model_copy(
        update={
            "requirement_class": requirement_class_payload or governed_state.governance.requirement_class,
            "rfq_admissible": str(
                governance_state.get("rfq_admissibility")
                or rfq_state.get("rfq_admissibility")
                or "inadmissible"
            ) == "ready",
            "validity_limits": list(
                governance_state.get("scope_of_validity")
                or governed_state.governance.validity_limits
            ),
            "open_validation_points": list(
                governance_state.get("unknowns_manufacturer_validation")
                or governed_state.governance.open_validation_points
            ),
        }
    )

    updated_rfq = governed_state.rfq.model_copy(
        update={
            "status": str(rfq_state.get("handover_status") or rfq_state.get("status") or governed_state.rfq.status),
            "rfq_admissible": str(governance_state.get("rfq_admissibility") or rfq_state.get("rfq_admissibility") or "inadmissible") == "ready",
            "critical_review_status": str(
                governance_state.get("critical_review_status")
                or rfq_state.get("critical_review_status")
                or review_state.get("review_state")
                or governed_state.rfq.critical_review_status
            ),
            "critical_review_passed": bool(
                governance_state.get("critical_review_passed", rfq_state.get("critical_review_passed", governed_state.rfq.critical_review_passed))
            ),
            "blocking_findings": list(
                governance_state.get("blocking_findings")
                or rfq_state.get("blocking_findings")
                or review_state.get("blocking_findings")
                or governed_state.rfq.blocking_findings
            ),
            "soft_findings": list(
                governance_state.get("soft_findings")
                or rfq_state.get("soft_findings")
                or review_state.get("soft_findings")
                or governed_state.rfq.soft_findings
            ),
            "required_corrections": list(
                governance_state.get("required_corrections")
                or rfq_state.get("required_corrections")
                or review_state.get("required_corrections")
                or governed_state.rfq.required_corrections
            ),
            "handover_status": str(rfq_state.get("handover_status") or handover.get("handover_status") or governed_state.rfq.handover_status or ""),
            "rfq_ready": bool(rfq_state.get("handover_ready", rfq_state.get("rfq_ready", handover.get("is_handover_ready", governed_state.rfq.rfq_ready)))),
            "rfq_object": dict(rfq_state.get("rfq_object") or governed_state.rfq.rfq_object or {}),
            "selected_manufacturer_ref": selected_manufacturer_ref or governed_state.rfq.selected_manufacturer_ref,
            "requirement_class": requirement_class_payload or governed_state.rfq.requirement_class,
            "handover_summary": str(handover.get("handover_reason") or governed_state.rfq.handover_summary or ""),
            "notes": list(rfq_state.get("notes") or governed_state.rfq.notes),
        }
    )
    updated_dispatch = governed_state.dispatch.model_copy(
        update={
            "dispatch_ready": bool(
                dispatch_intent.get("dispatch_ready", handover.get("is_handover_ready", governed_state.dispatch.dispatch_ready))
            ),
            "dispatch_status": str(
                dispatch_intent.get("dispatch_status")
                or handover.get("handover_status")
                or governed_state.dispatch.dispatch_status
            ),
            "selected_manufacturer_ref": selected_manufacturer_ref or governed_state.dispatch.selected_manufacturer_ref,
            "requirement_class": requirement_class_payload or governed_state.dispatch.requirement_class,
            "handover_summary": str(handover.get("handover_reason") or governed_state.dispatch.handover_summary or ""),
            "dispatch_notes": list(dispatch_intent.get("dispatch_blockers") or governed_state.dispatch.dispatch_notes),
        }
    )
    return governed_state.model_copy(
        update={
            "governance": updated_governance,
            "rfq": updated_rfq,
            "dispatch": updated_dispatch,
        }
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
        _log.debug("[router] review governed sync load skipped: %s", exc)
        return
    if governed_state is None:
        return
    updated = _sync_governed_state_from_review_outcome(
        governed_state,
        case_state=case_state,
        sealing_state=sealing_state,
    )
    if assistant_reply:
        updated = _with_governed_conversation_turn(
            updated,
            user_message="",
            assistant_reply=assistant_reply,
        )
    await _persist_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        state=updated,
    )


def _current_governed_medium_label(state: GraphState) -> str | None:
    classification_label = str(state.medium_classification.canonical_label or "").strip()
    if classification_label:
        return classification_label
    asserted_medium = state.asserted.assertions.get("medium")
    if asserted_medium is not None and asserted_medium.asserted_value is not None:
        text = str(asserted_medium.asserted_value).strip()
        if text:
            return text
    normalized_medium = state.normalized.parameters.get("medium")
    if normalized_medium is not None and normalized_medium.value is not None:
        text = str(normalized_medium.value).strip()
        if text:
            return text
    return None


def _enrich_medium_context_state(
    *,
    result_state: GraphState,
    persisted_state: GovernedSessionState,
) -> tuple[GraphState, GovernedSessionState]:
    medium_label = _current_governed_medium_label(result_state)
    medium_family = (
        str(result_state.medium_classification.family or "").strip()
        if result_state.medium_classification.status in {"recognized", "family_only"}
        else None
    )
    medium_key = normalize_medium_context_key(medium_label)
    if not medium_key and not medium_family:
        empty_context = MediumContext()
        return (
            result_state.model_copy(update={"medium_context": empty_context}),
            persisted_state.model_copy(update={"medium_context": empty_context}),
        )

    existing_context = persisted_state.medium_context
    resolved_context = resolve_medium_context(
        medium_label,
        medium_family=medium_family,
        previous=existing_context,
    )

    return (
        result_state.model_copy(update={"medium_context": resolved_context}),
        persisted_state.model_copy(update={"medium_context": resolved_context}),
    )

# ---------------------------------------------------------------------------
# Phase F Feature-Flags — read once at import time from environment.
# Both default to True so the productive chat path uses the new runtime by
# default. Rollback: set to "false" in env, no code deployment needed.
# ---------------------------------------------------------------------------
_ENABLE_BINARY_GATE: bool = (
    os.environ.get("SEALAI_ENABLE_BINARY_GATE", "true").lower() == "true"
)
_ENABLE_CONVERSATION_RUNTIME: bool = (
    os.environ.get("SEALAI_ENABLE_CONVERSATION_RUNTIME", "true").lower() == "true"
)
_ENABLE_GOVERNED_REDUCERS: bool = (
    # Phase F-B.4: run reducer chain + Redis persist in the GOVERNED chat path.
    # Safe rollout: set SEALAI_ENABLE_GOVERNED_REDUCERS=true in env.
    # Rollback: set to "false" — no code deployment needed.
    os.environ.get("SEALAI_ENABLE_GOVERNED_REDUCERS", "false").lower() == "true"
)


@dataclass(frozen=True)
class RuntimeDispatchResolution:
    gate_route: Literal["CONVERSATION", "EXPLORATION", "GOVERNED"]
    gate_reason: str
    runtime_mode: Literal["CONVERSATION", "EXPLORATION", "GOVERNED"]
    gate_applied: bool
    session_zone: str | None = None
    direct_reply: str | None = None
    governed_state: GovernedSessionState | None = None


async def execute_agent(state: AgentState) -> AgentState:
    """Residual compat helper for legacy/unauthenticated flows only."""
    _log.warning(
        "[%s] execute_agent invoked policy_path=%s inquiry_id=%s",
        _RESIDUAL_LEGACY_RUNTIME_LABEL,
        state.get("policy_path"),
        state.get("inquiry_id") or state.get("session_id"),
    )
    return await app.ainvoke(state)


async def _resolve_runtime_dispatch(
    request: ChatRequest,
    *,
    current_user: RequestUser | None,
) -> RuntimeDispatchResolution:
    if current_user is None:
        return RuntimeDispatchResolution(
            gate_route="GOVERNED",
            gate_reason="missing_current_user",
            runtime_mode="GOVERNED",
            gate_applied=False,
        )

    if not _ENABLE_BINARY_GATE:
        return RuntimeDispatchResolution(
            gate_route="GOVERNED",
            gate_reason="binary_gate_disabled",
            runtime_mode="GOVERNED",
            gate_applied=False,
        )

    try:
        from redis.asyncio import Redis as AsyncRedis  # noqa: PLC0415
        from app.agent.runtime.gate import decide_route_async  # noqa: PLC0415
        from app.agent.runtime.session_manager import (  # noqa: PLC0415
            apply_gate_decision_and_persist_async,
            get_or_create_session_async,
        )

        redis_url = os.getenv("REDIS_URL", "")
        tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=request.session_id)
        governed_state = None
        if request.session_id:
            governed_state = await _load_live_governed_state(
                current_user=current_user,
                session_id=request.session_id,
                create_if_missing=True,
            )
        short_state_summary = _build_light_case_summary(governed_state) if governed_state is not None else None
        missing_critical_fields = _collect_light_missing_fields(governed_state) if governed_state is not None else []
        case_active = _light_case_active(governed_state) if governed_state is not None else False
        last_route = (
            str(governed_state.exploration_progress.last_route or "").strip() or None
            if governed_state is not None
            else None
        )

        async with AsyncRedis.from_url(redis_url, decode_responses=True) as redis_client:
            envelope = await get_or_create_session_async(
                tenant_id,
                request.session_id,
                owner_id,
                redis_client=redis_client,
            )
            gate = await decide_route_async(
                request.message,
                envelope,
                short_state_summary=short_state_summary,
                missing_critical_fields=missing_critical_fields,
                case_active=case_active,
                last_route=last_route,
            )
            updated_envelope = await apply_gate_decision_and_persist_async(
                envelope,
                gate_route=gate.route,
                gate_reason=gate.reason,
                redis_client=redis_client,
            )

        runtime_mode: Literal["CONVERSATION", "EXPLORATION", "GOVERNED"] = (
            gate.route
            if _ENABLE_CONVERSATION_RUNTIME and gate.route in {"CONVERSATION", "EXPLORATION"}
            else "GOVERNED"
        )
        _log.debug(
            "[runtime_dispatch] gate=%s reason=%s session_zone=%s runtime_mode=%s",
            gate.route,
            gate.reason,
            updated_envelope.session_zone,
            runtime_mode,
        )
        return RuntimeDispatchResolution(
            gate_route=gate.route,
            gate_reason=gate.reason,
            runtime_mode=runtime_mode,
            gate_applied=True,
            session_zone=updated_envelope.session_zone,
            direct_reply=gate.direct_reply,
            governed_state=governed_state,
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "[runtime_dispatch] gate/session resolution failed (%s: %s) — fail-open to governed",
            type(exc).__name__,
            exc,
        )
        return RuntimeDispatchResolution(
            gate_route="GOVERNED",
            gate_reason=f"gate_session_fail_open:{type(exc).__name__}",
            runtime_mode="GOVERNED",
            gate_applied=False,
        )


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


def _canonical_scope(current_user: RequestUser, *, case_id: str) -> tuple[str, str, str]:
    owner_id = canonical_user_id(current_user)
    tenant_id = current_user.tenant_id or owner_id
    return tenant_id, owner_id, _case_cache_key(tenant_id, owner_id, case_id)


def _canonical_case_token(state: AgentState) -> dict[str, Any]:
    case_meta = dict(((state.get("case_state") or {}).get("case_meta") or {}))
    cycle = dict(((state.get("sealing_state") or {}).get("cycle") or {}))
    return {
        "state_revision": case_meta.get("state_revision")
        if case_meta.get("state_revision") is not None
        else cycle.get("state_revision"),
        "snapshot_parent_revision": case_meta.get("snapshot_parent_revision")
        if case_meta.get("snapshot_parent_revision") is not None
        else cycle.get("snapshot_parent_revision"),
        "analysis_cycle_id": case_meta.get("analysis_cycle_id")
        if case_meta.get("analysis_cycle_id") is not None
        else cycle.get("analysis_cycle_id"),
    }


def _canonical_state_revision(state: AgentState) -> int:
    token = _canonical_case_token(state)
    return int(token.get("state_revision", 0) or 0)


def _cache_loaded_state(
    *,
    state: AgentState,
    current_user: RequestUser,
    session_id: str,
) -> AgentState:
    tenant_id, owner_id, cache_key = _canonical_scope(current_user, case_id=session_id)
    state["owner_id"] = owner_id
    state["tenant_id"] = tenant_id
    state["loaded_state_revision"] = _canonical_state_revision(state)
    SESSION_STORE[cache_key] = state
    return state


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
    token = _canonical_case_token(updated_state)
    sealing_state = dict(updated_state.get("sealing_state") or {})
    cycle = dict(sealing_state.get("cycle") or {})
    current_revision = int(token.get("state_revision", 0) or 0)
    next_revision = current_revision + 1
    next_cycle_id = f"{token.get('analysis_cycle_id') or case_id}::{write_scope}::rev{next_revision}::{uuid.uuid4().hex[:8]}"
    if updated_state.get("case_state"):
        case_state = dict(updated_state["case_state"])
        for section in ("case_meta", "result_contract", "sealing_requirement_spec"):
            if isinstance(case_state.get(section), dict):
                entry = dict(case_state[section])
                entry["snapshot_parent_revision"] = current_revision
                entry["state_revision"] = next_revision
                entry["analysis_cycle_id"] = next_cycle_id
                if section == "case_meta":
                    entry["version"] = next_revision
                case_state[section] = entry
        updated_state["case_state"] = case_state
    cycle["snapshot_parent_revision"] = current_revision
    cycle["state_revision"] = next_revision
    cycle["analysis_cycle_id"] = next_cycle_id
    sealing_state["cycle"] = cycle
    updated_state["sealing_state"] = sealing_state
    return updated_state


# ---------------------------------------------------------------------------
# Residual structured/canonical surface
# ---------------------------------------------------------------------------
# Active residual truth:
# - load_structured_residual_state(...)
# - require_structured_residual_state(...)
# - persist_structured_residual_commit(...)
#
# Explicit residual special-case entry points:
# - load/require_structured_handover_state(...)
# - load/require_structured_review_state(...)
# - persist_structured_review_commit(...)
#
# Normal governed authority remains Redis live state + Postgres governed snapshots.


async def load_structured_residual_state(
    *,
    current_user: RequestUser,
    session_id: str,
) -> AgentState | None:
    """Residual structured read core for non-governed fallback and special cases."""
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=session_id)
    state = await load_structured_case(tenant_id=tenant_id, owner_id=owner_id, case_id=session_id)
    if state is None:
        return None
    governed_state = await _load_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        create_if_missing=False,
    )
    if governed_state is not None:
        state = _overlay_live_governed_snapshot(
            state=state,
            governed_state=governed_state,
        )
    return _cache_loaded_state(state=state, current_user=current_user, session_id=session_id)


async def require_structured_residual_state(
    *,
    current_user: RequestUser,
    session_id: str,
) -> AgentState:
    state = await load_structured_residual_state(
        current_user=current_user,
        session_id=session_id,
    )
    if state is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return state


async def load_structured_handover_state(
    *,
    current_user: RequestUser,
    session_id: str,
) -> AgentState | None:
    """Residual structured read reserved for RFQ/handover special cases."""
    return await load_structured_residual_state(
        current_user=current_user,
        session_id=session_id,
    )


async def require_structured_handover_state(
    *,
    current_user: RequestUser,
    session_id: str,
) -> AgentState:
    state = await load_structured_handover_state(
        current_user=current_user,
        session_id=session_id,
    )
    if state is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return state


async def load_structured_review_state(
    *,
    current_user: RequestUser,
    session_id: str,
) -> AgentState | None:
    """Residual structured read reserved for review and handover commit special cases."""
    return await load_structured_residual_state(
        current_user=current_user,
        session_id=session_id,
    )


async def require_structured_review_state(
    *,
    current_user: RequestUser,
    session_id: str,
) -> AgentState:
    state = await load_structured_review_state(
        current_user=current_user,
        session_id=session_id,
    )
    if state is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return state


async def _load_governed_state_snapshot_projection_source(
    *,
    current_user: RequestUser,
    session_id: str,
) -> GovernedSessionState | None:
    """Load the latest governed Postgres snapshot as additive workspace read source."""
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=session_id)
    del tenant_id  # current snapshot rows are keyed by case_number + owner
    snapshot = await get_latest_governed_case_snapshot_async(
        case_number=session_id,
        user_id=owner_id,
    )
    if snapshot is None:
        return None
    try:
        return GovernedSessionState.model_validate(snapshot.state_json)
    except Exception:
        _log.warning(
            "[workspace] failed to validate governed snapshot projection source case=%s revision=%s",
            session_id,
            snapshot.revision,
            exc_info=True,
        )
        return None


async def _load_preferred_governed_workspace_source(
    *,
    current_user: RequestUser,
    session_id: str,
) -> GovernedSessionState | None:
    """Prefer live Redis state, then persisted Postgres snapshot, for governed read projections."""
    live_state = await _load_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        create_if_missing=False,
    )
    if live_state is not None:
        return live_state
    return await _load_governed_state_snapshot_projection_source(
        current_user=current_user,
        session_id=session_id,
    )


async def persist_structured_residual_commit(
    *,
    current_user: RequestUser,
    session_id: str,
    state: AgentState,
    runtime_path: str,
    binding_level: str,
) -> AgentState:
    """Residual structured write core for fallback and special-case commits."""
    tenant_id, owner_id, cache_key = _canonical_scope(current_user, case_id=session_id)
    current_revision = _canonical_state_revision(state)
    loaded_revision = int(state.get("loaded_state_revision", current_revision) or 0)
    if current_revision == loaded_revision:
        state = _advance_case_state_only_revision(state, case_id=session_id, write_scope="structured_persist")
    try:
        await save_structured_case(
            tenant_id=tenant_id,
            owner_id=owner_id,
            case_id=session_id,
            state=state,
            runtime_path=runtime_path,
            binding_level=binding_level,
        )
    except ConcurrencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    state["loaded_state_revision"] = _canonical_state_revision(state)
    state["owner_id"] = owner_id
    state["tenant_id"] = tenant_id
    SESSION_STORE[cache_key] = state
    return state


async def persist_structured_review_commit(
    *,
    current_user: RequestUser,
    session_id: str,
    state: AgentState,
    runtime_path: str,
    binding_level: str,
) -> AgentState:
    """Residual structured write reserved for review and handover commit special cases."""
    return await persist_structured_residual_commit(
        current_user=current_user,
        session_id=session_id,
        state=state,
        runtime_path=runtime_path,
        binding_level=binding_level,
    )


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
    structured_state: Any = None,
) -> Dict[str, Any]:
    qualified_action_gate = case_state.get("qualified_action_gate") if case_state else None
    result_contract = case_state.get("result_contract") if case_state else None
    return {
        **build_public_response_core(
            reply=reply,
            structured_state=jsonable_encoder(structured_state) if structured_state is not None else None,
            policy_path=getattr(getattr(decision, "path", None), "value", getattr(decision, "path", None)),
            run_meta=jsonable_encoder(version_provenance) if version_provenance is not None else None,
        ),
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


def _build_conversation_response_payload(decision: Any, *, session_id: str, reply: str, state: AgentState, working_profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
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
        structured_state=None,
    )


# ---------------------------------------------------------------------------
# Phase F-B.4 — Working-profile → ObservedExtraction bridge
# ---------------------------------------------------------------------------

# Maps working_profile keys to canonical ObservedExtraction field_names.
# Ordered list: for the same canonical name, later entries win (higher priority).
# Phase F-C will replace this with intake_observe_node inside the graph.
_WP_FIELD_MAP: list[tuple[str, str]] = [
    ("material", "material"),
    ("medium", "medium"),
    ("pressure_bar", "pressure_bar"),
    ("temperature", "temperature_c"),        # low-priority alias
    ("temperature_max_c", "temperature_c"),  # higher-priority alias (wins)
    ("installation", "installation"),
    ("geometry_context", "geometry_context"),
    ("clearance_gap_mm", "clearance_gap_mm"),
    ("counterface_surface", "counterface_surface"),
    ("counterface_material", "counterface_material"),
    ("shaft_diameter_mm", "shaft_diameter_mm"),
    ("speed_rpm", "speed_rpm"),
]


_PARAM_LABELS: dict[str, tuple[str, str]] = {
    "medium":            ("Medium",          ""),
    "temperature_c":     ("Temperatur",        "°C"),
    "pressure_bar":      ("Druck",            "bar"),
    "shaft_diameter_mm": ("Wellen-Ø",         "mm"),
    "speed_rpm":         ("Drehzahl",         "rpm"),
    "installation":      ("Einbausituation",  ""),
    "geometry_context":  ("Geometrie",        ""),
    "clearance_gap_mm":  ("Spalt",            "mm"),
    "counterface_surface": ("Oberflaeche",    ""),
    "counterface_material": ("Gegenlaufpartner", ""),
}


def _build_param_summary(governed_state_data: dict) -> Optional[str]:
    """Baut einen lesbaren Parameter-Block aus governed_state.asserted.assertions.

    Gibt None zurück wenn keine Werte vorhanden sind (frische Session).
    Das Ergebnis wird als case_summary an _prompt_builder.conversation() übergeben.

    Fallback-Priorität:
      1. asserted.assertions[key].asserted_value  — höchste Konfidenz
      2. normalized.parameters[key].value         — bereits normalisiert, aber noch unbestätigt
    """
    assertions: dict = (
        governed_state_data
        .get("asserted", {})
        .get("assertions", {})
    )
    normalized: dict = (
        governed_state_data
        .get("normalized", {})
        .get("parameters", {})
    )
    lines: list[str] = []
    for key, (label, unit) in _PARAM_LABELS.items():
        # Priority 1: asserted value
        entry = assertions.get(key)
        if entry and isinstance(entry, dict) and entry.get("asserted_value") is not None:
            val = entry["asserted_value"]
            val_str = str(int(val)) if isinstance(val, float) and val == int(val) else str(val)
            suffix = f" {unit}" if unit else ""
            lines.append(f"- {label}: {val_str}{suffix}")
            continue
        # Priority 2: normalized value (known but not yet asserted)
        norm_entry = normalized.get(key)
        if norm_entry and isinstance(norm_entry, dict) and norm_entry.get("value") is not None:
            val = norm_entry["value"]
            val_str = str(int(val)) if isinstance(val, float) and val == int(val) else str(val)
            suffix = f" {unit}" if unit else ""
            lines.append(f"- {label}: {val_str}{suffix}")
    return "\n".join(lines) if lines else None


def _collect_light_missing_fields(state: GovernedSessionState) -> list[str]:
    missing = list(state.asserted.blocking_unknowns) + list(state.asserted.conflict_flags)
    existing = list(state.exploration_progress.missing_critical_fields or [])
    seen: list[str] = []
    for item in missing + existing:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _collect_tentative_domain_signals(state: GovernedSessionState) -> list[str]:
    signals: list[str] = []
    for key, value in (
        ("motion", getattr(state.motion_hint, "label", None)),
        ("application", getattr(state.application_hint, "label", None)),
        ("medium_family", getattr(state.medium_classification, "family", None)),
        ("medium_status", getattr(state.medium_classification, "status", None)),
    ):
        text = str(value or "").strip()
        if text:
            signals.append(f"{key}:{text}")
    return signals


def _build_light_case_summary(governed_state: GovernedSessionState) -> Optional[str]:
    parts: list[str] = []
    param_summary = _build_param_summary(governed_state.model_dump())
    if param_summary:
        parts.append(param_summary)
    progress = governed_state.exploration_progress
    if progress.observed_topic:
        parts.append(f"- Beobachtetes Thema: {progress.observed_topic}")
    if progress.missing_critical_fields:
        parts.append(f"- Offene Kernangaben: {', '.join(progress.missing_critical_fields)}")
    if progress.next_best_question_candidate:
        parts.append(f"- Naechste Frage: {progress.next_best_question_candidate}")
    return "\n".join(part for part in parts if part).strip() or None


def _light_case_active(governed_state: GovernedSessionState) -> bool:
    if governed_state.conversation_messages:
        return True
    if governed_state.asserted.assertions:
        return True
    if governed_state.exploration_progress.case_active:
        return True
    return bool(_build_param_summary(governed_state.model_dump()))


def _truncate_light_topic(message: str, *, limit: int = 160) -> str | None:
    text = " ".join(str(message or "").split()).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def _with_light_route_progress(
    state: GovernedSessionState,
    *,
    message: str,
    mode: Literal["CONVERSATION", "EXPLORATION"],
    conversation_strategy: dict[str, Any] | None,
) -> GovernedSessionState:
    strategy = conversation_strategy or {}
    existing = state.exploration_progress
    observed_topic = existing.observed_topic
    if mode == "EXPLORATION":
        observed_topic = _truncate_light_topic(message) or observed_topic
    updated_progress = existing.model_copy(
        update={
            "observed_topic": observed_topic,
            "tentative_domain_signals": _collect_tentative_domain_signals(state),
            "missing_critical_fields": _collect_light_missing_fields(state),
            "next_best_question_candidate": str(strategy.get("primary_question") or "").strip() or None,
            "next_best_question_reason": str(strategy.get("primary_question_reason") or "").strip() or None,
            "last_route": mode,
            "case_active": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return state.model_copy(update={"exploration_progress": updated_progress})


def _light_structured_state(
    state: GovernedSessionState,
    *,
    mode: Literal["CONVERSATION", "EXPLORATION"],
) -> dict[str, Any]:
    progress = state.exploration_progress
    next_step = "answer_next_question" if progress.next_best_question_candidate else "continue_conversation"
    return {
        "case_status": "exploration_active" if mode == "EXPLORATION" else "conversation_active",
        "output_status": "conversational_answer",
        "next_step": next_step,
        "primary_allowed_action": next_step,
        "active_blockers": list(progress.missing_critical_fields),
        "last_route": progress.last_route,
        "observed_topic": progress.observed_topic,
        "tentative_domain_signals": list(progress.tentative_domain_signals),
        "missing_critical_fields": list(progress.missing_critical_fields),
        "next_best_question": progress.next_best_question_candidate,
        "next_best_question_reason": progress.next_best_question_reason,
        "case_active": progress.case_active,
    }


def _extract_extractions_from_working_profile(
    working_profile: Dict[str, Any],
    turn_index: int,
) -> list[ObservedExtraction]:
    """Map scalar values from working_profile to ObservedExtraction objects.

    Phase F-B.4 bridge: reads LLM-extracted values from the existing
    working_profile (populated by LangGraph nodes) and converts them into
    ObservedExtractions for the Pydantic reducer chain.

    Rules:
    - Only scalar values (str, int, float, bool) are extracted.
    - Nested dicts / lists (e.g. live_calc_tile) are ignored.
    - Later entries in _WP_FIELD_MAP overwrite earlier ones for the same
      canonical field_name (e.g. temperature_max_c beats temperature).
    - confidence=0.9 — high, but not user-confirmed (LLM source).
    """
    seen: Dict[str, ObservedExtraction] = {}
    for wp_key, canonical_name in _WP_FIELD_MAP:
        val = working_profile.get(wp_key)
        if val is None or isinstance(val, (dict, list)):
            continue
        seen[canonical_name] = ObservedExtraction(
            field_name=canonical_name,
            raw_value=val,
            source="llm",
            confidence=0.9,
            turn_index=turn_index,
        )
    return list(seen.values())


async def _update_governed_state_post_graph(
    *,
    governed_state: GovernedSessionState,
    final_agent_state: AgentState,
    tenant_id: str,
    session_id: str,
    turn_index: int,
) -> GovernedSessionState:
    """Extract params from working_profile, run reducer chain, persist to Redis.

    Called from the on_complete hook in event_generator after LangGraph finishes.

    Architecture invariant (F-B.2):
    - Never writes directly to Normalized/Asserted/GovernanceState.
    - Only ObservedState.with_extraction() is used for writes.
    - All downstream state is derived via the deterministic reducer chain.
    """
    working_profile: Dict[str, Any] = dict(final_agent_state.get("working_profile") or {})
    extractions = _extract_extractions_from_working_profile(working_profile, turn_index=turn_index)

    # Append new extractions to ObservedState (append-only — never mutate)
    observed = governed_state.observed
    for extraction in extractions:
        observed = observed.with_extraction(extraction)

    # Run the full deterministic reducer chain (no LLM, no I/O)
    previous_normalized = governed_state.normalized
    normalized = reduce_observed_to_normalized(observed)
    medium_capture = derive_medium_capture(
        message=str(final_agent_state.get("input_text") or final_agent_state.get("user_message") or ""),
        observed=observed,
        previous=governed_state.medium_capture,
    )
    medium_classification = derive_medium_classification(
        capture=medium_capture,
        normalized=normalized,
        previous=governed_state.medium_classification,
    )
    asserted = reduce_normalized_to_asserted(normalized)
    governance = reduce_asserted_to_governance(
        asserted,
        analysis_cycle=governed_state.analysis_cycle + 1,
        max_cycles=governed_state.max_cycles,
    )
    changed_fields = determine_changed_parameter_fields(previous_normalized, normalized)

    updated = governed_state.model_copy(update={
        "observed": observed,
        "normalized": normalized,
        "medium_capture": medium_capture,
        "medium_classification": medium_classification,
        "asserted": asserted,
        "derived": governed_state.derived.model_copy(update={
            "assertions": asserted.assertions,
            "blocking_unknowns": asserted.blocking_unknowns,
            "conflict_flags": asserted.conflict_flags,
            "requirement_class": governance.requirement_class,
        }),
        "governance": governance,
        "decision": governed_state.decision.model_copy(update={
            "requirement_class": governance.requirement_class,
            "gov_class": governance.gov_class,
            "rfq_admissible": governance.rfq_admissible,
            "validity_limits": governance.validity_limits,
            "open_validation_points": governance.open_validation_points,
        }),
        "analysis_cycle": governed_state.analysis_cycle + 1,
    })
    for changed_field in sorted(changed_fields):
        updated = invalidate_downstream(changed_field, updated)

    # Persist updated state to Redis (fail-safe — SSE stream is already done)
    from redis.asyncio import Redis as AsyncRedis  # noqa: PLC0415
    redis_url = os.getenv("REDIS_URL", "")
    if redis_url:
        try:
            async with AsyncRedis.from_url(redis_url, decode_responses=True) as _rc:
                await _persist_live_governed_state(
                    current_user=current_user,
                    session_id=session_id,
                    state=updated,
                    redis_client=_rc,
                )
        except Exception as _exc:  # noqa: BLE001
            _log.warning(
                "[event_generator] governed state Redis save failed "
                "tenant=%s session=%s: %s",
                tenant_id,
                session_id,
                _exc,
            )

    _log.debug(
        "[event_generator] governed_state updated "
        "gov_class=%s rfq_admissible=%s cycle=%d "
        "params=%s blocking=%s",
        governance.gov_class,
        governance.rfq_admissible,
        updated.analysis_cycle,
        sorted(normalized.parameters.keys()),
        asserted.blocking_unknowns,
    )
    return updated


def _governed_structured_state(state: GovernedSessionState, response_class: str) -> dict[str, Any]:
    response_class = normalize_outward_response_class(response_class)
    active_blockers = list(state.asserted.blocking_unknowns) + list(state.asserted.conflict_flags)
    medium_status = state.medium_classification.status
    medium_family = state.medium_classification.family
    if response_class == "inquiry_ready":
        selected = state.rfq.selected_manufacturer_ref
        return {
            "case_status": "inquiry_ready",
            "output_status": "inquiry_ready",
            "next_step": "review_inquiry_handover",
            "primary_allowed_action": "inspect_inquiry_basis",
            "active_blockers": active_blockers,
            **build_admissibility_payload(state.governance.rfq_admissible),
            "selected_manufacturer": selected.manufacturer_name if selected is not None else None,
            "dispatch_ready": state.dispatch.dispatch_ready,
            "dispatch_status": state.dispatch.dispatch_status,
            "medium_classification_status": medium_status,
            "medium_family": medium_family,
            "norm_status": state.sealai_norm.status,
            "export_status": state.export_profile.status,
            "mapping_status": state.manufacturer_mapping.status,
            "contract_status": state.dispatch_contract.status,
        }
    if response_class == "candidate_shortlist":
        selected = state.matching.selected_manufacturer_ref
        return {
            "case_status": "matching_available",
            "output_status": "candidate_shortlist",
            "next_step": "review_matching_result",
            "primary_allowed_action": "inspect_manufacturer_candidates",
            "active_blockers": active_blockers,
            **build_admissibility_payload(state.governance.rfq_admissible),
            "selected_manufacturer": selected.manufacturer_name if selected is not None else None,
            "medium_classification_status": medium_status,
            "medium_family": medium_family,
            "norm_status": state.sealai_norm.status,
            "export_status": state.export_profile.status,
            "mapping_status": state.manufacturer_mapping.status,
            "contract_status": state.dispatch_contract.status,
        }
    if response_class == "structured_clarification":
        return {
            "case_status": "clarification_needed",
            "output_status": "clarification_needed",
            "next_step": "provide_missing_parameters",
            "primary_allowed_action": "answer_open_points",
            "active_blockers": active_blockers,
            **build_admissibility_payload(state.governance.rfq_admissible),
            "medium_classification_status": medium_status,
            "medium_family": medium_family,
            "norm_status": state.sealai_norm.status,
            "export_status": state.export_profile.status,
            "mapping_status": state.manufacturer_mapping.status,
            "contract_status": state.dispatch_contract.status,
        }
    return {
        "case_status": "governed_visible",
        "output_status": response_class,
        "next_step": "review_governed_result",
        "primary_allowed_action": "continue_governed_session",
        "active_blockers": active_blockers,
        **build_admissibility_payload(state.governance.rfq_admissible),
        "medium_classification_status": medium_status,
        "medium_family": medium_family,
        "norm_status": state.sealai_norm.status,
        "export_status": state.export_profile.status,
        "mapping_status": state.manufacturer_mapping.status,
        "contract_status": state.dispatch_contract.status,
    }


def _compose_deterministic_governed_reply(
    *,
    response_class: str,
    turn_context: TurnContextContract,
    fallback_text: str,
) -> str:
    response_class = normalize_outward_response_class(response_class)
    if response_class == "structured_clarification":
        return compose_clarification_reply(
            turn_context,
            fallback_text=fallback_text,
        )
    if response_class == "governed_state_update":
        return compose_result_reply(
            turn_context,
            fallback_text=fallback_text,
            response_class=response_class,
            facts_prefix="Bisher steht",
            open_points_prefix="Zur Absicherung noch offen",
        )
    if response_class == "technical_preselection":
        return compose_result_reply(
            turn_context,
            fallback_text=fallback_text,
            response_class=response_class,
            facts_prefix="Technische Richtung",
            open_points_prefix="Im Scope jetzt noch pruefen",
        )
    if response_class == "candidate_shortlist":
        return compose_result_reply(
            turn_context,
            fallback_text=fallback_text,
            response_class=response_class,
            facts_prefix="Belastbarer Rahmen",
            open_points_prefix="Vor Herstellerfreigabe noch offen",
        )
    if response_class == "inquiry_ready":
        return compose_result_reply(
            turn_context,
            fallback_text=fallback_text,
            response_class=response_class,
            facts_prefix="Anfragebasis",
            open_points_prefix="Vor Versand noch im Blick",
        )
    return str(fallback_text or "").strip()


def _build_governed_reply_context(
    *,
    result_state: GraphState,
    persisted_state: GovernedSessionState,
) -> GovernedReplyAssemblyContext:
    def _sanitize_public_notes(notes: list[Any]) -> list[str]:
        blocked_fragments = (
            "transport",
            "bridge",
            "handoff",
            "dry-run",
            "internal trigger",
            "sender/connector",
            "connector consumption",
            "envelope",
        )
        public_notes: list[str] = []
        for note in notes:
            text = str(note or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if any(fragment in lowered for fragment in blocked_fragments):
                continue
            if text not in public_notes:
                public_notes.append(text)
        return public_notes

    def _strip_forbidden_keys(value: Any) -> Any:
        forbidden_keys = {
            "event_id",
            "event_key",
            "analysis_cycle_id",
            "partner_id",
            "transport_channel",
            "manufacturer_sku",
            "compound_code",
        }
        if isinstance(value, dict):
            return {
                key: _strip_forbidden_keys(item)
                for key, item in value.items()
                if key not in forbidden_keys
            }
        if isinstance(value, list):
            return [_strip_forbidden_keys(item) for item in value]
        return value

    ui_payload = project_for_ui(result_state).model_dump()
    if "inquiry" not in ui_payload and isinstance(ui_payload.get("rfq"), dict):
        ui_payload["inquiry"] = dict(ui_payload["rfq"])
    for tile_name, note_field in (
        ("rfq", "notes"),
        ("inquiry", "notes"),
        ("export_profile", "notes"),
        ("dispatch_contract", "handover_notes"),
    ):
        tile = ui_payload.get(tile_name)
        if isinstance(tile, dict) and isinstance(tile.get(note_field), list):
            tile[note_field] = _sanitize_public_notes(tile[note_field])
    ui_payload = _strip_forbidden_keys(ui_payload)

    rendered = render_response(result_state.output_reply, path="GOVERNED")
    response_class = str(result_state.output_response_class or "structured_clarification")
    conversation_strategy = build_governed_conversation_strategy_contract(result_state, response_class)
    turn_context = build_governed_turn_context(
        state=result_state,
        strategy=conversation_strategy,
        response_class=response_class,
    )
    allowed_surface_claims = _build_governed_allowed_surface_claims(response_class)
    assertions_payload: dict[str, Any] = {}
    for _key, _e in (result_state.asserted.assertions or {}).items():
        if _e.asserted_value is not None:
            _raw = _e.asserted_value
            _val_str = (
                str(int(_raw))
                if isinstance(_raw, float) and _raw == int(_raw)
                else str(_raw)
            )
            assertions_payload[_key] = {"value": _val_str, "confidence": _e.confidence}

    structured_state = _governed_structured_state(persisted_state, response_class)
    fallback_seed = str(allowed_surface_claims.get("fallback_text") or "").strip()
    deterministic_reply = _compose_deterministic_governed_reply(
        response_class=response_class,
        turn_context=turn_context,
        fallback_text=fallback_seed,
    )
    _req_class = result_state.governance.requirement_class
    _req_class_id = _req_class.class_id if _req_class is not None else None
    _applicable_norms: list[str] = list(getattr(result_state.derived, "applicable_norms", None) or [])
    _evidence: Any = result_state.evidence
    _evidence_summary_lines: list[str] = list(
        (getattr(_evidence, "source_backed_findings", None) or [])
        + (getattr(_evidence, "deterministic_findings", None) or [])
    )
    _preselection: dict[str, Any] | None = result_state.decision.preselection if result_state.decision is not None else None
    _material_candidates: list[str] = []
    if isinstance(_preselection, dict):
        for _key in ("candidates", "materials", "material_candidates"):
            _val = _preselection.get(_key)
            if isinstance(_val, list):
                _material_candidates = [str(v) for v in _val if v]
                break
    domain_context: dict[str, Any] = {
        "requirement_class_id": _req_class_id,
        "applicable_norms": _applicable_norms,
        "evidence_summary_lines": _evidence_summary_lines,
        "material_candidates": _material_candidates,
    }
    return GovernedReplyAssemblyContext(
        response_class=response_class,
        structured_state=structured_state,
        assertions_payload=assertions_payload,
        conversation_strategy=conversation_strategy,
        turn_context=turn_context,
        run_meta={
            "path": "governed_graph",
            "was_scrubbed": rendered.was_scrubbed,
        },
        ui_payload=ui_payload,
        deterministic_reply=deterministic_reply,
        domain_context=domain_context,
    )


def _assemble_governed_stream_payload(
    *,
    context: GovernedReplyAssemblyContext,
    visible_reply: str | None = None,
) -> dict[str, Any]:
    fallback_reply = str(context.deterministic_reply or "").strip()
    visible_reply_text = str(visible_reply or "").strip()
    final_reply = visible_reply_text or fallback_reply
    public_reply = assemble_user_facing_reply(
        reply=final_reply,
        structured_state=context.structured_state,
        policy_path="governed",
        run_meta=context.run_meta,
        response_class=context.response_class,
        fallback_text=fallback_reply,
    )

    return {
        "type": "state_update",
        **public_reply,
        "assertions": context.assertions_payload,
        "conversation_strategy": context.conversation_strategy.model_dump(),
        "turn_context": context.turn_context.model_dump(),
        "ui": context.ui_payload,
    }


def _build_governed_stream_payload(
    *,
    result_state: GraphState,
    persisted_state: GovernedSessionState,
    visible_reply: str | None = None,
) -> dict[str, Any]:
    context = _build_governed_reply_context(
        result_state=result_state,
        persisted_state=persisted_state,
    )
    return _assemble_governed_stream_payload(
        context=context,
        visible_reply=visible_reply,
    )


def _build_governed_allowed_surface_claims(response_class: str) -> GovernedAllowedSurfaceClaims:
    return get_surface_claims_spec(response_class)


def _is_light_runtime_mode(runtime_mode: str | None) -> bool:
    return runtime_mode in {"CONVERSATION", "EXPLORATION"}


def _legacy_decision_requires_governed_authority(decision: Any) -> bool:
    """Structured/case-state turns must never fall back to the legacy graph."""
    return bool(getattr(decision, "has_case_state", False))


def _block_residual_legacy_structured_usage(*, session_id: str, decision: Any) -> None:
    if not _legacy_decision_requires_governed_authority(decision):
        return
    path = str(getattr(getattr(decision, "path", None), "value", getattr(decision, "path", "")) or "").strip()
    _log.error(
        "[%s] blocked structured unauthenticated usage session=%s policy_path=%s",
        _RESIDUAL_LEGACY_RUNTIME_LABEL,
        session_id,
        path or "<unknown>",
    )
    raise HTTPException(
        status_code=401,
        detail=(
            "Structured technical turns require the authenticated governed runtime. "
            "Residual legacy helper paths are compat-only."
        ),
    )


async def _stream_light_runtime(
    *,
    message: str,
    request: ChatRequest,
    current_user: RequestUser,
    mode: Literal["CONVERSATION", "EXPLORATION"],
    governed_state_override: GovernedSessionState | None = None,
    direct_reply: str | None = None,
) -> AsyncGenerator[str, None]:
    from app.agent.runtime.conversation_runtime import stream_conversation  # noqa: PLC0415

    governed, history, case_summary = await _build_light_runtime_context(
        request=request,
        current_user=current_user,
        governed_state_override=governed_state_override,
    )
    final_reply = ""
    final_strategy: dict[str, Any] | None = None
    final_structured_state: dict[str, Any] | None = None
    async for frame in stream_conversation(
        message,
        history=history,
        case_summary=case_summary,
        mode=mode,
        direct_reply=direct_reply,
    ):
        if not frame.startswith("data: "):
            continue
        raw = frame[6:].strip()
        if raw == "[DONE]":
            yield frame
            continue
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        event_type = str(payload.get("type") or "")
        if event_type == "state_update":
            final_reply = str(payload.get("reply") or "").strip()
            final_strategy = payload.get("conversation_strategy") if isinstance(payload.get("conversation_strategy"), dict) else None
            if governed is not None and request.session_id and final_reply:
                updated = _with_governed_conversation_turn(
                    governed,
                    user_message=message,
                    assistant_reply=final_reply,
                )
                updated = _with_light_route_progress(
                    updated,
                    message=message,
                    mode=mode,
                    conversation_strategy=final_strategy,
                )
                await _persist_live_governed_state(
                    current_user=current_user,
                    session_id=request.session_id,
                    state=updated,
                )
                final_structured_state = _light_structured_state(updated, mode=mode)
                payload["structured_state"] = final_structured_state
                frame = f"data: {json.dumps(payload, default=str)}\n\n"
                governed = updated
            yield frame
            continue
        if event_type == "error":
            yield frame


async def _run_light_chat_response(
    *,
    message: str,
    request: ChatRequest,
    current_user: RequestUser,
    mode: Literal["CONVERSATION", "EXPLORATION"],
    governed_state_override: GovernedSessionState | None = None,
    direct_reply: str | None = None,
) -> ChatResponse:
    from app.agent.runtime.conversation_runtime import run_conversation  # noqa: PLC0415

    governed, history, case_summary = await _build_light_runtime_context(
        request=request,
        current_user=current_user,
        governed_state_override=governed_state_override,
    )

    result = await run_conversation(
        message,
        history=history,
        case_summary=case_summary,
        mode=mode,
        direct_reply=direct_reply,
    )
    structured_state: dict[str, Any] | None = None
    if governed is not None and request.session_id and result.reply_text:
        updated = _with_governed_conversation_turn(
            governed,
            user_message=message,
            assistant_reply=result.reply_text,
        )
        updated = _with_light_route_progress(
            updated,
            message=message,
            mode=mode,
            conversation_strategy=None,
        )
        await _persist_live_governed_state(
            current_user=current_user,
            session_id=request.session_id,
            state=updated,
        )
        structured_state = _light_structured_state(updated, mode=mode)
    return ChatResponse(
        session_id=request.session_id,
        **build_public_response_core(
            reply=result.reply_text,
            structured_state=structured_state,
            policy_path="fast",
            run_meta=None,
        ),
    )


async def _run_governed_graph_once(
    request: ChatRequest,
    *,
    current_user: RequestUser,
) -> tuple[GraphState, GovernedSessionState]:
    tenant_id, _, _ = _canonical_scope(current_user, case_id=request.session_id)
    redis_url = os.getenv("REDIS_URL", "")
    governed_state = GovernedSessionState()

    if redis_url:
        from redis.asyncio import Redis as AsyncRedis  # noqa: PLC0415

        async with AsyncRedis.from_url(redis_url, decode_responses=True) as redis_client:
            governed_state = await get_or_create_governed_state_async(
                tenant_id=tenant_id,
                session_id=request.session_id,
                redis_client=redis_client,
            )

            graph_input = GraphState.model_validate(
                {
                    **governed_state.model_dump(),
                    "tenant_id": tenant_id,
                    "session_id": request.session_id,
                    "pending_message": request.message,
                }
            )
            raw_result = await GOVERNED_GRAPH.ainvoke(graph_input)
            result_state = _materialize_graph_result(raw_result)
            persisted_state = GovernedSessionState.model_validate(result_state.model_dump())
            result_state, persisted_state = _enrich_medium_context_state(
                result_state=result_state,
                persisted_state=persisted_state,
            )
            await _persist_live_governed_state(
                current_user=current_user,
                session_id=request.session_id,
                state=persisted_state,
                redis_client=redis_client,
            )
            return result_state, persisted_state

    graph_input = GraphState.model_validate(
        {
            **governed_state.model_dump(),
            "tenant_id": tenant_id,
            "session_id": request.session_id,
            "pending_message": request.message,
        }
    )
    raw_result = await GOVERNED_GRAPH.ainvoke(graph_input)
    result_state = _materialize_graph_result(raw_result)
    persisted_state = GovernedSessionState.model_validate(result_state.model_dump())
    result_state, persisted_state = _enrich_medium_context_state(
        result_state=result_state,
        persisted_state=persisted_state,
    )
    return result_state, persisted_state


def _materialize_governed_graph_result(raw_result: object) -> GraphState:
    if isinstance(raw_result, dict) and "__interrupt__" in raw_result:
        interrupts = list(raw_result.get("__interrupt__") or [])
        if not interrupts:
            raise RuntimeError("governed graph returned empty interrupt payload")
        payload = getattr(interrupts[0], "value", None)
        if not isinstance(payload, dict) or "state" not in payload:
            raise RuntimeError("governed graph returned malformed interrupt payload")
        return GraphState.model_validate(payload["state"])
    return GraphState.model_validate(raw_result)


async def _stream_governed_graph(
    request: ChatRequest,
    *,
    current_user: RequestUser,
) -> AsyncGenerator[str, None]:
    if hasattr(GOVERNED_GRAPH, "astream"):
        tenant_id, _, _ = _canonical_scope(current_user, case_id=request.session_id)
        redis_url = os.getenv("REDIS_URL", "")
        governed_state = GovernedSessionState()

        async def _run_stream(redis_client=None):
            nonlocal governed_state
            if redis_client is not None:
                governed_state = await get_or_create_governed_state_async(
                    tenant_id=tenant_id,
                    session_id=request.session_id,
                    redis_client=redis_client,
                )

            graph_input = GraphState.model_validate(
                {
                    **governed_state.model_dump(),
                    "tenant_id": tenant_id,
                    "session_id": request.session_id,
                    "pending_message": request.message,
                }
            )

            latest_values: object = graph_input.model_dump(mode="python")
            async for mode, data in GOVERNED_GRAPH.astream(
                graph_input,
                stream_mode=["custom", "values"],
            ):
                if mode == "custom" and isinstance(data, dict):
                    yield f"data: {json.dumps({'type': 'progress', **data}, default=str)}\n\n"
                elif mode == "values":
                    latest_values = data

            result_state = _materialize_governed_graph_result(latest_values)
            persisted_state = GovernedSessionState.model_validate(result_state.model_dump())
            result_state, persisted_state = _enrich_medium_context_state(
                result_state=result_state,
                persisted_state=persisted_state,
            )

            if redis_client is not None:
                await _persist_live_governed_state(
                    current_user=current_user,
                    session_id=request.session_id,
                    state=persisted_state,
                    redis_client=redis_client,
                )

            context = _build_governed_reply_context(
                result_state=result_state,
                persisted_state=persisted_state,
            )
            visible_reply: str | None = None
            if context.deterministic_reply:
                visible_reply = await collect_governed_visible_reply(
                    response_class=context.response_class,
                    turn_context=context.turn_context,
                    fallback_text=context.deterministic_reply,
                    allowed_surface_claims=_build_governed_allowed_surface_claims(context.response_class),
                    **context.domain_context,
                )
            if request.session_id and visible_reply:
                persisted_state = _with_governed_conversation_turn(
                    persisted_state,
                    user_message=request.message,
                    assistant_reply=visible_reply,
                )
                await _persist_live_governed_state(
                    current_user=current_user,
                    session_id=request.session_id,
                    state=persisted_state,
                )
            payload = _assemble_governed_stream_payload(
                context=context,
                visible_reply=visible_reply,
            )
            yield f"data: {json.dumps(payload, default=str)}\n\n"
            yield "data: [DONE]\n\n"

        if redis_url:
            from redis.asyncio import Redis as AsyncRedis  # noqa: PLC0415

            async with AsyncRedis.from_url(redis_url, decode_responses=True) as redis_client:
                async for frame in _run_stream(redis_client):
                    yield frame
            return

        async for frame in _run_stream():
            yield frame
        return

    result_state, persisted_state = await _run_governed_graph_once(
        request,
        current_user=current_user,
    )

    context = _build_governed_reply_context(
        result_state=result_state,
        persisted_state=persisted_state,
    )
    visible_reply: str | None = None
    if context.deterministic_reply:
        visible_reply = await collect_governed_visible_reply(
            response_class=context.response_class,
            turn_context=context.turn_context,
            fallback_text=context.deterministic_reply,
            allowed_surface_claims=_build_governed_allowed_surface_claims(context.response_class),
            **context.domain_context,
        )
    if request.session_id and visible_reply:
        persisted_state = _with_governed_conversation_turn(
            persisted_state,
            user_message=request.message,
            assistant_reply=visible_reply,
        )
        await _persist_live_governed_state(
            current_user=current_user,
            session_id=request.session_id,
            state=persisted_state,
        )
    payload = _assemble_governed_stream_payload(
        context=context,
        visible_reply=visible_reply,
    )
    yield f"data: {json.dumps(payload, default=str)}\n\n"
    yield "data: [DONE]\n\n"


async def _run_governed_chat_response(
    request: ChatRequest,
    *,
    current_user: RequestUser,
) -> ChatResponse:
    result_state, persisted_state = await _run_governed_graph_once(
        request,
        current_user=current_user,
    )
    context = _build_governed_reply_context(
        result_state=result_state,
        persisted_state=persisted_state,
    )
    visible_reply = await collect_governed_visible_reply(
        response_class=context.response_class,
        turn_context=context.turn_context,
        fallback_text=context.deterministic_reply,
        allowed_surface_claims=_build_governed_allowed_surface_claims(context.response_class),
        **context.domain_context,
    )
    if request.session_id and visible_reply:
        persisted_state = _with_governed_conversation_turn(
            persisted_state,
            user_message=request.message,
            assistant_reply=visible_reply,
        )
        await _persist_live_governed_state(
            current_user=current_user,
            session_id=request.session_id,
            state=persisted_state,
        )
    payload = _assemble_governed_stream_payload(
        context=context,
        visible_reply=visible_reply,
    )
    return ChatResponse(
        session_id=request.session_id,
        reply=str(payload["reply"]),
        response_class=payload.get("response_class"),
        structured_state=payload.get("structured_state"),
        policy_path=payload.get("policy_path"),
        run_meta=payload.get("run_meta"),
    )


async def event_generator(
    request: ChatRequest,
    *,
    current_user: RequestUser,
) -> AsyncGenerator[str, None]:
    """SSE stream with Phase 0A.4 node filter.

    Only fast_guidance_node and final_response_node tokens reach the client.
    Internal nodes (reasoning_node, evidence_tool_node, selection_node) are
    silently filtered by agent_sse_generator.

    Phase 0F: policy_path / result_form are injected here so meta/blocked
    routing fires consistently on the streaming path too (same as /chat).

    Phase F-A (feature-flag guarded): If SEALAI_ENABLE_BINARY_GATE is true,
    the Gate + SessionEnvelope layer runs first. If SEALAI_ENABLE_CONVERSATION_RUNTIME
    is also true and gate decides CONVERSATION, stream_conversation() is used
    instead of the governed path. On any gate/session exception the dispatch
    fails closed to GOVERNED.
    """
    dispatch = await _resolve_runtime_dispatch(
        request,
        current_user=current_user,
    )
    if _is_light_runtime_mode(dispatch.runtime_mode):
        async for frame in _stream_light_runtime(
            message=request.message,
            request=request,
            current_user=current_user,
            mode=dispatch.runtime_mode,
            governed_state_override=dispatch.governed_state,
            direct_reply=dispatch.direct_reply,
        ):
            yield frame
        return

    if dispatch.runtime_mode == "GOVERNED":
        _log.debug(
            "[runtime_authority] stream session=%s authority=governed_graph reason=%s",
            request.session_id,
            dispatch.gate_reason,
        )
        async for frame in _stream_governed_graph(request, current_user=current_user):
            yield frame
        return

    _log.warning(
        "[runtime_authority] stream session=%s unexpected runtime_mode=%s — fail-closed to governed",
        request.session_id,
        dispatch.runtime_mode,
    )
    async for frame in _stream_governed_graph(request, current_user=current_user):
        yield frame


async def chat_endpoint(request: ChatRequest, current_user: RequestUser | None = None):
    if current_user is None:
        session_id = request.session_id
        if session_id not in SESSION_STORE:
            initial_sealing_state = create_initial_state()
            initial_sealing_state["cycle"]["analysis_cycle_id"] = f"session_{session_id}_1"
            SESSION_STORE[session_id] = {"messages": [], "sealing_state": initial_sealing_state, "working_profile": {}}
        current_state = SESSION_STORE[session_id]
        current_state["messages"].append(HumanMessage(content=request.message))
        # Phase W3.4: gate.py is the canonical routing authority for all paths.
        from app.agent.runtime.gate import decide_route_async as _gate_decide_route_async  # noqa: PLC0415

        class _AnonSession:
            session_zone = "conversation"

        _anon_gate = await _gate_decide_route_async(request.message, _AnonSession())
        if _anon_gate.route == "GOVERNED":
            _log.error(
                "[%s] blocked structured unauthenticated usage session=%s gate_reason=%s",
                _RESIDUAL_LEGACY_RUNTIME_LABEL,
                session_id,
                _anon_gate.reason,
            )
            raise HTTPException(
                status_code=401,
                detail=(
                    "Structured technical turns require the authenticated governed runtime. "
                    "Residual legacy helper paths are compat-only."
                ),
            )
        _log.warning(
            "[%s] unauthenticated JSON helper path used session=%s gate_route=%s",
            _RESIDUAL_LEGACY_RUNTIME_LABEL,
            session_id,
            _anon_gate.route,
        )
        current_state["policy_path"] = _anon_gate.route.lower()
        current_state["result_form"] = "direct_answer" if _anon_gate.route == "CONVERSATION" else "exploration"
        current_state["inquiry_id"] = session_id
        current_state.setdefault("turn_count", 0)
        current_state.setdefault("max_turns", 12)
        updated_state = await execute_agent(current_state)
        SESSION_STORE[session_id] = updated_state
        last_msg = [m for m in updated_state["messages"] if isinstance(m, AIMessage)][-1]
        return ChatResponse(
            session_id=session_id,
            **build_public_response_core(
                reply=last_msg.content,
                structured_state=None,
                policy_path=updated_state.get("policy_path"),
                run_meta=jsonable_encoder(updated_state.get("run_meta")) if updated_state.get("run_meta") is not None else None,
            ),
        )

    dispatch = await _resolve_runtime_dispatch(request, current_user=current_user)
    if _is_light_runtime_mode(dispatch.runtime_mode):
        return await _run_light_chat_response(
            message=request.message,
            request=request,
            current_user=current_user,
            mode=dispatch.runtime_mode,
            governed_state_override=dispatch.governed_state,
            direct_reply=dispatch.direct_reply,
        )

    if dispatch.runtime_mode == "GOVERNED":
        _log.debug(
            "[runtime_authority] json session=%s authority=governed_graph reason=%s",
            request.session_id,
            dispatch.gate_reason,
        )
        return await _run_governed_chat_response(
            request,
            current_user=current_user,
        )

    _log.warning(
        "[runtime_authority] json session=%s unexpected runtime_mode=%s — fail-closed to governed",
        request.session_id,
        dispatch.runtime_mode,
    )
    return await _run_governed_chat_response(
        request,
        current_user=current_user,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_route(request: ChatRequest, current_user: RequestUser = Depends(get_current_request_user)):
    return await chat_endpoint(request, current_user=current_user)


@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest, current_user: RequestUser = Depends(get_current_request_user)):
    return StreamingResponse(event_generator(request, current_user=current_user), media_type="text/event-stream")


@router.get("/cases", response_model=list[CaseListItemResponse])
async def list_cases(
    limit: int = Query(50, ge=1, le=200),
    current_user: RequestUser = Depends(get_current_request_user),
) -> list[CaseListItemResponse]:
    _, owner_id, _ = _canonical_scope(current_user, case_id="")
    items = await list_cases_async(user_id=owner_id, limit=limit)
    return [CaseListItemResponse(**item) for item in items]


@router.get("/cases/{case_id}", response_model=CaseMetadataResponse)
async def get_case_metadata(
    case_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
) -> CaseMetadataResponse:
    _, owner_id, _ = _canonical_scope(current_user, case_id=case_id)
    case_row = await get_case_by_number_async(case_number=case_id, user_id=owner_id)
    if case_row is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return CaseMetadataResponse(**case_row)


@router.get("/cases/{case_id}/snapshots/latest", response_model=GovernedSnapshotResponse)
async def get_latest_case_snapshot(
    case_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
) -> GovernedSnapshotResponse:
    _, owner_id, _ = _canonical_scope(current_user, case_id=case_id)
    snapshot = await get_latest_governed_case_snapshot_async(case_number=case_id, user_id=owner_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Latest snapshot for case '{case_id}' not found")
    return GovernedSnapshotResponse(
        case_id=snapshot.case_id,
        case_number=snapshot.case_number,
        user_id=snapshot.user_id,
        revision=snapshot.revision,
        state_json=snapshot.state_json,
        basis_hash=snapshot.basis_hash,
        ontology_version=snapshot.ontology_version,
        prompt_version=snapshot.prompt_version,
        model_version=snapshot.model_version,
        created_at=snapshot.created_at,
    )


@router.get("/cases/{case_id}/snapshots", response_model=list[GovernedSnapshotRevisionListItemResponse])
async def list_case_snapshots(
    case_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: RequestUser = Depends(get_current_request_user),
) -> list[GovernedSnapshotRevisionListItemResponse]:
    _, owner_id, _ = _canonical_scope(current_user, case_id=case_id)
    case_row = await get_case_by_number_async(case_number=case_id, user_id=owner_id)
    if case_row is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    items = await list_governed_case_snapshots_async(
        case_number=case_id,
        user_id=owner_id,
        limit=limit,
    )
    return [
        GovernedSnapshotRevisionListItemResponse(
            revision=item.revision,
            basis_hash=item.basis_hash,
            ontology_version=item.ontology_version,
            prompt_version=item.prompt_version,
            model_version=item.model_version,
            created_at=item.created_at,
        )
        for item in items
    ]


@router.get("/cases/{case_id}/snapshots/{revision}", response_model=GovernedSnapshotResponse)
async def get_case_snapshot_by_revision(
    case_id: str,
    revision: int = Path(..., ge=1),
    current_user: RequestUser = Depends(get_current_request_user),
) -> GovernedSnapshotResponse:
    _, owner_id, _ = _canonical_scope(current_user, case_id=case_id)
    snapshot = await get_governed_case_snapshot_by_revision_async(
        case_number=case_id,
        revision=revision,
        user_id=owner_id,
    )
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"Snapshot revision {revision} for case '{case_id}' not found",
        )
    return GovernedSnapshotResponse(
        case_id=snapshot.case_id,
        case_number=snapshot.case_number,
        user_id=snapshot.user_id,
        revision=snapshot.revision,
        state_json=snapshot.state_json,
        basis_hash=snapshot.basis_hash,
        ontology_version=snapshot.ontology_version,
        prompt_version=snapshot.prompt_version,
        model_version=snapshot.model_version,
        created_at=snapshot.created_at,
    )


@router.get("/workspace/{case_id}", response_model=CaseWorkspaceProjection)
async def get_workspace_projection(
    case_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
) -> CaseWorkspaceProjection:
    """Canonical workspace read contract backed by persisted agent state."""
    governed_state = await _load_preferred_governed_workspace_source(
        current_user=current_user,
        session_id=case_id,
    )
    if governed_state is not None:
        return project_case_workspace_from_governed_state(governed_state, chat_id=case_id)
    state = await require_structured_residual_state(
        current_user=current_user,
        session_id=case_id,
    )
    return project_case_workspace_from_ssot(state, chat_id=case_id)


@router.get("/chat/history/{case_id}")
async def get_live_chat_history(
    case_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
) -> dict[str, Any]:
    governed_state = await _load_preferred_governed_workspace_source(
        current_user=current_user,
        session_id=case_id,
    )
    if governed_state is not None and governed_state.conversation_messages:
        return _serialize_governed_history_payload(
            conversation_id=case_id,
            governed_state=governed_state,
        )
    state = await require_structured_residual_state(
        current_user=current_user,
        session_id=case_id,
    )
    raw_messages = (state or {}).get("messages") or []
    return {
        "conversation_id": case_id,
        "title": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "messages": [
            {
                "id": uuid.uuid4().hex,
                "role": "user" if isinstance(raw, HumanMessage) else "assistant",
                "content": str(getattr(raw, "content", raw) or ""),
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "index": index,
            }
            for index, raw in enumerate(raw_messages)
            if str(getattr(raw, "content", raw) or "").strip()
        ],
    }


@router.get("/workspace/{case_id}/rfq-document")
async def get_workspace_rfq_document(
    case_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
) -> HTMLResponse:
    """Return an RFQ HTML representation from the residual structured handover state."""
    state = await require_structured_handover_state(
        current_user=current_user,
        session_id=case_id,
    )
    case_state = dict(state.get("case_state") or {})
    rfq_state = dict(case_state.get("rfq_state") or {})
    rfq_object = dict(rfq_state.get("rfq_object") or {})
    sealing = dict(state.get("sealing_state") or {})
    handover = dict(sealing.get("handover") or {})
    if (rfq_object or handover.get("rfq_html_report")) and not _is_review_handover_releasable(
        case_state=case_state,
        sealing_handover=handover,
    ):
        raise HTTPException(
            status_code=409,
            detail="RFQ document is blocked until the mandatory critical review passes.",
        )
    if rfq_object:
        projection = project_case_workspace_from_ssot(state, chat_id=case_id)
        return HTMLResponse(
            content=render_rfq_html(projection),
            headers={
                "Content-Disposition": "inline; filename=\"sealai-rfq-document.html\"",
            },
        )

    html_report = handover.get("rfq_html_report")
    if not html_report:
        raise HTTPException(
            status_code=404,
            detail="No RFQ document has been generated yet.",
        )
    return HTMLResponse(
        content=html_report,
        headers={
            "Content-Disposition": "inline; filename=\"sealai-rfq-document.html\"",
        },
    )


# ---------------------------------------------------------------------------
# HITL Review — Blueprint Sections 08 & 12
# ---------------------------------------------------------------------------

def _find_session(session_id: str) -> AgentState | None:
    """Cache lookup by exact key only.

    Active runtime flows must use persisted canonical state loaders instead of
    suffix-based SESSION_STORE discovery.
    """
    return SESSION_STORE.get(session_id)


def _save_session(session_id: str, state: AgentState) -> None:
    """Write back by exact cache key only."""
    SESSION_STORE[session_id] = state


def _build_review_handover_response(
    *,
    case_state: dict[str, Any] | None,
    sealing_handover: dict[str, Any] | None,
) -> dict[str, Any] | None:
    rfq_state = dict((case_state or {}).get("rfq_state") or {})
    rfq_object = dict(rfq_state.get("rfq_object") or {})

    structured_handover = {
        "is_handover_ready": bool(
            rfq_state.get(
                "handover_ready",
                (sealing_handover or {}).get("is_handover_ready", False),
            )
        ),
        "handover_status": rfq_state.get("handover_status")
        or (sealing_handover or {}).get("handover_status"),
    }
    if not _is_review_handover_releasable(
        case_state=case_state,
        sealing_handover=sealing_handover,
    ):
        return structured_handover

    if rfq_object:
        structured_handover["handover_payload"] = {
            "qualified_material_ids": list(rfq_object.get("qualified_material_ids") or []),
            "qualified_materials": list(rfq_object.get("qualified_materials") or []),
            "confirmed_parameters": dict(rfq_object.get("confirmed_parameters") or {}),
            "dimensions": dict(rfq_object.get("dimensions") or {}),
        }
        if rfq_object.get("target_system") is not None:
            structured_handover["target_system"] = rfq_object.get("target_system")
        return structured_handover

    if rfq_state:
        fallback_payload = dict((sealing_handover or {}).get("handover_payload") or {})
        if fallback_payload:
            structured_handover["handover_payload"] = fallback_payload
        if (sealing_handover or {}).get("target_system") is not None:
            structured_handover["target_system"] = (sealing_handover or {}).get("target_system")
        return structured_handover

    return sealing_handover


def _is_review_handover_releasable(
    *,
    case_state: dict[str, Any] | None,
    sealing_handover: dict[str, Any] | None,
) -> bool:
    rfq_state = dict((case_state or {}).get("rfq_state") or {})
    if rfq_state:
        if rfq_state.get("handover_ready") is not None:
            return bool(rfq_state.get("handover_ready"))
        if rfq_state.get("rfq_ready") is not None:
            return bool(rfq_state.get("rfq_ready"))
    return bool((sealing_handover or {}).get("is_handover_ready", False))


def _apply_review_decision(state: AgentState, request: ReviewRequest) -> AgentState:
    """Return a deep-copied state with governance, review and selection layers patched.

    Does NOT call the LLM or any external service — purely deterministic.
    The cycle revision is advanced so concurrent writes are detectable.
    """
    patched = deepcopy(state)
    sealing_state: dict = patched["sealing_state"]
    existing_case_state = dict(patched.get("case_state") or {})
    governance_state = dict(existing_case_state.get("governance_state") or {})

    governance = dict(sealing_state.get("governance") or {})
    review = dict(sealing_state.get("review") or {})
    selection = dict(sealing_state.get("selection") or {})
    now_iso = datetime.now(timezone.utc).isoformat()

    if request.action == "approve":
        governance_state["release_status"] = "inquiry_ready"
        governance_state["rfq_admissibility"] = "ready"
        governance_state["review_required"] = False
        governance_state["review_state"] = "approved"

        # Governance
        governance["release_status"] = governance_state["release_status"]
        governance["rfq_admissibility"] = governance_state["rfq_admissibility"]
        # Review lifecycle
        review["review_required"] = governance_state["review_required"]
        review["review_state"] = governance_state["review_state"]
        review["reviewed_by"] = "reviewer"
        review["review_decision"] = "approved"
        review["review_note"] = request.reviewer_notes or ""
        review["reviewed_at"] = now_iso
        # Selection projection — keep aligned with governance so build_final_reply
        # can produce a meaningful response (not just SAFEGUARDED_WITHHELD_REPLY).
        selection["release_status"] = "inquiry_ready"
        selection["rfq_admissibility"] = "ready"
        selection["output_blocked"] = False
        selection.setdefault("specificity_level", "compound_required")
        artifact = dict(selection.get("recommendation_artifact") or {})
        if artifact:
            artifact["release_status"] = "inquiry_ready"
            artifact["rfq_admissibility"] = "ready"
            artifact["output_blocked"] = False
            selection["recommendation_artifact"] = artifact

    elif request.action == "reject":
        governance_state["release_status"] = "inadmissible"
        governance_state["rfq_admissibility"] = "inadmissible"
        governance_state["review_required"] = False
        governance_state["review_state"] = "rejected"

        governance["release_status"] = governance_state["release_status"]
        governance["rfq_admissibility"] = governance_state["rfq_admissibility"]
        review["review_required"] = governance_state["review_required"]
        review["review_state"] = governance_state["review_state"]
        review["reviewed_by"] = "reviewer"
        review["review_decision"] = "rejected"
        review["review_note"] = request.reviewer_notes or ""
        review["reviewed_at"] = now_iso
        selection["release_status"] = "inadmissible"
        selection["rfq_admissibility"] = "inadmissible"
        selection["output_blocked"] = True
        artifact = dict(selection.get("recommendation_artifact") or {})
        if artifact:
            artifact["release_status"] = "inadmissible"
            artifact["rfq_admissibility"] = "inadmissible"
            artifact["output_blocked"] = True
            selection["recommendation_artifact"] = artifact

    existing_case_state["governance_state"] = governance_state
    patched["case_state"] = existing_case_state
    sealing_state["governance"] = governance
    sealing_state["review"] = review
    sealing_state["selection"] = selection

    # Advance revision so optimistic-locking checks remain valid
    cycle = dict(sealing_state.get("cycle") or {})
    case_meta = dict(existing_case_state.get("case_meta") or {})
    current_rev = int(cycle.get("state_revision", 0) or 0)
    next_revision = current_rev + 1
    next_cycle_id = (
        f"{cycle.get('analysis_cycle_id') or request.session_id}"
        f"::review::{request.action}::rev{next_revision}::{uuid.uuid4().hex[:8]}"
    )

    case_meta["snapshot_parent_revision"] = current_rev
    case_meta["state_revision"] = next_revision
    case_meta["analysis_cycle_id"] = next_cycle_id
    case_meta["version"] = next_revision
    existing_case_state["case_meta"] = case_meta
    patched["case_state"] = existing_case_state

    cycle["state_revision"] = case_meta["state_revision"]
    cycle["snapshot_parent_revision"] = case_meta["snapshot_parent_revision"]
    cycle["analysis_cycle_id"] = case_meta["analysis_cycle_id"]
    sealing_state["cycle"] = cycle
    patched["sealing_state"] = sealing_state
    result_contract = dict(existing_case_state.get("result_contract") or {})
    patched = ensure_case_state(
        patched,
        session_id=request.session_id,
        runtime_path=str(case_meta.get("runtime_path") or "STRUCTURED_QUALIFICATION"),
        binding_level=str(
            case_meta.get("binding_level")
            or result_contract.get("binding_level")
            or "ORIENTATION"
        ),
    )
    return patched


def _governed_native_review_commit(state: AgentState) -> tuple[AgentState, str]:
    """Finalize review deterministically without routing through the legacy final node."""
    committed = deepcopy(state)
    sealing_state: dict[str, Any] = dict(committed.get("sealing_state") or {})
    case_state: dict[str, Any] = dict(committed.get("case_state") or {})
    governance_state: dict[str, Any] = dict(case_state.get("governance_state") or {})
    rfq_state: dict[str, Any] = dict(case_state.get("rfq_state") or {})
    selection_state: dict[str, Any] = dict(sealing_state.get("selection") or {})
    review_state: dict[str, Any] = dict(sealing_state.get("review") or {})
    matching_state: dict[str, Any] = dict(case_state.get("matching_state") or {})
    recipient_selection: dict[str, Any] = dict(
        case_state.get("recipient_selection")
        or rfq_state.get("recipient_selection")
        or {}
    )
    requirement_class = dict(
        case_state.get("requirement_class")
        or governance_state.get("requirement_class")
        or selection_state.get("requirement_class")
        or {}
    )
    selected_manufacturer_ref = (
        matching_state.get("selected_manufacturer_ref")
        or rfq_state.get("selected_manufacturer_ref")
        or {}
    )

    critical_review = run_critical_review_specialist(
        payload=CriticalReviewSpecialistInput(
            governance_summary=CriticalReviewGovernanceSummary(
                release_status=str(governance_state.get("release_status") or "inadmissible"),
                rfq_admissibility=str(governance_state.get("rfq_admissibility") or "inadmissible"),
                unknowns_release_blocking=tuple(governance_state.get("unknowns_release_blocking") or ()),
                unknowns_manufacturer_validation=tuple(governance_state.get("unknowns_manufacturer_validation") or ()),
                scope_of_validity=tuple(governance_state.get("scope_of_validity") or ()),
                conflicts=tuple(governance_state.get("conflicts") or ()),
                review_required=bool(governance_state.get("review_required", False)),
            ),
            recommendation_package=CriticalReviewRecommendationPackage(
                requirement_class=requirement_class or None,
            ),
            matching_package=CriticalReviewMatchingPackage(
                status=str(matching_state.get("status") or ""),
                selected_manufacturer_ref=dict(selected_manufacturer_ref or {}) or None,
            ),
            rfq_basis=CriticalReviewRfqBasis(
                rfq_object=dict(rfq_state.get("rfq_object") or {}) or None,
                recipient_refs=tuple(
                    dict(ref)
                    for ref in list(
                        recipient_selection.get("candidate_recipient_refs")
                        or recipient_selection.get("selected_recipient_refs")
                        or rfq_state.get("recipient_refs")
                        or []
                    )
                    if isinstance(ref, dict) and ref
                ),
            ),
        )
    )
    review_projection = critical_review_result_to_dict(critical_review)
    review_state.update(review_projection)
    governance_state.update(review_projection)
    rfq_state.update(review_projection)
    review_state["critical_review_status"] = critical_review.critical_review_status

    rfq_state["rfq_admissibility"] = str(governance_state.get("rfq_admissibility") or rfq_state.get("rfq_admissibility") or "inadmissible")
    rfq_state["status"] = "ready" if rfq_state.get("rfq_admissibility") == "ready" else str(rfq_state.get("rfq_admissibility") or "inadmissible")
    if requirement_class:
        rfq_state["requirement_class"] = dict(requirement_class)
    if selected_manufacturer_ref:
        rfq_state["selected_manufacturer_ref"] = dict(selected_manufacturer_ref)

    sealing_state["review"] = review_state
    sealing_state["governance"] = dict(sealing_state.get("governance") or {})
    sealing_state["governance"].update(
        {
            "release_status": governance_state.get("release_status"),
            "rfq_admissibility": governance_state.get("rfq_admissibility"),
            "scope_of_validity": list(governance_state.get("scope_of_validity") or []),
            "unknowns_release_blocking": list(governance_state.get("unknowns_release_blocking") or []),
            "unknowns_manufacturer_validation": list(governance_state.get("unknowns_manufacturer_validation") or []),
        }
    )

    handover = build_handover_payload(
        sealing_state,
        canonical_case_state={
            **case_state,
            "governance_state": governance_state,
            "rfq_state": rfq_state,
        },
        canonical_rfq_object=dict(rfq_state.get("rfq_object") or {}) or None,
        rfq_admissibility=str(rfq_state.get("rfq_admissibility") or governance_state.get("rfq_admissibility") or "inadmissible"),
    )
    sealing_state["handover"] = handover
    rfq_state["handover_status"] = handover.get("handover_status")
    rfq_state["handover_ready"] = bool(handover.get("is_handover_ready", False))
    rfq_state["rfq_ready"] = bool(handover.get("is_handover_ready", False))

    if requirement_class:
        case_state["requirement_class"] = dict(requirement_class)
    case_state["governance_state"] = governance_state
    case_state["rfq_state"] = rfq_state

    dispatch_intent = build_dispatch_intent(rfq_state.get("rfq_dispatch"))
    if dispatch_intent is not None:
        case_state["dispatch_intent"] = dispatch_intent
        sealing_state["dispatch_intent"] = dispatch_intent

    dispatch_state_input = {
        "case_state": case_state,
        "sealing_state": sealing_state,
    }
    sealing_state["dispatch_trigger"] = build_dispatch_trigger(dispatch_state_input)
    sealing_state["dispatch_dry_run"] = build_dispatch_dry_run(dispatch_state_input)
    sealing_state["dispatch_event"] = build_dispatch_event(dispatch_state_input)
    sealing_state["dispatch_bridge"] = build_dispatch_bridge(dispatch_state_input)
    sealing_state["dispatch_handoff"] = build_dispatch_handoff(dispatch_state_input)
    sealing_state["dispatch_transport_envelope"] = build_dispatch_transport_envelope(dispatch_state_input)

    for key in (
        "dispatch_trigger",
        "dispatch_dry_run",
        "dispatch_event",
        "dispatch_bridge",
        "dispatch_handoff",
        "dispatch_transport_envelope",
    ):
        case_state[key] = dict(sealing_state.get(key) or {})

    committed["case_state"] = case_state
    committed["sealing_state"] = sealing_state

    reply_text = build_final_reply(
        selection_state,
        review_required=bool(review_state.get("review_required", False)),
        review_reason=str(review_state.get("review_note") or review_state.get("review_reason") or ""),
        review_state=review_state,
        asserted_state=sealing_state.get("asserted"),
        working_profile=committed.get("working_profile"),
        case_state=case_state,
    )
    committed["messages"] = list(committed.get("messages") or []) + [AIMessage(content=reply_text)]
    return committed, reply_text


@router.post("/review", response_model=ReviewResponse)
async def review_endpoint(
    request: ReviewRequest,
    current_user: RequestUser = Depends(get_current_request_user),
) -> ReviewResponse:
    """HITL resume — apply a reviewer decision and commit the bounded review result.

    The review path stays deterministic and does not re-run the graph end-to-end.
    Phase 4 removes the legacy final_response_node handover commit dependency.
    """
    state = await require_structured_review_state(
        current_user=current_user,
        session_id=request.session_id,
    )

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

    # 4. Deterministic governed-native review commit
    patched_state, reply_text = _governed_native_review_commit(patched_state)

    # 5. Persist canonical state
    patched_state = await persist_structured_review_commit(
        current_user=current_user,
        session_id=request.session_id,
        state=patched_state,
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level=_resolve_payload_binding_level("ORIENTATION", case_state=patched_state.get("case_state")),
    )

    # 6. Build response
    final_sealing: dict = patched_state["sealing_state"]
    final_case_state: dict = (
        patched_state.get("case_state")
        or {}
    )
    final_governance: dict = final_sealing.get("governance") or {}
    final_review: dict = final_sealing.get("review") or {}
    final_governance_state: dict = final_case_state.get("governance_state") or {}
    final_rfq_state: dict = final_case_state.get("rfq_state") or {}
    handover: dict | None = _build_review_handover_response(
        case_state=final_case_state,
        sealing_handover=final_sealing.get("handover"),
    )
    structured_state = build_structured_api_exposure(
        final_sealing.get("selection") or {},
        case_state=final_case_state,
    )
    await _persist_review_outcome_to_live_governed_state(
        current_user=current_user,
        session_id=request.session_id,
        case_state=final_case_state,
        sealing_state=final_sealing,
        assistant_reply=reply_text,
    )
    try:
        live_governed_state = await _load_live_governed_state(
            current_user=current_user,
            session_id=request.session_id,
            create_if_missing=False,
        )
    except Exception as exc:  # noqa: BLE001
        _log.debug("[router] review governed reply load skipped: %s", exc)
        live_governed_state = None
    if live_governed_state is not None:
        review_graph_state = GraphState.model_validate(live_governed_state.model_dump())
        review_response_class = _determine_response_class(review_graph_state)
        review_structured_state = _governed_structured_state(
            live_governed_state,
            review_response_class,
        )
        review_strategy = build_governed_conversation_strategy_contract(
            review_graph_state,
            review_response_class,
        )
        review_turn_context = build_governed_turn_context(
            state=review_graph_state,
            strategy=review_strategy,
            response_class=review_response_class,
        )
        review_allowed_surface_claims = _build_governed_allowed_surface_claims(review_response_class)
        review_fallback_seed = str(
            review_allowed_surface_claims.get("fallback_text") or reply_text or ""
        ).strip()
        review_deterministic_reply = _compose_deterministic_governed_reply(
            response_class=review_response_class,
            turn_context=review_turn_context,
            fallback_text=review_fallback_seed,
        )
        visible_review_reply = await collect_governed_visible_reply(
            response_class=review_response_class,
            turn_context=review_turn_context,
            fallback_text=review_deterministic_reply,
            allowed_surface_claims=review_allowed_surface_claims,
        )
        public_reply = assemble_user_facing_reply(
            reply=visible_review_reply or review_deterministic_reply,
            structured_state=review_structured_state,
            policy_path="governed",
            response_class=review_response_class,
            fallback_text=review_deterministic_reply,
        )["reply"]
    else:
        public_reply = build_public_response_core(
            reply=reply_text,
            structured_state=structured_state,
            policy_path="structured",
        )["reply"]

    return ReviewResponse(
        session_id=request.session_id,
        action=request.action,
        review_state=str(final_governance_state.get("review_state") or final_review.get("review_state", "")),
        release_status=str(final_governance_state.get("release_status") or final_governance.get("release_status", "")),
        is_handover_ready=bool(final_rfq_state.get("handover_ready", bool((handover or {}).get("is_handover_ready", False)))),
        handover=handover,
        reply=public_reply,
    )


@router.post("/review/seed", response_model=ReviewSeedResponse)
async def review_seed_endpoint() -> ReviewSeedResponse:
    raise HTTPException(
        status_code=501,
        detail="review/seed is disabled in the canonical SSoT runtime.",
    )


# ---------------------------------------------------------------------------
# F-B.3 — Override Endpoint
# ---------------------------------------------------------------------------

@router.patch("/session/{session_id}/override", response_model=OverrideResponse)
async def session_override_endpoint(
    session_id: str,
    request: OverrideRequest,
    current_user: RequestUser = Depends(get_current_request_user),
) -> OverrideResponse:
    """Apply user-submitted tile overrides to ObservedState and re-evaluate.

    Architecture invariant (F-B.3):
      User overrides ALWAYS write into ObservedState.user_overrides.
      They NEVER bypass the reducer chain to write directly into
      NormalizedState, AssertedState, or GovernanceState.

    Flow:
      1. Load or create GovernedSessionState from Redis.
      2. Append each OverrideItem as a UserOverride to ObservedState.
      3. Run the full reducer chain deterministically.
      4. Persist the updated GovernedSessionState.
      5. Return governance outcome to the caller.
    """
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=session_id)

    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        raise HTTPException(status_code=503, detail="REDIS_URL not configured")

    try:
        from redis.asyncio import Redis as AsyncRedis  # noqa: PLC0415
        async with AsyncRedis.from_url(redis_url, decode_responses=True) as redis_client:
            # 1. Load or create governed state
            state = await get_or_create_governed_state_async(
                tenant_id=tenant_id,
                session_id=session_id,
                redis_client=redis_client,
            )

            # 2. Append user overrides to ObservedState
            observed = state.observed
            for item in request.overrides:
                override = UserOverride(
                    field_name=item.field_name,
                    override_value=item.value,
                    override_unit=item.unit,
                    turn_index=request.turn_index,
                )
                observed = observed.with_override(override)

            # 3. Re-evaluate deterministically through the full reducer chain
            previous_normalized = state.normalized
            normalized = reduce_observed_to_normalized(observed)
            asserted = reduce_normalized_to_asserted(normalized)
            governance = reduce_asserted_to_governance(
                asserted,
                analysis_cycle=state.analysis_cycle,
                max_cycles=state.max_cycles,
            )
            changed_fields = determine_changed_parameter_fields(previous_normalized, normalized)

            # 4. Persist updated state
            updated_state = state.model_copy(update={
                "observed": observed,
                "normalized": normalized,
                "asserted": asserted,
                "derived": state.derived.model_copy(update={
                    "assertions": asserted.assertions,
                    "blocking_unknowns": asserted.blocking_unknowns,
                    "conflict_flags": asserted.conflict_flags,
                    "requirement_class": governance.requirement_class,
                }),
                "governance": governance,
                "decision": state.decision.model_copy(update={
                    "requirement_class": governance.requirement_class,
                    "gov_class": governance.gov_class,
                    "rfq_admissible": governance.rfq_admissible,
                    "validity_limits": governance.validity_limits,
                    "open_validation_points": governance.open_validation_points,
                }),
            })
            for changed_field in sorted(changed_fields):
                updated_state = invalidate_downstream(changed_field, updated_state)
            await _persist_live_governed_state(
                current_user=current_user,
                session_id=session_id,
                state=updated_state,
                redis_client=redis_client,
            )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Override processing failed: {exc}") from exc

    return OverrideResponse(
        session_id=session_id,
        applied_fields=[item.field_name for item in request.overrides],
        governance=OverrideGovernanceResult(
            gov_class=governance.gov_class,
            inquiry_admissible=governance.rfq_admissible,
            blocking_unknowns=list(asserted.blocking_unknowns),
            conflict_flags=list(asserted.conflict_flags),
            validity_limits=list(governance.validity_limits),
            open_validation_points=list(governance.open_validation_points),
        ),
    )


@router.get("/health")
async def agent_health() -> dict:
    """Liveness probe for the SSoT Agent router.

    Phase 0C.5: Docker Compose and load-balancer health checks MUST point to
    this endpoint, not to the legacy /api/v1/langgraph/health path.

    Returns a deterministic JSON payload — no DB or LLM calls.
    """
    return {"status": "ok", "service": "sealai-agent"}


# Dashboard helper only: this endpoint returns non-authoritative context data and
# does not participate in governed preselection, matching, or inquiry release.
_MEDIUM_INTELLIGENCE_SYSTEM_PROMPT = """\
Du bist ein Experte für Dichtungstechnik und Fluidchemie.
Analysiere das Medium "{medium}" und liefere alle dichtungsrelevanten Eigenschaften.
Antworte NUR mit diesem JSON-Schema (kein Text davor/danach):
{{
  "canonicalName": "Vollständiger chemischer/technischer Name",
  "family": "Mediumfamilie (z.B. wässrig, mineralölbasiert, synthetisch)",
  "subFamily": "Unterkategorie oder null",
  "pH": {{"min": null, "max": null, "note": "string"}},
  "viscosityMpas": {{"at20c": null, "at40c": null, "at80c": null}},
  "temperatureRange": {{"minC": -10, "maxC": 100, "criticalNoteC": null}},
  "pressureTypical": {{"maxBar": null, "note": "string"}},
  "corrosiveness": "low|medium|high|very_high",
  "chemicalAggressiveness": "low|medium|high|very_high",
  "compatibleMaterials": ["NBR", "FKM"],
  "incompatibleMaterials": [{{"material": "Naturkautschuk", "reason": "Quellung"}}],
  "specialChallenges": ["string"],
  "sealingConsiderations": ["string"],
  "typicalIndustries": ["string"],
  "normsStandards": [],
  "warningFlags": [],
  "confidenceLevel": "high|medium|low"
}}
"""

_MEDIUM_INTELLIGENCE_MODEL = os.environ.get("SEALAI_MEDIUM_INTELLIGENCE_MODEL", "gpt-4o-mini")


@router.get("/medium-intelligence")
async def get_medium_intelligence(
    medium: str,
    current_user: RequestUser = Depends(get_current_request_user),
) -> dict:
    """Generate LLM-powered medium intelligence data for the dashboard tile.

    Accepts a single ?medium=<label> query parameter.
    Returns structured JSON with physical properties, compatibility, and sealing notes.
    This is an orientierend (non-binding) information resource — not a governance decision.
    """
    medium_clean = str(medium or "").strip()
    if not medium_clean:
        raise HTTPException(status_code=400, detail="medium parameter required")

    try:
        import openai as _openai  # noqa: PLC0415
        client = _openai.AsyncOpenAI()
        system_prompt = _MEDIUM_INTELLIGENCE_SYSTEM_PROMPT.format(medium=medium_clean)
        response = await client.chat.completions.create(
            model=_MEDIUM_INTELLIGENCE_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Medium: {medium_clean}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=1200,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        # Ensure canonical output shape even if model omitted optional fields
        data.setdefault("canonicalName", medium_clean)
        data.setdefault("family", "")
        data.setdefault("warningFlags", [])
        data.setdefault("normsStandards", [])
        data.setdefault("confidenceLevel", "medium")
        return data
    except Exception as exc:  # noqa: BLE001
        _log.warning("[medium_intelligence] LLM call failed for medium=%s: %s", medium_clean, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Medium intelligence generation failed: {type(exc).__name__}",
        ) from exc


app_api = FastAPI(title="SealAI LangGraph PoC API")
app_api.include_router(router)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app_api.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
