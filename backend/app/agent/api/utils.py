import logging
import json
import dataclasses
from datetime import datetime, timezone
from typing import Any, List, Optional, Literal

from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from app.agent.state.models import ConversationMessage, GovernedSessionState, ObservedExtraction
from app.agent.graph import GraphState
from app.agent.state.projections import project_for_ui
from app.agent.runtime.outward_names import normalize_outward_response_class
from app.agent.state.case_state import build_visible_case_narrative
from app.agent.api.deps import _LIGHT_HISTORY_MESSAGES

_log = logging.getLogger(__name__)

def _conversation_message_payload(
    *,
    role: str,
    content: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    return {
        "role": role,
        "content": content,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }

def _with_governed_conversation_turn(
    state: GovernedSessionState,
    *,
    role: str,
    content: str,
) -> GovernedSessionState:
    new_messages = list(state.conversation_messages) + [
        ConversationMessage(role=role, content=content)
    ]
    return state.model_copy(update={"conversation_messages": new_messages})

def _governed_history_slice(
    state: GovernedSessionState,
    *,
    limit: int = _LIGHT_HISTORY_MESSAGES,
) -> list[ConversationMessage]:
    return list(state.conversation_messages[-limit:])

def _serialize_governed_history_payload(
    *,
    state: GovernedSessionState,
    limit: int = _LIGHT_HISTORY_MESSAGES,
) -> list[dict[str, Any]]:
    return [
        _conversation_message_payload(role=m.role, content=m.content)
        for m in _governed_history_slice(state, limit=limit)
    ]

def _governed_working_profile_snapshot(state: GovernedSessionState) -> dict[str, Any]:
    profile: dict[str, Any] = {}
    for k, v in state.asserted.assertions.items():
        profile[k] = v.asserted_value
    working_profile = getattr(state, "working_profile", None)
    if working_profile is not None and getattr(working_profile, "live_calc_tile", None):
        profile["live_calc_tile"] = working_profile.live_calc_tile
    if working_profile is not None and getattr(working_profile, "calc_results", None):
        profile["calc_results"] = working_profile.calc_results
    return profile

def _governed_messages_as_langchain(
    state: GovernedSessionState,
) -> list[BaseMessage]:
    lc_messages: list[BaseMessage] = []
    for m in state.conversation_messages:
        if m.role == "user":
            lc_messages.append(HumanMessage(content=m.content))
        else:
            lc_messages.append(AIMessage(content=m.content))
    return lc_messages

def _governed_release_status_snapshot(state: GovernedSessionState) -> str:
    if state.rfq.rfq_ready or (state.governance.rfq_admissible and state.rfq.critical_review_passed):
        return "released"
    if state.governance.rfq_admissible:
        return "technical_release_admissible"
    return "in_progress"

def _overlay_live_governed_snapshot(
    *,
    state: Any,  # AgentState (TypedDict)
    governed_state: GovernedSessionState,
) -> None:
    state["working_profile"] = _governed_working_profile_snapshot(governed_state)
    state["messages"] = _governed_messages_as_langchain(governed_state)

    case_meta_source = getattr(governed_state, "case_meta", None)
    phase = (
        getattr(case_meta_source, "phase", None)
        or getattr(governed_state.case_lifecycle, "phase", None)
    )
    runtime_path = getattr(case_meta_source, "runtime_path", "governed_graph")
    binding_level = getattr(case_meta_source, "binding_level", "ORIENTATION")
    case_meta = {
        "case_id": getattr(case_meta_source, "case_id", None),
        "phase": phase,
        "runtime_path": runtime_path,
        "binding_level": binding_level,
    }
    case_state = {
        "case_meta": case_meta,
        "requirement_class": governed_state.governance.requirement_class,
    }
    state["case_state"] = case_state
    state["policy_path"] = runtime_path
    state["result_form"] = "governed_session"

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

    updated_governance = governed_state.governance.model_copy(
        update={
            "requirement_class": requirement_class_payload or governed_state.governance.requirement_class,
            "rfq_admissible": str(
                governance_state.get("rfq_admissibility")
                or rfq_state.get("rfq_admissibility")
                or "inadmissible"
            ) == "ready",
        }
    )

    updated_rfq = governed_state.rfq.model_copy(
        update={
            "status": str(rfq_state.get("handover_status") or rfq_state.get("status") or governed_state.rfq.status),
            "rfq_admissible": str(governance_state.get("rfq_admissibility") or rfq_state.get("rfq_admissibility") or "inadmissible") == "ready",
            "selected_manufacturer_ref": selected_manufacturer_ref or governed_state.rfq.selected_manufacturer_ref,
        }
    )

    return governed_state.model_copy(
        update={
            "governance": updated_governance,
            "rfq": updated_rfq,
        }
    )

def _current_governed_medium_label(state: GovernedSessionState | GraphState) -> str | None:
    classification_label = str(state.medium_classification.canonical_label or "").strip()
    if classification_label:
        return classification_label

    # Fallback to direct assertion if classification is missing
    # Supports both GovernedSessionState (pydantic) and GraphState (pydantic)
    # The assertions dict access is the same
    assertions = state.asserted.assertions
    medium_claim = assertions.get("medium")
    if medium_claim:
        return str(medium_claim.asserted_value)

    return None

def _truncate_light_topic(message: str, *, limit: int = 160) -> str | None:
    text = " ".join(str(message or "").split()).strip()
    return text[:limit] if text else None

def _extract_extractions_from_working_profile(
    working_profile: dict[str, Any],
) -> List[ObservedExtraction]:
    extractions = []
    for k, v in (working_profile or {}).items():
        if k in {"live_calc_tile", "calc_results"}:
            continue
        extractions.append(ObservedExtraction(field_name=k, value=v))
    return extractions

def _build_param_summary(governed_state_data: dict) -> Optional[str]:
    assertions = (governed_state_data.get("asserted") or {}).get("assertions") or {}
    if not assertions:
        return None

    lines = []
    fields = [
        ("medium", "Medium"),
        ("pressure_bar", "Druck"),
        ("temperature_c", "Temp"),
        ("shaft_diameter_mm", "Welle"),
        ("speed_rpm", "Drehzahl"),
    ]

    for field, label in fields:
        claim = assertions.get(field)
        if claim:
            val = claim.get("asserted_value")
            if val:
                lines.append(f"{label}: {val}")

    return ", ".join(lines) if lines else None

def _collect_light_missing_fields(state: GovernedSessionState) -> list[str]:
    missing = list(state.asserted.blocking_unknowns) + list(state.asserted.conflict_flags)
    return [str(m) for m in missing]

def _collect_tentative_domain_signals(state: GovernedSessionState) -> list[str]:
    signals: list[str] = []
    if state.governance.requirement_class:
        signals.append(f"requirement_class:{state.governance.requirement_class.class_id}")
    if state.governance.gov_class:
        signals.append(f"gov_class:{state.governance.gov_class}")
    return signals

def _build_light_case_summary(governed_state: GovernedSessionState) -> Optional[str]:
    parts: list[str] = []
    medium = _current_governed_medium_label(governed_state)
    if medium:
        parts.append(f"Medium: {medium}")
    if governed_state.governance.requirement_class:
        parts.append(f"Seal: {governed_state.governance.requirement_class.class_id}")
    if governed_state.governance.gov_class:
        parts.append(f"Gov: {governed_state.governance.gov_class}")

    return " | ".join(parts) if parts else None

def _light_case_active(governed_state: GovernedSessionState) -> bool:
    if governed_state.conversation_messages:
        return True
    if governed_state.asserted.assertions:
        return True
    return False

def _with_light_route_progress(
    state: GovernedSessionState,
    *,
    role: str,
    content: str,
    pre_gate_classification: str | None = None,
) -> GovernedSessionState:
    new_messages = list(state.conversation_messages) + [
        ConversationMessage(role=role, content=content)
    ]
    update_data: dict[str, Any] = {"conversation_messages": new_messages}
    if pre_gate_classification:
        update_data["case_lifecycle"] = state.case_lifecycle.model_copy(
            update={"phase": pre_gate_classification}
        )
    return state.model_copy(update=update_data)

def _compose_deterministic_governed_reply(
    *,
    response_class: str,
    deterministic_reply: str,
) -> str:
    if response_class == "governed_state_update":
        return "Ich habe die Parameter Ihrer Anfrage strukturiert erfasst und das Modell aktualisiert."
    return deterministic_reply

def _governed_state_extras_inquiry(state: GovernedSessionState) -> dict[str, Any]:
    selected = state.rfq.selected_manufacturer_ref
    return {
        "rfq_ready": state.rfq.rfq_ready,
        "selected_manufacturer": selected,
        "recipient_count": 1 if selected else 0,
        "dispatch_status": state.dispatch.status,
    }

def _governed_state_extras_shortlist(state: GovernedSessionState) -> dict[str, Any]:
    selected = state.matching.selected_manufacturer_ref
    return {
        "candidate_count": state.matching.manufacturer_count,
        "primary_candidate": selected,
    }

def _governed_structured_state(state: GovernedSessionState, response_class: str) -> dict[str, Any]:
    response_class = normalize_outward_response_class(response_class)
    view = project_for_ui(_governed_working_profile_snapshot(state))
    case_meta_source = getattr(state, "case_meta", None)
    binding_level = getattr(case_meta_source, "binding_level", "ORIENTATION")
    phase = (
        getattr(case_meta_source, "phase", None)
        or getattr(state.case_lifecycle, "phase", None)
    )
    runtime_path = getattr(case_meta_source, "runtime_path", "governed_graph")
    requirement_class = state.governance.requirement_class

    extras = {}
    if response_class == "inquiry_ready":
        extras = _governed_state_extras_inquiry(state)
    elif response_class == "candidate_shortlist":
        extras = _governed_state_extras_shortlist(state)

    return {
        "view": view,
        "narrative": build_visible_case_narrative(
            state=None,
            case_state={
                "case_meta": {
                    "binding_level": binding_level,
                    "phase": phase,
                },
                "requirement_class": requirement_class,
            },
            binding_level=binding_level,
            policy_context={
                "policy_path": runtime_path,
                "phase": phase,
                "governance_class": state.governance.gov_class,
                "response_class": response_class,
            },
        ),
        "extras": extras,
    }

def _light_structured_state(
    state: GovernedSessionState,
    *,
    governance_class: str = "B",
) -> dict[str, Any]:
    case_meta_source = getattr(state, "case_meta", None)
    phase = (
        getattr(case_meta_source, "phase", None)
        or getattr(state.case_lifecycle, "phase", None)
    )
    runtime_path = getattr(case_meta_source, "runtime_path", "conversation")
    return {
        "view": project_for_ui(_governed_working_profile_snapshot(state)),
        "narrative": build_visible_case_narrative(
            state=None,
            case_state={
                "case_meta": {"binding_level": "ORIENTATION", "phase": phase},
                "requirement_class": state.governance.requirement_class,
            },
            binding_level="ORIENTATION",
            policy_context={
                "policy_path": runtime_path,
                "phase": phase,
                "governance_class": governance_class,
            },
        ),
    }

def _fast_response_run_meta(fast_response: Any) -> dict[str, Any]:
    registration_prompt = getattr(fast_response, "registration_prompt", None)
    return {
        "fast_responder": {
            "source_classification": getattr(
                getattr(fast_response, "source_classification", None),
                "value",
                getattr(fast_response, "source_classification", None),
            ),
            "no_case_created": bool(getattr(fast_response, "no_case_created", True)),
            "registration_prompt": (
                dataclasses.asdict(registration_prompt)
                if dataclasses.is_dataclass(registration_prompt)
                else None
            ),
        }
    }

def _materialize_governed_graph_result(raw_result: object) -> GraphState:
    if isinstance(raw_result, dict) and "__interrupt__" in raw_result:
        return GraphState(**raw_result)
    if isinstance(raw_result, GraphState):
        return raw_result
    return GraphState.model_validate(raw_result)

def _parameters_public(state: GraphState) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field_name, claim in state.asserted.assertions.items():
        out[field_name] = {
            "value":      claim.asserted_value,
            "confidence": claim.confidence,
            "origin":      claim.origin,
            "unit":        claim.unit,
        }
    return out
