import re
from typing import Any, Dict, List, Optional
from app.agent.domain.material import MaterialPhysicalProfile, MaterialValidator, normalize_fact_card_evidence
from app.agent.domain.parameters import PhysicalParameter
from app.agent.agent.boundaries import build_boundary_block


_MATERIAL_PATTERN = re.compile(r"\b(PTFE|NBR|FKM|EPDM|SILIKON)\b", re.I)
_GRADE_PATTERN = re.compile(r"\b(?:grade|compound|typ|type)\s*[:\-]?\s*([a-z0-9._-]+)\b", re.I)
_FILLER_PATTERN = re.compile(r"\b(filled|glass[- ]filled|carbon[- ]filled|bronze[- ]filled)\b", re.I)
SAFEGUARDED_WITHHELD_REPLY = "No governed recommendation can be released."
NO_CANDIDATES_REPLY = "No governed recommendation can be released from the current evidence."
NO_VIABLE_CANDIDATES_REPLY = "No governed recommendation can be released because no viable candidate remains after deterministic checks."
MISSING_INPUTS_REPLY = "No governed recommendation can be released because required engineering inputs are missing."
NEUTRAL_SCOPE_REPLY = (
    "Technischer Eignungsraum vorbereitet. Freigabe bleibt an Governance, "
    "Scope-of-validity und dokumentierte Open Points gebunden."
)
MANUFACTURER_VALIDATION_REPLY = (
    "Technischer Eignungsraum vorbereitet. Hersteller-Validierung ist erforderlich; "
    "keine Material- oder Compound-Freigabe wird ausgegeben."
)
PRECHECK_ONLY_REPLY = (
    "Technischer Vorpruefstand erreicht. Weitere deterministische Klaerung ist erforderlich."
)


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


def _governance_projection_blocks_output(governance_state: Dict[str, Any]) -> bool:
    """Projection-only gate: mirrors governance and never creates its own release truth."""

    if governance_state.get("release_status") != "rfq_ready":
        return True
    if governance_state.get("rfq_admissibility") != "ready":
        return True
    if governance_state.get("specificity_level") != "compound_required":
        return True
    if governance_state.get("unknowns_release_blocking"):
        return True
    if governance_state.get("gate_failures"):
        return True
    return any(str(conflict.get("severity") or "").upper() in {"CRITICAL", "BLOCKING_UNKNOWN"} for conflict in governance_state.get("conflicts", []))


def _build_recommendation_artifact(
    selection_status: str,
    winner_candidate_id: Optional[str],
    candidates: List[Dict[str, Any]],
    viable_candidate_ids: List[str],
    blocked_candidates: List[Dict[str, str]],
    evidence_basis: List[str],
    release_status: str,
    rfq_admissibility: str,
    specificity_level: str,
    output_blocked: bool,
    trace_refs: List[str],
) -> Dict[str, Any]:
    return {
        "selection_status": selection_status,
        "winner_candidate_id": winner_candidate_id,
        "candidate_ids": [candidate["candidate_id"] for candidate in candidates],
        "viable_candidate_ids": viable_candidate_ids,
        "blocked_candidates": blocked_candidates,
        "evidence_basis": evidence_basis,
        "release_status": release_status,
        "rfq_admissibility": rfq_admissibility,
        "specificity_level": specificity_level,
        "output_blocked": output_blocked,
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
    )


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
    elif viable_candidate_ids:
        selection_status = "winner_selected"
    elif any(block["block_reason"] == "blocked_missing_required_inputs" for block in blocked_candidates):
        selection_status = "blocked_missing_required_inputs"
    else:
        selection_status = "blocked_no_viable_candidates"
    governance_release_status = governance_state.get("release_status", "inadmissible")
    governance_rfq_admissibility = governance_state.get("rfq_admissibility", "inadmissible")
    specificity_level = governance_state.get("specificity_level", "family_only")
    output_blocked = (
        not viable_candidate_ids
        or _governance_projection_blocks_output(governance_state)
    )
    trace_refs = list(evidence_basis)
    cycle_id = cycle_state.get("analysis_cycle_id")
    if cycle_id:
        trace_refs.append(cycle_id)

    recommendation_artifact = _build_recommendation_artifact(
        selection_status=selection_status,
        winner_candidate_id=winner_candidate_id,
        candidates=ordered_candidates,
        viable_candidate_ids=viable_candidate_ids,
        blocked_candidates=blocked_candidates,
        evidence_basis=evidence_basis,
        release_status=governance_release_status,
        rfq_admissibility=governance_rfq_admissibility,
        specificity_level=specificity_level,
        output_blocked=output_blocked,
        trace_refs=trace_refs,
    )

    return {
        "selection_status": selection_status,
        "candidates": ordered_candidates,
        "viable_candidate_ids": viable_candidate_ids,
        "blocked_candidates": blocked_candidates,
        "winner_candidate_id": winner_candidate_id,
        "recommendation_artifact": recommendation_artifact,
        "release_status": governance_release_status,
        "rfq_admissibility": governance_rfq_admissibility,
        "specificity_level": specificity_level,
        "output_blocked": output_blocked,
    }


def build_final_reply(
    selection_state: Dict[str, Any],
    *,
    coverage_status: Optional[str] = None,
    known_unknowns: Optional[List[str]] = None,
    demo_data_present: bool = False,
    review_required: bool = False,
    review_reason: str = "",
) -> str:
    """Build the governed structured-path reply and append a deterministic boundary block.

    Phase 0B.2: the boundary block is ALWAYS appended — it is never produced by the LLM.
    Phase A3: if review_required, the boundary block includes the HITL pending notice.
    """
    artifact = selection_state.get("recommendation_artifact") or {}
    if not _artifact_is_aligned(selection_state, artifact):
        core_reply = SAFEGUARDED_WITHHELD_REPLY
    else:
        release_status = selection_state.get("release_status")
        rfq_admissibility = selection_state.get("rfq_admissibility")
        output_blocked = bool(selection_state.get("output_blocked", True))
        specificity_level = selection_state.get("specificity_level", "family_only")

        if release_status == "precheck_only":
            core_reply = PRECHECK_ONLY_REPLY
        elif release_status == "manufacturer_validation_required" or rfq_admissibility == "provisional":
            core_reply = MANUFACTURER_VALIDATION_REPLY
        elif (
            not output_blocked
            and release_status == "rfq_ready"
            and rfq_admissibility == "ready"
            and specificity_level == "compound_required"
        ):
            core_reply = NEUTRAL_SCOPE_REPLY
        elif selection_state.get("selection_status") == "blocked_no_candidates":
            core_reply = NO_CANDIDATES_REPLY
        elif selection_state.get("selection_status") == "blocked_missing_required_inputs":
            core_reply = MISSING_INPUTS_REPLY
        elif selection_state.get("selection_status") == "blocked_no_viable_candidates":
            core_reply = NO_VIABLE_CANDIDATES_REPLY
        else:
            core_reply = SAFEGUARDED_WITHHELD_REPLY

    boundary = build_boundary_block(
        "structured",
        coverage_status=coverage_status,
        known_unknowns=known_unknowns,
        demo_data_present=demo_data_present,
        review_required=review_required,
        review_reason=review_reason,
    )
    return f"{core_reply}\n\n{boundary}"
