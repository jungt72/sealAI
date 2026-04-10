"""
rfq_handover_node — Phase G Block 2

Deterministic RFQ handover preparation for the governed path.

Responsibility:
    Build the bounded RFQ-ready handover object from governed state after
    governance and matching have completed.

Architecture invariants:
    - No LLM call. No transport/dispatch side effects.
    - Reuses existing bounded commercial handover builders.
    - Output is persisted only in RfqState.
"""
from __future__ import annotations

import logging
from typing import Any

from app.agent.agent.commercial import build_handover_payload
from app.agent.domain.critical_review import (
    CriticalReviewGovernanceSummary,
    CriticalReviewMatchingPackage,
    CriticalReviewRecommendationPackage,
    CriticalReviewRfqBasis,
    CriticalReviewSpecialistInput,
    run_critical_review_specialist,
)
from app.agent.domain.manufacturer_rfq import (
    ManufacturerCapabilityPackage,
    ManufacturerRfqAdmissibleRequestPackage,
    ManufacturerRfqScopePackage,
    ManufacturerRfqSpecialistInput,
    run_manufacturer_rfq_specialist,
)
from app.agent.graph import GraphState
from app.agent.state.models import RecipientRef, RfqState

log = logging.getLogger(__name__)

_ALLOWED_PARAMETER_KEYS = (
    "temperature_c",
    "temperature_raw",
    "pressure_bar",
    "pressure_raw",
    "medium",
    "dynamic_type",
)

_ALLOWED_DIMENSION_KEYS = (
    "shaft_diameter_mm",
    "bore_diameter_mm",
    "groove_width_mm",
    "groove_depth_mm",
    "piston_rod_diameter_mm",
)


def _confirmed_parameters(state: GraphState) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in _ALLOWED_PARAMETER_KEYS:
        claim = state.asserted.assertions.get(key)
        if claim is not None and claim.asserted_value is not None:
            result[key] = claim.asserted_value
    return result


def _dimensions(state: GraphState) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in _ALLOWED_DIMENSION_KEYS:
        claim = state.asserted.assertions.get(key)
        if claim is not None and claim.asserted_value is not None:
            result[key] = claim.asserted_value
    return result


def _qualified_materials(state: GraphState) -> tuple[list[str], list[dict[str, Any]]]:
    material_ids: list[str] = []
    materials: list[dict[str, Any]] = []

    for ref in state.matching.manufacturer_refs:
        ids = list(ref.candidate_ids or [])
        families = list(ref.material_families or [])
        grades = list(ref.grade_names or [])
        if not ids and ref.manufacturer_name:
            continue
        for idx, candidate_id in enumerate(ids):
            entry: dict[str, Any] = {"candidate_id": candidate_id}
            if ref.manufacturer_name:
                entry["manufacturer_name"] = ref.manufacturer_name
            if families:
                entry["material_family"] = families[min(idx, len(families) - 1)]
            if grades:
                entry["grade_name"] = grades[min(idx, len(grades) - 1)]
            material_ids.append(candidate_id)
            materials.append(entry)

    return material_ids, materials


def _recipient_refs(state: GraphState) -> list[RecipientRef]:
    recipients: list[RecipientRef] = []
    seen: set[str] = set()
    for ref in state.matching.manufacturer_refs:
        if not ref.manufacturer_name or ref.manufacturer_name in seen:
            continue
        recipients.append(
            RecipientRef(
                manufacturer_name=ref.manufacturer_name,
                qualified_for_rfq=ref.qualified_for_rfq or state.matching.status == "matched_primary_candidate",
            )
        )
        seen.add(ref.manufacturer_name)
    return recipients


def _build_rfq_object(state: GraphState) -> dict[str, Any]:
    requirement_class = state.governance.requirement_class
    qualified_material_ids, qualified_materials = _qualified_materials(state)
    return {
        "object_type": "rfq_payload_basis",
        "object_version": "rfq_payload_basis_v1",
        "requirement_class": (
            {
                "requirement_class_id": requirement_class.class_id,
                "description": requirement_class.description,
                "seal_type": requirement_class.seal_type,
            }
            if requirement_class is not None
            else None
        ),
        "qualified_material_ids": qualified_material_ids,
        "qualified_materials": qualified_materials,
        "confirmed_parameters": _confirmed_parameters(state),
        "dimensions": _dimensions(state),
        "target_system": "rfq_portal",
    }


async def rfq_handover_node(state: GraphState) -> GraphState:
    """Build the bounded RFQ handover state after matching."""
    requirement_class = state.governance.requirement_class
    selected = state.matching.selected_manufacturer_ref

    if state.governance.gov_class != "A" or not state.governance.rfq_admissible:
        return state.model_copy(
            update={
                "rfq": RfqState(
                    status="needs_clarification",
                    rfq_admissible=state.governance.rfq_admissible,
                    rfq_object={},
                    requirement_class=requirement_class,
                    notes=["RFQ handover requires Class A governance with admissible technical scope."],
                )
            }
        )

    if state.matching.status != "matched_primary_candidate" or selected is None:
        return state.model_copy(
            update={
                "rfq": RfqState(
                    status="not_ready",
                    rfq_admissible=state.governance.rfq_admissible,
                    rfq_object={},
                    requirement_class=requirement_class,
                    notes=["RFQ handover requires a selected manufacturer candidate from deterministic matching."],
                )
            }
        )

    if requirement_class is None:
        return state.model_copy(
            update={
                "rfq": RfqState(
                    status="not_ready",
                    rfq_admissible=state.governance.rfq_admissible,
                    rfq_object={},
                    notes=["RFQ handover requires a resolved requirement class."],
                )
            }
        )

    recipients = _recipient_refs(state)
    critical_review = run_critical_review_specialist(
        CriticalReviewSpecialistInput(
            governance_summary=CriticalReviewGovernanceSummary(
                release_status="inquiry_ready" if state.governance.rfq_admissible else "inadmissible",
                rfq_admissibility="ready" if state.governance.rfq_admissible else "inadmissible",
                unknowns_release_blocking=tuple(str(item) for item in list(state.asserted.blocking_unknowns or []) if item is not None),
                unknowns_manufacturer_validation=tuple(str(item) for item in list(state.governance.open_validation_points or []) if item is not None),
                scope_of_validity=tuple(str(item) for item in list(state.governance.validity_limits or []) if item is not None),
                conflicts=tuple(str(item) for item in list(state.asserted.conflict_flags or []) if item is not None),
                review_required=False,
            ),
            recommendation_package=CriticalReviewRecommendationPackage(
                requirement_class={
                    "requirement_class_id": requirement_class.class_id,
                    "description": requirement_class.description,
                    "seal_type": requirement_class.seal_type,
                },
            ),
            matching_package=CriticalReviewMatchingPackage(
                status=state.matching.status,
                selected_manufacturer_ref={"manufacturer_name": selected.manufacturer_name} if selected else None,
            ),
            rfq_basis=CriticalReviewRfqBasis(
                recipient_refs=tuple(ref.model_dump() for ref in recipients),
            ),
        )
    )
    if not critical_review.critical_review_passed:
        return state.model_copy(
            update={
                "rfq": RfqState(
                    status="blocked_critical_review",
                    rfq_ready=False,
                    rfq_admissible=state.governance.rfq_admissible,
                    critical_review_status=critical_review.critical_review_status or "failed",
                    critical_review_passed=False,
                    blocking_findings=list(critical_review.blocking_findings),
                    soft_findings=list(critical_review.soft_findings),
                    required_corrections=list(critical_review.required_corrections),
                    selected_manufacturer_ref=selected,
                    recipient_refs=recipients,
                    requirement_class=requirement_class,
                    notes=["Critical review blocked RFQ handover."],
                )
            }
        )

    rfq_object = _build_rfq_object(state)
    manufacturer_rfq = run_manufacturer_rfq_specialist(
        ManufacturerRfqSpecialistInput(
            admissible_request_package=ManufacturerRfqAdmissibleRequestPackage(
                matchability_status=state.matching.matchability_status,
                rfq_admissibility="ready" if state.governance.rfq_admissible else "inadmissible",
                requirement_class={
                    "requirement_class_id": requirement_class.class_id,
                    "description": requirement_class.description,
                    "seal_type": requirement_class.seal_type,
                },
                confirmed_parameters=_confirmed_parameters(state),
                dimensions=_dimensions(state),
            ),
            manufacturer_capabilities=ManufacturerCapabilityPackage(
                manufacturer_refs=tuple(ref.model_dump() for ref in state.matching.manufacturer_refs),
                manufacturer_capabilities=tuple(
                    capability.model_dump() for capability in state.matching.manufacturer_capabilities
                ),
                selected_manufacturer_ref=selected.model_dump() if selected is not None else None,
            ),
            scope_package=ManufacturerRfqScopePackage(
                scope_of_validity=tuple(
                    str(item) for item in list(state.governance.validity_limits or []) if item is not None
                ),
                open_points=tuple(
                    str(item) for item in list(state.governance.open_validation_points or []) if item is not None
                ),
            ),
            rfq_object=rfq_object,
            recipient_refs=tuple(ref.model_dump() for ref in recipients),
        )
    )
    rfq_basis = dict(manufacturer_rfq.rfq_basis or {})
    rfq_object = dict(rfq_basis.get("rfq_object") or rfq_object)
    handover = build_handover_payload(
        {
            "governance": {
                "release_status": "inquiry_ready",
                "rfq_admissibility": "ready",
            },
            "review": {
                "review_required": False,
                "review_state": "none",
                **{
                    "critical_review_status": critical_review.critical_review_status,
                    "critical_review_passed": critical_review.critical_review_passed,
                    "blocking_findings": list(critical_review.blocking_findings),
                    "soft_findings": list(critical_review.soft_findings),
                    "required_corrections": list(critical_review.required_corrections),
                },
            },
            "selection": {},
            "asserted": {},
        },
        canonical_rfq_object=rfq_object,
        rfq_admissibility="ready",
    )

    payload = dict(rfq_basis.get("handover_payload") or handover.get("handover_payload") or {})

    log.debug(
        "[rfq_handover_node] rfq_ready=%s manufacturer=%s recipients=%d qualified_materials=%d",
        handover.get("is_handover_ready"),
        selected.manufacturer_name,
        len(recipients),
        len(payload.get("qualified_material_ids") or []),
    )

    return state.model_copy(
        update={
            "rfq": RfqState(
                status="rfq_ready" if handover.get("is_handover_ready") else "not_ready",
                rfq_ready=bool(handover.get("is_handover_ready")),
                rfq_admissible=state.governance.rfq_admissible,
                critical_review_status=critical_review.critical_review_status or "passed",
                critical_review_passed=critical_review.critical_review_passed,
                blocking_findings=list(critical_review.blocking_findings),
                soft_findings=list(critical_review.soft_findings),
                required_corrections=list(critical_review.required_corrections),
                handover_status=handover.get("handover_status"),
                rfq_object=rfq_object,
                rfq_send_payload=dict(manufacturer_rfq.rfq_send_payload or {}),
                selected_manufacturer_ref=selected,
                recipient_refs=recipients,
                qualified_material_ids=list(payload.get("qualified_material_ids") or []),
                qualified_materials=list(payload.get("qualified_materials") or []),
                confirmed_parameters=dict(payload.get("confirmed_parameters") or {}),
                dimensions=dict(payload.get("dimensions") or {}),
                requirement_class=requirement_class,
                handover_summary=str(handover.get("handover_reason") or "").strip() or None,
                notes=[note for note in [handover.get("handover_reason")] if note],
            )
        }
    )
