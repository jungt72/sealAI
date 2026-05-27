import logging
import json
import dataclasses
from datetime import datetime, timezone
from typing import Any, List, Optional, Literal

from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from app.agent.state.models import CaseEvent, ConversationMessage, GovernedSessionState, ObservedExtraction
from app.agent.graph import GraphState
from app.agent.runtime.answer_trace import build_answer_trace, with_answer_trace
from app.agent.state.projections import project_for_ui
from app.agent.runtime.outward_names import normalize_outward_response_class
from app.agent.state.case_state import build_visible_case_narrative
from app.agent.api.deps import _LIGHT_HISTORY_MESSAGES
from app.agent.communication.templates import render_communication_template

_log = logging.getLogger(__name__)

_LIGHT_CASE_SUMMARY_FIELD_LABELS: dict[str, str] = {
    "medium": "Medium",
    "pressure_bar": "Druck",
    "pressure_system_bar": "Systemdruck",
    "pressure_at_seal_bar": "Druck an der Dichtstelle",
    "pressure_delta_bar": "Differenzdruck",
    "temperature_c": "Temperatur",
    "shaft_diameter_mm": "Welle",
    "speed_rpm": "Drehzahl",
    "sealing_type": "Dichtungstyp",
    "motion_type": "Bewegung",
    "installation": "Anwendung",
    "counterface_surface": "Gegenlauf",
    "counterface_material": "Gegenlaufwerkstoff",
    "geometry_context": "Geometrie",
    "failure_mode": "Ziel/Fehlerbild",
    "application": "Anwendung",
}

_LIGHT_CASE_SUMMARY_UNITS: dict[str, str] = {
    "pressure_bar": "bar",
    "pressure_system_bar": "bar",
    "pressure_at_seal_bar": "bar",
    "pressure_delta_bar": "bar",
    "temperature_c": "C",
    "shaft_diameter_mm": "mm",
    "speed_rpm": "rpm",
}

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



def _with_case_event(
    state: GovernedSessionState,
    *,
    event: CaseEvent,
) -> GovernedSessionState:
    """Append one v0.4 CaseEvent without mutating authoritative state slices."""

    return state.model_copy(update={"case_events": list(state.case_events) + [event]})

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

def _light_summary_label(field_name: str) -> str:
    return _LIGHT_CASE_SUMMARY_FIELD_LABELS.get(field_name, field_name.replace("_", " "))

def _safe_model_dump(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except TypeError:
            return value.model_dump()
        except Exception:  # noqa: BLE001
            return {}
    return {}

def _light_value_text(value: Any, *, limit: int = 180) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "ja" if value else "nein"
    if isinstance(value, float):
        text = f"{value:g}"
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, str):
        text = " ".join(value.split()).strip()
    elif isinstance(value, (list, tuple, set)):
        text = ", ".join(_light_value_text(item, limit=80) for item in value if _light_value_text(item, limit=80))
    elif isinstance(value, dict):
        try:
            text = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
        except Exception:  # noqa: BLE001
            text = str(value)
    else:
        text = str(value)
    text = " ".join(str(text or "").split()).strip()
    if len(text) > limit:
        return f"{text[:limit - 1].rstrip()}..."
    return text

def _append_unique_light_item(items: list[str], value: Any, *, limit: int = 180) -> None:
    text = _light_value_text(value, limit=limit)
    if text and text not in items:
        items.append(text)

def _light_asserted_parameters(state: GovernedSessionState) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    for field_name, claim in list(state.asserted.assertions.items()):
        value = getattr(claim, "asserted_value", None)
        if value in (None, ""):
            continue
        engineering_value = getattr(claim, "engineering_value", None)
        unit = getattr(engineering_value, "unit", None) or _LIGHT_CASE_SUMMARY_UNITS.get(field_name)
        value_text = _light_value_text(value)
        if unit and value_text and not value_text.lower().endswith(str(unit).lower()):
            value_text = f"{value_text} {unit}"
        parameters.append(
            {
                "field": field_name,
                "label": _light_summary_label(field_name),
                "value": value_text,
                "status": getattr(claim, "status", None),
                "confidence": getattr(claim, "confidence", None),
                "provenance": getattr(claim, "provenance", None),
            }
        )
    return parameters[:16]

def _light_observed_candidates(state: GovernedSessionState) -> list[dict[str, Any]]:
    asserted_fields = set(state.asserted.assertions.keys())
    candidates: list[dict[str, Any]] = []
    for extraction in reversed(list(state.observed.raw_extractions or [])):
        field_name = str(getattr(extraction, "field_name", "") or "")
        if not field_name or field_name in asserted_fields:
            continue
        raw_value = getattr(extraction, "raw_value", None)
        if raw_value in (None, ""):
            continue
        raw_unit = getattr(extraction, "raw_unit", None)
        value_text = _light_value_text(raw_value)
        if raw_unit and value_text and not value_text.lower().endswith(str(raw_unit).lower()):
            value_text = f"{value_text} {raw_unit}"
        item = {
            "field": field_name,
            "label": _light_summary_label(field_name),
            "value": value_text,
            "confidence": getattr(extraction, "confidence", None),
            "turn_index": getattr(extraction, "turn_index", None),
        }
        if item not in candidates:
            candidates.append(item)
        if len(candidates) >= 8:
            break
    return list(reversed(candidates))

def _light_calculation_results(state: GovernedSessionState) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for result in list(getattr(state.calculation, "results", []) or []):
        outputs = _safe_model_dump(getattr(result, "outputs", None))
        units = _safe_model_dump(getattr(result, "units", None))
        output_parts: list[str] = []
        for key, value in list(outputs.items())[:4]:
            text = _light_value_text(value, limit=80)
            unit = units.get(key)
            if unit and text and not text.lower().endswith(str(unit).lower()):
                text = f"{text} {unit}"
            if text:
                output_parts.append(f"{_light_summary_label(str(key))}: {text}")
        results.append(
            {
                "id": getattr(result, "calculation_id", "") or getattr(result, "calculator", "") or "calculation",
                "status": getattr(result, "status", None),
                "claim_level": getattr(result, "claim_level", None),
                "outputs": output_parts,
                "missing_inputs": list(getattr(result, "missing_inputs", []) or [])[:6],
                "limitations": list(getattr(result, "limitations", []) or [])[:4],
                "signals": list(getattr(result, "engineering_signals", []) or [])[:4],
            }
        )
        if len(results) >= 6:
            break
    return results

def _light_plausibility_items(state: GovernedSessionState) -> list[str]:
    items: list[str] = []
    for finding in list(getattr(state.challenge, "findings", []) or []):
        title = getattr(finding, "title", "")
        summary = getattr(finding, "summary", "")
        severity = getattr(finding, "severity", "")
        status = getattr(finding, "status", "")
        if status and str(status) not in {"open", "watch"}:
            continue
        _append_unique_light_item(items, f"{severity}: {title} - {summary}".strip(" -"))
        if len(items) >= 6:
            return items
    for risk in list(getattr(state.engineering, "risk_findings", []) or []):
        payload = _safe_model_dump(risk)
        title = payload.get("title") or payload.get("risk_name") or payload.get("name") or payload.get("risk")
        summary = payload.get("summary") or payload.get("explanation_short") or payload.get("reason")
        severity = payload.get("severity") or payload.get("score") or payload.get("label")
        _append_unique_light_item(items, f"{severity}: {title} - {summary}".strip(" -"))
        if len(items) >= 6:
            return items
    for value in (
        list(getattr(state.asserted, "blocking_unknowns", []) or [])
        + list(getattr(state.asserted, "conflict_flags", []) or [])
        + list(getattr(state.governance, "preselection_blockers", []) or [])
        + list(getattr(state.governance, "compliance_blockers", []) or [])
        + list(getattr(state.governance, "open_validation_points", []) or [])
        + list(getattr(state.evidence, "evidence_gaps", []) or [])
        + list(getattr(state.calculation, "guardrail_violations", []) or [])
    ):
        _append_unique_light_item(items, value)
        if len(items) >= 8:
            break
    return items

def _light_next_questions(state: GovernedSessionState) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []

    def add(question: Any, reason: Any = "", source: str = "") -> None:
        text = _light_value_text(question, limit=220).rstrip()
        if not text:
            return
        if text and not text.endswith("?"):
            text = f"{text}?"
        if any(item["question"] == text for item in questions):
            return
        questions.append(
            {
                "question": text,
                "reason": _light_value_text(reason, limit=180),
                "source": source,
            }
        )

    pending = getattr(state, "pending_question", None)
    if pending is not None:
        add(
            getattr(pending, "question_text", None),
            f"offenes Feld: {getattr(pending, 'target_field', '')}",
            "pending_question",
        )
    challenge_question = getattr(getattr(state, "challenge", None), "next_best_question", None)
    if challenge_question is not None:
        add(
            getattr(challenge_question, "question", None),
            getattr(challenge_question, "reason", None),
            "challenge_engine",
        )
    progress = getattr(state, "exploration_progress", None)
    if progress is not None:
        add(
            getattr(progress, "next_best_question_candidate", None),
            getattr(progress, "next_best_question_reason", None),
            "exploration_progress",
        )
    plan = _safe_model_dump(getattr(state, "v91_question_plan", None))
    for key in ("next_question", "primary_question", "question"):
        add(plan.get(key), plan.get("reason") or plan.get("rationale"), "question_plan")
    for item in list(plan.get("questions") or plan.get("items") or [])[:3]:
        if isinstance(item, dict):
            add(item.get("question") or item.get("text"), item.get("reason"), "question_plan")
    return questions[:4]

def _legacy_light_case_summary(governed_state: GovernedSessionState) -> Optional[str]:
    parts: list[str] = []
    medium = _current_governed_medium_label(governed_state)
    if medium:
        parts.append(f"Medium: {medium}")
    if governed_state.governance.requirement_class:
        parts.append(f"Seal: {governed_state.governance.requirement_class.class_id}")
    if governed_state.governance.gov_class:
        parts.append(f"Gov: {governed_state.governance.gov_class}")
    return " | ".join(parts) if parts else None

def _build_light_case_summary(governed_state: GovernedSessionState) -> Optional[str]:
    context = {
        "legacy_summary": _legacy_light_case_summary(governed_state),
        "asserted_parameters": _light_asserted_parameters(governed_state),
        "observed_candidates": _light_observed_candidates(governed_state),
        "calculation_results": _light_calculation_results(governed_state),
        "plausibility_items": _light_plausibility_items(governed_state),
        "next_questions": _light_next_questions(governed_state),
        "governance": {
            "requirement_class": (
                governed_state.governance.requirement_class.class_id
                if governed_state.governance.requirement_class
                else None
            ),
            "gov_class": governed_state.governance.gov_class,
            "rfq_admissible": governed_state.governance.rfq_admissible,
            "validity_limits": list(governed_state.governance.validity_limits or [])[:6],
            "open_validation_points": list(governed_state.governance.open_validation_points or [])[:6],
        },
        "engine_status": {
            "engineering": getattr(governed_state.engineering, "status", None),
            "calculation": getattr(governed_state.calculation, "status", None),
            "challenge": getattr(governed_state.challenge, "status", None),
            "case_phase": getattr(governed_state.case_lifecycle, "phase", None),
        },
    }
    has_context = any(
        bool(context.get(key))
        for key in (
            "legacy_summary",
            "asserted_parameters",
            "observed_candidates",
            "calculation_results",
            "plausibility_items",
            "next_questions",
        )
    )
    if not has_context:
        return None
    return render_communication_template(
        "free_conversation_engine_context",
        context,
        fallback=_legacy_light_case_summary(governed_state) or "",
    ) or None

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
    existing_messages = list(state.conversation_messages)
    normalized_content = str(content or "").strip()
    if (
        existing_messages
        and existing_messages[-1].role == role
        and existing_messages[-1].content == normalized_content
    ):
        new_messages = existing_messages
    else:
        new_messages = existing_messages + [
            ConversationMessage(role=role, content=normalized_content)
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
    view = project_for_ui(state).model_dump(mode="json")
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
        "view": project_for_ui(state).model_dump(mode="json"),
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
    return with_answer_trace(
        {
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
        },
        build_answer_trace(
            reply_source="fast_responder",
            answer_markdown_source="fast_responder",
            final_visible_source="answer_markdown",
        ),
    )


def _knowledge_response_run_meta(knowledge_response: Any) -> dict[str, Any]:
    citations = [
        citation.as_dict()
        if hasattr(citation, "as_dict")
        else dataclasses.asdict(citation)
        for citation in tuple(getattr(knowledge_response, "citations", ()) or ())
        if dataclasses.is_dataclass(citation)
    ]
    answer_view = getattr(knowledge_response, "knowledge_answer_view", None)
    answer_contract = (
        answer_view.as_dict()
        if hasattr(answer_view, "as_dict")
        else None
    )
    rag_audit = _knowledge_rag_audit(
        knowledge_response=knowledge_response,
        answer_contract=answer_contract,
        citations=citations,
    )
    meta = {
        "knowledge_service": {
            "source_classification": getattr(
                getattr(knowledge_response, "source_classification", None),
                "value",
                getattr(knowledge_response, "source_classification", None),
            ),
            "output_class": getattr(knowledge_response, "output_class", "conversational_answer"),
            "no_case_created": bool(getattr(knowledge_response, "no_case_created", True)),
            "citations": citations,
            "knowledge_answer": answer_contract,
            "rag_audit": rag_audit,
        }
    }
    meta["rag_audit"] = rag_audit
    meta["knowledge_sources"] = rag_audit.get("sources", [])
    knowledge_debug = getattr(knowledge_response, "knowledge_debug", None)
    if isinstance(knowledge_debug, dict):
        meta["knowledge_debug"] = knowledge_debug
    answer_trace = getattr(knowledge_response, "answer_trace", None)
    rag_trace = {
        "rag_required": True,
        "rag_lookup_attempted": rag_audit.get("lookup_attempted"),
        "rag_answer_found": rag_audit.get("answer_found"),
        "rag_miss": rag_audit.get("rag_miss"),
        "rag_source_count": rag_audit.get("source_count"),
        "rag_evidence_count": rag_audit.get("evidence_count"),
        "rag_fallback_used": rag_audit.get("fallback_used"),
        "rag_miss_policy": rag_audit.get("miss_policy"),
        "rag_grounding_strategy": rag_audit.get("grounding_strategy"),
    }
    if isinstance(answer_trace, dict):
        enriched_trace = dict(answer_trace)
        enriched_trace.update(rag_trace)
        meta = with_answer_trace(meta, enriched_trace)
    else:
        base_trace = build_answer_trace(
            reply_source="knowledge_service",
            answer_markdown_source="knowledge_service",
            final_visible_source="answer_markdown",
        )
        base_trace.update(rag_trace)
        meta = with_answer_trace(
            meta,
            base_trace,
        )
    return meta

def _knowledge_rag_audit(
    *,
    knowledge_response: Any,
    answer_contract: dict[str, Any] | None,
    citations: list[dict[str, Any]],
) -> dict[str, Any]:
    contract = dict(answer_contract or {})
    sources = _knowledge_source_summaries(contract.get("sources") or citations)
    evidence_items = [
        item
        for item in list(contract.get("knowledge_evidence") or [])
        if isinstance(item, dict)
    ]
    source_types = sorted(
        {
            str(item.get("source_type") or "unknown")
            for item in [*sources, *evidence_items]
            if str(item.get("source_type") or "").strip()
        }
    )
    validation_statuses = sorted(
        {
            str(item.get("validation_status") or "")
            for item in sources
            if str(item.get("validation_status") or "").strip()
        }
    )
    lookup_attempted = bool(contract.get("rag_lookup_attempted"))
    answer_found = bool(contract.get("rag_answer_found"))
    rag_miss = bool(contract.get("rag_miss"))
    fallback_used = bool(contract.get("fallback_used"))
    answer_available = bool(contract.get("answer_available"))
    source_type = str(contract.get("source_type") or "")
    grounding_strategy, miss_policy = _knowledge_grounding_strategy(
        answer_found=answer_found,
        rag_miss=rag_miss,
        fallback_used=fallback_used,
        answer_available=answer_available,
        source_type=source_type,
        evidence_items=evidence_items,
    )
    source_count = len(sources)
    evidence_count = len(evidence_items)
    return {
        "contract_version": "sealai_rag_audit_v1",
        "retrieval_path": "knowledge_service",
        "required_for_technical_knowledge": True,
        "lookup_attempted": lookup_attempted,
        "answer_found": answer_found,
        "rag_miss": rag_miss,
        "source_count": source_count,
        "evidence_count": evidence_count,
        "source_types": source_types,
        "validation_statuses": validation_statuses,
        "fallback_allowed": bool(contract.get("fallback_allowed")),
        "fallback_used": fallback_used,
        "fallback_error": contract.get("fallback_error"),
        "missing_reason": contract.get("missing_reason"),
        "next_step": contract.get("next_step"),
        "user_visible_label": contract.get("user_visible_label"),
        "grounding_strategy": grounding_strategy,
        "miss_policy": miss_policy,
        "sources": sources[:8],
        "evidence_preview": [
            {
                "title": _light_value_text(item.get("title"), limit=120),
                "source_type": _light_value_text(item.get("source_type"), limit=80),
                "source_name": _light_value_text(item.get("source_name"), limit=120),
                "confidence": item.get("confidence"),
                "excerpt": _light_value_text(item.get("content"), limit=240),
            }
            for item in evidence_items[:6]
        ],
        "response_output_class": getattr(
            knowledge_response,
            "output_class",
            "conversational_answer",
        ),
    }

def _knowledge_grounding_strategy(
    *,
    answer_found: bool,
    rag_miss: bool,
    fallback_used: bool,
    answer_available: bool,
    source_type: str,
    evidence_items: list[dict[str, Any]],
) -> tuple[str, str]:
    evidence_source_types = {
        str(item.get("source_type") or "").strip()
        for item in evidence_items
        if str(item.get("source_type") or "").strip()
    }
    if answer_found:
        return "rag_grounded", "source_grounded"
    if fallback_used:
        return "llm_fallback_unvalidated", "llm_fallback_must_remain_unvalidated"
    if source_type == "system_derived" or "deterministic" in evidence_source_types:
        return (
            "deterministic_orientation_without_rag_hit",
            "deterministic_orientation_limited_no_release",
        )
    if rag_miss and not answer_available:
        return "rag_miss_no_answer", "no_technical_claim_on_miss"
    if rag_miss:
        return "rag_miss_answer_limited", "limited_answer_without_rag_source"
    return "source_grounded_or_deterministic", "source_grounded_or_deterministic"

def _knowledge_source_summaries(raw_sources: Any) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, raw in enumerate(list(raw_sources or []), start=1):
        if hasattr(raw, "as_dict"):
            raw = raw.as_dict()
        elif dataclasses.is_dataclass(raw):
            raw = dataclasses.asdict(raw)
        if not isinstance(raw, dict):
            continue
        summaries.append(
            {
                "rank": raw.get("rank") or index,
                "source_id": _light_value_text(raw.get("source_id"), limit=120),
                "title": _light_value_text(raw.get("title"), limit=180),
                "url": _light_value_text(raw.get("url"), limit=240),
                "source_type": _light_value_text(raw.get("source_type"), limit=80),
                "validation_status": _light_value_text(
                    raw.get("validation_status"),
                    limit=80,
                ),
                "evidence_ref": _light_value_text(raw.get("evidence_ref"), limit=120),
                "confidence": raw.get("confidence"),
                "excerpt": _light_value_text(raw.get("excerpt"), limit=260),
            }
        )
    return summaries

def _state_from_interrupt_payload(interrupts: object) -> GraphState | None:
    if interrupts is None:
        return None
    try:
        interrupt_items = list(interrupts)  # type: ignore[arg-type]
    except TypeError:
        interrupt_items = [interrupts]

    for interrupt_item in interrupt_items:
        payload = getattr(interrupt_item, "value", interrupt_item)
        if not isinstance(payload, dict):
            continue
        state_payload = payload.get("state")
        if isinstance(state_payload, GraphState):
            return state_payload
        if isinstance(state_payload, dict):
            return GraphState.model_validate(state_payload)
    return None


def _materialize_governed_graph_result(raw_result: object) -> GraphState:
    if isinstance(raw_result, dict) and "__interrupt__" in raw_result:
        interrupted_state = _state_from_interrupt_payload(raw_result.get("__interrupt__"))
        if interrupted_state is not None:
            return interrupted_state
        return GraphState()
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
