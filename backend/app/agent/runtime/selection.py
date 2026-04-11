"""
Selection — candidate aggregation, classification, and governed output orchestration.

Canonical location for build_selection_state and supporting helpers.
Moved from app.agent.agent.selection (G1.1 Move 11).
"""
import re
from typing import Any, Dict, List, Optional

from app.agent.runtime.clarification import (
    CLARIFICATION_PAUSED_PREFIX,
    NEXT_QUESTION_PREFIX,
    STRUCTURED_CONTEXT_PARAMS,
    STRUCTURED_REQUIRED_CORE_PARAMS,
    STRUCTURED_SUPPLEMENTARY_PARAMS,
    _CLARIFICATION_FIELD_META,
    _build_missing_data_reply,
    _build_missing_inputs_text,
    _field_is_known_or_pending,
    _missing_core_input_items,
    build_clarification_projection,
    build_next_clarification_question,
    prioritize_missing_inputs,
)
from app.agent.domain.readiness import (
    CaseReadinessStatus,
    EvidenceProvenanceStatus,
    OutputReadinessDecision,
    OutputReadinessStatus,
    ReviewEscalationStatus,
    _governance_projection_blocks_output,
    evaluate_output_readiness,
    has_confirmed_core_params,
    is_releasable,
    is_sufficient_for_structured,
    project_case_readiness,
)
from app.agent.runtime.reply_builder import (
    AMBIGUOUS_CANDIDATE_REPLY,
    DEMO_DATA_QUARANTINE_REPLY,
    EVIDENCE_MISSING_REPLY,
    ESCALATION_NEEDED_REPLY,
    MANUFACTURER_VALIDATION_REPLY,
    NEUTRAL_SCOPE_REPLY,
    NO_CANDIDATES_REPLY,
    NO_VIABLE_CANDIDATES_REPLY,
    PRECHECK_ONLY_REPLY,
    REVIEW_PENDING_REPLY,
    SAFEGUARDED_WITHHELD_REPLY,
    _STRUCTURED_API_EXPOSURE_KEYS,
    _artifact_is_aligned,
    _assert_structured_api_exposure_contract,
    _build_candidate_projection,
    _build_recommendation_artifact,
    _build_recommendation_rationale_summary,
    _can_surface_governed_rationale_reply,
    _find_candidate,
    _minimal_structured_snapshot_contract,
    _minimal_structured_snapshot_from_case_state,
    _normalize_structured_api_exposure_value,
    _resolve_runtime_dispatch_source,
    build_final_reply,
    build_structured_api_exposure,
)
from app.agent.domain.material import (
    MaterialPhysicalProfile,
    MaterialValidator,
    normalize_fact_card_evidence,
)
from app.agent.domain.parameters import PhysicalParameter
from app.agent.domain.threshold import (
    _build_rwdr_threshold_payload,
    _threshold_scope_level,
    compare_threshold_scope,
    project_threshold_status,
)
from app.agent.state.projections_extended import (
    CORRECTION_APPLIED_PREFIX,
    DOMAIN_WARNING_PREFIX,
    INTEGRITY_UNUSABLE_REPLY,
    INTEGRITY_WARNING_PREFIX,
    INVARIANT_BLOCKED_REPLY,
    OUT_OF_DOMAIN_REPLY,
    THRESHOLD_ESCALATION_REPLY,
    UNRESOLVED_CONFLICT_REPLY,
    _ACTIONABILITY_ACTIONS,
    _STATE_DELTA_FIELD_ORDER,
    _apply_invariant_safeguards,
    _build_conflict_correction_note,
    _build_domain_scope_note,
    _build_evidence_binding_note,
    _build_integrity_note,
    _collect_provenance_refs,
    _compare_transition,
    _extract_observed_field_values,
    _field_integrity_status,
    _identity_or_normalized_value,
    _resolve_current_field_value,
    build_actionability_projection,
    build_case_summary_projection,
    build_correction_projection,
    build_output_contract_projection,
    build_parameter_integrity_projection,
    build_state_delta_projection,
    build_state_trace_audit_projection,
    build_structured_snapshot,
    compare_actionability,
    compare_case_status,
    compare_structured_snapshots,
    get_case_status,
    get_next_case_step,
    get_next_expected_user_action,
    get_primary_allowed_action,
    get_primary_trace_reason,
    has_active_blockers,
    is_action_blocked,
    is_blocked_by_trace,
    project_conflict_status,
    project_domain_scope_status,
    project_evidence_provenance_state,
    project_projection_invariants,
    project_review_escalation_state,
    project_unit_normalization_status,
    project_user_facing_output_status,
)


# Thin compatibility layer for the split modules introduced by W5.1.
# Selection-specific candidate aggregation/orchestration stays here.

_MATERIAL_PATTERN = re.compile(r"\b(PTFE|NBR|FKM|EPDM|SILIKON)\b", re.I)
_GRADE_PATTERN = re.compile(r"\b(?:grade|compound|typ|type)\s*[:\-]?\s*([a-z0-9._-]+)\b", re.I)
_FILLER_PATTERN = re.compile(r"\b(filled|glass[- ]filled|carbon[- ]filled|bronze[- ]filled)\b", re.I)


def _pick_material_family(text: str, metadata: Dict[str, Any]) -> Optional[str]:
    for key in ("material_family", "material", "family"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    match = _MATERIAL_PATTERN.search(text)
    if match:
        return match.group(1).upper()
    return None


def _pick_filler_hint(text: str, metadata: Dict[str, Any]) -> Optional[str]:
    for key in ("filler_hint", "filler", "fill"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    match = _FILLER_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def _pick_grade_name(text: str, metadata: Dict[str, Any]) -> Optional[str]:
    for key in ("grade_name", "grade", "compound_code", "compound"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    match = _GRADE_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def _pick_manufacturer(metadata: Dict[str, Any]) -> Optional[str]:
    for key in ("manufacturer_name", "manufacturer", "brand"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _candidate_kind(
    family: str,
    filler_hint: Optional[str],
    grade_name: Optional[str],
    manufacturer_name: Optional[str],
) -> str:
    if manufacturer_name and grade_name:
        return "manufacturer_grade"
    if grade_name:
        return "grade"
    if filler_hint:
        return "filled_family"
    return "family"


def _candidate_id(
    family: str,
    filler_hint: Optional[str],
    grade_name: Optional[str],
    manufacturer_name: Optional[str],
) -> str:
    parts = [
        family.lower(),
        (filler_hint or "").lower(),
        (grade_name or "").lower(),
        (manufacturer_name or "").lower(),
    ]
    return "::".join(part for part in parts if part)


def _resolve_recommendation_projection(
    *,
    selection_status: str,
    winner_candidate_id: Optional[str],
    candidates: List[Dict[str, Any]],
    asserted_state: Optional[Dict[str, Any]],
    governance_state: Optional[Dict[str, Any]],
    review_state: Optional[Dict[str, Any]],
    evidence_available: bool,
    demo_data_present: bool,
    conflict_status_projection: Optional[Dict[str, Any]],
    parameter_integrity_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[Dict[str, Any]], str, str]:
    readiness = evaluate_output_readiness(
        asserted_state,
        governance_state,
        review_state=review_state,
        evidence_available=evidence_available,
        demo_data_present=demo_data_present,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
    )

    if not readiness.releasable:
        return None, readiness.status, readiness.blocking_reason

    if selection_status == "multiple_viable_candidates":
        blocking_reason = (
            "Multiple viable candidates remain after deterministic checks; "
            "no single governed candidate projection is available."
        )
        return None, "candidate_ambiguity", blocking_reason

    candidate_projection = _build_candidate_projection(candidates, winner_candidate_id)
    if candidate_projection is None:
        blocking_reason = "No single governed candidate projection is available."
        return None, "no_governed_candidate", blocking_reason

    return candidate_projection, readiness.status, readiness.blocking_reason


def _normalize_temperature(asserted_state: Dict[str, Any]) -> Optional[PhysicalParameter]:
    temperature_value = (asserted_state or {}).get("operating_conditions", {}).get("temperature")
    if temperature_value is None:
        return None
    try:
        return PhysicalParameter(value=float(temperature_value), unit="C")
    except Exception:
        return None


def _normalize_pressure(asserted_state: Dict[str, Any]) -> Optional[PhysicalParameter]:
    pressure_value = (asserted_state or {}).get("operating_conditions", {}).get("pressure")
    if pressure_value is None:
        return None
    try:
        return PhysicalParameter(value=float(pressure_value), unit="bar")
    except Exception:
        return None


def _classify_candidates(
    candidates: List[Dict[str, Any]],
    relevant_fact_cards: List[Dict[str, Any]],
    asserted_state: Dict[str, Any],
) -> tuple[List[str], List[Dict[str, str]]]:
    temperature = _normalize_temperature(asserted_state)
    pressure = _normalize_pressure(asserted_state)

    cards_by_evidence_id = {
        (card.get("evidence_id") or card.get("id")): {
            "card": card,
            "normalized_evidence": card.get("normalized_evidence") or normalize_fact_card_evidence(card),
        }
        for card in relevant_fact_cards
        if (card.get("evidence_id") or card.get("id"))
    }
    viable_candidate_ids: List[str] = []
    blocked_candidates: List[Dict[str, str]] = []

    for candidate in candidates:
        supporting_profiles: List[MaterialPhysicalProfile] = []
        for evidence_ref in candidate.get("evidence_refs", []):
            entry = cards_by_evidence_id.get(evidence_ref)
            if not entry:
                continue
            card = dict(entry["card"])
            card["normalized_evidence"] = entry["normalized_evidence"]
            profile = MaterialPhysicalProfile.from_fact_card(card)
            if profile and profile.material_id.upper() == candidate.get("material_family", "").upper():
                supporting_profiles.append(profile)

        if not supporting_profiles:
            candidate["viability_status"] = "blocked_missing_required_inputs"
            candidate["block_reason"] = "blocked_missing_required_inputs"
            blocked_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "block_reason": "blocked_missing_required_inputs",
                }
            )
            continue

        requires_temperature = True
        requires_pressure = any(getattr(profile, "pressure_max", None) is not None for profile in supporting_profiles)

        if requires_temperature and temperature is None:
            candidate["viability_status"] = "blocked_missing_required_inputs"
            candidate["block_reason"] = "blocked_missing_required_inputs"
            blocked_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "block_reason": "blocked_missing_required_inputs",
                }
            )
            continue

        if requires_pressure and pressure is None:
            candidate["viability_status"] = "blocked_missing_required_inputs"
            candidate["block_reason"] = "blocked_missing_required_inputs"
            blocked_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "block_reason": "blocked_missing_required_inputs",
                }
            )
            continue

        has_temperature_conflict = any(
            not MaterialValidator(profile).validate_temperature(temperature)
            for profile in supporting_profiles
        )
        if has_temperature_conflict:
            candidate["viability_status"] = "blocked_temperature_conflict"
            candidate["block_reason"] = "blocked_temperature_conflict"
            blocked_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "block_reason": "blocked_temperature_conflict",
                }
            )
            continue

        has_pressure_conflict = any(
            getattr(profile, "pressure_max", None) is not None
            and not MaterialValidator(profile).validate_pressure(pressure)
            for profile in supporting_profiles
        )
        if has_pressure_conflict:
            candidate["viability_status"] = "blocked_pressure_conflict"
            candidate["block_reason"] = "blocked_pressure_conflict"
            blocked_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "block_reason": "blocked_pressure_conflict",
                }
            )
            continue

        candidate["viability_status"] = "viable"
        candidate["block_reason"] = None
        viable_candidate_ids.append(candidate["candidate_id"])

    return viable_candidate_ids, blocked_candidates


def build_selection_state(
    relevant_fact_cards: List[Dict[str, Any]],
    cycle_state: Dict[str, Any],
    governance_state: Optional[Dict[str, Any]] = None,
    asserted_state: Optional[Dict[str, Any]] = None,
    *,
    review_state: Optional[Dict[str, Any]] = None,
    evidence_available: bool = True,
    demo_data_present: bool = False,
    working_profile: Optional[Dict[str, Any]] = None,
    observed_state: Optional[Dict[str, Any]] = None,
    normalized_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    candidates_by_id: Dict[str, Dict[str, Any]] = {}
    evidence_basis: List[str] = []
    governance_state = governance_state or {}
    asserted_state = asserted_state or {}

    for card in relevant_fact_cards:
        normalized_evidence = card.get("normalized_evidence") or normalize_fact_card_evidence(card)
        family = normalized_evidence.get("material_family")
        if not family:
            continue

        filler_hint = normalized_evidence.get("filler_hint")
        grade_name = normalized_evidence.get("grade_name")
        manufacturer_name = normalized_evidence.get("manufacturer_name")
        kind = normalized_evidence.get("candidate_kind") or _candidate_kind(family, filler_hint, grade_name, manufacturer_name)
        candidate_id = _candidate_id(family, filler_hint, grade_name, manufacturer_name)
        evidence_id = card.get("evidence_id") or card.get("id")
        if not evidence_id:
            continue

        existing = candidates_by_id.get(candidate_id)
        if not existing:
            existing = {
                "candidate_id": candidate_id,
                "candidate_kind": kind,
                "material_family": family,
                "filler_hint": filler_hint,
                "grade_name": grade_name,
                "manufacturer_name": manufacturer_name,
                "viability_status": "blocked_missing_required_inputs",
                "block_reason": None,
                "evidence_refs": [],
                "_best_rank": card.get("retrieval_rank", 9999),
            }
            candidates_by_id[candidate_id] = existing

        if evidence_id not in existing["evidence_refs"]:
            existing["evidence_refs"].append(evidence_id)
        existing["_best_rank"] = min(existing["_best_rank"], card.get("retrieval_rank", 9999))
        if evidence_id not in evidence_basis:
            evidence_basis.append(evidence_id)

    ordered_candidates = sorted(candidates_by_id.values(), key=lambda candidate: candidate["candidate_id"])
    for candidate in ordered_candidates:
        candidate.pop("_best_rank", None)

    viable_candidate_ids, blocked_candidates = _classify_candidates(
        ordered_candidates,
        relevant_fact_cards,
        asserted_state,
    )
    winner_candidate_id = viable_candidate_ids[0] if len(viable_candidate_ids) == 1 else None
    if not ordered_candidates:
        selection_status = "blocked_no_candidates"
    elif winner_candidate_id:
        selection_status = "winner_selected"
    elif viable_candidate_ids:
        selection_status = "multiple_viable_candidates"
    elif any(block["block_reason"] == "blocked_missing_required_inputs" for block in blocked_candidates):
        selection_status = "blocked_missing_required_inputs"
    else:
        selection_status = "blocked_no_viable_candidates"

    governance_release_status = governance_state.get("release_status", "inadmissible")
    governance_rfq_admissibility = governance_state.get("rfq_admissibility", "inadmissible")
    specificity_level = governance_state.get("specificity_level", "family_only")
    evidence_provenance_projection = project_evidence_provenance_state(
        relevant_fact_cards,
        evidence_basis,
    )
    conflict_status_projection = project_conflict_status(
        observed_state=observed_state,
        normalized_state=normalized_state,
        governance_state=governance_state,
        asserted_state=asserted_state,
    )
    unit_normalization_projection = project_unit_normalization_status(
        normalized_state=normalized_state,
        asserted_state=asserted_state,
    )
    parameter_integrity_projection = build_parameter_integrity_projection(
        unit_normalization_projection
    )
    threshold_projection = project_threshold_status(
        asserted_state=asserted_state,
        working_profile=working_profile,
    )
    domain_scope_projection = project_domain_scope_status(threshold_projection)
    correction_projection = build_correction_projection(conflict_status_projection)
    effective_evidence_available = bool(
        evidence_available and evidence_provenance_projection.get("status") != "no_evidence"
    )
    candidate_projection, readiness_status, blocking_reason = _resolve_recommendation_projection(
        selection_status=selection_status,
        winner_candidate_id=winner_candidate_id,
        candidates=ordered_candidates,
        asserted_state=asserted_state,
        governance_state=governance_state,
        review_state=review_state,
        evidence_available=effective_evidence_available,
        demo_data_present=demo_data_present,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
        working_profile=working_profile,
    )
    review_escalation_projection = project_review_escalation_state(
        selection_status=selection_status,
        readiness_status=readiness_status,
        blocking_reason=blocking_reason,
        viable_candidate_ids=viable_candidate_ids,
        asserted_state=asserted_state,
        review_state=review_state,
        evidence_available=effective_evidence_available,
        demo_data_present=demo_data_present,
        evidence_provenance_projection=evidence_provenance_projection,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
    )
    clarification_projection = build_clarification_projection(
        asserted_state=asserted_state,
        working_profile=working_profile,
        review_escalation_projection=review_escalation_projection,
        evidence_provenance_projection=evidence_provenance_projection,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
    )
    rationale_summary = _build_recommendation_rationale_summary(
        review_escalation_projection=review_escalation_projection,
        clarification_projection=clarification_projection,
        evidence_provenance_projection=evidence_provenance_projection,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        unit_normalization_projection=unit_normalization_projection,
        domain_scope_projection=domain_scope_projection,
        selection_status=selection_status,
        release_status=governance_release_status,
        rfq_admissibility=governance_rfq_admissibility,
        readiness_status=readiness_status,
        blocking_reason=blocking_reason,
        candidate_projection=candidate_projection,
        asserted_state=asserted_state,
        working_profile=working_profile,
    )
    output_blocked = candidate_projection is None
    trace_refs = list(evidence_basis)
    cycle_id = cycle_state.get("analysis_cycle_id")
    if cycle_id:
        trace_refs.append(cycle_id)

    recommendation_artifact = _build_recommendation_artifact(
        selection_status=selection_status,
        winner_candidate_id=winner_candidate_id,
        candidate_projection=candidate_projection,
        candidates=ordered_candidates,
        viable_candidate_ids=viable_candidate_ids,
        blocked_candidates=blocked_candidates,
        evidence_basis=evidence_basis,
        evidence_status=str(evidence_provenance_projection.get("status") or "no_evidence"),
        provenance_refs=list(evidence_provenance_projection.get("provenance_refs") or []),
        conflict_status=str(conflict_status_projection.get("status") or "no_conflict"),
        integrity_status=str(parameter_integrity_projection.get("integrity_status") or "normalized_ok"),
        domain_scope_status=str(domain_scope_projection.get("status") or "in_domain_scope"),
        threshold_status=str(threshold_projection.get("threshold_status") or "threshold_free"),
        release_status=governance_release_status,
        rfq_admissibility=governance_rfq_admissibility,
        specificity_level=specificity_level,
        output_blocked=output_blocked,
        readiness_status=readiness_status,
        blocking_reason=blocking_reason,
        rationale_summary=rationale_summary,
        trace_refs=trace_refs,
    )
    user_facing_output_projection = project_user_facing_output_status(
        selection_status=selection_status,
        recommendation_artifact=recommendation_artifact,
        review_escalation_projection=review_escalation_projection,
        clarification_projection=clarification_projection,
        domain_scope_projection=domain_scope_projection,
    )
    output_contract_projection = build_output_contract_projection(
        user_facing_output_projection=user_facing_output_projection,
        recommendation_artifact=recommendation_artifact,
        clarification_projection=clarification_projection,
        review_escalation_projection=review_escalation_projection,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
        threshold_projection=threshold_projection,
    )
    projection_invariant_projection = project_projection_invariants(
        recommendation_artifact=recommendation_artifact,
        review_escalation_projection=review_escalation_projection,
        clarification_projection=clarification_projection,
        evidence_provenance_projection=evidence_provenance_projection,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
        output_contract_projection=output_contract_projection,
    )
    if not projection_invariant_projection.get("invariant_ok", True):
        recommendation_artifact, user_facing_output_projection, output_contract_projection, output_blocked = _apply_invariant_safeguards(
            recommendation_artifact=recommendation_artifact,
            user_facing_output_projection=user_facing_output_projection,
            output_contract_projection=output_contract_projection,
            projection_invariant_projection=projection_invariant_projection,
        )
    state_trace_audit_projection = build_state_trace_audit_projection(
        selection_status=selection_status,
        recommendation_artifact=recommendation_artifact,
        review_escalation_projection=review_escalation_projection,
        clarification_projection=clarification_projection,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
        output_contract_projection=output_contract_projection,
        projection_invariant_projection=projection_invariant_projection,
    )
    case_summary_projection = build_case_summary_projection(
        asserted_state=asserted_state,
        output_contract_projection=output_contract_projection,
        clarification_projection=clarification_projection,
        state_trace_audit_projection=state_trace_audit_projection,
    )
    actionability_projection = build_actionability_projection(
        case_summary_projection=case_summary_projection,
        output_contract_projection=output_contract_projection,
        review_escalation_projection=review_escalation_projection,
        clarification_projection=clarification_projection,
        projection_invariant_projection=projection_invariant_projection,
    )
    structured_snapshot_contract = build_structured_snapshot(
        {
            "selection_status": selection_status,
            "recommendation_artifact": recommendation_artifact,
            "review_escalation_projection": review_escalation_projection,
            "clarification_projection": clarification_projection,
            "conflict_status_projection": conflict_status_projection,
            "parameter_integrity_projection": parameter_integrity_projection,
            "domain_scope_projection": domain_scope_projection,
            "output_contract_projection": output_contract_projection,
            "projection_invariant_projection": projection_invariant_projection,
            "state_trace_audit_projection": state_trace_audit_projection,
            "case_summary_projection": case_summary_projection,
            "actionability_projection": actionability_projection,
        },
        asserted_state=asserted_state,
    )

    return {
        "selection_status": selection_status,
        "candidates": ordered_candidates,
        "viable_candidate_ids": viable_candidate_ids,
        "blocked_candidates": blocked_candidates,
        "winner_candidate_id": winner_candidate_id,
        "recommendation_artifact": recommendation_artifact,
        "evidence_provenance_projection": evidence_provenance_projection,
        "conflict_status_projection": conflict_status_projection,
        "unit_normalization_projection": unit_normalization_projection,
        "parameter_integrity_projection": parameter_integrity_projection,
        "threshold_projection": threshold_projection,
        "domain_scope_projection": domain_scope_projection,
        "correction_projection": correction_projection,
        "review_escalation_projection": review_escalation_projection,
        "clarification_projection": clarification_projection,
        "user_facing_output_projection": user_facing_output_projection,
        "output_contract_projection": output_contract_projection,
        "projection_invariant_projection": projection_invariant_projection,
        "state_trace_audit_projection": state_trace_audit_projection,
        "case_summary_projection": case_summary_projection,
        "actionability_projection": actionability_projection,
        "structured_snapshot_contract": structured_snapshot_contract,
        "release_status": governance_release_status,
        "rfq_admissibility": governance_rfq_admissibility,
        "specificity_level": specificity_level,
        "output_blocked": output_blocked,
    }
