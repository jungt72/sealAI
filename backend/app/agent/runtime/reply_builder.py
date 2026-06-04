"""
Reply Builder — deterministic reply constants and structured reply assembly.

Builds the final user-visible reply text from selection state projections.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agent.runtime.boundaries import build_boundary_block
from app.agent.runtime.clarification import _build_missing_data_reply, _build_missing_inputs_text
from app.agent.state.projections_extended import (
    INVARIANT_BLOCKED_REPLY,
    OUT_OF_DOMAIN_REPLY,
    THRESHOLD_ESCALATION_REPLY,
    UNRESOLVED_CONFLICT_REPLY,
    _build_conflict_correction_note,
    _build_domain_scope_note,
    _build_evidence_binding_note,
    _build_integrity_note,
    build_actionability_projection,
    build_case_summary_projection,
    build_state_trace_audit_projection,
    get_case_status,
    get_next_case_step,
    get_primary_allowed_action,
    get_primary_trace_reason,
    has_active_blockers,
    project_projection_invariants,
)

# Avoid unused import warnings — these are re-exported for callers
_ = (build_actionability_projection, get_next_case_step)


SAFEGUARDED_WITHHELD_REPLY = "Eine Auslegungsempfehlung kann auf Basis der vorliegenden Angaben derzeit nicht ausgegeben werden."
NO_CANDIDATES_REPLY = "Für diese Anfrage konnten keine technisch geeigneten Referenzdaten gefunden werden."
NO_VIABLE_CANDIDATES_REPLY = "Die vorliegenden Referenzkandidaten erfüllen die technischen Anforderungen nicht vollständig. Eine gebundene Auslegung ist derzeit nicht möglich."
NEUTRAL_SCOPE_REPLY = (
    "Technischer Auslegungsbereich vorbereitet. Die Freigabe bleibt an die vollständige "
    "technische Überprüfung und dokumentierte Offene Punkte gebunden."
)
MANUFACTURER_VALIDATION_REPLY = (
    "Technischer Eignungsraum vorbereitet. Hersteller-Validierung ist erforderlich; "
    "keine Material- oder Compound-Freigabe wird ausgegeben."
)
PRECHECK_ONLY_REPLY = (
    "Technischer Vorprüfstand erreicht. Weitere fachliche Klärung ist erforderlich."
)
AMBIGUOUS_CANDIDATE_REPLY = (
    "Es liegen mehrere technisch tragfähige Kandidaten vor. "
    "Eine eindeutige Auslegungsempfehlung kann derzeit nicht ausgegeben werden."
)
REVIEW_PENDING_REPLY = (
    "Technische Vorbeurteilung liegt vor. "
    "Freigabe ist zurückgestellt — ein manueller Experten-Review ist erforderlich."
)
EVIDENCE_MISSING_REPLY = (
    "Die technischen Betriebsparameter sind erfasst. "
    "Qualifizierte technische Referenzdaten für diese Anfrage sind derzeit nicht verfügbar — "
    "eine Auslegungsempfehlung ohne qualifizierte Referenzbasis ist nicht möglich."
)
ESCALATION_NEEDED_REPLY = (
    "Der Fall erfordert eine fachliche Eskalation. "
    "Eine Auslegungsempfehlung kann aus dem aktuellen Zustand nicht ausgegeben werden."
)
DEMO_DATA_QUARANTINE_REPLY = (
    "Die Anfrage enthält synthetische Referenzdaten. "
    "Eine Auslegungsempfehlung ist zurückgestellt, bis echte qualifizierte Referenzdaten vorliegen."
)

_STRUCTURED_API_EXPOSURE_KEYS: tuple[str, ...] = (
    "case_status",
    "output_status",
    "next_step",
    "primary_allowed_action",
    "active_blockers",
)


def _resolve_runtime_dispatch_source(canonical_case_state: Dict[str, Any]) -> Dict[str, Any]:
    canonical_state = dict(canonical_case_state or {})
    dispatch_intent = dict(canonical_state.get("dispatch_intent") or {})
    if dispatch_intent:
        return dispatch_intent
    rfq_state = dict(canonical_state.get("rfq_state") or {})
    return dict(rfq_state.get("rfq_dispatch") or {})


def _build_recommendation_artifact(
    selection_status: str,
    winner_candidate_id: Optional[str],
    candidate_projection: Optional[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    viable_candidate_ids: List[str],
    blocked_candidates: List[Dict[str, str]],
    evidence_basis: List[str],
    evidence_status: str,
    provenance_refs: List[str],
    conflict_status: str,
    integrity_status: str,
    domain_scope_status: str,
    threshold_status: str,
    release_status: str,
    rfq_admissibility: str,
    specificity_level: str,
    output_blocked: bool,
    readiness_status: str,
    blocking_reason: str,
    rationale_summary: str,
    trace_refs: List[str],
) -> Dict[str, Any]:
    return {
        "selection_status": selection_status,
        "winner_candidate_id": winner_candidate_id,
        "candidate_projection": candidate_projection,
        "candidate_ids": [candidate["candidate_id"] for candidate in candidates],
        "viable_candidate_ids": viable_candidate_ids,
        "blocked_candidates": blocked_candidates,
        "evidence_basis": evidence_basis,
        "evidence_status": evidence_status,
        "provenance_refs": provenance_refs,
        "rationale_basis": [
            selection_status,
            readiness_status,
            evidence_status,
            conflict_status,
            integrity_status,
            domain_scope_status,
            threshold_status,
            "non_binding_projection",
        ],
        "conflict_status": conflict_status,
        "integrity_status": integrity_status,
        "domain_scope_status": domain_scope_status,
        "threshold_status": threshold_status,
        "release_status": release_status,
        "rfq_admissibility": rfq_admissibility,
        "specificity_level": specificity_level,
        "output_blocked": output_blocked,
        "binding_level": "non_binding",
        "readiness_status": readiness_status,
        "blocking_reason": blocking_reason,
        "rationale_summary": rationale_summary,
        "trace_provenance_refs": trace_refs,
    }


def _artifact_is_aligned(selection_state: Dict[str, Any], artifact: Dict[str, Any]) -> bool:
    if not artifact:
        return False
    return (
        artifact.get("selection_status") == selection_state.get("selection_status")
        and artifact.get("winner_candidate_id") == selection_state.get("winner_candidate_id")
        and artifact.get("viable_candidate_ids") == selection_state.get("viable_candidate_ids")
        and artifact.get("blocked_candidates") == selection_state.get("blocked_candidates")
        and artifact.get("release_status") == selection_state.get("release_status")
        and artifact.get("rfq_admissibility") == selection_state.get("rfq_admissibility")
        and artifact.get("specificity_level") == selection_state.get("specificity_level")
        and artifact.get("output_blocked") == selection_state.get("output_blocked")
        and artifact.get("binding_level") in {None, "non_binding"}
    )


def _find_candidate(
    candidates: List[Dict[str, Any]],
    candidate_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not candidate_id:
        return None
    for candidate in candidates:
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    return None


def _build_candidate_projection(
    candidates: List[Dict[str, Any]],
    winner_candidate_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    winner = _find_candidate(candidates, winner_candidate_id)
    if not winner:
        return None
    return {
        "candidate_id": winner["candidate_id"],
        "candidate_kind": winner.get("candidate_kind"),
        "material_family": winner.get("material_family"),
        "grade_name": winner.get("grade_name"),
        "manufacturer_name": winner.get("manufacturer_name"),
        "evidence_refs": list(winner.get("evidence_refs") or []),
    }


def _normalize_structured_api_exposure_value(key: str, value: Any) -> Any:
    if key == "active_blockers":
        return [str(item) for item in (value or [])]
    return str(value or "")


def _assert_structured_api_exposure_contract(exposure: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if exposure is None:
        return None

    normalized = {
        key: _normalize_structured_api_exposure_value(key, exposure.get(key))
        for key in _STRUCTURED_API_EXPOSURE_KEYS
    }

    if set(normalized.keys()) != set(_STRUCTURED_API_EXPOSURE_KEYS):
        raise ValueError("structured_state exposure keys drifted from the allowlist")
    if not isinstance(normalized["active_blockers"], list):
        raise ValueError("structured_state.active_blockers must be a list")
    if any(not isinstance(item, str) for item in normalized["active_blockers"]):
        raise ValueError("structured_state.active_blockers must contain only strings")
    for key in _STRUCTURED_API_EXPOSURE_KEYS:
        if key == "active_blockers":
            continue
        if not isinstance(normalized[key], str):
            raise ValueError(f"structured_state.{key} must be a string")

    return normalized


def _minimal_structured_snapshot_contract(selection_state: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    state = selection_state or {}
    snapshot = state.get("structured_snapshot_contract")
    if not isinstance(snapshot, dict):
        return None
    return snapshot


def _minimal_structured_snapshot_from_case_state(
    case_state: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    state = case_state or {}
    governance_state = dict(state.get("governance_state") or {})
    rfq_state = dict(state.get("rfq_state") or {})
    qualified_action_gate = dict(state.get("qualified_action_gate") or {})
    release_status = str(governance_state.get("release_status") or "")
    rfq_admissibility = str(
        rfq_state.get("rfq_admissibility")
        or governance_state.get("rfq_admissibility")
        or ""
    )
    review_required = bool(governance_state.get("review_required", False))

    if review_required:
        blockers = list(rfq_state.get("blocking_reasons") or rfq_state.get("blockers") or [])
        if "review_pending" not in blockers:
            blockers = ["review_pending", *blockers]
        return {
            "case_status": "withheld_review",
            "output_status": "withheld_review",
            "primary_reason": "review_pending",
            "next_step": "human_review",
            "primary_allowed_action": "await_review",
            "active_blockers": blockers,
        }

    if rfq_admissibility == "ready" and release_status == "inquiry_ready":
        return {
            "case_status": "governed_non_binding_result",
            "output_status": "governed_non_binding_result",
            "primary_reason": "governed_releasable_result",
            "next_step": "confirmed_result_review",
            "primary_allowed_action": (
                "prepare_handover" if bool(qualified_action_gate.get("allowed", False))
                else "consume_governed_result"
            ),
            "active_blockers": list(rfq_state.get("blocking_reasons") or rfq_state.get("blockers") or []),
        }

    return None


def build_structured_api_exposure(
    selection_state: Optional[Dict[str, Any]],
    *,
    case_state: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    snapshot = _minimal_structured_snapshot_from_case_state(case_state) or _minimal_structured_snapshot_contract(selection_state)
    if not snapshot:
        return None

    return _assert_structured_api_exposure_contract({
        key: list(snapshot.get(key) or []) if key == "active_blockers" else snapshot.get(key)
        for key in _STRUCTURED_API_EXPOSURE_KEYS
    })


def _can_surface_governed_rationale_reply(
    *,
    artifact: Dict[str, Any],
    output_contract: Dict[str, Any],
    case_summary: Dict[str, Any],
    selection_state: Dict[str, Any],
    review_state: Optional[Dict[str, Any]] = None,
) -> bool:
    rationale_summary = artifact.get("rationale_summary")
    if not isinstance(rationale_summary, str) or not rationale_summary.strip():
        return False
    if str(output_contract.get("output_status") or "") != "governed_non_binding_result":
        return False
    if bool(output_contract.get("suppress_recommendation_details")):
        return False
    if str(selection_state.get("release_status") or "") != "inquiry_ready":
        return False
    if str(selection_state.get("rfq_admissibility") or "") != "ready":
        return False
    if bool(selection_state.get("output_blocked", True)):
        return False
    if get_case_status(case_summary) != "governed_non_binding_result":
        return False
    if has_active_blockers(case_summary):
        return False
    if bool((review_state or {}).get("review_required")):
        return False
    return True


def _build_recommendation_rationale_summary(
    *,
    review_escalation_projection: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    evidence_provenance_projection: Optional[Dict[str, Any]],
    conflict_status_projection: Optional[Dict[str, Any]],
    parameter_integrity_projection: Optional[Dict[str, Any]],
    unit_normalization_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
    selection_status: str,
    release_status: str,
    rfq_admissibility: str,
    readiness_status: str,
    blocking_reason: str,
    candidate_projection: Optional[Dict[str, Any]],
    asserted_state: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]] = None,
) -> str:
    from app.agent.state.projections_extended import INTEGRITY_UNUSABLE_REPLY
    evidence_note = _build_evidence_binding_note(evidence_provenance_projection)
    conflict_note = _build_conflict_correction_note(conflict_status_projection)
    integrity_note = _build_integrity_note(parameter_integrity_projection, unit_normalization_projection)
    domain_scope_note = _build_domain_scope_note(domain_scope_projection)
    if candidate_projection:
        candidate_label = (
            candidate_projection.get("grade_name")
            or candidate_projection.get("candidate_id")
            or candidate_projection.get("material_family")
            or "unbekannter_kandidat"
        )
        prefix_parts = [note for note in (conflict_note, integrity_note, domain_scope_note) if note]
        prefix = " ".join(prefix_parts)
        return ((f"{prefix} " if prefix else "")) + (
            f"{NEUTRAL_SCOPE_REPLY} "
            f"Technischer Orientierungsrahmen: {candidate_label}. "
            f"{evidence_note} "
            "Kein verbindlicher Freigabeschluss; Herstellervalidierung bleibt erforderlich."
        )

    projection_status = (review_escalation_projection or {}).get("status")
    if release_status == "precheck_only":
        return f"{PRECHECK_ONLY_REPLY} {evidence_note}"
    if release_status == "manufacturer_validation_required" or rfq_admissibility == "provisional":
        return f"{MANUFACTURER_VALIDATION_REPLY} {evidence_note}"
    if projection_status == "review_pending":
        return f"{REVIEW_PENDING_REPLY} {evidence_note}"
    if projection_status == "ambiguous_but_reviewable":
        return f"{AMBIGUOUS_CANDIDATE_REPLY} {evidence_note}"
    if projection_status == "escalation_needed":
        if conflict_note:
            return f"{conflict_note} {evidence_note}"
        if integrity_note:
            return f"{integrity_note} {evidence_note}"
        if domain_scope_note:
            return f"{domain_scope_note} {evidence_note}"
        return f"{ESCALATION_NEEDED_REPLY} {evidence_note}"
    if readiness_status == "demo_data_quarantine":
        return f"{DEMO_DATA_QUARANTINE_REPLY} {evidence_note}"
    if readiness_status == "evidence_missing":
        return f"{EVIDENCE_MISSING_REPLY} {evidence_note}"
    if readiness_status == "review_pending":
        return f"{REVIEW_PENDING_REPLY} {evidence_note}"
    if readiness_status == "integrity_unusable":
        if integrity_note:
            return f"{integrity_note} {evidence_note}"
        return f"{INTEGRITY_UNUSABLE_REPLY} {evidence_note}"
    if readiness_status == "domain_scope_blocked":
        if domain_scope_note:
            return f"{domain_scope_note} {evidence_note}"
        return f"{THRESHOLD_ESCALATION_REPLY} {evidence_note}"
    if readiness_status == "conflict_unresolved":
        if conflict_note:
            return f"{conflict_note} {evidence_note}"
        return f"{UNRESOLVED_CONFLICT_REPLY} {evidence_note}"
    if selection_status == "multiple_viable_candidates":
        return f"{AMBIGUOUS_CANDIDATE_REPLY} {evidence_note}"
    if selection_status == "blocked_no_candidates":
        return f"{NO_CANDIDATES_REPLY} {evidence_note}"
    if selection_status == "blocked_no_viable_candidates":
        return f"{NO_VIABLE_CANDIDATES_REPLY} {evidence_note}"
    if selection_status == "blocked_missing_required_inputs" or readiness_status == "insufficient_inputs":
        base = f"{_build_missing_data_reply(asserted_state, working_profile, clarification_projection)}\n\n{evidence_note}"
        if integrity_note:
            return f"{integrity_note} {base}"
        return base
    if blocking_reason:
        if conflict_note:
            return f"{conflict_note} {evidence_note}"
        if integrity_note:
            return f"{integrity_note} {evidence_note}"
        if domain_scope_note:
            return f"{domain_scope_note} {evidence_note}"
        return f"{SAFEGUARDED_WITHHELD_REPLY} {evidence_note}"
    base_text = f"{_build_missing_inputs_text(asserted_state, working_profile)}\n\n{evidence_note}"
    if conflict_note:
        return f"{conflict_note} {base_text}"
    if integrity_note:
        return f"{integrity_note} {base_text}"
    if domain_scope_note:
        return f"{domain_scope_note} {base_text}"
    return base_text


def build_final_reply(
    selection_state: Dict[str, Any],
    *,
    coverage_status: Optional[str] = None,
    known_unknowns: Optional[List[str]] = None,
    demo_data_present: bool = False,
    review_required: bool = False,
    review_reason: str = "",
    asserted_state: Optional[Dict[str, Any]] = None,
    working_profile: Optional[Dict[str, Any]] = None,
    evidence_available: bool = True,
    review_state: Optional[Dict[str, Any]] = None,
    case_state: Optional[Dict[str, Any]] = None,
) -> str:
    artifact = selection_state.get("recommendation_artifact") or {}
    review_projection = selection_state.get("review_escalation_projection") or {}
    clarification_projection = selection_state.get("clarification_projection") or {}
    correction_projection = selection_state.get("correction_projection") or {}
    parameter_integrity_projection = selection_state.get("parameter_integrity_projection") or {}
    unit_normalization_projection = selection_state.get("unit_normalization_projection") or {}
    domain_scope_projection = selection_state.get("domain_scope_projection") or {}
    output_contract = selection_state.get("output_contract_projection") or {}
    state_trace_audit = selection_state.get("state_trace_audit_projection") or build_state_trace_audit_projection(
        selection_status=str(selection_state.get("selection_status") or ""),
        recommendation_artifact=artifact,
        review_escalation_projection=review_projection,
        clarification_projection=clarification_projection,
        conflict_status_projection=selection_state.get("conflict_status_projection"),
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
        output_contract_projection=output_contract,
        projection_invariant_projection=selection_state.get("projection_invariant_projection"),
    )
    case_summary = selection_state.get("case_summary_projection") or build_case_summary_projection(
        asserted_state=asserted_state,
        output_contract_projection=output_contract,
        clarification_projection=clarification_projection,
        state_trace_audit_projection=state_trace_audit,
    )
    actionability = selection_state.get("actionability_projection")
    canonical_case_state = dict(case_state or {})
    canonical_dispatch_source = _resolve_runtime_dispatch_source(canonical_case_state)
    canonical_result_contract = dict(canonical_case_state.get("result_contract") or {})
    canonical_requirement_class = dict(canonical_case_state.get("requirement_class") or {})
    canonical_rfq_state = dict(canonical_case_state.get("rfq_state") or {})
    invariant_projection = selection_state.get("projection_invariant_projection") or project_projection_invariants(
        recommendation_artifact=artifact,
        review_escalation_projection=review_projection,
        clarification_projection=clarification_projection,
        evidence_provenance_projection=selection_state.get("evidence_provenance_projection"),
        conflict_status_projection=selection_state.get("conflict_status_projection"),
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
        output_contract_projection=output_contract,
    )
    if not _artifact_is_aligned(selection_state, artifact):
        core_reply = SAFEGUARDED_WITHHELD_REPLY
    elif get_primary_trace_reason(state_trace_audit) == "invariant_blocked" or not invariant_projection.get("invariant_ok", True):
        core_reply = INVARIANT_BLOCKED_REPLY
    elif _can_surface_governed_rationale_reply(
        artifact=artifact,
        output_contract=output_contract,
        case_summary=case_summary,
        selection_state=selection_state,
        review_state=review_state,
    ):
        core_reply = str(artifact["rationale_summary"]).strip()
    else:
        release_status = (
            canonical_result_contract.get("release_status")
            or selection_state.get("release_status")
        )
        rfq_admissibility = (
            canonical_rfq_state.get("rfq_admissibility")
            or canonical_result_contract.get("rfq_admissibility")
            or selection_state.get("rfq_admissibility")
        )
        output_blocked = bool(selection_state.get("output_blocked", True))
        specificity_level = (
            canonical_requirement_class.get("specificity_level")
            or canonical_result_contract.get("specificity_level")
            or selection_state.get("specificity_level", "family_only")
        )
        output_status = str(output_contract.get("output_status") or "")
        canonical_dispatch_ready = bool(canonical_dispatch_source.get("dispatch_ready", False))

        if release_status == "precheck_only":
            core_reply = PRECHECK_ONLY_REPLY
        elif release_status == "manufacturer_validation_required" or rfq_admissibility == "provisional":
            core_reply = MANUFACTURER_VALIDATION_REPLY
        elif actionability and get_primary_allowed_action(actionability) == "no_action_until_clarified":
            core_reply = INVARIANT_BLOCKED_REPLY
        elif actionability and get_primary_allowed_action(actionability) == "provide_missing_input":
            core_reply = _build_missing_data_reply(asserted_state, working_profile, clarification_projection)
        elif actionability and get_primary_allowed_action(actionability) == "obtain_qualified_evidence":
            core_reply = EVIDENCE_MISSING_REPLY
        elif actionability and get_primary_allowed_action(actionability) == "await_review":
            core_reply = REVIEW_PENDING_REPLY
        elif actionability and get_primary_allowed_action(actionability) == "prepare_handover":
            if "candidate_ambiguity" in list(case_summary.get("active_blockers") or []):
                core_reply = AMBIGUOUS_CANDIDATE_REPLY
            else:
                core_reply = REVIEW_PENDING_REPLY
        elif actionability and get_primary_allowed_action(actionability) == "consume_governed_result" and _can_surface_governed_rationale_reply(
            artifact=artifact,
            output_contract=output_contract,
            case_summary=case_summary,
            selection_state=selection_state,
            review_state=review_state,
        ):
            core_reply = str(artifact["rationale_summary"]).strip()
        elif actionability and get_primary_allowed_action(actionability) == "escalate_engineering":
            if correction_projection.get("conflict_still_open") or (selection_state.get("conflict_status_projection") or {}).get("conflict_still_open"):
                core_reply = _build_conflict_correction_note(
                    selection_state.get("conflict_status_projection")
                ) or ESCALATION_NEEDED_REPLY
            elif parameter_integrity_projection.get("integrity_status") == "unusable_until_clarified":
                core_reply = _build_integrity_note(
                    parameter_integrity_projection,
                    unit_normalization_projection,
                ) or ESCALATION_NEEDED_REPLY
            elif domain_scope_projection.get("status") in {"out_of_domain_scope", "escalation_required"}:
                core_reply = _build_domain_scope_note(domain_scope_projection) or ESCALATION_NEEDED_REPLY
            else:
                core_reply = ESCALATION_NEEDED_REPLY
        elif get_case_status(case_summary) == "clarification_needed":
            core_reply = _build_missing_data_reply(asserted_state, working_profile, clarification_projection)
        elif get_case_status(case_summary) == "withheld_no_evidence":
            core_reply = EVIDENCE_MISSING_REPLY
        elif get_case_status(case_summary) == "withheld_review":
            if "candidate_ambiguity" in list(case_summary.get("active_blockers") or []):
                core_reply = AMBIGUOUS_CANDIDATE_REPLY
            else:
                core_reply = REVIEW_PENDING_REPLY
        elif get_case_status(case_summary) == "withheld_domain_block":
            core_reply = _build_domain_scope_note(domain_scope_projection) or OUT_OF_DOMAIN_REPLY
        elif get_primary_trace_reason(state_trace_audit) == "withheld_no_evidence":
            core_reply = EVIDENCE_MISSING_REPLY
        elif get_primary_trace_reason(state_trace_audit) in {"review_pending", "review_candidate_ambiguity", "review_governance_withheld", "review_required"}:
            if get_primary_trace_reason(state_trace_audit) == "review_candidate_ambiguity":
                core_reply = AMBIGUOUS_CANDIDATE_REPLY
            else:
                core_reply = REVIEW_PENDING_REPLY
        elif get_primary_trace_reason(state_trace_audit) == "clarification_missing_inputs":
            core_reply = _build_missing_data_reply(asserted_state, working_profile, clarification_projection)
        elif get_primary_trace_reason(state_trace_audit) == "domain_scope_blocked":
            core_reply = _build_domain_scope_note(domain_scope_projection) or OUT_OF_DOMAIN_REPLY
        elif get_primary_trace_reason(state_trace_audit) == "escalation_conflict_open":
            core_reply = _build_conflict_correction_note(
                selection_state.get("conflict_status_projection")
            ) or ESCALATION_NEEDED_REPLY
        elif get_primary_trace_reason(state_trace_audit) == "escalation_integrity_blocked":
            core_reply = _build_integrity_note(
                parameter_integrity_projection,
                unit_normalization_projection,
            ) or ESCALATION_NEEDED_REPLY
        elif get_primary_trace_reason(state_trace_audit) == "escalation_domain_threshold":
            core_reply = _build_domain_scope_note(domain_scope_projection) or ESCALATION_NEEDED_REPLY
        elif output_status == "clarification_needed":
            core_reply = _build_missing_data_reply(asserted_state, working_profile, clarification_projection)
        elif output_status == "withheld_no_evidence":
            core_reply = EVIDENCE_MISSING_REPLY
        elif output_status == "withheld_review":
            if review_projection.get("status") == "ambiguous_but_reviewable" or selection_state.get("selection_status") == "multiple_viable_candidates":
                core_reply = AMBIGUOUS_CANDIDATE_REPLY
            else:
                core_reply = REVIEW_PENDING_REPLY
        elif output_status == "withheld_domain_block":
            core_reply = _build_domain_scope_note(domain_scope_projection) or OUT_OF_DOMAIN_REPLY
        elif output_status == "withheld_escalation":
            if correction_projection.get("conflict_still_open"):
                core_reply = _build_conflict_correction_note(
                    selection_state.get("conflict_status_projection")
                ) or ESCALATION_NEEDED_REPLY
            elif parameter_integrity_projection.get("integrity_status") == "unusable_until_clarified":
                core_reply = _build_integrity_note(
                    parameter_integrity_projection,
                    unit_normalization_projection,
                ) or ESCALATION_NEEDED_REPLY
            elif domain_scope_projection.get("status") in {"out_of_domain_scope", "escalation_required"}:
                core_reply = _build_domain_scope_note(domain_scope_projection) or ESCALATION_NEEDED_REPLY
            else:
                core_reply = ESCALATION_NEEDED_REPLY
        elif demo_data_present:
            core_reply = DEMO_DATA_QUARANTINE_REPLY
        elif not evidence_available:
            core_reply = EVIDENCE_MISSING_REPLY
        elif (review_state or {}).get("review_required"):
            core_reply = REVIEW_PENDING_REPLY
        elif (
            not output_blocked
            and (
                (
                    release_status == "inquiry_ready"
                    and rfq_admissibility == "ready"
                    and specificity_level == "compound_required"
                )
                or (
                    canonical_dispatch_ready
                    and specificity_level == "compound_required"
                )
            )
        ):
            core_reply = NEUTRAL_SCOPE_REPLY
        elif selection_state.get("selection_status") == "blocked_no_candidates":
            core_reply = NO_CANDIDATES_REPLY
        elif selection_state.get("selection_status") == "blocked_no_viable_candidates":
            core_reply = NO_VIABLE_CANDIDATES_REPLY
        elif review_projection.get("status") == "escalation_needed":
            if correction_projection.get("conflict_still_open"):
                core_reply = _build_conflict_correction_note(
                    selection_state.get("conflict_status_projection")
                ) or ESCALATION_NEEDED_REPLY
            elif parameter_integrity_projection.get("integrity_status") == "unusable_until_clarified":
                core_reply = _build_integrity_note(
                    parameter_integrity_projection,
                    unit_normalization_projection,
                ) or ESCALATION_NEEDED_REPLY
            elif domain_scope_projection.get("status") in {"out_of_domain_scope", "escalation_required"}:
                core_reply = _build_domain_scope_note(domain_scope_projection) or ESCALATION_NEEDED_REPLY
            else:
                core_reply = ESCALATION_NEEDED_REPLY
        elif selection_state.get("selection_status") == "multiple_viable_candidates":
            core_reply = AMBIGUOUS_CANDIDATE_REPLY
        elif selection_state.get("selection_status") == "blocked_missing_required_inputs":
            core_reply = _build_missing_data_reply(asserted_state, working_profile, clarification_projection)
        else:
            core_reply = _build_missing_data_reply(asserted_state, working_profile, clarification_projection)

    boundary = build_boundary_block(
        "structured",
        coverage_status=coverage_status,
        known_unknowns=known_unknowns,
        demo_data_present=demo_data_present,
        review_required=review_required,
        review_reason=review_reason,
        evidence_available=evidence_available,
    )
    return f"{core_reply}\n\n{boundary}"
