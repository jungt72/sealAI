import re
from typing import Any, Dict, List, Optional

from app.agent.domain.material import normalize_fact_card_evidence
from app.agent.material_core import build_material_candidate_source_adapter, evaluate_material_qualification_core


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


def _resolve_binding_scope(
    selection_state: Dict[str, Any],
    qualification_context: Dict[str, Any],
) -> str:
    release_status = selection_state.get("release_status")
    rfq_admissibility = selection_state.get("rfq_admissibility")
    specificity_level = selection_state.get("specificity_level", "family_only")
    output_blocked = bool(selection_state.get("output_blocked", True))
    if (
        not output_blocked
        and release_status == "rfq_ready"
        and rfq_admissibility == "ready"
        and specificity_level == "compound_required"
    ):
        return "RFQ-Basis"
    if release_status == "manufacturer_validation_required" or rfq_admissibility == "provisional":
        return "Belastbare Vorqualifikation"
    if qualification_context.get("hard_stop") or selection_state.get("selection_status", "").startswith("blocked_"):
        return "Orientierung"
    if release_status == "precheck_only":
        return "Orientierung"
    return "Technische Orientierung"


def _resolve_direction_statement(
    selection_state: Dict[str, Any],
    qualification_context: Dict[str, Any],
) -> str:
    hard_stop = qualification_context.get("hard_stop")
    rwdr_type_class = qualification_context.get("rwdr_type_class")
    winner_candidate_id = selection_state.get("winner_candidate_id")
    viable_candidate_ids = list(selection_state.get("viable_candidate_ids", []))
    selection_status = str(selection_state.get("selection_status") or "not_started")

    if hard_stop:
        return f"Aktuelle technische Richtung: blockiert durch {hard_stop}."
    if winner_candidate_id:
        return f"Aktuelle technische Richtung: Materialpfad {winner_candidate_id} bleibt der fuehrende Kandidat."
    if rwdr_type_class:
        return f"Aktuelle technische Richtung: RWDR-Typklasse {rwdr_type_class} ist vorselektiert."
    if viable_candidate_ids:
        return (
            "Aktuelle technische Richtung: materialseitiger Shortlist-Raum ist bestimmt, "
            "aber noch nicht auf einen einzelnen Kandidaten verengt."
        )
    if selection_status == "blocked_missing_required_inputs":
        return "Aktuelle technische Richtung: noch keine belastbare Freigaberichtung, weil Kernangaben fehlen."
    if selection_status == "blocked_no_viable_candidates":
        return "Aktuelle technische Richtung: kein tragfaehiger Kandidat bleibt nach den deterministischen Pruefungen uebrig."
    if selection_status == "blocked_no_candidates":
        return "Aktuelle technische Richtung: es liegt noch keine belastbare Kandidatenbasis vor."
    return "Aktuelle technische Richtung: nur ein vorlaeufiger technischer Eignungsraum ist sichtbar."


def _build_contextual_reply(
    selection_state: Dict[str, Any],
    qualification_context: Dict[str, Any],
) -> str:
    direction = _resolve_direction_statement(selection_state, qualification_context)
    binding_scope = _resolve_binding_scope(selection_state, qualification_context)
    release_status = str(selection_state.get("release_status") or "inadmissible")
    rfq_admissibility = str(selection_state.get("rfq_admissibility") or "inadmissible")
    review_flags = [str(item) for item in qualification_context.get("review_flags", []) if item][:3]
    blockers = [str(item) for item in qualification_context.get("blockers", []) if item][:3]
    scope_markers = [str(item) for item in qualification_context.get("scope_of_validity", []) if item][:2]
    assumptions = [str(item) for item in qualification_context.get("assumptions_active", []) if item][:2]
    obsolescence_state = str(qualification_context.get("obsolescence_state") or "").strip()
    recompute_requirement = str(qualification_context.get("recompute_requirement") or "").strip()

    detail_parts = [f"Bindungsgrad: {binding_scope}", f"RFQ: {rfq_admissibility}", f"Release: {release_status}"]
    if scope_markers:
        detail_parts.append(f"Geltungsgrenze: {', '.join(scope_markers)}")
    if assumptions:
        detail_parts.append(f"Annahmen: {', '.join(assumptions)}")
    if blockers:
        detail_parts.append(f"Blocker: {', '.join(blockers)}")
    if review_flags:
        detail_parts.append(f"Review-pflichtig: {', '.join(review_flags)}")
    if obsolescence_state:
        detail_parts.append(f"Obsoleszenz: {obsolescence_state}")
    if recompute_requirement:
        detail_parts.append(f"Recompute: {recompute_requirement}")
    return f"{direction} {'. '.join(detail_parts)}."


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


def build_selection_state(
    relevant_fact_cards: List[Dict[str, Any]],
    cycle_state: Dict[str, Any],
    governance_state: Optional[Dict[str, Any]] = None,
    asserted_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    governance_state = governance_state or {}
    asserted_state = asserted_state or {}
    adapter_output = build_material_candidate_source_adapter(
        relevant_fact_cards=relevant_fact_cards,
    )
    ordered_candidates = [record.model_dump() for record in adapter_output.candidate_source_records]
    evidence_basis = list(adapter_output.evidence_basis)

    core_output = evaluate_material_qualification_core(
        candidate_source_records=adapter_output.candidate_source_records,
        relevant_fact_cards=relevant_fact_cards,
        asserted_state=asserted_state,
        governance_state=governance_state,
    )
    assessments_by_id = {
        assessment.candidate_id: assessment.model_dump()
        for assessment in core_output.candidate_assessments
    }
    for candidate in ordered_candidates:
        assessment = assessments_by_id.get(candidate["candidate_id"])
        if not assessment:
            continue
        candidate["viability_status"] = assessment["viability_status"]
        candidate["block_reason"] = assessment.get("block_reason")
        candidate["candidate_source_class"] = assessment.get("candidate_source_class")
        candidate["candidate_source_quality"] = assessment.get("candidate_source_quality")
        candidate["qualified_eligible"] = bool(assessment.get("qualified_eligible"))
        candidate["source_gate_reasons"] = list(assessment.get("source_gate_reasons", []))

    viable_candidate_ids = list(core_output.viable_candidate_ids)
    qualified_candidate_ids = list(core_output.qualified_viable_candidate_ids)
    blocked_candidates = list(core_output.blocked_candidates)
    winner_candidate_id = viable_candidate_ids[0] if len(viable_candidate_ids) == 1 else None
    if not ordered_candidates:
        selection_status = "blocked_no_candidates"
    elif viable_candidate_ids:
        selection_status = "winner_selected"
    elif any(block["block_reason"] == "blocked_missing_required_inputs" for block in blocked_candidates):
        selection_status = "blocked_missing_required_inputs"
    else:
        selection_status = "blocked_no_viable_candidates"
    if winner_candidate_id and winner_candidate_id in qualified_candidate_ids:
        direction_authority = "governed_authority"
    elif viable_candidate_ids:
        direction_authority = "evidence_oriented"
    else:
        direction_authority = "none"
    governance_release_status = governance_state.get("release_status", "inadmissible")
    governance_rfq_admissibility = governance_state.get("rfq_admissibility", "inadmissible")
    specificity_level = governance_state.get("specificity_level", "family_only")
    output_blocked = bool(core_output.output_blocked or _governance_projection_blocks_output(governance_state))
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
        "direction_authority": direction_authority,
        "recommendation_artifact": recommendation_artifact,
        "release_status": governance_release_status,
        "rfq_admissibility": governance_rfq_admissibility,
        "specificity_level": specificity_level,
        "output_blocked": output_blocked,
        "material_core_status": core_output.qualification_status,
        "material_core_open_points": list(core_output.open_points),
        "material_core_missing_required_inputs": list(core_output.missing_required_inputs),
        "qualified_candidate_ids": qualified_candidate_ids,
        "exploratory_candidate_ids": list(core_output.exploratory_candidate_ids),
        "promoted_candidate_ids": list(core_output.promoted_candidate_ids),
        "transition_candidate_ids": list(core_output.transition_candidate_ids),
        "blocked_by_candidate_source": list(core_output.blocked_by_candidate_source),
        "candidate_source_adapter": adapter_output.source_adapter,
        "candidate_source_origin": adapter_output.source_origin,
        "candidate_source_origins": list(adapter_output.source_origins),
        "candidate_source_records": [record.model_dump() for record in adapter_output.candidate_source_records],
    }


def build_final_reply(
    selection_state: Dict[str, Any],
    qualification_context: Optional[Dict[str, Any]] = None,
) -> str:
    artifact = selection_state.get("recommendation_artifact") or {}
    if not _artifact_is_aligned(selection_state, artifact):
        return SAFEGUARDED_WITHHELD_REPLY

    if qualification_context:
        return _build_contextual_reply(selection_state, qualification_context)

    release_status = selection_state.get("release_status")
    rfq_admissibility = selection_state.get("rfq_admissibility")
    output_blocked = bool(selection_state.get("output_blocked", True))
    specificity_level = selection_state.get("specificity_level", "family_only")

    if release_status == "precheck_only":
        return PRECHECK_ONLY_REPLY
    if release_status == "manufacturer_validation_required" or rfq_admissibility == "provisional":
        return MANUFACTURER_VALIDATION_REPLY
    if (
        not output_blocked
        and release_status == "rfq_ready"
        and rfq_admissibility == "ready"
        and specificity_level == "compound_required"
    ):
        return NEUTRAL_SCOPE_REPLY

    if selection_state.get("selection_status") == "blocked_no_candidates":
        return NO_CANDIDATES_REPLY
    if selection_state.get("selection_status") == "blocked_missing_required_inputs":
        return MISSING_INPUTS_REPLY
    if selection_state.get("selection_status") == "blocked_no_viable_candidates":
        return NO_VIABLE_CANDIDATES_REPLY

    return SAFEGUARDED_WITHHELD_REPLY


def build_visible_reply_fallback(
    selection_state: Dict[str, Any],
    guidance_contract: Dict[str, Any],
) -> str:
    governed_summary = build_final_reply(selection_state)
    ask_mode = str(guidance_contract.get("ask_mode") or "no_question_needed")
    requested_fields = [str(item) for item in guidance_contract.get("requested_fields", []) if item][:3]

    if ask_mode == "recompute_first":
        return (
            f"{governed_summary} Vor dem nächsten Eingabeschritt muss ich zuerst die veralteten "
            "Qualifikationsabschnitte mit dem aktuellen Fallstand neu berechnen."
        )
    if ask_mode == "critical_inputs" and requested_fields:
        fields = ", ".join(requested_fields)
        return (
            f"{governed_summary} Damit ich den Fall belastbar weiterführen kann, brauche ich als Nächstes nur noch: {fields}."
        )
    if ask_mode == "review_inputs" and requested_fields:
        fields = ", ".join(requested_fields)
        return (
            f"{governed_summary} Der Kernfall steht; zur technischen Absicherung fehlen noch diese Review-Angaben: {fields}."
        )
    if ask_mode == "qualification_ready":
        return f"{governed_summary} Der aktuelle Fall ist aus deterministischer Sicht bereit für den nächsten Qualification-Schritt."
    return governed_summary
