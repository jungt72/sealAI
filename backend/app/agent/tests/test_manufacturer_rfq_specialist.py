from __future__ import annotations

from app.agent.domain.manufacturer_rfq import (
    ManufacturerCapabilityPackage,
    ManufacturerRfqAdmissibleRequestPackage,
    ManufacturerRfqScopePackage,
    ManufacturerRfqSpecialistInput,
    project_dispatch_intent_from_rfq_send_payload,
    run_manufacturer_rfq_specialist,
)


def _payload(
    *,
    matchability_status: str = "ready_for_matching",
    rfq_admissibility: str = "ready",
    rfq_object: dict | None = None,
    recipient_refs: tuple[dict, ...] = ({"manufacturer_name": "Acme", "qualified_for_rfq": True},),
    open_points: tuple[str, ...] = (),
    scope_of_validity: tuple[str, ...] = (),
) -> ManufacturerRfqSpecialistInput:
    requirement_class = {
        "requirement_class_id": "PTFE10",
        "description": "High-temperature steam application — PTFE sealing class",
        "seal_type": "gasket",
    }
    match_candidate = {
        "candidate_id": "registry-ptfe-g25-acme",
        "manufacturer_name": "Acme",
        "material_family": "PTFE",
        "grade_name": "G25",
        "candidate_kind": "manufacturer_grade",
        "viability_status": "viable",
        "fit_score": 100,
        "fit_reasons": ["requirement class 'PTFE10' is supported."],
    }
    manufacturer_ref = {
        "manufacturer_name": "Acme",
        "candidate_ids": ["registry-ptfe-g25-acme"],
        "material_families": ["PTFE"],
        "grade_names": ["G25"],
        "qualified_for_rfq": True,
    }
    manufacturer_capability = {
        "manufacturer_name": "Acme",
        "requirement_class_ids": ["PTFE10"],
        "material_families": ["PTFE"],
        "grade_names": ["G25"],
        "candidate_ids": ["registry-ptfe-g25-acme"],
        "capability_hints": ["steam_service"],
        "capability_sources": ["domain_record:registry-ptfe-g25-acme"],
        "rfq_qualified": True,
    }
    return ManufacturerRfqSpecialistInput(
        admissible_request_package=ManufacturerRfqAdmissibleRequestPackage(
            matchability_status=matchability_status,
            rfq_admissibility=rfq_admissibility,
            requirement_class=requirement_class,
            confirmed_parameters={"medium": "Dampf", "temperature_c": 180.0},
            dimensions={"shaft_diameter_mm": 25.0},
        ),
        manufacturer_capabilities=ManufacturerCapabilityPackage(
            match_candidates=(match_candidate,),
            manufacturer_refs=(manufacturer_ref,),
            manufacturer_capabilities=(manufacturer_capability,),
            winner_candidate_id="registry-ptfe-g25-acme",
            recommendation_identity=match_candidate,
            selected_manufacturer_ref=manufacturer_ref,
        ),
        scope_package=ManufacturerRfqScopePackage(
            scope_of_validity=scope_of_validity,
            open_points=open_points,
        ),
        rfq_object=rfq_object,
        recipient_refs=recipient_refs,
    )


def test_admissible_package_returns_manufacturer_match_result() -> None:
    result = run_manufacturer_rfq_specialist(_payload())

    assert result.manufacturer_match_result is not None
    assert result.manufacturer_match_result["status"] == "matched_primary_candidate"
    assert result.manufacturer_match_result["selected_manufacturer_ref"]["manufacturer_name"] == "Acme"


def test_non_ready_matching_package_does_not_claim_a_match() -> None:
    result = run_manufacturer_rfq_specialist(
        _payload(matchability_status="insufficient_matching_basis")
    )

    assert result.manufacturer_match_result is not None
    assert result.manufacturer_match_result["status"] == "blocked_insufficient_matching_basis"
    assert result.manufacturer_match_result["selected_manufacturer_ref"] is None


def test_rfq_basis_is_built_from_structured_rfq_object() -> None:
    result = run_manufacturer_rfq_specialist(
        _payload(
            rfq_object={
                "object_type": "rfq_payload_basis",
                "object_version": "rfq_payload_basis_v1",
                "qualified_material_ids": ["registry-ptfe-g25-acme"],
                "qualified_materials": [{"candidate_id": "registry-ptfe-g25-acme", "manufacturer_name": "Acme"}],
                "confirmed_parameters": {"medium": "Dampf"},
                "dimensions": {"shaft_diameter_mm": 25.0},
                "target_system": "rfq_portal",
            }
        )
    )

    assert result.rfq_basis is not None
    assert result.rfq_basis["handover_payload"]["qualified_material_ids"] == ["registry-ptfe-g25-acme"]
    assert result.rfq_send_payload is not None
    assert result.rfq_send_payload["send_ready"] is True


def test_inadmissible_or_incomplete_package_does_not_create_artificial_send_safety() -> None:
    result = run_manufacturer_rfq_specialist(
        _payload(
            rfq_admissibility="inadmissible",
            rfq_object=None,
            recipient_refs=(),
        )
    )

    assert result.rfq_basis is None
    assert result.rfq_send_payload is not None
    assert result.rfq_send_payload["send_ready"] is False
    assert result.rfq_send_payload["blocking_reasons"] == [
        "rfq_not_admissible",
        "missing_rfq_basis",
        "no_recipient_refs",
    ]


def test_scope_limits_and_open_points_are_preserved_in_rfq_outputs() -> None:
    result = run_manufacturer_rfq_specialist(
        _payload(
            rfq_object={
                "object_type": "rfq_payload_basis",
                "object_version": "rfq_payload_basis_v1",
                "qualified_material_ids": ["registry-ptfe-g25-acme"],
                "qualified_materials": [{"candidate_id": "registry-ptfe-g25-acme"}],
                "confirmed_parameters": {"medium": "Dampf"},
                "dimensions": {},
                "target_system": "rfq_portal",
            },
            scope_of_validity=("manufacturer_validation_scope",),
            open_points=("temperature_confirmation",),
        )
    )

    assert result.rfq_basis is not None
    assert result.rfq_basis["scope_of_validity"] == ["manufacturer_validation_scope"]
    assert result.rfq_basis["open_points"] == ["temperature_confirmation"]
    assert result.rfq_send_payload["scope_of_validity"] == ["manufacturer_validation_scope"]
    assert result.rfq_send_payload["open_points"] == ["temperature_confirmation"]


def test_dispatch_intent_projection_uses_bounded_send_payload_contract() -> None:
    result = run_manufacturer_rfq_specialist(
        _payload(
            rfq_object={
                "object_type": "rfq_payload_basis",
                "object_version": "rfq_payload_basis_v1",
                "qualified_material_ids": ["registry-ptfe-g25-acme"],
                "qualified_materials": [{"candidate_id": "registry-ptfe-g25-acme", "manufacturer_name": "Acme"}],
                "confirmed_parameters": {"medium": "Dampf"},
                "dimensions": {"shaft_diameter_mm": 25.0},
                "target_system": "rfq_portal",
            }
        )
    )

    dispatch_intent = project_dispatch_intent_from_rfq_send_payload(result.rfq_send_payload)

    assert dispatch_intent is not None
    assert dispatch_intent["dispatch_ready"] is True
    assert dispatch_intent["dispatch_status"] == "dispatch_ready"
    assert dispatch_intent["recommendation_identity"]["candidate_id"] == "registry-ptfe-g25-acme"


def test_dispatch_intent_projection_preserves_blocked_recipient_status() -> None:
    result = run_manufacturer_rfq_specialist(
        _payload(
            rfq_object={
                "object_type": "rfq_payload_basis",
                "object_version": "rfq_payload_basis_v1",
                "qualified_material_ids": ["registry-ptfe-g25-acme"],
            },
            recipient_refs=(),
        )
    )

    dispatch_intent = project_dispatch_intent_from_rfq_send_payload(result.rfq_send_payload)

    assert dispatch_intent is not None
    assert dispatch_intent["dispatch_ready"] is False
    assert dispatch_intent["dispatch_status"] == "not_ready_no_recipients"
    assert dispatch_intent["dispatch_blockers"] == ["no_recipient_refs"]


def test_rfq_dispatch_projection_reuses_bounded_send_payload_contract() -> None:
    result = run_manufacturer_rfq_specialist(
        _payload(
            rfq_object={
                "object_type": "rfq_payload_basis",
                "object_version": "rfq_payload_basis_v1",
                "qualified_material_ids": ["registry-ptfe-g25-acme"],
            }
        )
    )

    rfq_dispatch = project_dispatch_intent_from_rfq_send_payload(
        result.rfq_send_payload,
        projection="rfq_dispatch",
        recipient_selection={
            "selection_status": "selected_recipient",
            "selected_recipient_refs": [{"manufacturer_name": "Acme", "qualified_for_rfq": True}],
            "candidate_recipient_refs": [{"manufacturer_name": "Acme", "qualified_for_rfq": True}],
        },
        handover_status="releasable",
        dispatch_open_points=["temperature_confirmation"],
    )

    assert rfq_dispatch is not None
    assert rfq_dispatch["object_type"] == "rfq_dispatch"
    assert rfq_dispatch["dispatch_ready"] is True
    assert rfq_dispatch["recipient_selection"]["selection_status"] == "selected_recipient"
    assert rfq_dispatch["dispatch_open_points"] == ["temperature_confirmation"]
