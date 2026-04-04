"""
matching_node — Phase G Block 1

Deterministic manufacturer matching for the governed path.

Responsibility:
    Build a bounded matching result from the governed state after governance
    has derived the requirement class and scope status.

Architecture invariants:
    - No LLM call. No I/O outside the governed data provider.
    - No legacy case_state dump in or out.
    - Matching only runs once technical narrowing has reached at least Class B
      and a requirement class has bounded the admissible solution space.
    - Output is persisted in MatchingState only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.agent.case_state import _build_manufacturer_capabilities, _build_manufacturer_refs
from app.agent.domain.governed_data import get_default_domain_data_provider
from app.agent.domain.manufacturer_rfq import (
    ManufacturerCapabilityPackage,
    ManufacturerRfqAdmissibleRequestPackage,
    ManufacturerRfqScopePackage,
    ManufacturerRfqSpecialistInput,
    run_manufacturer_rfq_specialist,
)
from app.agent.graph import GraphState
from app.agent.state.models import MatchingState

log = logging.getLogger(__name__)


_ALLOWED_GOV_CLASSES = {"A", "B"}
_MEDIUM_ALIASES: dict[str, str] = {
    "dampf": "steam",
    "steam": "steam",
    "wasser": "water",
    "water": "water",
}
_REQUIREMENT_CLASS_MATERIAL_HINTS: dict[str, str] = {
    "PTFE": "PTFE",
    "FKM": "FKM",
}


@dataclass(frozen=True)
class _CapabilityFit:
    is_fit: bool
    score: int
    positive_reasons: tuple[str, ...]
    blocking_reasons: tuple[str, ...]


def _asserted_str(state: GraphState, field_name: str) -> str | None:
    claim = state.asserted.assertions.get(field_name)
    if claim is None or claim.asserted_value is None:
        return None
    value = str(claim.asserted_value).strip()
    return value or None


def _asserted_float(state: GraphState, field_name: str) -> float | None:
    claim = state.asserted.assertions.get(field_name)
    if claim is None or claim.asserted_value is None:
        return None
    try:
        return float(claim.asserted_value)
    except (TypeError, ValueError):
        return None


def _material_family_for_matching(state: GraphState) -> str | None:
    material = _asserted_str(state, "material")
    if material:
        return material.upper()
    requirement_class = state.governance.requirement_class
    if requirement_class is not None:
        class_id = str(requirement_class.class_id or "").upper()
        for prefix, material_family in _REQUIREMENT_CLASS_MATERIAL_HINTS.items():
            if class_id.startswith(prefix):
                return material_family
    return None


def _candidate_kind(record: Any) -> str:
    if record.manufacturer_name and record.grade_name:
        return "manufacturer_grade"
    if record.grade_name:
        return "grade"
    return "family"


def _fit_record(state: GraphState, record: Any) -> _CapabilityFit:
    target_family = _material_family_for_matching(state)
    temp = _asserted_float(state, "temperature_c")
    pressure = _asserted_float(state, "pressure_bar")
    medium = _asserted_str(state, "medium")
    requirement_class = state.governance.requirement_class
    coverage = dict(record.coverage_metadata or {})
    positive_reasons: list[str] = []
    blocking_reasons: list[str] = []
    score = 0

    record_family = str(record.material_family or "").upper()
    if target_family and record_family != target_family:
        blocking_reasons.append(
            f"material family '{record_family or 'unknown'}' does not satisfy required family '{target_family}'."
        )
    elif record_family:
        score += 25
        positive_reasons.append(f"material family '{record_family}' matches.")

    requirement_class_ids = {
        str(item).strip()
        for item in list(coverage.get("requirement_class_ids") or [])
        if item
    }
    requirement_class_id = str(requirement_class.class_id or "").strip() if requirement_class else ""
    if requirement_class_id and requirement_class_ids:
        if requirement_class_id in requirement_class_ids:
            score += 30
            positive_reasons.append(f"requirement class '{requirement_class_id}' is supported.")
        else:
            blocking_reasons.append(
                f"requirement class '{requirement_class_id}' is not covered by this record."
            )
    elif requirement_class_id:
        score += 10
        positive_reasons.append(
            f"requirement class '{requirement_class_id}' has no explicit record-level restriction."
        )

    max_temp_c = coverage.get("max_temp_c")
    if temp is not None and max_temp_c is not None:
        try:
            if temp > float(max_temp_c):
                blocking_reasons.append(
                    f"temperature {temp:g}C exceeds limit {float(max_temp_c):g}C."
                )
            else:
                score += 15
                positive_reasons.append(
                    f"temperature {temp:g}C is within limit {float(max_temp_c):g}C."
                )
        except (TypeError, ValueError):
            pass

    allowed_media = {
        str(item).strip().lower()
        for item in list(coverage.get("allowed_media") or [])
        if item
    }
    if medium and allowed_media:
        medium_key = _MEDIUM_ALIASES.get(medium.strip().lower(), medium.strip().lower())
        if medium_key not in allowed_media:
            blocking_reasons.append(f"medium '{medium_key}' is not in the supported media set.")
        else:
            score += 20
            positive_reasons.append(f"medium '{medium_key}' is supported.")

    max_pressure_bar = coverage.get("max_pressure_bar")
    if pressure is not None and max_pressure_bar is not None:
        try:
            if pressure > float(max_pressure_bar):
                blocking_reasons.append(
                    f"pressure {pressure:g}bar exceeds limit {float(max_pressure_bar):g}bar."
                )
            else:
                score += 10
                positive_reasons.append(
                    f"pressure {pressure:g}bar is within limit {float(max_pressure_bar):g}bar."
                )
        except (TypeError, ValueError):
            pass

    supported_seal_types = {
        str(item).strip().lower()
        for item in list(coverage.get("supported_seal_types") or [])
        if item
    }
    seal_type = str(requirement_class.seal_type or "").strip().lower() if requirement_class else ""
    if seal_type and supported_seal_types:
        if seal_type in supported_seal_types:
            score += 5
            positive_reasons.append(f"seal type '{seal_type}' is supported.")
        else:
            blocking_reasons.append(f"seal type '{seal_type}' is not supported by this record.")

    return _CapabilityFit(
        is_fit=not blocking_reasons,
        score=score,
        positive_reasons=tuple(positive_reasons),
        blocking_reasons=tuple(blocking_reasons),
    )


def _build_match_candidates(state: GraphState) -> tuple[list[dict[str, Any]], list[str]]:
    provider = get_default_domain_data_provider()
    records = provider.list_material_records()
    notes: list[str] = []
    candidates: list[dict[str, Any]] = []

    if not records:
        return [], ["No governed manufacturer records are available."]

    if any(bool(getattr(record, "is_demo_only", False)) for record in records):
        notes.append("Matching uses the current demo manufacturer catalog.")

    for record in records:
        fit = _fit_record(state, record)
        if not fit.is_fit:
            notes.append(
                f"Rejected {record.record_id}: {'; '.join(fit.blocking_reasons)}"
            )
            continue
        candidates.append(
            {
                "candidate_id": record.record_id,
                "manufacturer_name": record.manufacturer_name,
                "material_family": record.material_family,
                "grade_name": record.grade_name,
                "candidate_kind": _candidate_kind(record),
                "viability_status": "viable",
                "fit_score": fit.score,
                "fit_reasons": list(fit.positive_reasons),
                "capability_hints": list((record.coverage_metadata or {}).get("capability_hints") or []),
                "evidence_refs": [f"domain_record:{record.record_id}"],
            }
        )

    candidates.sort(
        key=lambda item: (
            -int(item.get("fit_score") or 0),
            str(item.get("manufacturer_name") or ""),
            str(item.get("candidate_id") or ""),
        )
    )

    if not candidates:
        notes.append("No manufacturer record matches the current governed material and operating window.")
    else:
        top_candidate = candidates[0]
        notes.append(
            "Selected "
            f"{top_candidate['candidate_id']} with capability score {int(top_candidate.get('fit_score') or 0)} "
            f"based on {', '.join(list(top_candidate.get('fit_reasons') or []))}."
        )
    return candidates, notes


async def matching_node(state: GraphState) -> GraphState:
    """Deterministically derive MatchingState from the governed state."""
    gov_class = state.governance.gov_class
    requirement_class = state.governance.requirement_class

    if gov_class not in _ALLOWED_GOV_CLASSES:
        return state.model_copy(
            update={
                "matching": MatchingState(
                    matchability_status="blocked_governance",
                    status="not_ready",
                    matching_notes=["Matching is only available after technical narrowing reaches Class B or A."],
                )
            }
        )

    if requirement_class is None:
        return state.model_copy(
            update={
                "matching": MatchingState(
                    matchability_status="insufficient_matching_basis",
                    status="not_ready",
                    matching_notes=[
                        "Matching requires a resolved requirement class or an equivalent admissible requirement space."
                    ],
                )
            }
        )

    material_family = _material_family_for_matching(state)
    if material_family is None:
        return state.model_copy(
            update={
                "matching": MatchingState(
                    matchability_status="insufficient_matching_basis",
                    status="not_ready",
                    matching_notes=["Matching requires a governed material family or a requirement-class-backed material hint."],
                )
            }
        )

    match_candidates, notes = _build_match_candidates(state)
    manufacturer_refs = _build_manufacturer_refs(
        recommendation_identity=match_candidates[0] if match_candidates else None,
        match_candidates=match_candidates,
        qualified_materials=[],
        handover_ready=False,
    )
    requirement_class_payload = (
        {
            "requirement_class_id": requirement_class.class_id,
            "description": requirement_class.description,
            "seal_type": requirement_class.seal_type,
        }
        if requirement_class is not None
        else None
    )
    manufacturer_capabilities = _build_manufacturer_capabilities(
        manufacturer_refs=manufacturer_refs,
        requirement_class=requirement_class_payload,
        match_candidates=match_candidates,
    )
    matchability_status = "ready_for_matching"
    specialist_result = run_manufacturer_rfq_specialist(
        ManufacturerRfqSpecialistInput(
            admissible_request_package=ManufacturerRfqAdmissibleRequestPackage(
                matchability_status=matchability_status,
                rfq_admissibility="ready" if state.governance.rfq_admissible else "inadmissible",
                requirement_class=requirement_class_payload,
            ),
            manufacturer_capabilities=ManufacturerCapabilityPackage(
                match_candidates=tuple(dict(item) for item in match_candidates),
                manufacturer_refs=tuple(dict(item) for item in manufacturer_refs),
                manufacturer_capabilities=tuple(dict(item) for item in manufacturer_capabilities),
                winner_candidate_id=match_candidates[0]["candidate_id"] if match_candidates else None,
                recommendation_identity=dict(match_candidates[0]) if match_candidates else None,
            ),
            scope_package=ManufacturerRfqScopePackage(
                scope_of_validity=tuple(
                    str(item)
                    for item in list(state.governance.validity_limits or [])
                    if item is not None
                ),
                open_points=tuple(
                    str(item)
                    for item in list(state.governance.open_validation_points or [])
                    if item is not None
                ),
            ),
        )
    )
    outcome = dict(specialist_result.manufacturer_match_result or {})

    notes = list(notes)
    reason = str(outcome.get("reason") or "").strip()
    if reason:
        notes.append(reason)

    log.debug(
        "[matching_node] gov_class=%s material_family=%s candidates=%d status=%s",
        gov_class,
        material_family,
        len(match_candidates),
        outcome.get("status"),
    )

    return state.model_copy(
        update={
            "matching": MatchingState.model_validate(
                {
                    "matchability_status": outcome.get("matchability_status") or matchability_status,
                    "status": outcome.get("status") or "not_ready",
                    "selected_manufacturer_ref": outcome.get("selected_manufacturer_ref"),
                    "manufacturer_refs": manufacturer_refs,
                    "manufacturer_capabilities": [
                        {
                            "manufacturer_name": item.get("manufacturer_name"),
                            "requirement_class_ids": list(item.get("requirement_class_ids") or []),
                            "material_families": list(item.get("material_families") or []),
                            "grade_names": list(item.get("grade_names") or []),
                            "candidate_ids": list(item.get("candidate_ids") or []),
                            "capability_hints": list(item.get("capability_hints") or []),
                            "source_refs": list(item.get("capability_sources") or []),
                            "qualified_for_rfq": bool(item.get("rfq_qualified", False)),
                        }
                        for item in manufacturer_capabilities
                    ],
                    "matching_notes": notes,
                }
            )
        }
    )
