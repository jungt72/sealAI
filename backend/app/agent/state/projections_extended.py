from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.agent.runtime.clarification import (
    STRUCTURED_REQUIRED_CORE_PARAMS,
    _missing_core_input_items,
)
from app.agent.domain.readiness import (
    evaluate_output_readiness,
)
from app.agent.domain.threshold import compare_threshold_scope, project_threshold_status
from app.agent.domain.normalization import extract_parameters as norm_extract


CORRECTION_APPLIED_PREFIX = "Aktualisierte Angabe übernommen:"
INTEGRITY_WARNING_PREFIX = "Parameter verwendbar mit Warnhinweis:"
INTEGRITY_UNUSABLE_REPLY = (
    "Parameterangaben liegen vor, sind aber fachlich noch nicht sauber verwendbar. "
    "Eine Auslegungsempfehlung kann derzeit nicht ausgegeben werden."
)
DOMAIN_WARNING_PREFIX = "Fachlicher Grenzfall im aktuellen Anwendungsbereich:"
OUT_OF_DOMAIN_REPLY = (
    "Der Fall liegt außerhalb des fachlich abgedeckten Anwendungsbereichs. "
    "Eine Auslegungsempfehlung kann aus dem aktuellen Zustand nicht ausgegeben werden."
)
THRESHOLD_ESCALATION_REPLY = (
    "Technische Grenzwerte erfordern eine fachliche Eskalation. "
    "Eine Auslegungsempfehlung kann aus dem aktuellen Zustand nicht ausgegeben werden."
)
UNRESOLVED_CONFLICT_REPLY = (
    "Widersprüchliche Parameterangaben liegen vor. "
    "Eine Auslegungsempfehlung kann aus dem aktuellen Zustand nicht ausgegeben werden."
)
INVARIANT_BLOCKED_REPLY = (
    "Die interne Zustandsprüfung hat einen Konsistenzfehler festgestellt. "
    "Eine Auslegungsempfehlung kann aus dem aktuellen Zustand nicht ausgegeben werden."
)

_ACTIONABILITY_ACTIONS: tuple[str, ...] = (
    "provide_missing_input",
    "await_review",
    "escalate_engineering",
    "consume_governed_result",
    "prepare_handover",
    "obtain_qualified_evidence",
    "no_action_until_clarified",
)

_STATE_DELTA_FIELD_ORDER: tuple[str, ...] = (
    "invariant_ok",
    "conflict_status",
    "integrity_status",
    "domain_scope_status",
    "threshold_status",
    "output_status",
    "case_status",
    "actionability_status",
    "primary_allowed_action",
    "next_step",
    "next_expected_user_action",
    "active_blockers",
    "blocked_actions",
)


def project_review_escalation_state(
    *,
    selection_status: str,
    readiness_status: str,
    blocking_reason: str,
    viable_candidate_ids: List[str],
    asserted_state: Optional[Dict[str, Any]],
    review_state: Optional[Dict[str, Any]],
    evidence_available: bool,
    demo_data_present: bool,
    evidence_provenance_projection: Optional[Dict[str, Any]],
    conflict_status_projection: Optional[Dict[str, Any]],
    parameter_integrity_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    missing_items = _missing_core_input_items(asserted_state)
    ambiguous_candidate_ids = list(viable_candidate_ids) if selection_status == "multiple_viable_candidates" else []
    evidence_status = str((evidence_provenance_projection or {}).get("status") or "no_evidence")
    provenance_refs = list((evidence_provenance_projection or {}).get("provenance_refs") or [])
    conflict_status = str((conflict_status_projection or {}).get("status") or "no_conflict")
    affected_keys = list((conflict_status_projection or {}).get("affected_keys") or [])
    integrity_status = str((parameter_integrity_projection or {}).get("integrity_status") or "normalized_ok")
    integrity_blocking_keys = list((parameter_integrity_projection or {}).get("blocking_keys") or [])
    domain_scope_status = str((domain_scope_projection or {}).get("status") or "in_domain_scope")

    if missing_items:
        return {
            "status": "withheld_missing_core_inputs",
            "reason": blocking_reason or "Required core params are not yet confirmed.",
            "missing_items": missing_items,
            "ambiguous_candidate_ids": [],
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": False,
            "handover_possible": False,
            "human_validation_ready": False,
        }

    if demo_data_present:
        return {
            "status": "withheld_demo_data",
            "reason": blocking_reason or "Demo data is quarantined from governed output.",
            "missing_items": [],
            "ambiguous_candidate_ids": [],
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": False,
            "human_validation_ready": False,
        }

    if not evidence_available:
        return {
            "status": "withheld_no_evidence",
            "reason": blocking_reason or "Qualified evidence is missing.",
            "missing_items": [],
            "ambiguous_candidate_ids": [],
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": False,
            "handover_possible": False,
            "human_validation_ready": False,
        }

    if domain_scope_status in {"out_of_domain_scope", "escalation_required"}:
        return {
            "status": "escalation_needed",
            "reason": _build_domain_scope_note(domain_scope_projection),
            "missing_items": [],
            "ambiguous_candidate_ids": ambiguous_candidate_ids,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": False,
            "human_validation_ready": bool(provenance_refs),
        }

    if selection_status == "multiple_viable_candidates":
        return {
            "status": "ambiguous_but_reviewable",
            "reason": blocking_reason or "Multiple viable candidates remain after deterministic checks.",
            "missing_items": [],
            "ambiguous_candidate_ids": ambiguous_candidate_ids,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": True,
            "human_validation_ready": True,
        }

    review = review_state or {}
    if review.get("review_required"):
        return {
            "status": "review_pending",
            "reason": str(review.get("review_reason") or blocking_reason or "Human review pending."),
            "missing_items": [],
            "ambiguous_candidate_ids": [],
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": True,
            "human_validation_ready": True,
        }

    if readiness_status == "releasable":
        return {
            "status": "releasable",
            "reason": "",
            "missing_items": [],
            "ambiguous_candidate_ids": [],
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": True,
            "human_validation_ready": True,
        }

    if integrity_status == "unusable_until_clarified":
        return {
            "status": "escalation_needed",
            "reason": blocking_reason or "Parameterintegrität erfordert weitere Klärung oder Review.",
            "missing_items": [],
            "ambiguous_candidate_ids": ambiguous_candidate_ids,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": False,
            "human_validation_ready": bool(provenance_refs),
        }

    if (conflict_status_projection or {}).get("conflict_still_open"):
        return {
            "status": "escalation_needed",
            "reason": blocking_reason or "Offener Parameterkonflikt erfordert Klärung oder Review.",
            "missing_items": [],
            "ambiguous_candidate_ids": ambiguous_candidate_ids,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": False,
            "human_validation_ready": bool(provenance_refs),
        }

    reviewable_escalation = selection_status in {
        "blocked_no_candidates",
        "blocked_no_viable_candidates",
    } or readiness_status in {"candidate_ambiguity", "no_governed_candidate", "governance_blocked"}
    return {
        "status": "escalation_needed",
        "reason": blocking_reason or "Deterministic engineering escalation is required.",
        "missing_items": [],
        "ambiguous_candidate_ids": ambiguous_candidate_ids,
        "evidence_status": evidence_status,
        "provenance_refs": provenance_refs,
        "conflict_status": conflict_status,
        "integrity_status": integrity_status,
        "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
        "review_meaningful": reviewable_escalation,
        "handover_possible": reviewable_escalation,
        "human_validation_ready": reviewable_escalation,
    }


def _collect_provenance_refs(
    relevant_fact_cards: List[Dict[str, Any]],
    evidence_basis: List[str],
) -> List[str]:
    refs: List[str] = []
    evidence_basis_set = {str(ref) for ref in evidence_basis}
    for card in relevant_fact_cards:
        evidence_id = card.get("evidence_id") or card.get("id")
        if str(evidence_id) not in evidence_basis_set:
            continue
        provenance_ref = card.get("source_ref") or evidence_id
        if not provenance_ref:
            continue
        provenance_ref = str(provenance_ref)
        if provenance_ref not in refs:
            refs.append(provenance_ref)
    return refs


def project_evidence_provenance_state(
    relevant_fact_cards: List[Dict[str, Any]],
    evidence_basis: List[str],
) -> Dict[str, Any]:
    provenance_refs = _collect_provenance_refs(relevant_fact_cards, evidence_basis)
    if not provenance_refs:
        status = "no_evidence"
    elif len(provenance_refs) == 1:
        status = "thin_evidence"
    else:
        status = "grounded_evidence"
    return {
        "status": status,
        "provenance_refs": provenance_refs,
        "evidence_basis": list(evidence_basis),
    }


def _build_evidence_binding_note(
    evidence_provenance_projection: Optional[Dict[str, Any]],
) -> str:
    projection = evidence_provenance_projection or {}
    status = str(projection.get("status") or "no_evidence")
    refs = list(projection.get("provenance_refs") or [])
    ref_text = ", ".join(refs) if refs else "keine"
    if status == "grounded_evidence":
        return "Die technischen Angaben sind durch qualifizierte Referenzdaten gestützt."
    if status == "thin_evidence":
        return "Die technische Referenzbasis ist eingeschränkt; eine ergänzende Herstellerprüfung ist ratsam."
    return "Qualifizierte technische Referenzdaten sind für diese Anfrage nicht verfügbar."


def _extract_observed_field_values(
    observed_state: Optional[Dict[str, Any]],
) -> Dict[str, List[Any]]:
    observed_values: Dict[str, List[Any]] = {}
    for entry in (observed_state or {}).get("observed_inputs", []):
        raw_text = str(entry.get("raw_text") or "")
        if not raw_text:
            continue
        extracted = norm_extract(raw_text)
        field_map = {
            "medium": extracted.get("medium_normalized"),
            "pressure": extracted.get("pressure_bar"),
            "temperature": extracted.get("temperature_c"),
        }
        for field_name, value in field_map.items():
            if value in (None, ""):
                continue
            observed_values.setdefault(field_name, [])
            if value not in observed_values[field_name]:
                observed_values[field_name].append(value)
    return observed_values


def _resolve_current_field_value(
    field_name: str,
    asserted_state: Optional[Dict[str, Any]],
    normalized_state: Optional[Dict[str, Any]],
) -> Any:
    asserted = asserted_state or {}
    normalized_parameters = (normalized_state or {}).get("normalized_parameters") or {}
    operating = asserted.get("operating_conditions") or {}
    if field_name == "medium":
        return (asserted.get("medium_profile") or {}).get("name") or normalized_parameters.get("medium_normalized")
    if field_name == "pressure":
        return operating.get("pressure") if operating.get("pressure") is not None else normalized_parameters.get("pressure_bar")
    if field_name == "temperature":
        return operating.get("temperature") if operating.get("temperature") is not None else normalized_parameters.get("temperature_c")
    return None


def project_conflict_status(
    *,
    observed_state: Optional[Dict[str, Any]],
    normalized_state: Optional[Dict[str, Any]],
    governance_state: Optional[Dict[str, Any]],
    asserted_state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    observed_values = _extract_observed_field_values(observed_state)
    governance_conflicts = list((governance_state or {}).get("conflicts") or [])
    normalized_identities = (normalized_state or {}).get("identity_records") or {}

    conflicting_fields = sorted(
        field_name for field_name, values in observed_values.items()
        if len(values) > 1
    )
    open_conflict_fields = {
        str(conflict.get("field"))
        for conflict in governance_conflicts
        if conflict.get("field") in {"medium", "pressure", "temperature"}
    }
    for field_name, identity in normalized_identities.items():
        if field_name not in {"medium", "pressure", "temperature"}:
            continue
        if identity.get("identity_class") == "identity_unresolved" and "conflict" in str(identity.get("mapping_reason") or ""):
            open_conflict_fields.add(field_name)

    corrected_fields: List[str] = []
    unresolved_fields = set(open_conflict_fields)
    previous_parts: List[str] = []
    current_parts: List[str] = []

    for field_name in conflicting_fields:
        values = list(observed_values.get(field_name) or [])
        current_value = _resolve_current_field_value(field_name, asserted_state, normalized_state)
        previous_value = values[0]
        if len(values) > 1 and current_value not in (None, "") and current_value == values[-1] and field_name not in unresolved_fields:
            corrected_fields.append(field_name)
            previous_parts.append(f"{field_name}={previous_value}")
            current_parts.append(f"{field_name}={current_value}")
        else:
            unresolved_fields.add(field_name)
            previous_parts.append(f"{field_name}={values[0]}")
            current_parts.append(f"{field_name}={values[-1]}")

    affected_keys = sorted(set(corrected_fields) | set(unresolved_fields))
    if unresolved_fields:
        status = "unresolved_conflict" if open_conflict_fields else "conflicting_values"
    elif corrected_fields:
        status = "corrected_value"
    else:
        status = "no_conflict"

    return {
        "status": status,
        "affected_keys": affected_keys,
        "previous_value_summary": ", ".join(previous_parts),
        "current_value_summary": ", ".join(current_parts),
        "correction_applied": bool(corrected_fields) and not bool(unresolved_fields),
        "conflict_still_open": bool(unresolved_fields),
    }


def build_correction_projection(
    conflict_status_projection: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    projection = conflict_status_projection or {}
    if projection.get("status") == "no_conflict":
        return None
    return {
        "affected_keys": list(projection.get("affected_keys") or []),
        "previous_value_summary": str(projection.get("previous_value_summary") or ""),
        "current_value_summary": str(projection.get("current_value_summary") or ""),
        "correction_applied": bool(projection.get("correction_applied")),
        "conflict_still_open": bool(projection.get("conflict_still_open")),
    }


def _identity_or_normalized_value(
    field_name: str,
    normalized_state: Optional[Dict[str, Any]],
    asserted_state: Optional[Dict[str, Any]],
) -> Any:
    identity_records = (normalized_state or {}).get("identity_records") or {}
    identity = identity_records.get(field_name) or {}
    if identity.get("normalized_value") not in (None, ""):
        return identity.get("normalized_value")
    return _resolve_current_field_value(field_name, asserted_state, normalized_state)


def _field_integrity_status(
    field_name: str,
    normalized_state: Optional[Dict[str, Any]],
    asserted_state: Optional[Dict[str, Any]],
) -> Optional[str]:
    identity_records = (normalized_state or {}).get("identity_records") or {}
    identity = identity_records.get(field_name) or {}
    current_value = _identity_or_normalized_value(field_name, normalized_state, asserted_state)
    if current_value in (None, ""):
        return None

    raw_value = str(identity.get("raw_value") or "").strip().lower()
    normalization_certainty = str(identity.get("normalization_certainty") or "")
    mapping_reason = str(identity.get("mapping_reason") or "")
    identity_class = str(identity.get("identity_class") or "")

    if identity_class == "identity_unresolved":
        return "unusable_until_clarified"

    if field_name == "temperature":
        try:
            numeric_value = float(current_value)
        except Exception:
            return "unusable_until_clarified"
        if numeric_value < -273.15:
            return "implausible_value"
        if raw_value.endswith("grad") or (raw_value and re.fullmatch(r"[+-]?\\d+(?:[.,]\\d+)?", raw_value)):
            return "unit_ambiguous"
        if "umgerechnet von" in mapping_reason.lower():
            return "usable_with_warning"
        return "normalized_ok"

    if field_name == "pressure":
        try:
            numeric_value = float(current_value)
        except Exception:
            return "unusable_until_clarified"
        if numeric_value < 0:
            return "implausible_value"
        if raw_value and re.fullmatch(r"[+-]?\\d+(?:[.,]\\d+)?", raw_value):
            return "unit_ambiguous"
        if "umgerechnet von" in mapping_reason.lower():
            return "usable_with_warning"
        return "normalized_ok"

    if field_name == "medium":
        if identity_class == "identity_probable" or normalization_certainty == "inferred":
            return "usable_with_warning"
        if identity_class == "identity_unresolved":
            return "unusable_until_clarified"
        return "normalized_ok"

    return "normalized_ok"


def project_unit_normalization_status(
    *,
    normalized_state: Optional[Dict[str, Any]],
    asserted_state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    statuses: Dict[str, str] = {}
    for field_name in STRUCTURED_REQUIRED_CORE_PARAMS:
        status = _field_integrity_status(field_name, normalized_state, asserted_state)
        if status:
            statuses[field_name] = status

    warning_keys = sorted(
        key for key, status in statuses.items()
        if status == "usable_with_warning"
    )
    blocking_keys = sorted(
        key for key, status in statuses.items()
        if status in {"unit_ambiguous", "implausible_value", "unusable_until_clarified"}
    )
    return {
        "statuses": statuses,
        "affected_keys": sorted(statuses.keys()),
        "warning_keys": warning_keys,
        "blocking_keys": blocking_keys,
    }


def build_parameter_integrity_projection(
    unit_normalization_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    projection = unit_normalization_projection or {}
    warning_keys = list(projection.get("warning_keys") or [])
    blocking_keys = list(projection.get("blocking_keys") or [])
    affected_keys = list(projection.get("affected_keys") or [])
    if blocking_keys:
        integrity_status = "unusable_until_clarified"
    elif warning_keys:
        integrity_status = "usable_with_warning"
    else:
        integrity_status = "normalized_ok"
    return {
        "affected_keys": affected_keys,
        "integrity_status": integrity_status,
        "warning_keys": warning_keys,
        "blocking_keys": blocking_keys,
        "usable_for_structured_step": not bool(blocking_keys),
    }


def project_domain_scope_status(
    threshold_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    projection = threshold_projection or {}
    warning_thresholds = list(projection.get("warning_thresholds") or [])
    blocking_thresholds = list(projection.get("blocking_thresholds") or [])
    threshold_status = str(projection.get("threshold_status") or "threshold_free")

    if (
        "material_limit_exceeded" in blocking_thresholds
        and "extrusion_risk" not in blocking_thresholds
        and "shrinkage_risk" not in blocking_thresholds
    ):
        status = "out_of_domain_scope"
    elif blocking_thresholds:
        status = "escalation_required"
    elif warning_thresholds:
        status = "in_domain_with_warning"
    else:
        status = "in_domain_scope"

    return {
        "status": status,
        "triggered_thresholds": list(projection.get("triggered_thresholds") or []),
        "warning_thresholds": warning_thresholds,
        "blocking_thresholds": blocking_thresholds,
        "threshold_status": threshold_status,
        "usable_for_governed_step": not bool(blocking_thresholds),
    }


def _build_conflict_correction_note(
    conflict_status_projection: Optional[Dict[str, Any]],
) -> str:
    projection = conflict_status_projection or {}
    status = str(projection.get("status") or "no_conflict")
    previous_summary = str(projection.get("previous_value_summary") or "").strip()
    current_summary = str(projection.get("current_value_summary") or "").strip()
    if status == "corrected_value":
        return f"{CORRECTION_APPLIED_PREFIX} {previous_summary} -> {current_summary}."
    if status in {"conflicting_values", "unresolved_conflict"}:
        detail = current_summary or previous_summary
        if detail:
            return f"{UNRESOLVED_CONFLICT_REPLY} Offener Konflikt: {detail}."
        return UNRESOLVED_CONFLICT_REPLY
    return ""


def _build_integrity_note(
    parameter_integrity_projection: Optional[Dict[str, Any]],
    unit_normalization_projection: Optional[Dict[str, Any]],
) -> str:
    integrity = parameter_integrity_projection or {}
    unit_projection = unit_normalization_projection or {}
    integrity_status = str(integrity.get("integrity_status") or "normalized_ok")
    blocking_keys = list(integrity.get("blocking_keys") or [])
    warning_keys = list(integrity.get("warning_keys") or [])
    statuses = dict(unit_projection.get("statuses") or {})
    if integrity_status == "unusable_until_clarified":
        param_count = len(blocking_keys) if blocking_keys else 1
        subject = "Ein Betriebsparameter bedarf" if param_count == 1 else f"{param_count} Betriebsparameter bedürfen"
        return f"{INTEGRITY_UNUSABLE_REPLY} {subject} fachlicher Klärung."
    if integrity_status == "usable_with_warning":
        param_count = len(warning_keys) if warning_keys else 1
        subject = "Ein Betriebsparameter ist" if param_count == 1 else f"{param_count} Betriebsparameter sind"
        return f"{INTEGRITY_WARNING_PREFIX} {subject} mit Vorbehalt verwendbar."
    return ""


def _build_domain_scope_note(
    domain_scope_projection: Optional[Dict[str, Any]],
) -> str:
    projection = domain_scope_projection or {}
    status = str(projection.get("status") or "in_domain_scope")
    warnings = list(projection.get("warning_thresholds") or [])
    blocking = list(projection.get("blocking_thresholds") or [])
    if status == "in_domain_with_warning":
        return f"{DOMAIN_WARNING_PREFIX} Die Betriebsbedingungen liegen an den Grenzen des fachlich abgedeckten Bereichs."
    if status == "out_of_domain_scope":
        return f"{OUT_OF_DOMAIN_REPLY} Die angegebenen Betriebsbedingungen überschreiten den fachlich abgedeckten Bereich."
    if status == "escalation_required":
        return f"{THRESHOLD_ESCALATION_REPLY} Die angegebenen Betriebsbedingungen erfordern eine fachliche Einzelfallprüfung."
    return ""


def project_user_facing_output_status(
    *,
    selection_status: str,
    recommendation_artifact: Optional[Dict[str, Any]],
    review_escalation_projection: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
    projection_invariant_projection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    artifact = recommendation_artifact or {}
    review_projection = review_escalation_projection or {}
    clarification = clarification_projection or {}
    domain_scope = domain_scope_projection or {}
    invariant_projection = projection_invariant_projection or {}

    review_status = str(review_projection.get("status") or "")
    domain_status = str(domain_scope.get("status") or "in_domain_scope")
    readiness_status = str(artifact.get("readiness_status") or "")
    release_status = str(artifact.get("release_status") or "")
    rfq_admissibility = str(artifact.get("rfq_admissibility") or "")

    if not invariant_projection.get("invariant_ok", True):
        status = "withheld_escalation"
    elif selection_status == "blocked_missing_required_inputs":
        status = "clarification_needed"
    elif release_status in {"precheck_only", "manufacturer_validation_required"} or rfq_admissibility == "provisional":
        status = "withheld_review"
    elif review_status == "withheld_no_evidence" or readiness_status == "evidence_missing":
        status = "withheld_no_evidence"
    elif domain_status == "out_of_domain_scope":
        status = "withheld_domain_block"
    elif review_status in {"review_pending", "ambiguous_but_reviewable"} or readiness_status == "review_pending":
        status = "withheld_review"
    elif review_status == "escalation_needed" or readiness_status in {
        "conflict_unresolved",
        "integrity_unusable",
        "domain_scope_blocked",
        "candidate_ambiguity",
        "no_governed_candidate",
        "governance_blocked",
    }:
        status = "withheld_escalation"
    elif artifact.get("candidate_projection"):
        status = "governed_non_binding_result"
    elif clarification.get("clarification_still_meaningful"):
        status = "clarification_needed"
    else:
        status = "withheld_escalation"

    return {"status": status}


def build_output_contract_projection(
    *,
    user_facing_output_projection: Optional[Dict[str, Any]],
    recommendation_artifact: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    review_escalation_projection: Optional[Dict[str, Any]],
    conflict_status_projection: Optional[Dict[str, Any]],
    parameter_integrity_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
    threshold_projection: Optional[Dict[str, Any]],
    projection_invariant_projection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    output_status = str((user_facing_output_projection or {}).get("status") or "withheld_escalation")
    artifact = recommendation_artifact or {}
    clarification = clarification_projection or {}
    review_projection = review_escalation_projection or {}
    conflict_projection = conflict_status_projection or {}
    integrity_projection = parameter_integrity_projection or {}
    domain_scope = domain_scope_projection or {}
    threshold = threshold_projection or {}
    invariant_projection = projection_invariant_projection or {}
    invariant_violations = list(invariant_projection.get("invariant_violations") or [])

    visible_warning_flags: List[str] = []
    if artifact.get("evidence_status") == "thin_evidence":
        visible_warning_flags.append("thin_evidence")
    if conflict_projection.get("correction_applied"):
        visible_warning_flags.append("corrected_value")
    if integrity_projection.get("integrity_status") == "usable_with_warning":
        visible_warning_flags.append("integrity_warning")
    if domain_scope.get("status") == "in_domain_with_warning":
        visible_warning_flags.append("domain_warning")
    if threshold.get("threshold_status") == "warning_thresholds":
        visible_warning_flags.append("threshold_warning")

    if invariant_violations:
        allowed_surface_claims = ["withheld", "state_invariant_violation"]
        next_user_action = (
            "human_review"
            if review_projection.get("review_meaningful")
            else "engineering_escalation"
        )
        suppress_recommendation_details = True
    elif output_status == "governed_non_binding_result":
        allowed_surface_claims = ["non_binding_result", "warnings", "next_step_none"]
        next_user_action = "confirmed_result_review"
        suppress_recommendation_details = False
    elif output_status == "clarification_needed":
        allowed_surface_claims = ["missing_inputs", "single_next_question"]
        next_user_action = (
            "answer_next_question"
            if clarification.get("clarification_still_meaningful")
            else "pause_for_review_or_escalation"
        )
        suppress_recommendation_details = True
    elif output_status == "withheld_review":
        allowed_surface_claims = ["withheld", "review_required"]
        next_user_action = "human_review"
        suppress_recommendation_details = True
    elif output_status == "withheld_no_evidence":
        allowed_surface_claims = ["withheld", "evidence_missing"]
        next_user_action = "obtain_qualified_evidence"
        suppress_recommendation_details = True
    elif output_status == "withheld_domain_block":
        allowed_surface_claims = ["withheld", "domain_block"]
        next_user_action = "engineering_escalation"
        suppress_recommendation_details = True
    else:
        allowed_surface_claims = ["withheld", "escalation_required"]
        next_user_action = (
            "human_review"
            if review_projection.get("review_meaningful")
            else "engineering_escalation"
        )
        suppress_recommendation_details = True

    if conflict_projection.get("conflict_still_open"):
        visible_warning_flags.append("conflict_open")
    if integrity_projection.get("integrity_status") == "unusable_until_clarified":
        visible_warning_flags.append("integrity_blocked")
    if domain_scope.get("status") in {"out_of_domain_scope", "escalation_required"}:
        visible_warning_flags.append("domain_blocked")
    if invariant_violations:
        visible_warning_flags.append("invariant_violation")

    return {
        "output_status": output_status,
        "allowed_surface_claims": visible_warning_flags and list(dict.fromkeys(allowed_surface_claims)) or allowed_surface_claims,
        "next_user_action": next_user_action,
        "visible_warning_flags": list(dict.fromkeys(visible_warning_flags)),
        "suppress_recommendation_details": suppress_recommendation_details,
    }


def project_projection_invariants(
    *,
    recommendation_artifact: Optional[Dict[str, Any]],
    review_escalation_projection: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    evidence_provenance_projection: Optional[Dict[str, Any]],
    conflict_status_projection: Optional[Dict[str, Any]],
    parameter_integrity_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
    output_contract_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    artifact = recommendation_artifact or {}
    review_projection = review_escalation_projection or {}
    clarification = clarification_projection or {}
    evidence_projection = evidence_provenance_projection or {}
    conflict_projection = conflict_status_projection or {}
    integrity_projection = parameter_integrity_projection or {}
    domain_scope = domain_scope_projection or {}
    output_contract = output_contract_projection or {}

    output_status = str(output_contract.get("output_status") or "withheld_escalation")
    suppress_details = bool(output_contract.get("suppress_recommendation_details"))
    candidate_projection = artifact.get("candidate_projection")
    readiness_status = str(artifact.get("readiness_status") or "")
    review_status = str(review_projection.get("status") or "")
    evidence_status = str(evidence_projection.get("status") or "no_evidence")
    clarification_meaningful = bool(clarification.get("clarification_still_meaningful"))
    conflict_open = bool(conflict_projection.get("conflict_still_open"))
    integrity_blocked = str(integrity_projection.get("integrity_status") or "") == "unusable_until_clarified"
    domain_blocked = str(domain_scope.get("status") or "") in {"out_of_domain_scope", "escalation_required"}
    blocked_by_review = review_status in {
        "review_pending",
        "ambiguous_but_reviewable",
        "withheld_no_evidence",
        "withheld_demo_data",
        "escalation_needed",
    }
    blocked_clarification_step = review_status in {
        "review_pending",
        "ambiguous_but_reviewable",
        "withheld_no_evidence",
        "withheld_demo_data",
    }

    violations: List[str] = []

    if output_status == "governed_non_binding_result" and suppress_details:
        violations.append("governed_result_cannot_suppress_recommendation_details")
    if output_status == "governed_non_binding_result" and not candidate_projection:
        violations.append("governed_result_requires_candidate_projection")
    if output_status == "governed_non_binding_result" and (
        conflict_open
        or integrity_blocked
        or domain_blocked
        or evidence_status == "no_evidence"
        or blocked_by_review
    ):
        violations.append("governed_result_conflicts_with_blocking_projection")
    if output_status == "clarification_needed" and (
        blocked_clarification_step
        or domain_blocked
        or evidence_status == "no_evidence"
    ):
        violations.append("clarification_output_conflicts_with_blocking_projection")
    if conflict_open and (output_status == "governed_non_binding_result" or candidate_projection):
        violations.append("unresolved_conflict_cannot_surface_technical_preselection")
    if readiness_status == "releasable" and (
        review_status != "releasable"
        or evidence_status == "no_evidence"
        or conflict_open
        or integrity_blocked
        or domain_blocked
    ):
        violations.append("releasable_readiness_conflicts_with_blocking_projection")

    return {
        "invariant_ok": not violations,
        "invariant_violations": list(dict.fromkeys(violations)),
    }


def _apply_invariant_safeguards(
    *,
    recommendation_artifact: Dict[str, Any],
    user_facing_output_projection: Dict[str, Any],
    output_contract_projection: Dict[str, Any],
    projection_invariant_projection: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], bool]:
    if projection_invariant_projection.get("invariant_ok", True):
        return (
            recommendation_artifact,
            user_facing_output_projection,
            output_contract_projection,
            bool(recommendation_artifact.get("output_blocked")),
        )

    safe_artifact = dict(recommendation_artifact)
    safe_artifact["candidate_projection"] = None
    safe_artifact["output_blocked"] = True
    safe_artifact["readiness_status"] = "invariant_blocked"
    safe_artifact["blocking_reason"] = (
        "Projection invariants violated — governed output downgraded to a safe withheld state."
    )
    safe_artifact["rationale_summary"] = INVARIANT_BLOCKED_REPLY

    safe_user_facing = {"status": "withheld_escalation"}
    safe_output_contract = dict(output_contract_projection)
    safe_output_contract["output_status"] = "withheld_escalation"
    safe_output_contract["allowed_surface_claims"] = ["withheld", "state_invariant_violation"]
    safe_output_contract["suppress_recommendation_details"] = True
    safe_output_contract["visible_warning_flags"] = list(dict.fromkeys(
        list(safe_output_contract.get("visible_warning_flags") or []) + ["invariant_violation"]
    ))

    return safe_artifact, safe_user_facing, safe_output_contract, True


def build_state_trace_audit_projection(
    *,
    selection_status: str,
    recommendation_artifact: Optional[Dict[str, Any]],
    review_escalation_projection: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    conflict_status_projection: Optional[Dict[str, Any]],
    parameter_integrity_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
    output_contract_projection: Optional[Dict[str, Any]],
    projection_invariant_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    artifact = recommendation_artifact or {}
    review_projection = review_escalation_projection or {}
    clarification = clarification_projection or {}
    conflict_projection = conflict_status_projection or {}
    integrity_projection = parameter_integrity_projection or {}
    domain_scope = domain_scope_projection or {}
    output_contract = output_contract_projection or {}
    invariant_projection = projection_invariant_projection or {}

    output_status = str(output_contract.get("output_status") or "withheld_escalation")
    review_status = str(review_projection.get("status") or "")
    readiness_status = str(artifact.get("readiness_status") or "")
    release_status = str(artifact.get("release_status") or "")
    rfq_admissibility = str(artifact.get("rfq_admissibility") or "")
    candidate_projection = artifact.get("candidate_projection")
    conflict_open = bool(conflict_projection.get("conflict_still_open"))
    integrity_status = str(integrity_projection.get("integrity_status") or "normalized_ok")
    domain_status = str(domain_scope.get("status") or "in_domain_scope")
    invariant_violations = list(invariant_projection.get("invariant_violations") or [])
    missing_items = list(clarification.get("missing_items") or [])

    blocking_reasons: List[str] = []
    contributing_reasons: List[str] = []
    trace_flags = list(output_contract.get("visible_warning_flags") or [])

    if invariant_violations:
        blocking_reasons.append("invariant_blocked")
        contributing_reasons.extend(invariant_violations)
        primary_reason = "invariant_blocked"
    elif output_status == "governed_non_binding_result" and candidate_projection:
        primary_reason = "governed_releasable_result"
        if artifact.get("evidence_status") == "thin_evidence":
            contributing_reasons.append("evidence_thin")
    elif output_status == "clarification_needed":
        primary_reason = "clarification_missing_inputs"
        if missing_items:
            contributing_reasons.append("missing_inputs")
    elif output_status == "withheld_review":
        if review_status == "review_pending":
            primary_reason = "review_pending"
            blocking_reasons.append("review_pending")
        elif review_status == "ambiguous_but_reviewable" or selection_status == "multiple_viable_candidates":
            primary_reason = "review_candidate_ambiguity"
            blocking_reasons.append("candidate_ambiguity")
        elif release_status in {"precheck_only", "manufacturer_validation_required"} or rfq_admissibility == "provisional":
            primary_reason = "review_governance_withheld"
            blocking_reasons.append("governance_withheld")
        else:
            primary_reason = "review_required"
            blocking_reasons.append("review_required")
    elif output_status == "withheld_no_evidence":
        primary_reason = "withheld_no_evidence"
        blocking_reasons.append("no_evidence")
    elif output_status == "withheld_domain_block":
        primary_reason = "domain_scope_blocked"
        blocking_reasons.append("domain_blocked")
    elif conflict_open or readiness_status == "conflict_unresolved":
        primary_reason = "escalation_conflict_open"
        blocking_reasons.append("conflict_open")
    elif integrity_status == "unusable_until_clarified" or readiness_status == "integrity_unusable":
        primary_reason = "escalation_integrity_blocked"
        blocking_reasons.append("integrity_blocked")
    elif domain_status == "escalation_required" or readiness_status == "domain_scope_blocked":
        primary_reason = "escalation_domain_threshold"
        blocking_reasons.append("domain_threshold_blocked")
    elif selection_status == "blocked_no_candidates":
        primary_reason = "escalation_no_candidates"
        blocking_reasons.append("no_candidates")
    elif selection_status == "blocked_no_viable_candidates":
        primary_reason = "escalation_no_viable_candidates"
        blocking_reasons.append("no_viable_candidates")
    elif readiness_status == "governance_blocked":
        primary_reason = "escalation_governance_blocked"
        blocking_reasons.append("governance_blocked")
    elif readiness_status == "no_governed_candidate":
        primary_reason = "escalation_no_governed_candidate"
        blocking_reasons.append("no_governed_candidate")
    elif readiness_status == "candidate_ambiguity":
        primary_reason = "review_candidate_ambiguity"
        blocking_reasons.append("candidate_ambiguity")
    else:
        primary_reason = "escalation_required"
        if output_status != "governed_non_binding_result":
            blocking_reasons.append("escalation_required")

    if missing_items and primary_reason != "clarification_missing_inputs":
        contributing_reasons.append("missing_inputs")
    if review_status == "escalation_needed":
        contributing_reasons.append("review_escalation")
    elif review_status == "review_pending":
        contributing_reasons.append("review_pending")
    elif review_status == "ambiguous_but_reviewable":
        contributing_reasons.append("candidate_ambiguity")
    elif review_status == "withheld_no_evidence":
        contributing_reasons.append("no_evidence")
    elif review_status == "withheld_demo_data":
        contributing_reasons.append("demo_data_quarantine")

    if conflict_open:
        contributing_reasons.append("conflict_open")
    if integrity_status == "unusable_until_clarified":
        contributing_reasons.append("integrity_blocked")
    elif integrity_status == "usable_with_warning":
        trace_flags.append("integrity_warning")
    if domain_status == "out_of_domain_scope":
        contributing_reasons.append("domain_blocked")
    elif domain_status == "escalation_required":
        contributing_reasons.append("domain_threshold_blocked")
    elif domain_status == "in_domain_with_warning":
        trace_flags.append("domain_warning")
    if artifact.get("evidence_status") == "no_evidence":
        contributing_reasons.append("no_evidence")
    if release_status in {"precheck_only", "manufacturer_validation_required"} or rfq_admissibility == "provisional":
        contributing_reasons.append("governance_withheld")

    return {
        "primary_status_reason": primary_reason,
        "contributing_reasons": list(dict.fromkeys(contributing_reasons)),
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "trace_flags": list(dict.fromkeys(trace_flags)),
    }


def get_primary_trace_reason(state_trace_audit_projection: Optional[Dict[str, Any]]) -> str:
    projection = state_trace_audit_projection or {}
    return str(projection.get("primary_status_reason") or "")


def is_blocked_by_trace(
    state_trace_audit_projection: Optional[Dict[str, Any]],
    reason_code: Optional[str] = None,
) -> bool:
    projection = state_trace_audit_projection or {}
    blocking_reasons = set(str(item) for item in (projection.get("blocking_reasons") or []))
    if reason_code is None:
        return bool(blocking_reasons)
    return str(reason_code) in blocking_reasons


def build_case_summary_projection(
    *,
    asserted_state: Optional[Dict[str, Any]],
    output_contract_projection: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    state_trace_audit_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    output_contract = output_contract_projection or {}
    clarification = clarification_projection or {}
    trace_projection = state_trace_audit_projection or {}

    missing_core_fields = _missing_core_input_items(asserted_state)
    confirmed_core_fields = [
        key for key in STRUCTURED_REQUIRED_CORE_PARAMS
        if key not in missing_core_fields
    ]
    current_case_status = str(output_contract.get("output_status") or "withheld_escalation")
    active_blockers = list(trace_projection.get("blocking_reasons") or [])
    next_step = str(output_contract.get("next_user_action") or "")

    if "invariant_blocked" in active_blockers:
        next_step = "engineering_escalation"
    elif current_case_status == "withheld_escalation" and active_blockers and not set(active_blockers).issubset({"review_pending", "candidate_ambiguity", "review_required"}):
        next_step = "engineering_escalation"
    elif current_case_status == "clarification_needed" and not next_step:
        next_step = (
            "answer_next_question"
            if clarification.get("clarification_still_meaningful")
            else "pause_for_review_or_escalation"
        )
    elif current_case_status == "governed_non_binding_result" and not next_step:
        next_step = "confirmed_result_review"
    elif not next_step:
        next_step = "engineering_escalation"

    return {
        "current_case_status": current_case_status,
        "confirmed_core_fields": confirmed_core_fields,
        "missing_core_fields": missing_core_fields,
        "active_blockers": active_blockers,
        "next_step": next_step,
    }


def get_case_status(case_summary_projection: Optional[Dict[str, Any]]) -> str:
    projection = case_summary_projection or {}
    return str(projection.get("current_case_status") or "")


def get_next_case_step(case_summary_projection: Optional[Dict[str, Any]]) -> str:
    projection = case_summary_projection or {}
    return str(projection.get("next_step") or "")


def has_active_blockers(case_summary_projection: Optional[Dict[str, Any]]) -> bool:
    projection = case_summary_projection or {}
    return bool(projection.get("active_blockers") or [])


def build_actionability_projection(
    *,
    case_summary_projection: Optional[Dict[str, Any]],
    output_contract_projection: Optional[Dict[str, Any]],
    review_escalation_projection: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    projection_invariant_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    summary = case_summary_projection or {}
    output_contract = output_contract_projection or {}
    review_projection = review_escalation_projection or {}
    clarification = clarification_projection or {}
    invariant_projection = projection_invariant_projection or {}

    current_case_status = str(summary.get("current_case_status") or "withheld_escalation")
    active_blockers = list(summary.get("active_blockers") or [])
    next_expected_user_action = str(
        summary.get("next_step")
        or output_contract.get("next_user_action")
        or "engineering_escalation"
    )
    review_status = str(review_projection.get("status") or "")
    handover_possible = bool(review_projection.get("handover_possible"))

    if not invariant_projection.get("invariant_ok", True) or "invariant_blocked" in active_blockers:
        actionability_status = "blocked"
        primary_allowed_action = "no_action_until_clarified"
    elif current_case_status == "clarification_needed":
        if clarification.get("clarification_still_meaningful"):
            actionability_status = "input_required"
            primary_allowed_action = "provide_missing_input"
        else:
            actionability_status = "blocked"
            primary_allowed_action = "no_action_until_clarified"
    elif current_case_status == "withheld_no_evidence":
        actionability_status = "evidence_required"
        primary_allowed_action = "obtain_qualified_evidence"
    elif current_case_status == "withheld_review":
        if handover_possible and review_status == "ambiguous_but_reviewable":
            actionability_status = "handoverable_restricted"
            primary_allowed_action = "prepare_handover"
        else:
            actionability_status = "review_pending"
            primary_allowed_action = "await_review"
    elif current_case_status == "governed_non_binding_result":
        actionability_status = "result_available"
        primary_allowed_action = "consume_governed_result"
    else:
        actionability_status = "escalation_required"
        primary_allowed_action = "escalate_engineering"

    blocked_actions = [
        action for action in _ACTIONABILITY_ACTIONS
        if action != primary_allowed_action
    ]
    return {
        "actionability_status": actionability_status,
        "primary_allowed_action": primary_allowed_action,
        "blocked_actions": blocked_actions,
        "next_expected_user_action": next_expected_user_action,
    }


def get_primary_allowed_action(actionability_projection: Optional[Dict[str, Any]]) -> str:
    projection = actionability_projection or {}
    return str(projection.get("primary_allowed_action") or "")


def get_next_expected_user_action(actionability_projection: Optional[Dict[str, Any]]) -> str:
    projection = actionability_projection or {}
    return str(projection.get("next_expected_user_action") or "")


def is_action_blocked(
    actionability_projection: Optional[Dict[str, Any]],
    action_code: str,
) -> bool:
    projection = actionability_projection or {}
    blocked_actions = set(str(item) for item in (projection.get("blocked_actions") or []))
    return str(action_code) in blocked_actions


def _compare_transition(previous_value: Any, current_value: Any) -> str:
    previous_code = str(previous_value or "none")
    current_code = str(current_value or "none")
    if previous_code == current_code:
        return "unchanged"
    return f"{previous_code}_to_{current_code}"


def compare_case_status(
    previous_case_summary_projection: Optional[Dict[str, Any]],
    current_case_summary_projection: Optional[Dict[str, Any]],
) -> str:
    return _compare_transition(
        get_case_status(previous_case_summary_projection),
        get_case_status(current_case_summary_projection),
    )


def compare_actionability(
    previous_actionability_projection: Optional[Dict[str, Any]],
    current_actionability_projection: Optional[Dict[str, Any]],
) -> str:
    previous_projection = previous_actionability_projection or {}
    current_projection = current_actionability_projection or {}
    return _compare_transition(
        previous_projection.get("actionability_status"),
        current_projection.get("actionability_status"),
    )


def _delta_state_severity(selection_state: Optional[Dict[str, Any]]) -> int:
    from app.agent.domain.threshold import _threshold_scope_level

    state = selection_state or {}
    output_contract = state.get("output_contract_projection") or {}
    case_summary = state.get("case_summary_projection") or {}
    actionability = state.get("actionability_projection") or {}
    invariant_projection = state.get("projection_invariant_projection") or {}
    domain_scope = state.get("domain_scope_projection") or {}
    threshold_projection = state.get("threshold_projection") or {}
    integrity_projection = state.get("parameter_integrity_projection") or {}
    active_blockers = set(str(item) for item in (case_summary.get("active_blockers") or []))
    output_status = str(output_contract.get("output_status") or "")
    actionability_status = str(actionability.get("actionability_status") or "")

    if not invariant_projection.get("invariant_ok", True) or "invariant_blocked" in active_blockers:
        return 6
    if output_status in {"withheld_domain_block", "withheld_escalation", "withheld_no_evidence"} or actionability_status in {"blocked", "escalation_required", "evidence_required"}:
        return 5
    if output_status == "withheld_review" or actionability_status in {"review_pending", "handoverable_restricted"}:
        return 4
    if output_status == "clarification_needed" or actionability_status == "input_required":
        return 3
    if _threshold_scope_level(
        threshold_projection=threshold_projection,
        domain_scope_projection=domain_scope,
    ) == "warning" or str(integrity_projection.get("integrity_status") or "") == "usable_with_warning":
        return 2
    if output_status == "governed_non_binding_result" and actionability_status == "result_available":
        return 0
    return 4


def _classify_delta_direction(
    *,
    previous_selection_state: Optional[Dict[str, Any]],
    current_selection_state: Optional[Dict[str, Any]],
    changed_keys: List[str],
) -> str:
    if not changed_keys:
        return "unchanged"

    previous_score = _delta_state_severity(previous_selection_state)
    current_score = _delta_state_severity(current_selection_state)

    if current_score < previous_score:
        return "improved"
    if current_score > previous_score:
        if current_score >= 5 and previous_score < 5:
            return "more_blocked"
        return "degraded"
    return "changed"


def build_state_delta_projection(
    *,
    previous_selection_state: Optional[Dict[str, Any]],
    current_selection_state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    previous_state = previous_selection_state or {}
    current_state = current_selection_state or {}
    previous_summary = previous_state.get("case_summary_projection") or {}
    current_summary = current_state.get("case_summary_projection") or {}
    previous_actionability = previous_state.get("actionability_projection") or {}
    current_actionability = current_state.get("actionability_projection") or {}
    previous_output_contract = previous_state.get("output_contract_projection") or {}
    current_output_contract = current_state.get("output_contract_projection") or {}
    previous_domain_scope = previous_state.get("domain_scope_projection") or {}
    current_domain_scope = current_state.get("domain_scope_projection") or {}
    previous_threshold = previous_state.get("threshold_projection") or {}
    current_threshold = current_state.get("threshold_projection") or {}
    previous_integrity = previous_state.get("parameter_integrity_projection") or {}
    current_integrity = current_state.get("parameter_integrity_projection") or {}
    previous_conflict = previous_state.get("conflict_status_projection") or {}
    current_conflict = current_state.get("conflict_status_projection") or {}
    previous_invariant = previous_state.get("projection_invariant_projection") or {}
    current_invariant = current_state.get("projection_invariant_projection") or {}

    case_status_delta = compare_case_status(previous_summary, current_summary)
    actionability_delta = compare_actionability(previous_actionability, current_actionability)
    threshold_scope_delta = compare_threshold_scope(
        previous_threshold_projection=previous_threshold,
        current_threshold_projection=current_threshold,
        previous_domain_scope_projection=previous_domain_scope,
        current_domain_scope_projection=current_domain_scope,
    )

    changed_statuses: Dict[str, Dict[str, Any]] = {}

    def record_change(key: str, previous_value: Any, current_value: Any, *, delta: Optional[str] = None) -> None:
        if previous_value == current_value:
            return
        payload: Dict[str, Any] = {
            "from": previous_value,
            "to": current_value,
        }
        if delta and delta != "unchanged":
            payload["delta"] = delta
        changed_statuses[key] = payload

    previous_active_blockers = list(previous_summary.get("active_blockers") or [])
    current_active_blockers = list(current_summary.get("active_blockers") or [])
    previous_blocked_actions = sorted(str(item) for item in (previous_actionability.get("blocked_actions") or []))
    current_blocked_actions = sorted(str(item) for item in (current_actionability.get("blocked_actions") or []))

    record_change(
        "invariant_ok",
        bool(previous_invariant.get("invariant_ok", True)),
        bool(current_invariant.get("invariant_ok", True)),
        delta=_compare_transition(
            bool(previous_invariant.get("invariant_ok", True)),
            bool(current_invariant.get("invariant_ok", True)),
        ),
    )
    record_change(
        "conflict_status",
        str(previous_conflict.get("status") or "no_conflict"),
        str(current_conflict.get("status") or "no_conflict"),
        delta=_compare_transition(
            previous_conflict.get("status") or "no_conflict",
            current_conflict.get("status") or "no_conflict",
        ),
    )
    record_change(
        "integrity_status",
        str(previous_integrity.get("integrity_status") or "normalized_ok"),
        str(current_integrity.get("integrity_status") or "normalized_ok"),
        delta=_compare_transition(
            previous_integrity.get("integrity_status") or "normalized_ok",
            current_integrity.get("integrity_status") or "normalized_ok",
        ),
    )
    record_change(
        "domain_scope_status",
        str(previous_domain_scope.get("status") or "in_domain_scope"),
        str(current_domain_scope.get("status") or "in_domain_scope"),
        delta=threshold_scope_delta,
    )
    record_change(
        "threshold_status",
        str(previous_threshold.get("threshold_status") or "threshold_free"),
        str(current_threshold.get("threshold_status") or "threshold_free"),
        delta=threshold_scope_delta,
    )
    record_change(
        "output_status",
        str(previous_output_contract.get("output_status") or ""),
        str(current_output_contract.get("output_status") or ""),
        delta=_compare_transition(
            previous_output_contract.get("output_status"),
            current_output_contract.get("output_status"),
        ),
    )
    record_change(
        "case_status",
        get_case_status(previous_summary),
        get_case_status(current_summary),
        delta=case_status_delta,
    )
    record_change(
        "actionability_status",
        str(previous_actionability.get("actionability_status") or ""),
        str(current_actionability.get("actionability_status") or ""),
        delta=actionability_delta,
    )
    record_change(
        "primary_allowed_action",
        get_primary_allowed_action(previous_actionability),
        get_primary_allowed_action(current_actionability),
        delta=_compare_transition(
            get_primary_allowed_action(previous_actionability),
            get_primary_allowed_action(current_actionability),
        ),
    )
    record_change(
        "next_step",
        get_next_case_step(previous_summary),
        get_next_case_step(current_summary),
        delta=_compare_transition(
            get_next_case_step(previous_summary),
            get_next_case_step(current_summary),
        ),
    )
    record_change(
        "next_expected_user_action",
        get_next_expected_user_action(previous_actionability),
        get_next_expected_user_action(current_actionability),
        delta=_compare_transition(
            get_next_expected_user_action(previous_actionability),
            get_next_expected_user_action(current_actionability),
        ),
    )
    record_change(
        "active_blockers",
        previous_active_blockers,
        current_active_blockers,
        delta=_compare_transition(
            "|".join(previous_active_blockers),
            "|".join(current_active_blockers),
        ),
    )
    record_change(
        "blocked_actions",
        previous_blocked_actions,
        current_blocked_actions,
        delta=_compare_transition(
            "|".join(previous_blocked_actions),
            "|".join(current_blocked_actions),
        ),
    )

    changed_keys = [
        key for key in _STATE_DELTA_FIELD_ORDER
        if key in changed_statuses
    ]

    if "invariant_ok" in changed_statuses:
        primary_delta_reason = "invariant_status_changed"
    elif "conflict_status" in changed_statuses:
        primary_delta_reason = "conflict_status_changed"
    elif "integrity_status" in changed_statuses:
        primary_delta_reason = "integrity_status_changed"
    elif "domain_scope_status" in changed_statuses or "threshold_status" in changed_statuses:
        primary_delta_reason = "threshold_scope_changed"
    elif "output_status" in changed_statuses:
        primary_delta_reason = "output_status_changed"
    elif "case_status" in changed_statuses:
        primary_delta_reason = "case_status_changed"
    elif "actionability_status" in changed_statuses or "primary_allowed_action" in changed_statuses:
        primary_delta_reason = "actionability_changed"
    elif "next_step" in changed_statuses or "next_expected_user_action" in changed_statuses:
        primary_delta_reason = "next_step_changed"
    elif "active_blockers" in changed_statuses:
        primary_delta_reason = "blocker_set_changed"
    elif "blocked_actions" in changed_statuses:
        primary_delta_reason = "blocked_actions_changed"
    else:
        primary_delta_reason = "no_relevant_change"

    return {
        "changed_keys": changed_keys,
        "changed_statuses": changed_statuses,
        "primary_delta_reason": primary_delta_reason,
        "delta_direction": _classify_delta_direction(
            previous_selection_state=previous_state,
            current_selection_state=current_state,
            changed_keys=changed_keys,
        ),
    }


def build_structured_snapshot(
    selection_state: Optional[Dict[str, Any]],
    *,
    asserted_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    state = selection_state or {}
    output_contract = state.get("output_contract_projection") or {}
    trace_projection = state.get("state_trace_audit_projection") or build_state_trace_audit_projection(
        selection_status=str(state.get("selection_status") or ""),
        recommendation_artifact=state.get("recommendation_artifact"),
        review_escalation_projection=state.get("review_escalation_projection"),
        clarification_projection=state.get("clarification_projection"),
        conflict_status_projection=state.get("conflict_status_projection"),
        parameter_integrity_projection=state.get("parameter_integrity_projection"),
        domain_scope_projection=state.get("domain_scope_projection"),
        output_contract_projection=output_contract,
        projection_invariant_projection=state.get("projection_invariant_projection"),
    )
    case_summary = state.get("case_summary_projection") or build_case_summary_projection(
        asserted_state=asserted_state,
        output_contract_projection=output_contract,
        clarification_projection=state.get("clarification_projection"),
        state_trace_audit_projection=trace_projection,
    )
    actionability = state.get("actionability_projection") or build_actionability_projection(
        case_summary_projection=case_summary,
        output_contract_projection=output_contract,
        review_escalation_projection=state.get("review_escalation_projection"),
        clarification_projection=state.get("clarification_projection"),
        projection_invariant_projection=state.get("projection_invariant_projection"),
    )

    return {
        "case_status": get_case_status(case_summary),
        "output_status": str(output_contract.get("output_status") or ""),
        "primary_reason": get_primary_trace_reason(trace_projection),
        "next_step": get_next_case_step(case_summary),
        "primary_allowed_action": get_primary_allowed_action(actionability),
        "active_blockers": list(case_summary.get("active_blockers") or []),
    }


def compare_structured_snapshots(
    previous_snapshot: Optional[Dict[str, Any]],
    current_snapshot: Optional[Dict[str, Any]],
    *,
    delta_projection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    previous = previous_snapshot or {}
    current = current_snapshot or {}
    delta = delta_projection or {}

    previous_blockers = list(previous.get("active_blockers") or [])
    current_blockers = list(current.get("active_blockers") or [])
    previous_blocker_set = set(str(item) for item in previous_blockers)
    current_blocker_set = set(str(item) for item in current_blockers)

    previous_action = str(previous.get("primary_allowed_action") or "")
    current_action = str(current.get("primary_allowed_action") or "")
    action_changed = previous_action != current_action

    return {
        "from_status": str(previous.get("case_status") or ""),
        "to_status": str(current.get("case_status") or ""),
        "changed_actions": {
            "from_primary_allowed_action": previous_action,
            "to_primary_allowed_action": current_action,
            "action_changed": action_changed,
        },
        "changed_blockers": {
            "added": sorted(current_blocker_set - previous_blocker_set),
            "removed": sorted(previous_blocker_set - current_blocker_set),
        },
        "primary_delta_reason": str(delta.get("primary_delta_reason") or "no_relevant_change"),
        "delta_direction": str(delta.get("delta_direction") or "unchanged"),
    }
