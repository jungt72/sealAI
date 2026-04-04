from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent.agent.commercial import (
    build_handover_payload_basis_from_rfq_object,
    build_matching_outcome,
)


@dataclass(frozen=True)
class ManufacturerRfqAdmissibleRequestPackage:
    matchability_status: str = "not_ready"
    rfq_admissibility: str = "inadmissible"
    requirement_class: dict[str, Any] | None = None
    confirmed_parameters: dict[str, Any] = field(default_factory=dict)
    dimensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ManufacturerCapabilityPackage:
    match_candidates: tuple[dict[str, Any], ...] = ()
    manufacturer_refs: tuple[dict[str, Any], ...] = ()
    manufacturer_capabilities: tuple[dict[str, Any], ...] = ()
    winner_candidate_id: str | None = None
    recommendation_identity: dict[str, Any] | None = None
    selected_manufacturer_ref: dict[str, Any] | None = None


@dataclass(frozen=True)
class ManufacturerRfqScopePackage:
    scope_of_validity: tuple[str, ...] = ()
    open_points: tuple[str, ...] = ()


@dataclass(frozen=True)
class ManufacturerRfqSpecialistInput:
    admissible_request_package: ManufacturerRfqAdmissibleRequestPackage
    manufacturer_capabilities: ManufacturerCapabilityPackage = field(default_factory=ManufacturerCapabilityPackage)
    scope_package: ManufacturerRfqScopePackage = field(default_factory=ManufacturerRfqScopePackage)
    rfq_object: dict[str, Any] | None = None
    recipient_refs: tuple[dict[str, Any], ...] = ()
    review_required: bool = False
    contract_obsolete: bool = False


@dataclass(frozen=True)
class ManufacturerRfqSpecialistResult:
    manufacturer_match_result: dict[str, Any] | None = None
    rfq_basis: dict[str, Any] | None = None
    rfq_send_payload: dict[str, Any] | None = None


def _compact_dict(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    compact = {str(key): item for key, item in value.items() if item is not None}
    return compact or None


def _compact_dicts(items: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        compact = _compact_dict(item)
        if compact:
            result.append(compact)
    return result


def _compact_maybe_dicts(items: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        compact = _compact_dict(item if isinstance(item, dict) else None)
        if compact:
            result.append(compact)
    return result


def _first_dict(items: list[Any]) -> dict[str, Any] | None:
    for item in items:
        compact = _compact_dict(item if isinstance(item, dict) else None)
        if compact:
            return compact
    return None


def _matching_state(payload: ManufacturerRfqSpecialistInput) -> dict[str, Any]:
    capabilities = payload.manufacturer_capabilities
    request = payload.admissible_request_package
    return {
        "matchability_status": request.matchability_status,
        "match_candidates": _compact_dicts(capabilities.match_candidates),
        "winner_candidate_id": capabilities.winner_candidate_id,
        "recommendation_identity": _compact_dict(capabilities.recommendation_identity),
        "requirement_class": _compact_dict(request.requirement_class),
        "review_required": payload.review_required,
        "contract_obsolete": payload.contract_obsolete,
        "manufacturer_validation_required": bool(payload.scope_package.open_points),
    }


def _manufacturer_state(payload: ManufacturerRfqSpecialistInput) -> dict[str, Any]:
    capabilities = payload.manufacturer_capabilities
    request = payload.admissible_request_package
    return {
        "manufacturer_refs": _compact_dicts(capabilities.manufacturer_refs),
        "manufacturer_capabilities": _compact_dicts(capabilities.manufacturer_capabilities),
        "recommendation_identity": _compact_dict(capabilities.recommendation_identity),
        "requirement_class": _compact_dict(request.requirement_class),
    }


def _recipient_selection(payload: ManufacturerRfqSpecialistInput) -> dict[str, Any] | None:
    capabilities = payload.manufacturer_capabilities
    selected = _compact_dict(capabilities.selected_manufacturer_ref)
    candidates = _compact_dicts(capabilities.manufacturer_refs)
    if not selected and not candidates:
        return None
    selected_refs = [selected] if selected else []
    candidate_refs = candidates or selected_refs
    return {
        "selected_recipient_refs": selected_refs,
        "candidate_recipient_refs": candidate_refs,
    }


def _build_manufacturer_match_result(
    payload: ManufacturerRfqSpecialistInput,
) -> dict[str, Any]:
    request = payload.admissible_request_package
    matching_outcome = build_matching_outcome(
        {
            "case_state": {
                "matching_state": _matching_state(payload),
                "manufacturer_state": _manufacturer_state(payload),
                "recipient_selection": _recipient_selection(payload),
            },
            "sealing_state": {
                "governance": {
                    "release_status": "manufacturer_validation_required",
                },
                "review": {
                    "review_required": payload.review_required,
                },
            },
        }
    )
    return dict(matching_outcome or {})


def _build_rfq_basis(
    payload: ManufacturerRfqSpecialistInput,
) -> dict[str, Any] | None:
    request = payload.admissible_request_package
    rfq_object = _compact_dict(payload.rfq_object)
    if not rfq_object:
        return None
    basis = build_handover_payload_basis_from_rfq_object(
        rfq_object,
        rfq_admissibility=request.rfq_admissibility,
    )
    return {
        "object_type": "manufacturer_rfq_basis",
        "object_version": "manufacturer_rfq_basis_v1",
        "rfq_object": rfq_object,
        "handover_payload": dict(basis.get("handover_payload") or {}),
        "target_system": basis.get("target_system"),
        "requirement_class": _compact_dict(request.requirement_class),
        "recipient_refs": _compact_dicts(payload.recipient_refs),
        "selected_manufacturer_ref": _compact_dict(payload.manufacturer_capabilities.selected_manufacturer_ref),
        "scope_of_validity": list(payload.scope_package.scope_of_validity),
        "open_points": list(payload.scope_package.open_points),
    }


def _build_rfq_send_payload(
    payload: ManufacturerRfqSpecialistInput,
    *,
    rfq_basis: dict[str, Any] | None,
) -> dict[str, Any]:
    request = payload.admissible_request_package
    recipient_refs = _compact_dicts(payload.recipient_refs)
    blocking_reasons: list[str] = []
    if request.rfq_admissibility != "ready":
        blocking_reasons.append("rfq_not_admissible")
    if rfq_basis is None:
        blocking_reasons.append("missing_rfq_basis")
    if not recipient_refs:
        blocking_reasons.append("no_recipient_refs")

    send_ready = not blocking_reasons
    return {
        "object_type": "rfq_send_payload",
        "object_version": "rfq_send_payload_v1",
        "send_ready": send_ready,
        "send_status": "send_ready" if send_ready else "send_blocked",
        "blocking_reasons": blocking_reasons,
        "recipient_refs": recipient_refs,
        "selected_manufacturer_ref": _compact_dict(payload.manufacturer_capabilities.selected_manufacturer_ref),
        "target_system": rfq_basis.get("target_system") if rfq_basis else None,
        "handover_payload": dict(rfq_basis.get("handover_payload") or {}) if rfq_basis else None,
        "requirement_class": _compact_dict(request.requirement_class),
        "scope_of_validity": list(payload.scope_package.scope_of_validity),
        "open_points": list(payload.scope_package.open_points),
    }


def run_manufacturer_rfq_specialist(
    payload: ManufacturerRfqSpecialistInput,
) -> ManufacturerRfqSpecialistResult:
    manufacturer_match_result = _build_manufacturer_match_result(payload)
    rfq_basis = _build_rfq_basis(payload)
    rfq_send_payload = _build_rfq_send_payload(payload, rfq_basis=rfq_basis)
    return ManufacturerRfqSpecialistResult(
        manufacturer_match_result=manufacturer_match_result,
        rfq_basis=rfq_basis,
        rfq_send_payload=rfq_send_payload,
    )


def build_manufacturer_rfq_specialist_input_from_runtime_state(
    state: dict[str, Any],
) -> ManufacturerRfqSpecialistInput:
    case_state = dict(state.get("case_state") or {})
    sealing_state = dict(state.get("sealing_state") or {})

    matching_state = dict(case_state.get("matching_state") or {})
    manufacturer_state = dict(case_state.get("manufacturer_state") or {})
    rfq_state = dict(case_state.get("rfq_state") or {})
    result_contract = dict(case_state.get("result_contract") or {})
    recipient_selection = (
        case_state.get("recipient_selection")
        or rfq_state.get("recipient_selection")
        or {}
    )
    selection_state = dict(sealing_state.get("selection") or {})
    governance_state = dict(sealing_state.get("governance") or case_state.get("governance_state") or {})
    review_state = dict(sealing_state.get("review") or {})

    matching_outcome = (
        matching_state.get("matching_outcome")
        or case_state.get("matching_outcome")
        or sealing_state.get("matching_outcome")
        or {}
    )
    requirement_class = (
        matching_state.get("requirement_class")
        or manufacturer_state.get("requirement_class")
        or rfq_state.get("requirement_class")
        or result_contract.get("requirement_class")
        or case_state.get("requirement_class")
    )
    recommendation_identity = (
        matching_state.get("recommendation_identity")
        or manufacturer_state.get("recommendation_identity")
        or result_contract.get("recommendation_identity")
    )
    selected_manufacturer_ref = _first_dict(
        [
            (matching_outcome if isinstance(matching_outcome, dict) else {}).get("selected_manufacturer_ref"),
            (recipient_selection if isinstance(recipient_selection, dict) else {}).get("selected_manufacturer_ref"),
            ((recipient_selection if isinstance(recipient_selection, dict) else {}).get("selected_recipient_refs") or [None])[0],
        ]
    )
    candidate_recipient_refs = tuple(
        dict(ref)
        for ref in list((recipient_selection if isinstance(recipient_selection, dict) else {}).get("candidate_recipient_refs") or [])
        if isinstance(ref, dict) and ref
    )
    selected_recipient_refs = tuple(
        dict(ref)
        for ref in list((recipient_selection if isinstance(recipient_selection, dict) else {}).get("selected_recipient_refs") or [])
        if isinstance(ref, dict) and ref
    )
    recipient_refs = selected_recipient_refs or candidate_recipient_refs or tuple(
        dict(ref)
        for ref in list(manufacturer_state.get("manufacturer_refs") or [])
        if isinstance(ref, dict) and ref
    )
    return ManufacturerRfqSpecialistInput(
        admissible_request_package=ManufacturerRfqAdmissibleRequestPackage(
            matchability_status=str(
                matching_state.get("matchability_status")
                or ("ready_for_matching" if matching_state.get("matchable") else "not_ready")
            ),
            rfq_admissibility=str(governance_state.get("rfq_admissibility") or "inadmissible"),
            requirement_class=_compact_dict(requirement_class),
        ),
        manufacturer_capabilities=ManufacturerCapabilityPackage(
            match_candidates=tuple(
                dict(item)
                for item in list(matching_state.get("match_candidates") or [])
                if isinstance(item, dict) and item
            ),
            manufacturer_refs=tuple(
                dict(item)
                for item in list(manufacturer_state.get("manufacturer_refs") or [])
                if isinstance(item, dict) and item
            ),
            manufacturer_capabilities=tuple(
                dict(item)
                for item in list(manufacturer_state.get("manufacturer_capabilities") or [])
                if isinstance(item, dict) and item
            ),
            winner_candidate_id=str(selection_state.get("winner_candidate_id") or matching_state.get("winner_candidate_id") or "") or None,
            recommendation_identity=_compact_dict(recommendation_identity),
            selected_manufacturer_ref=selected_manufacturer_ref,
        ),
        scope_package=ManufacturerRfqScopePackage(
            scope_of_validity=tuple(
                str(item)
                for item in list(governance_state.get("scope_of_validity") or governance_state.get("validity_limits") or [])
                if item is not None
            ),
            open_points=tuple(
                str(item)
                for item in list(governance_state.get("unknowns_manufacturer_validation") or governance_state.get("open_validation_points") or [])
                if item is not None
            ),
        ),
        rfq_object=_compact_dict(rfq_state.get("rfq_object")),
        recipient_refs=recipient_refs,
        review_required=bool(
            matching_state.get("review_required", rfq_state.get("review_required", review_state.get("review_required", False)))
        ),
        contract_obsolete=bool(
            matching_state.get("contract_obsolete")
            or rfq_state.get("contract_obsolete")
            or result_contract.get("contract_obsolete")
        ),
    )


def build_manufacturer_match_result_from_runtime_state(
    state: dict[str, Any],
) -> dict[str, Any]:
    result = run_manufacturer_rfq_specialist(
        build_manufacturer_rfq_specialist_input_from_runtime_state(state)
    )
    return dict(result.manufacturer_match_result or {})


def project_rfq_payload_basis_from_specialist_result(
    result: ManufacturerRfqSpecialistResult,
    *,
    payload: ManufacturerRfqSpecialistInput,
    recommendation_identity: dict[str, Any] | None = None,
    requirement_class: dict[str, Any] | None = None,
    requirement_class_hint: str | None = None,
) -> dict[str, Any]:
    rfq_basis = dict(result.rfq_basis or {})
    rfq_object = dict(rfq_basis.get("rfq_object") or payload.rfq_object or {})
    handover_payload = dict(rfq_basis.get("handover_payload") or {})
    projected_requirement_class = (
        _compact_dict(rfq_object.get("requirement_class"))
        or _compact_dict(rfq_basis.get("requirement_class"))
        or _compact_dict(requirement_class)
    )
    return {
        "object_type": str(rfq_object.get("object_type") or "rfq_payload_basis"),
        "object_version": str(rfq_object.get("object_version") or "rfq_payload_basis_v1"),
        "recommendation_identity": _compact_dict(recommendation_identity),
        "requirement_class": projected_requirement_class,
        "requirement_class_hint": requirement_class_hint,
        "qualified_material_ids": list(handover_payload.get("qualified_material_ids") or rfq_object.get("qualified_material_ids") or []),
        "qualified_materials": list(handover_payload.get("qualified_materials") or rfq_object.get("qualified_materials") or []),
        "confirmed_parameters": dict(handover_payload.get("confirmed_parameters") or rfq_object.get("confirmed_parameters") or {}),
        "dimensions": dict(handover_payload.get("dimensions") or rfq_object.get("dimensions") or {}),
        "target_system": rfq_basis.get("target_system") or rfq_object.get("target_system"),
        "payload_present": bool(handover_payload or rfq_object.get("payload_present", False)),
    }


def project_rfq_payload_basis_from_specialist(
    payload: ManufacturerRfqSpecialistInput,
    *,
    recommendation_identity: dict[str, Any] | None = None,
    requirement_class: dict[str, Any] | None = None,
    requirement_class_hint: str | None = None,
) -> dict[str, Any]:
    result = run_manufacturer_rfq_specialist(payload)
    return project_rfq_payload_basis_from_specialist_result(
        result,
        payload=payload,
        recommendation_identity=recommendation_identity,
        requirement_class=requirement_class,
        requirement_class_hint=requirement_class_hint,
    )


def project_dispatch_intent_from_rfq_send_payload(
    rfq_send_payload: dict[str, Any] | None,
    *,
    projection: str = "dispatch_intent",
    recipient_selection: dict[str, Any] | None = None,
    handover_status: str | None = None,
    dispatch_open_points: list[str] | tuple[str, ...] = (),
) -> dict[str, Any] | None:
    payload = _compact_dict(rfq_send_payload)
    if not payload:
        return None

    blocking_reasons = [
        str(item)
        for item in list(payload.get("blocking_reasons") or [])
        if str(item or "").strip()
    ]
    recipient_refs = _compact_maybe_dicts(list(payload.get("recipient_refs") or []))
    selected_manufacturer_ref = _compact_dict(payload.get("selected_manufacturer_ref"))
    requirement_class = _compact_dict(payload.get("requirement_class"))
    handover_payload = dict(payload.get("handover_payload") or {})
    qualified_material_ids = [
        str(item)
        for item in list(handover_payload.get("qualified_material_ids") or [])
        if str(item or "").strip()
    ]

    if bool(payload.get("send_ready")):
        dispatch_status = "dispatch_ready"
    elif not recipient_refs or "no_recipient_refs" in blocking_reasons:
        dispatch_status = "not_ready_no_recipients"
    else:
        dispatch_status = "not_ready_dispatch_blocked"

    recommendation_identity = None
    if qualified_material_ids or selected_manufacturer_ref:
        recommendation_identity = {
            "candidate_id": qualified_material_ids[0] if qualified_material_ids else None,
            "manufacturer_name": (
                selected_manufacturer_ref.get("manufacturer_name")
                if isinstance(selected_manufacturer_ref, dict)
                else None
            ),
        }

    selected_recipient_refs = [selected_manufacturer_ref] if selected_manufacturer_ref else []

    base_projection = {
        "dispatch_ready": bool(payload.get("send_ready")),
        "dispatch_status": dispatch_status,
        "dispatch_blockers": blocking_reasons,
        "recipient_refs": recipient_refs,
        "selected_manufacturer_ref": selected_manufacturer_ref,
        "recipient_selection": {
            "selected_recipient_refs": selected_recipient_refs,
            "candidate_recipient_refs": recipient_refs,
        }
        if recipient_refs
        else None,
        "requirement_class": requirement_class,
        "recommendation_identity": recommendation_identity,
        "rfq_object_basis": {
            "object_type": "rfq_payload_basis",
            "object_version": "rfq_payload_basis_v1",
            "payload_present": bool(handover_payload),
            "qualified_material_ids": qualified_material_ids,
        },
    }

    if projection == "rfq_dispatch":
        projected_selection = dict(recipient_selection or {}) if isinstance(recipient_selection, dict) else {}
        selected_refs = [
            dict(ref)
            for ref in list(projected_selection.get("selected_recipient_refs") or [])
            if isinstance(ref, dict) and ref
        ]
        candidate_refs = [
            dict(ref)
            for ref in list(projected_selection.get("candidate_recipient_refs") or [])
            if isinstance(ref, dict) and ref
        ] or recipient_refs
        effective_recipient_refs = selected_refs or candidate_refs or recipient_refs
        return {
            "object_type": "rfq_dispatch",
            "object_version": "rfq_dispatch_v1",
            "dispatch_ready": base_projection["dispatch_ready"],
            "dispatch_status": base_projection["dispatch_status"],
            "dispatch_blockers": blocking_reasons,
            "dispatch_open_points": list(dict.fromkeys(str(item) for item in list(dispatch_open_points) if item)),
            "recipient_basis_summary": {
                "recipient_count": len(effective_recipient_refs),
                "selected_recipient_count": len(selected_refs),
                "candidate_recipient_count": len(candidate_refs),
                "has_selected_manufacturer_ref": bool(selected_manufacturer_ref),
                "derived_from_matching_outcome": bool(selected_manufacturer_ref),
                "handover_status": handover_status,
                "handover_ready": bool(payload.get("send_ready")),
            },
            "recipient_refs": effective_recipient_refs,
            "recipient_selection": projected_selection or None,
            "selected_manufacturer_ref": selected_manufacturer_ref,
            "recommendation_identity": recommendation_identity,
            "requirement_class": requirement_class,
            "rfq_object_basis": base_projection["rfq_object_basis"],
        }

    return {
        "object_type": "dispatch_intent",
        "object_version": "dispatch_intent_v1",
        **base_projection,
        "source": "rfq_send_payload",
    }
