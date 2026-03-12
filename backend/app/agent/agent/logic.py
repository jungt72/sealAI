from typing import List, Dict, Any, Tuple, Optional
import re
from app.agent.evidence.models import Claim, ClaimType
from app.agent.agent.state import SealingAIState
from app.agent.domain.parameters import PhysicalParameter
from app.agent.domain.limits import OperatingLimit
from app.agent.domain.material import MaterialValidator, MaterialPhysicalProfile, normalize_fact_card_evidence
from app.agent.agent.calc import calculate_physics
from app.agent.agent.utils import validate_material_risk
from copy import deepcopy

_NORMATIVE_RELEASE_STATUSES = {
    "inadmissible",
    "precheck_only",
    "manufacturer_validation_required",
    "rfq_ready",
}
_NORMATIVE_RFQ_ADMISSIBILITY = {"inadmissible", "provisional", "ready"}
_NORMATIVE_SPECIFICITY = {
    "family_only",
    "subfamily",
    "compound_required",
    "product_family_required",
}
_BLOCKING_CONFLICT_SEVERITIES = {"CRITICAL", "BLOCKING_UNKNOWN"}
_MANUFACTURER_CONFLICT_SEVERITIES = {"RESOLUTION_REQUIRES_MANUFACTURER_SCOPE"}
_BLOCKING_CONFLICT_TYPES = {
    "domain_limit_violation",
    "parameter_conflict",
    "scope_conflict",
    "condition_conflict",
    "compound_specificity_conflict",
    "identity_unresolved",
    "temporal_validity_conflict",
    "assumption_conflict",
}
_MANUFACTURER_CONFLICT_TYPES = {
    "manufacturer_scope_required",
    "resolution_requires_manufacturer_scope",
}
_MATERIAL_FAMILY_PATTERN = re.compile(r"\b(NBR|PTFE|FKM|EPDM|SILIKON)\b", re.I)
_SPECIFIC_GRADE_PATTERN = re.compile(r"\b(?:grade|compound|typ|type)\s*[:\-]?\s*([a-z0-9._-]+)\b", re.I)
_FILLER_HINT_PATTERN = re.compile(r"\b(filled|glass[- ]filled|carbon[- ]filled|bronze[- ]filled)\b", re.I)
_MANUFACTURER_NAME_PATTERN = re.compile(
    r"\b(?:manufacturer|hersteller|brand)\s*[:\-]?\s*([a-z0-9][a-z0-9_-]*(?: [a-z0-9][a-z0-9_-]*){0,3})\b",
    re.I,
)


def _ensure_state_shape(state: SealingAIState) -> SealingAIState:
    """Blueprint Section 02/12: keep all five layers and mandatory governance fields present."""

    state.setdefault("observed", {"observed_inputs": [], "raw_parameters": {}})
    state.setdefault("normalized", {"identity_records": {}, "normalized_parameters": {}})
    state.setdefault(
        "asserted",
        {
            "medium_profile": {},
            "machine_profile": {},
            "installation_profile": {},
            "operating_conditions": {},
            "sealing_requirement_spec": {},
        },
    )
    state.setdefault(
        "governance",
        {
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "scope_of_validity": [],
            "assumptions_active": [],
            "gate_failures": [],
            "unknowns_release_blocking": [],
            "unknowns_manufacturer_validation": [],
            "conflicts": [],
        },
    )
    state.setdefault(
        "cycle",
        {
            "analysis_cycle_id": "session_init_1",
            "snapshot_parent_revision": 0,
            "superseded_by_cycle": None,
            "contract_obsolete": False,
            "contract_obsolete_reason": None,
            "state_revision": 1,
        },
    )
    state.setdefault(
        "selection",
        {
            "selection_status": "not_started",
            "candidates": [],
            "viable_candidate_ids": [],
            "blocked_candidates": [],
            "winner_candidate_id": None,
            "recommendation_artifact": None,
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "output_blocked": True,
        },
    )
    return state


def _normalize_release_status(value: Optional[str]) -> str:
    if value in _NORMATIVE_RELEASE_STATUSES:
        return value
    return "inadmissible"


def _normalize_rfq_admissibility(value: Optional[str]) -> str:
    if value in _NORMATIVE_RFQ_ADMISSIBILITY:
        return value
    return "inadmissible"


def _normalize_specificity(value: Optional[str]) -> str:
    if value in _NORMATIVE_SPECIFICITY:
        return value
    return "family_only"


def _normalize_conflict_record(conflict: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(conflict)
    conflict_type = str(normalized.get("type") or "parameter_conflict").strip().lower()
    severity = str(normalized.get("severity") or "CRITICAL").strip().upper()

    if conflict_type in _MANUFACTURER_CONFLICT_TYPES and severity not in _MANUFACTURER_CONFLICT_SEVERITIES:
        severity = "RESOLUTION_REQUIRES_MANUFACTURER_SCOPE"
    elif conflict_type in _BLOCKING_CONFLICT_TYPES and severity not in _BLOCKING_CONFLICT_SEVERITIES:
        severity = "CRITICAL"

    normalized["type"] = conflict_type
    normalized["severity"] = severity
    return normalized


def _record_observed_claims(state: SealingAIState, raw_claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    observed_entries: List[Dict[str, Any]] = []
    observed_layer = state["observed"]
    raw_parameters = observed_layer.setdefault("raw_parameters", {})

    for claim in raw_claims:
        statement = str(claim.get("statement") or "").strip()
        if not statement:
            continue
        entry = {
            "source": str(claim.get("source") or "llm_claim"),
            "raw_text": statement,
            "claim_type": str(claim.get("claim_type") or ClaimType.FACT_OBSERVED),
            "confidence": float(claim.get("confidence") or 0.0),
            "source_fact_ids": list(claim.get("source_fact_ids") or []),
        }
        observed_layer.setdefault("observed_inputs", []).append(entry)
        observed_entries.append(entry)

        temp_match = re.search(r"(\d+)\s*(c|grad|°c)", statement, re.I)
        if temp_match:
            raw_parameters["temperature_raw"] = temp_match.group(0)
        pressure_match = re.search(r"(\d+)\s*(bar|psi|mpa)", statement, re.I)
        if pressure_match:
            raw_parameters["pressure_raw"] = pressure_match.group(0)
        if "wasser" in statement.lower():
            raw_parameters["medium_raw_input"] = "Wasser"
        elif "öl" in statement.lower() or "oil" in statement.lower():
            raw_parameters["medium_raw_input"] = "Öl"

    return observed_entries


def _write_identity_record(
    identity_records: Dict[str, Dict[str, Any]],
    field_name: str,
    raw_value: str,
    normalized_value: Any,
    mapping_reason: str,
    source_fact_ids: Optional[List[str]] = None,
    deterministic_source: str = "state_derivation",
    evidence_quality: str = "qualified",
    authority_quality: str = "unknown",
    temporal_quality: str = "unknown",
) -> None:
    identity_records[field_name] = {
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "identity_class": "identity_confirmed",
        "normalization_confidence": 1.0,
        "mapping_reason": mapping_reason,
        "source_fact_ids": list(dict.fromkeys(source_fact_ids or [])),
        "deterministic_source": deterministic_source,
        "evidence_quality": evidence_quality,
        "authority_quality": authority_quality,
        "temporal_quality": temporal_quality,
    }


def _write_unresolved_identity_record(
    identity_records: Dict[str, Dict[str, Any]],
    field_name: str,
    raw_value: str,
    mapping_reason: str,
    source_fact_ids: Optional[List[str]] = None,
    deterministic_source: str = "state_derivation",
    evidence_quality: str = "unqualified",
    authority_quality: str = "unknown",
    temporal_quality: str = "unknown",
) -> None:
    identity_records[field_name] = {
        "raw_value": raw_value,
        "normalized_value": None,
        "identity_class": "identity_unresolved",
        "normalization_confidence": 0.0,
        "mapping_reason": mapping_reason,
        "source_fact_ids": list(dict.fromkeys(source_fact_ids or [])),
        "deterministic_source": deterministic_source,
        "evidence_quality": evidence_quality,
        "authority_quality": authority_quality,
        "temporal_quality": temporal_quality,
    }


def _build_evidence_index(relevant_fact_cards: Optional[List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    evidence_index: Dict[str, Dict[str, Any]] = {}
    for card in relevant_fact_cards or []:
        evidence_id = card.get("evidence_id") or card.get("id")
        if not evidence_id:
            continue
        evidence_index[str(evidence_id)] = {
            "card": card,
            "normalized_evidence": card.get("normalized_evidence") or normalize_fact_card_evidence(card),
        }
    return evidence_index


def _derive_claim_bound_specificity(
    raw_text: str,
    source_fact_ids: List[str],
    evidence_index: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    bound_fact_ids = [str(fact_id) for fact_id in source_fact_ids if str(fact_id) in evidence_index]
    per_field_values: Dict[str, List[str]] = {
        "material_family": [],
        "filler_hint": [],
        "grade_name": [],
        "manufacturer_name": [],
    }
    for fact_id in bound_fact_ids:
        normalized = evidence_index[fact_id]["normalized_evidence"]
        for field_name in per_field_values:
            value = normalized.get(field_name)
            if isinstance(value, str) and value.strip():
                per_field_values[field_name].append(value.strip())

    derived: Dict[str, Dict[str, Any]] = {}
    for field_name, values in per_field_values.items():
        unique_values = list(dict.fromkeys(values))
        quality_states = []
        quality_reasons = []
        authority_states = []
        authority_reasons = []
        temporal_states = []
        temporal_reasons = []
        for fact_id in bound_fact_ids:
            normalized_evidence = evidence_index[fact_id]["normalized_evidence"]
            quality_entry = normalized_evidence.get("identity_quality", {}).get(field_name, {})
            quality_states.append(quality_entry.get("quality"))
            if quality_entry.get("reason"):
                quality_reasons.append(str(quality_entry["reason"]))
            authority_states.append(normalized_evidence.get("authority_quality"))
            if normalized_evidence.get("authority_reason"):
                authority_reasons.append(str(normalized_evidence["authority_reason"]))
            temporal_states.append(normalized_evidence.get("temporal_quality"))
            if normalized_evidence.get("temporal_reason"):
                temporal_reasons.append(str(normalized_evidence["temporal_reason"]))
        if any(state == "conflict" for state in quality_states):
            derived[field_name] = {
                "status": "conflict",
                "source_fact_ids": bound_fact_ids,
                "mapping_reason": f"fact_card_identity_conflict:{field_name}",
                "deterministic_source": "fact_card_binding_conflict",
                "raw_value": " | ".join(unique_values) if unique_values else raw_text,
                "evidence_quality": "conflict",
                "authority_quality": "unknown",
                "temporal_quality": "unknown",
            }
            continue
        if unique_values and any(state != "qualified" for state in quality_states if state not in {None, "missing"}):
            derived[field_name] = {
                "status": "insufficient_quality",
                "source_fact_ids": bound_fact_ids,
                "mapping_reason": quality_reasons[0] if quality_reasons else f"fact_card_insufficient_quality:{field_name}",
                "deterministic_source": "fact_card_binding_unqualified",
                "raw_value": " | ".join(unique_values),
                "evidence_quality": "unqualified",
                "authority_quality": "unknown",
                "temporal_quality": "unknown",
            }
            continue
        if unique_values and any(state != "sufficient" for state in authority_states if state):
            derived[field_name] = {
                "status": "insufficient_authority",
                "source_fact_ids": bound_fact_ids,
                "mapping_reason": authority_reasons[0] if authority_reasons else f"fact_card_insufficient_authority:{field_name}",
                "deterministic_source": "fact_card_binding_insufficient_authority",
                "raw_value": " | ".join(unique_values),
                "evidence_quality": "qualified",
                "authority_quality": "insufficient",
                "temporal_quality": "unknown",
            }
            continue
        if unique_values and any(state != "sufficient" for state in temporal_states if state):
            derived[field_name] = {
                "status": "insufficient_temporal",
                "source_fact_ids": bound_fact_ids,
                "mapping_reason": temporal_reasons[0] if temporal_reasons else f"fact_card_temporal_insufficient:{field_name}",
                "deterministic_source": "fact_card_binding_insufficient_temporal",
                "raw_value": " | ".join(unique_values),
                "evidence_quality": "qualified",
                "authority_quality": "sufficient",
                "temporal_quality": "insufficient",
            }
            continue
        if len(unique_values) == 1:
            derived[field_name] = {
                "status": "confirmed",
                "value": unique_values[0],
                "source_fact_ids": bound_fact_ids,
                "mapping_reason": f"fact_card_binding:{field_name}",
                "deterministic_source": "fact_card_binding",
                "evidence_quality": "qualified",
                "authority_quality": "sufficient",
                "temporal_quality": "sufficient",
            }
        elif len(unique_values) > 1:
            derived[field_name] = {
                "status": "conflict",
                "source_fact_ids": bound_fact_ids,
                "mapping_reason": f"fact_card_identity_conflict:{field_name}",
                "deterministic_source": "fact_card_binding_conflict",
                "raw_value": " | ".join(unique_values),
                "evidence_quality": "conflict",
                "authority_quality": "unknown",
                "temporal_quality": "unknown",
            }

    hinted_fields = {
        "material_family": bool(_MATERIAL_FAMILY_PATTERN.search(raw_text)),
        "filler_hint": bool(_FILLER_HINT_PATTERN.search(raw_text)),
        "grade_name": bool(_SPECIFIC_GRADE_PATTERN.search(raw_text)),
        "manufacturer_name": bool(_MANUFACTURER_NAME_PATTERN.search(raw_text)),
    }
    for field_name, hinted in hinted_fields.items():
        if hinted and field_name not in derived:
            derived[field_name] = {
                "status": "missing_evidence",
                "source_fact_ids": bound_fact_ids,
                "mapping_reason": f"claim_hint_without_fact_card_binding:{field_name}",
                "deterministic_source": "claim_hint_without_fact_card_binding",
                "evidence_quality": "unqualified",
                "authority_quality": "unknown",
                "temporal_quality": "unknown",
            }

    return derived


def _normalize_observed_entries(
    state: SealingAIState,
    observed_entries: List[Dict[str, Any]],
    evidence_index: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[str]:
    normalized = state["normalized"].setdefault("normalized_parameters", {})
    identity_records = state["normalized"].setdefault("identity_records", {})
    blocking_unknowns: List[str] = []
    evidence_index = evidence_index or {}

    for entry in observed_entries:
        raw_text = entry.get("raw_text", "")
        temp_match = re.search(r"(\d+)\s*(c|grad|°c)", raw_text, re.I)
        if temp_match:
            normalized["temperature_c"] = float(temp_match.group(1))
            identity_records["temperature"] = {
                "raw_value": temp_match.group(0),
                "normalized_value": float(temp_match.group(1)),
                "identity_class": "identity_confirmed",
                "normalization_confidence": 1.0,
                "mapping_reason": "regex_temperature_c",
                "source_fact_ids": [],
                "deterministic_source": "raw_claim_regex",
            }
        pressure_match = re.search(r"(\d+)\s*(bar|psi)", raw_text, re.I)
        if pressure_match:
            raw_value = pressure_match.group(0)
            param = PhysicalParameter(value=float(pressure_match.group(1)), unit=pressure_match.group(2))
            normalized["pressure_bar"] = param.to_base_unit()
            identity_records["pressure"] = {
                "raw_value": raw_value,
                "normalized_value": param.to_base_unit(),
                "identity_class": "identity_confirmed",
                "normalization_confidence": 1.0,
                "mapping_reason": "regex_pressure",
                "source_fact_ids": [],
                "deterministic_source": "raw_claim_regex",
            }
        medium_value: Optional[str] = None
        if "wasser" in raw_text.lower():
            medium_value = "Wasser"
        elif "öl" in raw_text.lower() or "oil" in raw_text.lower():
            medium_value = "Öl"
        elif "medium" in raw_text.lower():
            medium_value = None
        if medium_value:
            normalized["medium_normalized"] = medium_value
            identity_records["medium"] = {
                "raw_value": medium_value,
                "normalized_value": medium_value,
                "identity_class": "identity_confirmed",
                "normalization_confidence": 1.0,
                "mapping_reason": "keyword_match",
                "source_fact_ids": [],
                "deterministic_source": "raw_claim_regex",
            }
        elif "medium" in raw_text.lower():
            _write_unresolved_identity_record(
                identity_records,
                "medium",
                raw_text,
                "medium_mentioned_but_unresolved",
                deterministic_source="raw_claim_regex",
            )
            blocking_unknowns.append("medium_identity_unresolved")

        specificity_bindings = _derive_claim_bound_specificity(
            raw_text=raw_text,
            source_fact_ids=list(entry.get("source_fact_ids") or []),
            evidence_index=evidence_index,
        )
        for field_name, binding in specificity_bindings.items():
            if binding["status"] == "confirmed":
                normalized[field_name] = binding["value"]
                _write_identity_record(
                    identity_records,
                    field_name,
                    raw_text,
                    binding["value"],
                    binding["mapping_reason"],
                    source_fact_ids=binding["source_fact_ids"],
                    deterministic_source=binding["deterministic_source"],
                    evidence_quality=binding.get("evidence_quality", "qualified"),
                    authority_quality=binding.get("authority_quality", "unknown"),
                    temporal_quality=binding.get("temporal_quality", "unknown"),
                )
            else:
                _write_unresolved_identity_record(
                    identity_records,
                    field_name,
                    binding.get("raw_value") or raw_text,
                    binding["mapping_reason"],
                    source_fact_ids=binding["source_fact_ids"],
                    deterministic_source=binding["deterministic_source"],
                    evidence_quality=binding.get("evidence_quality", "unqualified"),
                    authority_quality=binding.get("authority_quality", "unknown"),
                    temporal_quality=binding.get("temporal_quality", "unknown"),
                )

    return blocking_unknowns


def _derive_asserted_from_normalized(
    state: SealingAIState,
    blocked_fields: set[str],
) -> None:
    """Blueprint Section 02: asserted values are derived only from normalized values."""

    normalized = state["normalized"].get("normalized_parameters", {})
    asserted = state["asserted"]

    if "medium" not in blocked_fields and normalized.get("medium_normalized"):
        asserted.setdefault("medium_profile", {})["name"] = normalized["medium_normalized"]

    operating_conditions = asserted.setdefault("operating_conditions", {})
    if "temperature" not in blocked_fields and "temperature_c" in normalized:
        operating_conditions["temperature"] = normalized["temperature_c"]
    if "pressure" not in blocked_fields and "pressure_bar" in normalized:
        operating_conditions["pressure"] = normalized["pressure_bar"]


def _has_confirmed_identity(identity_records: Dict[str, Dict[str, Any]], field_name: str) -> bool:
    identity = identity_records.get(field_name) or {}
    return (
        identity.get("identity_class") == "identity_confirmed"
        and identity.get("normalized_value") not in (None, "")
        and identity.get("deterministic_source") == "fact_card_binding"
        and bool(identity.get("source_fact_ids"))
        and identity.get("evidence_quality") == "qualified"
        and identity.get("authority_quality") == "sufficient"
        and identity.get("temporal_quality") == "sufficient"
    )


def _derive_specificity_state(identity_records: Dict[str, Dict[str, Any]]) -> tuple[str, List[str], List[str]]:
    """
    Deterministic specificity ladder:
    family_only -> confirmed family only
    subfamily -> confirmed family plus filler or grade
    compound_required -> confirmed family plus grade plus manufacturer
    """

    family_confirmed = _has_confirmed_identity(identity_records, "material_family")
    filler_confirmed = _has_confirmed_identity(identity_records, "filler_hint")
    grade_confirmed = _has_confirmed_identity(identity_records, "grade_name")
    manufacturer_confirmed = _has_confirmed_identity(identity_records, "manufacturer_name")

    scope_markers: List[str] = []
    manufacturer_unknowns: List[str] = []

    if family_confirmed:
        scope_markers.append("specificity_basis:family_confirmed")
    else:
        manufacturer_unknowns.extend(
            [
                "material_family_identity_unconfirmed",
                "specificity_not_compound_confirmed",
            ]
        )
        scope_markers.append("specificity_basis:family_unconfirmed")
        return "family_only", manufacturer_unknowns, scope_markers

    if grade_confirmed:
        scope_markers.append("specificity_basis:grade_confirmed")
    if filler_confirmed:
        scope_markers.append("specificity_basis:filler_confirmed")
    if manufacturer_confirmed:
        scope_markers.append("specificity_basis:manufacturer_confirmed")

    if grade_confirmed and manufacturer_confirmed:
        return "compound_required", manufacturer_unknowns, scope_markers

    if grade_confirmed or filler_confirmed:
        manufacturer_unknowns.append("specificity_not_compound_confirmed")
        if grade_confirmed and not manufacturer_confirmed:
            manufacturer_unknowns.append("manufacturer_name_unconfirmed_for_compound")
        elif filler_confirmed and not grade_confirmed:
            manufacturer_unknowns.append("compound_grade_unconfirmed")
        return "subfamily", manufacturer_unknowns, scope_markers

    manufacturer_unknowns.append("specificity_not_compound_confirmed")
    manufacturer_unknowns.append("subfamily_identity_unconfirmed")
    return "family_only", manufacturer_unknowns, scope_markers


def _derive_governance_from_state(state: SealingAIState) -> None:
    """Blueprint Sections 06/08: deterministic admissibility only from normalized/asserted/conflicts."""

    governance = state["governance"]
    identity_records = state["normalized"].get("identity_records", {})
    conflicts = [_normalize_conflict_record(conflict) for conflict in governance.get("conflicts", [])]
    gate_failures: List[str] = []
    blocking_unknowns: List[str] = list(governance.get("unknowns_release_blocking", []))
    manufacturer_unknowns: List[str] = list(governance.get("unknowns_manufacturer_validation", []))
    scope_markers: List[str] = [
        "deterministic_agent_firewall",
        "observed_normalized_asserted_reducer",
    ]

    specificity_level, specificity_unknowns, specificity_scope_markers = _derive_specificity_state(identity_records)
    governance["specificity_level"] = _normalize_specificity(specificity_level)
    manufacturer_unknowns.extend(specificity_unknowns)
    scope_markers.extend(specificity_scope_markers)
    specificity_level = governance["specificity_level"]
    for field_name, identity in identity_records.items():
        if identity.get("identity_class") == "identity_unresolved":
            if field_name in {"material_family", "grade_name", "manufacturer_name", "filler_hint"}:
                if identity.get("deterministic_source") == "fact_card_binding_conflict":
                    gate_failures.append(identity.get("mapping_reason") or f"{field_name}_identity_conflict")
                    blocking_unknowns.append(identity.get("mapping_reason") or f"{field_name}_identity_conflict")
                else:
                    manufacturer_unknowns.append(identity.get("mapping_reason") or f"{field_name}_identity_unresolved")
            else:
                blocking_unknowns.append(f"{field_name}_identity_unresolved")

    for conflict in conflicts:
        severity = str(conflict.get("severity") or "").upper()
        conflict_type = str(conflict.get("type") or "").lower()
        if severity in _MANUFACTURER_CONFLICT_SEVERITIES or conflict_type in _MANUFACTURER_CONFLICT_TYPES:
            manufacturer_unknowns.append(conflict.get("message") or conflict_type or "manufacturer_scope_required")
        elif severity in _BLOCKING_CONFLICT_SEVERITIES or conflict_type in _BLOCKING_CONFLICT_TYPES:
            gate_failures.append(conflict.get("message") or conflict.get("type") or "critical_conflict")
            blocking_unknowns.append(conflict_type or "critical_conflict")

    # Deduplicate while preserving order.
    governance["conflicts"] = conflicts
    governance["gate_failures"] = list(dict.fromkeys(str(item) for item in gate_failures if item))
    governance["unknowns_release_blocking"] = list(
        dict.fromkeys(str(item) for item in blocking_unknowns if item)
    )
    governance["unknowns_manufacturer_validation"] = list(
        dict.fromkeys(str(item) for item in manufacturer_unknowns if item)
    )
    if governance["unknowns_release_blocking"]:
        scope_markers.append("release_blocked_pending_unknowns")
    if governance["unknowns_manufacturer_validation"]:
        scope_markers.append("manufacturer_validation_scope")
    scope_markers.append(f"specificity_level:{specificity_level}")
    governance["scope_of_validity"] = list(dict.fromkeys(scope_markers))
    governance["assumptions_active"] = list(dict.fromkeys(governance.get("assumptions_active", [])))

    asserted = state["asserted"]
    has_asserted_signal = bool(asserted.get("medium_profile")) or bool(asserted.get("operating_conditions"))

    if governance["unknowns_release_blocking"] or governance["gate_failures"]:
        governance["release_status"] = "inadmissible"
        governance["rfq_admissibility"] = "inadmissible"
    elif not has_asserted_signal:
        governance["release_status"] = "precheck_only"
        governance["rfq_admissibility"] = "inadmissible"
    elif governance["unknowns_manufacturer_validation"]:
        governance["release_status"] = "manufacturer_validation_required"
        governance["rfq_admissibility"] = "provisional"
    else:
        governance["release_status"] = "rfq_ready"
        governance["rfq_admissibility"] = "ready"

    governance["release_status"] = _normalize_release_status(governance["release_status"])
    governance["rfq_admissibility"] = _normalize_rfq_admissibility(governance["rfq_admissibility"])


def _advance_cycle_state(state: SealingAIState, expected_revision: int) -> None:
    cycle = state["cycle"]
    cycle["state_revision"] = expected_revision + 1
    cycle["snapshot_parent_revision"] = expected_revision
    cycle["superseded_by_cycle"] = None
    cycle["contract_obsolete"] = False
    cycle["contract_obsolete_reason"] = None


def apply_engineering_firewall_transition(
    old_state: SealingAIState,
    intelligence_conflicts: List[Dict[str, Any]],
    expected_revision: int,
    validated_params: Optional[Dict[str, float]] = None,
    raw_claims: Optional[List[Dict[str, Any]]] = None,
    relevant_fact_cards: Optional[List[Dict[str, Any]]] = None,
) -> SealingAIState:
    """
    Blueprint Sections 02/03/08/12:
    central reducer path Observed -> Normalized -> Asserted -> Governance -> Cycle.
    """

    new_state = _ensure_state_shape(deepcopy(old_state))
    if new_state["cycle"]["state_revision"] != expected_revision:
        raise ValueError(
            f"Revision mismatch: expected {expected_revision}, got {new_state['cycle']['state_revision']}"
        )

    raw_claims = raw_claims or []
    evidence_index = _build_evidence_index(relevant_fact_cards)
    observed_entries = _record_observed_claims(new_state, raw_claims)
    blocking_unknowns = _normalize_observed_entries(new_state, observed_entries, evidence_index=evidence_index)

    # Deterministic values may enter normalized only, never asserted directly.
    normalized_parameters = new_state["normalized"].setdefault("normalized_parameters", {})
    if validated_params:
        if "temperature" in validated_params:
            normalized_parameters["temperature_c"] = float(validated_params["temperature"])
        if "pressure" in validated_params:
            normalized_parameters["pressure_bar"] = float(validated_params["pressure"])

    governance = new_state["governance"]
    existing_conflicts = list(governance.get("conflicts", []))
    governance["conflicts"] = existing_conflicts + intelligence_conflicts
    governance["unknowns_release_blocking"] = list(
        dict.fromkeys(list(governance.get("unknowns_release_blocking", [])) + blocking_unknowns)
    )

    blocked_fields = {
        str(conflict.get("field"))
        for conflict in intelligence_conflicts
        if conflict.get("field")
    }
    _derive_asserted_from_normalized(new_state, blocked_fields=blocked_fields)
    _derive_governance_from_state(new_state)
    _advance_cycle_state(new_state, expected_revision=expected_revision)
    return new_state

def search_alternative_materials(p_req: float, t_req: float, all_fact_cards: List[Dict[str, Any]]) -> List[str]:
    """Sucht nach alternativen Materialien, die den Anforderungen p/t entsprechen."""
    alternatives = []
    for card in all_fact_cards:
        profile = MaterialPhysicalProfile.from_fact_card(card)
        if profile and profile.temp_max >= t_req and profile.pressure_max >= p_req:
            if profile.material_id.upper() not in alternatives:
                alternatives.append(profile.material_id.upper())
    return alternatives

def extract_parameters(text: str, current_profile: Dict[str, Any], all_fact_cards: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Phase H3/H8: Heuristische Extraktion technischer Parameter mittels Regex.
    Dient dem working_profile (Live-UI) und bereitet Claims vor.
    """
    new_profile = deepcopy(current_profile)
    all_fact_cards = all_fact_cards or []
    
    # 1. Drehzahl (RPM)
    speed_match = re.search(r"(\d+)\s*(rpm|u/min)", text, re.I)
    if speed_match:
        new_profile["speed"] = float(speed_match.group(1))

    # 2. Durchmesser (mm)
    diam_match = re.search(r"(\d+)\s*(mm|millimeter)", text, re.I)
    if diam_match:
        new_profile["diameter"] = float(diam_match.group(1))

    # 3. Druck (bar)
    pres_match = re.search(r"(\d+)\s*(bar|mpa)", text, re.I)
    if pres_match:
        val = float(pres_match.group(1))
        # Einfache bar/mpa Konvertierung falls nötig
        new_profile["pressure"] = val

    # 4. Temperatur (C)
    temp_match = re.search(r"(\d+)\s*(c|grad|°c)", text, re.I)
    if temp_match:
        new_profile["temperature"] = float(temp_match.group(1))

    # 5. Medium
    if "medium" in text.lower() or "wasser" in text.lower() or "öl" in text.lower():
        if "wasser" in text.lower(): new_profile["medium"] = "Wasser"
        elif "öl" in text.lower(): new_profile["medium"] = "Öl"

    # 6. Material
    if "ptfe" in text.upper():
        new_profile["material"] = "PTFE"
    elif "nbr" in text.upper():
        new_profile["material"] = "NBR"

    # Risiko-Checks und Alternativen (Phase H8 UI-Logic)
    risk_msg = validate_material_risk(new_profile)
    if risk_msg:
        new_profile["risk_warning"] = risk_msg
        # Suche nach Alternativen
        if all_fact_cards:
            p_req = new_profile.get("pressure", 0)
            t_req = new_profile.get("temperature", 0)
            new_profile["alternatives"] = search_alternative_materials(p_req, t_req, all_fact_cards)
    else:
        new_profile.pop("risk_warning", None)
        new_profile.pop("alternatives", None)

    # Physik-Berechnungen (v_m_s, pv_value)
    new_profile = calculate_physics(new_profile)

    return new_profile

def evaluate_claim_conflicts(
    claims: List[Claim], 
    asserted_state: Dict[str, Any],
    relevant_fact_cards: List[Dict[str, Any]] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """
    Phase B2/H3/H6/H7: Prüft neue Claims gegen den aktuellen asserted state.
    Nutzt die FactCard Factory für dynamische Material-Validierung.
    """
    conflicts = []
    validated_params = {}
    relevant_fact_cards = relevant_fact_cards or []
    
    # 1. Aktuellen Kontext extrahieren
    current_medium = asserted_state.get("medium_profile", {}).get("name")
    
    # 2. Dynamische Material-Validatoren aus RAG-Kontext (via Factory H7)
    material_validators = {}
    for card in relevant_fact_cards:
        profile = MaterialPhysicalProfile.from_fact_card(card)
        if profile:
            material_validators[profile.material_id.lower()] = MaterialValidator(profile)

    for claim in claims:
        # Medium-Konflikt (legacy)
        if "medium" in claim.statement.lower() or "öl" in claim.statement.lower() or "wasser" in claim.statement.lower():
            new_medium = "öl" if "öl" in claim.statement.lower() else "wasser" if "wasser" in claim.statement.lower() else None
            if current_medium and new_medium and current_medium.lower() != new_medium.lower():
                conflicts.append({
                    "type": "PARAMETER_CONFLICT",
                    "severity": "CRITICAL",
                    "field": "medium",
                    "message": f"Konflikt: Assertiert ist '{current_medium}', Claim behauptet '{new_medium}'.",
                    "claim_statement": claim.statement
                })

        # Physikalische Parameter-Validierung (H3/H6/H7)
        if claim.claim_type == ClaimType.FACT_OBSERVED:
            # Temperatur-Parsing
            temp_match = re.search(r"(\d+)\s*(C|F|°C|°F)", claim.statement)
            if temp_match:
                val = float(temp_match.group(1))
                unit = temp_match.group(2).replace("°", "")
                
                try:
                    temp_param = PhysicalParameter(value=val, unit=unit)
                    has_conflict = False
                    
                    # Dynamische Prüfung gegen alle gefundenen Material-Validatoren
                    for mat_id, validator in material_validators.items():
                        # Prüfe ob das Material für diesen Kontext relevant ist
                        if (current_medium and mat_id in current_medium.lower()) or (mat_id in claim.statement.lower()):
                            if not validator.validate_temperature(temp_param):
                                conflicts.append({
                                    "type": "DOMAIN_LIMIT_VIOLATION",
                                    "severity": "CRITICAL",
                                    "field": "temperature",
                                    "message": f"{mat_id.upper()} Limit überschritten: {temp_param.to_base_unit()}°C > {validator.profile.temp_max}°C (Quelle: FactCard Factory).",
                                    "claim_statement": claim.statement
                                })
                                has_conflict = True
                    
                    if not has_conflict:
                        validated_params["temperature"] = temp_param.to_base_unit()
                        
                except Exception:
                    pass

            # Druck-Parsing
            pressure_match = re.search(r"(\d+)\s*(bar|psi)", claim.statement.lower())
            if pressure_match:
                val = float(pressure_match.group(1))
                unit = pressure_match.group(2)
                
                try:
                    pressure_param = PhysicalParameter(value=val, unit=unit)
                    validated_params["pressure"] = pressure_param.to_base_unit()
                except Exception:
                    pass
                
    return conflicts, validated_params

def process_cycle_update(
    old_state: SealingAIState, 
    intelligence_conflicts: List[Dict[str, Any]], 
    expected_revision: int,
    validated_params: Dict[str, float] = None,
    raw_claims: Optional[List[Dict[str, Any]]] = None,
    relevant_fact_cards: Optional[List[Dict[str, Any]]] = None,
) -> SealingAIState:
    """
    Backward-compatible wrapper around the central firewall reducer.
    """
    return apply_engineering_firewall_transition(
        old_state=old_state,
        intelligence_conflicts=intelligence_conflicts,
        expected_revision=expected_revision,
        validated_params=validated_params,
        raw_claims=raw_claims,
        relevant_fact_cards=relevant_fact_cards,
    )
