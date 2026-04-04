# backend/app/api/v1/projections/case_workspace.py
"""Workspace projection helpers for transitional v1 and canonical agent reads.

project_case_workspace maps the 4-pillar workspace state shape to
CaseWorkspaceProjection.

The additional synthesis helpers convert canonical SSoT AgentState into that
same 4-pillar shape so both `/api/v1/state/*` and `/api/agent/*` can expose the
same workspace contract without inventing a parallel projection path.
"""
from __future__ import annotations

from typing import Any, Dict

from app.agent.runtime.clarification_priority import select_next_focus_from_known_context
from app.agent.state.models import GovernedSessionState
from app.agent.domain.medium_registry import classify_medium_value
from app.api.v1.schemas.case_workspace import (
    ArtifactStatus,
    CaseSummary,
    CaseWorkspaceProjection,
    CommunicationContext,
    CycleInfo,
    GovernanceStatus,
    MediumCaptureSummary,
    MediumClassificationSummary,
    MediumContextSummary,
    PartnerMatchingSummary,
    RFQPackageSummary,
    RFQStatus,
    TechnicalDerivationItem,
)


def _d(value: Any) -> Dict[str, Any]:
    """Safely coerce to dict."""
    return dict(value) if isinstance(value, dict) else {}


def _ls(value: Any) -> list:
    """Safely coerce to list."""
    return list(value) if isinstance(value, list) else []


def _compact_unique_strings(items: list[str], *, limit: int = 3) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


_FIELD_LABELS: dict[str, str] = {
    "medium": "Medium",
    "pressure_bar": "Betriebsdruck",
    "temperature_c": "Betriebstemperatur",
    "movement_type": "Bewegungsart",
    "application_context": "Anwendung",
}

_MOVEMENT_LABELS: dict[str, str] = {
    "rotary": "rotierend",
    "linear": "linear",
    "static": "statisch",
}

_APPLICATION_LABELS: dict[str, str] = {
    "shaft_sealing": "Wellenabdichtung",
    "linear_sealing": "lineare Abdichtung",
    "static_sealing": "statische Abdichtung",
    "housing_sealing": "Gehaeuseabdichtung",
    "external_sealing": "nach aussen abdichten",
    "marine_propulsion": "Schiffsschraube / Wellenabdichtung",
}


def _build_confirmed_facts_summary(working_profile_pillar: Dict[str, Any]) -> list[str]:
    profile = _d(working_profile_pillar.get("engineering_profile")) or _d(
        working_profile_pillar.get("extracted_params")
    )
    facts: list[str] = []
    for key in ("movement_type", "application_context", "medium", "pressure_bar", "temperature_c"):
        value = profile.get(key)
        if value in (None, ""):
            continue
        rendered_value = value
        if key == "movement_type":
            rendered_value = _MOVEMENT_LABELS.get(str(value), value)
        elif key == "application_context":
            rendered_value = _APPLICATION_LABELS.get(str(value), value)
        facts.append(f"{_FIELD_LABELS.get(key, key)}: {rendered_value}")
    return _compact_unique_strings(facts)


def _technical_derivation_from_live_calc_tile(tile: Dict[str, Any]) -> TechnicalDerivationItem | None:
    if not tile:
        return None
    if not any(tile.get(key) is not None for key in ("v_surface_m_s", "pv_value_mpa_m_s", "dn_value")):
        return None
    return TechnicalDerivationItem(
        calc_type="rwdr",
        status=str(tile.get("status") or "insufficient_data"),
        v_surface_m_s=tile.get("v_surface_m_s"),
        pv_value_mpa_m_s=tile.get("pv_value_mpa_m_s"),
        dn_value=tile.get("dn_value"),
        notes=[str(item) for item in _ls(tile.get("notes")) if item],
    )


def _build_technical_derivations(
    *,
    working_profile_pillar: Dict[str, Any],
    system: Dict[str, Any],
) -> list[TechnicalDerivationItem]:
    items: list[TechnicalDerivationItem] = []
    for item in _ls(system.get("technical_derivations")):
        if not isinstance(item, dict):
            continue
        try:
            items.append(TechnicalDerivationItem.model_validate(item))
        except Exception:
            continue
    if items:
        return items

    live_calc_tile = _d(working_profile_pillar.get("live_calc_tile")) or _d(system.get("live_calc_tile"))
    live_calc_derivation = _technical_derivation_from_live_calc_tile(live_calc_tile)
    return [live_calc_derivation] if live_calc_derivation is not None else []


def _question_from_open_point(open_point: str | None) -> str | None:
    text = str(open_point or "").strip()
    if not text:
        return None
    return f"Koennen Sie {text} noch einordnen?"


def _is_stale_medium_open_point(label: str, *, medium_present: bool) -> bool:
    text = str(label or "").strip().casefold()
    if not medium_present or not text:
        return False
    return text == "medium" or text.startswith("medium ")


def _is_stale_rotary_open_point(label: str, *, movement_type: str | None) -> bool:
    text = str(label or "").strip().casefold()
    if str(movement_type or "").strip().casefold() != "linear":
        return False
    return any(marker in text for marker in ("rotierend", "welle", "wellen", "rwdr", "wellendichtring"))


def _filter_stale_focus_points(items: list[str], *, profile: Dict[str, Any]) -> list[str]:
    medium_present = profile.get("medium") not in (None, "")
    movement_type = str(profile.get("movement_type") or "").strip()
    result: list[str] = []
    for item in items:
        if _is_stale_medium_open_point(item, medium_present=medium_present):
            continue
        if _is_stale_rotary_open_point(item, movement_type=movement_type):
            continue
        result.append(item)
    return result


def _build_communication_context(
    *,
    phase: str | None,
    completeness: Dict[str, Any],
    governance_metadata: Dict[str, Any],
    matching_ready: bool,
    material_fit_items: list[dict[str, Any]],
    not_ready_reasons: list[str],
    rfq_ready: bool,
    rfq_status: RFQStatus,
    working_profile_pillar: Dict[str, Any],
) -> CommunicationContext:
    profile = _d(working_profile_pillar.get("engineering_profile")) or _d(
        working_profile_pillar.get("extracted_params")
    )
    missing = [str(item) for item in _ls(completeness.get("missing_critical_parameters")) if item]
    unknowns = [
        str(item)
        for item in list(
            dict.fromkeys(
                list(governance_metadata.get("unknowns_release_blocking") or [])
                + list(governance_metadata.get("unknowns_manufacturer_validation") or [])
            )
        )
        if item
    ]

    confirmed_facts_summary = _build_confirmed_facts_summary(working_profile_pillar)
    known_fields = {str(key) for key, value in profile.items() if value not in (None, "")}
    focus_priority = None
    if any(
        profile.get(key) not in (None, "")
        for key in ("movement_type", "application_context", "installation", "geometry_context", "speed_rpm", "shaft_diameter_mm")
    ):
        focus_priority = select_next_focus_from_known_context(
            known_fields=known_fields,
            medium_status="recognized" if profile.get("medium") not in (None, "") else "unknown",
            current_text=" ".join(str(item) for item in confirmed_facts_summary),
            application_anchor_present=bool(profile.get("application_context") or profile.get("movement_type") or profile.get("installation")),
            rotary_context_detected=bool(
                profile.get("movement_type") == "rotary"
                or {"speed_rpm", "shaft_diameter_mm"} & known_fields
            ),
        )

    if missing or unknowns:
        prioritized_open_points = [focus_priority.open_point_label] if focus_priority is not None else []
        open_points_summary = _compact_unique_strings(
            _filter_stale_focus_points(prioritized_open_points + missing + unknowns, profile=profile)
        )
        return CommunicationContext(
            conversation_phase="clarification",
            turn_goal="clarify_primary_open_point",
            primary_question=(
                focus_priority.question
                if focus_priority is not None
                else _question_from_open_point(open_points_summary[0] if open_points_summary else None)
            ),
            supporting_reason=(
                focus_priority.reason
                if focus_priority is not None
                else "Dann kann ich die technische Einengung sauber weiterfuehren."
            ),
            response_mode="single_question",
            confirmed_facts_summary=confirmed_facts_summary,
            open_points_summary=open_points_summary,
        )

    if rfq_ready or rfq_status.handover_ready or rfq_status.handover_initiated:
        return CommunicationContext(
            conversation_phase="rfq_handover",
            turn_goal="prepare_handover",
            response_mode="handover_summary",
            confirmed_facts_summary=confirmed_facts_summary,
            open_points_summary=_compact_unique_strings(
                [str(item) for item in list(rfq_status.open_points) + list(rfq_status.blockers) if item]
            ),
        )

    if matching_ready or material_fit_items:
        return CommunicationContext(
            conversation_phase="matching",
            turn_goal="explain_matching_result",
            response_mode="result_summary",
            confirmed_facts_summary=confirmed_facts_summary,
            open_points_summary=_compact_unique_strings(not_ready_reasons or list(rfq_status.open_points)),
        )

    mapped_phase = "exploration" if phase in {"intake", "conversation"} else "recommendation"
    return CommunicationContext(
        conversation_phase=mapped_phase,
        turn_goal="explain_governed_result",
        response_mode="guided_explanation",
        confirmed_facts_summary=confirmed_facts_summary,
        open_points_summary=_compact_unique_strings([str(item) for item in list(rfq_status.open_points) if item]),
    )


def _serialize_ssot_messages(messages: list) -> list:
    """Serialize LangChain message objects into JSON-safe dicts."""
    result = []
    for msg in (messages or []):
        msg_type = getattr(msg, "type", None)
        if msg_type is None:
            msg_type = type(msg).__name__.lower().replace("message", "")
        entry: Dict[str, Any] = {
            "type": str(msg_type),
            "content": getattr(msg, "content", "") or "",
        }
        msg_id = getattr(msg, "id", None)
        if msg_id:
            entry["id"] = msg_id
        result.append(entry)
    return result


def _serialize_governed_messages(messages: list) -> list:
    result = []
    for index, msg in enumerate(messages or []):
        if not isinstance(msg, dict):
            payload = msg.model_dump() if hasattr(msg, "model_dump") else {}
        else:
            payload = dict(msg)
        role = str(payload.get("role") or "").strip()
        content = str(payload.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        result.append(
            {
                "type": "human" if role == "user" else "ai",
                "content": content,
                "id": payload.get("created_at") or f"governed-{index}",
            }
        )
    return result


def _governed_release_status(state: GovernedSessionState) -> str:
    if state.rfq.rfq_ready:
        return "rfq_ready"
    if state.matching.status == "matched_primary_candidate" or state.governance.gov_class == "A":
        return "manufacturer_validation_required"
    if state.governance.gov_class == "B":
        return "precheck_only"
    return "inadmissible"


def _governed_working_profile(state: GovernedSessionState) -> Dict[str, Any]:
    profile: Dict[str, Any] = {}
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


def synthesize_workspace_state_from_governed(
    state: GovernedSessionState,
    *,
    chat_id: str,
) -> Dict[str, Any]:
    working_profile = _governed_working_profile(state)
    technical_derivations: list[dict[str, Any]] = []
    for result in list(getattr(state, "compute_results", []) or []):
        if not isinstance(result, dict):
            continue
        technical_derivations.append(
            {
                "calc_type": str(result.get("calc_type") or "unknown"),
                "status": str(result.get("status") or "insufficient_data"),
                "v_surface_m_s": result.get("v_surface_m_s"),
                "pv_value_mpa_m_s": result.get("pv_value_mpa_m_s"),
                "dn_value": result.get("dn_value"),
                "notes": [str(item) for item in list(result.get("notes") or []) if item],
            }
        )
    if technical_derivations:
        working_profile["live_calc_tile"] = {
            "status": technical_derivations[0].get("status"),
            "v_surface_m_s": technical_derivations[0].get("v_surface_m_s"),
            "pv_value_mpa_m_s": technical_derivations[0].get("pv_value_mpa_m_s"),
            "dn_value": technical_derivations[0].get("dn_value"),
            "notes": technical_derivations[0].get("notes") or [],
        }
    release_status = _governed_release_status(state)
    matching_state = {
        "status": state.matching.status,
        "matchability_status": state.matching.matchability_status,
        "selected_partner_id": (
            state.matching.selected_manufacturer_ref.manufacturer_name
            if state.matching.selected_manufacturer_ref is not None
            else None
        ),
        "match_candidates": [
            {
                "candidate_id": capability.manufacturer_name,
                "grade_name": (capability.grade_names[0] if capability.grade_names else None),
                "material_family": (
                    capability.material_families[0] if capability.material_families else None
                ),
                "fit_reasons": list(capability.capability_hints),
                "viability_status": "viable" if capability.qualified_for_rfq else "manufacturer_validation_required",
            }
            for capability in state.matching.manufacturer_capabilities
        ],
        "blocking_reasons": list(state.matching.matching_notes),
        "data_source": "candidate_derived",
    }
    rfq_state = {
        "status": state.rfq.status,
        "rfq_admissibility": "ready" if state.rfq.rfq_admissible else "inadmissible",
        "handover_ready": state.rfq.rfq_ready,
        "handover_status": state.rfq.handover_status,
        "rfq_ready": state.rfq.rfq_ready,
        "open_points": list(state.rfq.soft_findings),
        "blockers": list(state.rfq.blocking_findings),
        "rfq_object": dict(state.rfq.rfq_object or {}),
        "rfq_html_report_present": bool(state.rfq.handover_summary),
        "selected_partner_id": (
            state.rfq.selected_manufacturer_ref.manufacturer_name
            if state.rfq.selected_manufacturer_ref is not None
            else None
        ),
    }
    messages = _serialize_governed_messages(state.conversation_messages)
    user_turn_count = sum(1 for item in state.conversation_messages if getattr(item, "role", None) == "user")
    phase = (
        "rfq_handover"
        if state.rfq.rfq_ready
        else "matching"
        if state.matching.status == "matched_primary_candidate"
        else "recommendation"
        if state.governance.gov_class in {"A", "B"}
        else "clarification"
    )
    completeness = {
        "coverage_score": round(len(state.asserted.assertions) / 3.0, 2),
        "coverage_gaps": list(state.asserted.blocking_unknowns),
        "completeness_depth": "governed" if state.governance.gov_class in {"A", "B"} else "precheck",
        "missing_critical_parameters": list(state.asserted.blocking_unknowns),
        "analysis_complete": state.governance.gov_class in {"A", "B"},
        "recommendation_ready": state.governance.gov_class == "A",
    }
    return {
        "conversation": {
            "thread_id": chat_id,
            "messages": messages,
            "turn_count": user_turn_count,
            "max_turns": 12,
        },
        "working_profile": {
            "engineering_profile": working_profile,
            "extracted_params": working_profile,
            "completeness": completeness,
        },
        "reasoning": {
            "phase": phase,
            "last_node": "governed_live_state",
            "selected_partner_id": matching_state.get("selected_partner_id"),
            "state_revision": state.analysis_cycle,
        },
        "system": {
            "governed_output_text": "",
            "governed_output_ready": state.governance.gov_class == "A",
            "rfq_confirmed": state.rfq.rfq_ready,
            "rfq_html_report": None,
            "rfq_html_report_present": False,
            "rfq_handover_initiated": bool(state.rfq.handover_status),
            "rfq_draft": {
                "has_draft": bool(state.rfq.rfq_object),
                "rfq_id": str(state.rfq.rfq_object.get("object_version") or "") or None,
                "rfq_basis_status": state.rfq.status or release_status,
                "operating_context_redacted": dict(state.rfq.confirmed_parameters or {}),
                "manufacturer_questions_mandatory": [],
                "conflicts_visible_count": len(state.rfq.blocking_findings),
                "buyer_assumptions_acknowledged": [],
            },
            "rfq_admissibility": {
                "release_status": release_status,
                "status": state.rfq.status or ("rfq_ready" if state.rfq.rfq_ready else release_status),
                "blockers": list(state.rfq.blocking_findings),
                "open_points": list(state.rfq.soft_findings),
            },
            "answer_contract": {
                "release_status": release_status,
                "required_disclaimers": list(state.governance.validity_limits),
                "recommendation_identity": None,
                "requirement_class": (
                    state.governance.requirement_class.model_dump()
                    if state.governance.requirement_class is not None
                    else None
                ),
                "requirement_class_hint": (
                    state.governance.requirement_class.class_id
                    if state.governance.requirement_class is not None
                    else None
                ),
            },
            "governance_metadata": {
                "release_status": release_status,
                "unknowns_release_blocking": list(state.asserted.blocking_unknowns),
                "unknowns_manufacturer_validation": list(state.governance.open_validation_points),
                "assumptions_active": [],
                "scope_of_validity": list(state.governance.validity_limits),
                "required_disclaimers": list(state.governance.validity_limits),
                "review_required": False,
                "review_state": state.rfq.critical_review_status,
                "contract_obsolete": False,
            },
            "medium_capture": state.medium_capture.model_dump(),
            "medium_classification": state.medium_classification.model_dump(),
            "medium_context": state.medium_context.model_dump(),
            "technical_derivations": technical_derivations,
            "matching_state": matching_state,
            "rfq_state": rfq_state,
            "rfq_object": dict(state.rfq.rfq_object or {}),
            "manufacturer_state": {"data_source": "candidate_derived"},
        },
    }


def _build_rfq_draft_for_ssot(
    governance: Dict[str, Any],
    rfq_state: Dict[str, Any],
    handover: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the minimal rfq_draft shape expected by workspace projection."""
    release_status = governance.get("release_status") or rfq_state.get("status") or "inadmissible"
    rfq_object = _d(rfq_state.get("rfq_object"))
    payload = rfq_object or _d(handover.get("handover_payload"))
    if not payload:
        return {}
    return {
        "has_draft": True,
        "rfq_id": str(payload.get("object_version") or payload.get("object_type") or "rfq_payload_basis_v1"),
        "rfq_basis_status": release_status,
        "operating_context_redacted": dict(payload.get("confirmed_parameters") or {}),
        "manufacturer_questions_mandatory": [],
        "conflicts_visible_count": len(list(rfq_state.get("blockers") or rfq_state.get("blocking_reasons") or [])),
        "buyer_assumptions_acknowledged": list(governance.get("assumptions_active") or []),
    }


def synthesize_workspace_state_from_ssot(state: Dict[str, Any], *, chat_id: str) -> Dict[str, Any]:
    """Build the transitional 4-pillar workspace state from canonical SSoT state."""
    working_profile: Dict[str, Any] = dict(state.get("working_profile") or {})
    sealing_state: Dict[str, Any] = dict(state.get("sealing_state") or {})
    case_state: Dict[str, Any] = dict(state.get("case_state") or {})
    governance: Dict[str, Any] = dict(sealing_state.get("governance") or {})
    cycle: Dict[str, Any] = dict(sealing_state.get("cycle") or {})
    handover: Dict[str, Any] = dict(sealing_state.get("handover") or {})
    review: Dict[str, Any] = dict(sealing_state.get("review") or {})
    selection: Dict[str, Any] = dict(sealing_state.get("selection") or {})
    parameter_meta: Dict[str, Any] = dict(case_state.get("parameter_meta") or {})
    medium_capture: Dict[str, Any] = dict(state.get("medium_capture") or case_state.get("medium_capture") or {})
    medium_classification: Dict[str, Any] = dict(state.get("medium_classification") or case_state.get("medium_classification") or {})
    medium_context: Dict[str, Any] = dict(case_state.get("medium_context") or {})
    governance_state: Dict[str, Any] = dict(case_state.get("governance_state") or {})
    matching_state: Dict[str, Any] = dict(case_state.get("matching_state") or {})
    rfq_state: Dict[str, Any] = dict(case_state.get("rfq_state") or {})
    manufacturer_state: Dict[str, Any] = dict(case_state.get("manufacturer_state") or {})
    result_contract: Dict[str, Any] = dict(case_state.get("result_contract") or {})
    sealing_requirement_spec: Dict[str, Any] = dict(case_state.get("sealing_requirement_spec") or {})
    requirement_class: Dict[str, Any] = dict(
        case_state.get("requirement_class")
        or result_contract.get("requirement_class")
        or {}
    )
    recipient_selection: Dict[str, Any] = dict(
        case_state.get("recipient_selection")
        or rfq_state.get("recipient_selection")
        or {}
    )
    case_meta: Dict[str, Any] = dict(case_state.get("case_meta") or {})

    messages = _serialize_ssot_messages(state.get("messages") or [])
    release_status = governance.get("release_status")
    rfq_admissibility = governance.get("rfq_admissibility")
    phase = case_meta.get("phase") or cycle.get("phase")
    selected_partner_id = (
        recipient_selection.get("selected_partner_id")
        or selection.get("selected_partner_id")
    )
    rfq_confirmed = bool(rfq_state.get("rfq_confirmed", handover.get("rfq_confirmed", False)))
    rfq_handover_initiated = bool(
        rfq_state.get("rfq_handover_initiated", handover.get("handover_completed", False))
    )
    rfq_object = _d(rfq_state.get("rfq_object"))
    rfq_html_report = handover.get("rfq_html_report")
    rfq_html_report_present = bool(
        rfq_state.get("rfq_html_report_present", bool(rfq_html_report) or bool(rfq_object))
    )
    required_disclaimers = list(
        governance_state.get("required_disclaimers")
        or governance.get("scope_of_validity")
        or []
    )

    _ = parameter_meta
    _ = sealing_requirement_spec

    return {
        "conversation": {
            "thread_id": chat_id,
            "messages": messages,
        },
        "working_profile": {
            "engineering_profile": working_profile,
            "extracted_params": working_profile,
        },
        "reasoning": {
            "phase": phase,
            "last_node": "facade_hydration",
            "selected_partner_id": selected_partner_id,
            "state_revision": cycle.get("state_revision", 0),
        },
        "system": {
            "governed_output_text": governance.get("governed_output_text") or "",
            "governed_output_ready": release_status in ("approved", "rfq_ready"),
            "rfq_confirmed": rfq_confirmed,
            "rfq_html_report": rfq_html_report,
            "rfq_html_report_present": rfq_html_report_present,
            "rfq_handover_initiated": rfq_handover_initiated,
            "rfq_draft": _build_rfq_draft_for_ssot(governance, rfq_state, handover),
            "rfq_admissibility": {
                "release_status": release_status or "inadmissible",
                "status": rfq_state.get("status") or ("ready" if release_status == "rfq_ready" else "inadmissible"),
                "blockers": list(rfq_state.get("blockers") or rfq_state.get("blocking_reasons") or []),
                "open_points": list(rfq_state.get("open_points") or []),
            },
            "answer_contract": {
                "release_status": release_status or "inadmissible",
                "required_disclaimers": required_disclaimers,
                "recommendation_identity": result_contract.get("recommendation_identity"),
                "requirement_class": requirement_class or None,
                "requirement_class_hint": result_contract.get("requirement_class_hint"),
            },
            "governance_metadata": {
                "release_status": release_status or "inadmissible",
                "unknowns_release_blocking": governance.get("unknowns_release_blocking") or [],
                "unknowns_manufacturer_validation": governance.get("unknowns_manufacturer_validation") or [],
                "assumptions_active": governance.get("assumptions_active") or [],
                "scope_of_validity": governance_state.get("scope_of_validity") or governance.get("scope_of_validity") or [],
                "required_disclaimers": required_disclaimers,
                "review_required": bool(governance_state.get("review_required", review.get("review_required", False))),
                "review_state": governance_state.get("review_state") or review.get("review_state"),
                "contract_obsolete": bool(result_contract.get("contract_obsolete", cycle.get("contract_obsolete", False))),
            },
            "medium_capture": medium_capture,
            "medium_classification": medium_classification,
            "medium_context": medium_context,
            "matching_state": matching_state,
            "rfq_state": rfq_state,
            "rfq_object": rfq_object,
            "manufacturer_state": manufacturer_state,
        },
    }


def project_case_workspace_from_ssot(state: Dict[str, Any], *, chat_id: str) -> CaseWorkspaceProjection:
    """Project canonical SSoT AgentState into the public workspace contract."""
    return project_case_workspace(synthesize_workspace_state_from_ssot(state, chat_id=chat_id))


def project_case_workspace_from_governed_state(
    state: GovernedSessionState,
    *,
    chat_id: str,
) -> CaseWorkspaceProjection:
    """Project live governed state into the public workspace contract."""
    return project_case_workspace(synthesize_workspace_state_from_governed(state, chat_id=chat_id))


def project_case_workspace(state_values: Dict[str, Any]) -> CaseWorkspaceProjection:
    """Project a 4-pillar state dict into a CaseWorkspaceProjection.

    Understands both the legacy LangGraph pillar format and the synthesised
    SSoT format produced by _synthesize_state_response_from_ssot().
    """
    conversation = _d(state_values.get("conversation"))
    working_profile_pillar = _d(state_values.get("working_profile"))
    reasoning = _d(state_values.get("reasoning"))
    system = _d(state_values.get("system"))

    governance_metadata = _d(system.get("governance_metadata"))
    medium_capture = _d(system.get("medium_capture"))
    medium_classification = _d(system.get("medium_classification"))
    medium_context = _d(system.get("medium_context"))
    rfq_admissibility = _d(system.get("rfq_admissibility"))
    answer_contract = _d(system.get("answer_contract"))
    rfq_draft = _d(system.get("rfq_draft"))

    release_status: str = (
        governance_metadata.get("release_status")
        or answer_contract.get("release_status")
        or rfq_admissibility.get("release_status")
        or "inadmissible"
    )

    rfq_confirmed = bool(system.get("rfq_confirmed", False))
    rfq_html_report = system.get("rfq_html_report")
    rfq_html_report_present = bool(
        system.get("rfq_html_report_present", bool(rfq_html_report))
    )
    rfq_handover_initiated = bool(system.get("rfq_handover_initiated", False))
    rfq_state = _d(system.get("rfq_state"))
    matching_state = _d(system.get("matching_state"))
    manufacturer_state = _d(system.get("manufacturer_state"))
    state_revision = int(reasoning.get("state_revision") or 0)
    selected_partner_id = reasoning.get("selected_partner_id") or None

    # ── CaseSummary ────────────────────────────────────────────────────────────
    case_summary = CaseSummary(
        thread_id=conversation.get("thread_id"),
        user_id=conversation.get("user_id"),
        phase=reasoning.get("phase"),
        turn_count=int(conversation.get("turn_count") or 0),
        max_turns=int(conversation.get("max_turns") or 12),
    )

    # ── GovernanceStatus ───────────────────────────────────────────────────────
    governance_status = GovernanceStatus(
        release_status=release_status,
        unknowns_release_blocking=list(
            governance_metadata.get("unknowns_release_blocking") or []
        ),
        unknowns_manufacturer_validation=list(
            governance_metadata.get("unknowns_manufacturer_validation") or []
        ),
        assumptions_active=list(
            governance_metadata.get("assumptions_active") or []
        ),
        required_disclaimers=list(
            answer_contract.get("required_disclaimers") or []
        ),
    )

    # ── RFQStatus ──────────────────────────────────────────────────────────────
    rfq_ready = bool(rfq_admissibility.get("status") == "rfq_ready" or release_status == "rfq_ready")
    handover_ready = bool(
        rfq_state.get("handover_ready", rfq_confirmed and rfq_html_report_present and bool(selected_partner_id))
    )
    rfq_status = RFQStatus(
        admissibility_status=rfq_admissibility.get("status") or release_status,
        release_status=release_status,
        rfq_confirmed=rfq_confirmed,
        rfq_ready=rfq_ready,
        handover_ready=handover_ready,
        handover_initiated=rfq_handover_initiated,
        blockers=list(rfq_admissibility.get("blockers") or []),
        open_points=list(rfq_admissibility.get("open_points") or []),
        has_html_report=rfq_html_report_present,
    )

    # ── RFQPackageSummary ──────────────────────────────────────────────────────
    rfq_package = RFQPackageSummary(
        has_draft=bool(rfq_draft.get("has_draft", False)),
        rfq_id=rfq_draft.get("rfq_id"),
        rfq_basis_status=rfq_draft.get("rfq_basis_status") or release_status,
        operating_context_redacted=dict(rfq_draft.get("operating_context_redacted") or {}),
        manufacturer_questions_mandatory=list(rfq_draft.get("manufacturer_questions_mandatory") or []),
        conflicts_visible_count=int(rfq_draft.get("conflicts_visible_count") or 0),
        buyer_assumptions_acknowledged=list(rfq_draft.get("buyer_assumptions_acknowledged") or []),
    )

    # ── ArtifactStatus ─────────────────────────────────────────────────────────
    artifact_status = ArtifactStatus(
        has_rfq_draft=bool(rfq_draft.get("has_draft", False)),
    )

    # ── CycleInfo ──────────────────────────────────────────────────────────────
    cycle_info = CycleInfo(
        state_revision=state_revision,
        derived_artifacts_stale=bool(reasoning.get("derived_artifacts_stale", False)),
    )

    # ── PartnerMatchingSummary ─────────────────────────────────────────────────
    matching_ready = bool(
        matching_state.get("status") == "matched_primary_candidate"
        or matching_state.get("matchability_status") == "ready_for_matching"
    )
    not_ready_reasons = [
        str(item)
        for item in list(dict.fromkeys(_ls(matching_state.get("blocking_reasons"))))
        if item
    ]
    matchability_status = str(matching_state.get("matchability_status") or "").strip()
    if not matching_ready and not not_ready_reasons and matchability_status and matchability_status != "ready_for_matching":
        not_ready_reasons = [matchability_status]
    material_fit_items = []
    for candidate in _ls(matching_state.get("match_candidates")):
        if not isinstance(candidate, dict):
            continue
        fit_reasons = [str(item) for item in _ls(candidate.get("fit_reasons")) if item]
        block_reason = str(candidate.get("block_reason") or "").strip()
        fit_basis = "; ".join(fit_reasons) or block_reason or "governed_capability_fit"
        material_fit_items.append(
            {
                "material": str(
                    candidate.get("grade_name")
                    or candidate.get("material_family")
                    or candidate.get("candidate_id")
                    or ""
                ),
                "cluster": str(candidate.get("viability_status") or "viable"),
                "specificity": "compound_specific" if candidate.get("grade_name") else "family_only",
                "requires_validation": bool(
                    str(candidate.get("viability_status") or "viable") != "viable"
                    or release_status == "manufacturer_validation_required"
                ),
                "fit_basis": fit_basis,
                "grounded_facts": [],
            }
        )
    open_manufacturer_questions = [
        str(item)
        for item in list(
            dict.fromkeys(
                list(rfq_draft.get("manufacturer_questions_mandatory") or [])
                + list(rfq_state.get("open_points") or [])
            )
        )
        if item
    ]
    partner_matching = PartnerMatchingSummary(
        matching_ready=matching_ready,
        not_ready_reasons=not_ready_reasons,
        material_fit_items=material_fit_items,
        open_manufacturer_questions=open_manufacturer_questions,
        selected_partner_id=selected_partner_id,
        data_source=str(
            matching_state.get("data_source")
            or manufacturer_state.get("data_source")
            or "candidate_derived"
        ),
    )
    communication_context = _build_communication_context(
        phase=reasoning.get("phase"),
        completeness=working_profile_pillar.get("completeness") or {},
        governance_metadata=governance_metadata,
        matching_ready=matching_ready,
        material_fit_items=material_fit_items,
        not_ready_reasons=not_ready_reasons,
        rfq_ready=rfq_ready,
        rfq_status=rfq_status,
        working_profile_pillar=working_profile_pillar,
    )
    primary_raw_text = medium_capture.get("primary_raw_text")
    if not medium_classification and primary_raw_text:
        derived_medium = classify_medium_value(str(primary_raw_text))
        medium_classification = {
            "canonical_label": derived_medium.canonical_label,
            "family": derived_medium.family,
            "confidence": derived_medium.confidence,
            "status": derived_medium.status,
            "normalization_source": derived_medium.normalization_source,
            "mapping_confidence": derived_medium.mapping_confidence,
            "matched_alias": derived_medium.matched_alias,
            "source_registry_key": derived_medium.registry_key,
            "followup_question": derived_medium.followup_question,
        }
    medium_capture_summary = MediumCaptureSummary(
        raw_mentions=[str(item) for item in _ls(medium_capture.get("raw_mentions")) if item],
        primary_raw_text=primary_raw_text,
        source_turn_ref=medium_capture.get("source_turn_ref"),
        source_turn_index=medium_capture.get("source_turn_index"),
    )
    medium_classification_summary = MediumClassificationSummary(
        canonical_label=medium_classification.get("canonical_label"),
        family=str(medium_classification.get("family") or "unknown"),
        confidence=str(medium_classification.get("confidence") or "low"),
        status=str(medium_classification.get("status") or "unavailable"),
        normalization_source=medium_classification.get("normalization_source"),
        mapping_confidence=medium_classification.get("mapping_confidence"),
        matched_alias=medium_classification.get("matched_alias"),
        source_registry_key=medium_classification.get("source_registry_key"),
        followup_question=medium_classification.get("followup_question"),
    )
    medium_context_summary = MediumContextSummary(
        medium_label=medium_context.get("medium_label"),
        status=str(medium_context.get("status") or "unavailable"),
        scope=str(medium_context.get("scope") or "orientierend"),
        summary=medium_context.get("summary"),
        properties=[str(item) for item in _ls(medium_context.get("properties")) if item],
        challenges=[str(item) for item in _ls(medium_context.get("challenges")) if item],
        followup_points=[str(item) for item in _ls(medium_context.get("followup_points")) if item],
        confidence=medium_context.get("confidence"),
        source_type=medium_context.get("source_type"),
        not_for_release_decisions=bool(medium_context.get("not_for_release_decisions", True)),
        disclaimer=medium_context.get("disclaimer"),
    )
    technical_derivations = _build_technical_derivations(
        working_profile_pillar=working_profile_pillar,
        system=system,
    )

    return CaseWorkspaceProjection(
        case_summary=case_summary,
        governance_status=governance_status,
        rfq_status=rfq_status,
        rfq_package=rfq_package,
        artifact_status=artifact_status,
        cycle_info=cycle_info,
        partner_matching=partner_matching,
        communication_context=communication_context,
        medium_capture=medium_capture_summary,
        medium_classification=medium_classification_summary,
        medium_context=medium_context_summary,
        technical_derivations=technical_derivations,
    )
