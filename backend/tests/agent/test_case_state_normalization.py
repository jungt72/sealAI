import pytest

import app.agent.case_state as case_state_module
from app.agent.case_state import _infer_unit, _normalize_snapshot_value, build_case_state
from app.agent.domain.manufacturer_rfq import ManufacturerRfqSpecialistResult


@pytest.mark.parametrize("key,expected", [("pressure", "bar"), ("temperature_f", "F"), ("speed", "rpm"), ("unknown", None)])
def test_infer_unit(key, expected):
    assert _infer_unit(key) == expected


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("material", "Viton", "Viton"),
        ("material", "Nitril", "NBR"),
        ("medium", "water", "Wasser"),
        ("medium", "Heißdampf", "Dampf"),
        ("temperature_f", 68.0, 20.0),
        ("pressure_psi", 145.0, 9.997402),
    ],
)
def test_normalize_snapshot_value(key, value, expected):
    result = _normalize_snapshot_value(value, key)
    if isinstance(expected, float):
        assert result == pytest.approx(expected, abs=0.1)
    else:
        assert result == expected


def test_build_case_state_exposes_canonical_target_buckets():
    state = {
        "working_profile": {"medium": "water"},
        "relevant_fact_cards": [{"id": "fc-1", "name": "PTFE guide"}],
        "sealing_state": {
            "observed": {
                "observed_inputs": [{"source": "user", "raw_text": "PTFE ring"}],
                "raw_parameters": {"temperature_raw": "120 C"},
            },
            "normalized": {
                "normalized_parameters": {"material": "PTFE", "temperature_c": 120},
                "identity_records": {"material": {"source": "normalizer", "confidence": "high"}},
            },
            "governance": {
                "release_status": "manufacturer_validation_required",
                "rfq_admissibility": "provisional",
                "scope_of_validity": ["Manufacturer validation required."],
            },
            "selection": {
                "selection_status": "shortlisted",
                "selected_partner_id": "partner-1",
                "winner_candidate_id": "ptfe::g25::acme",
                "viable_candidate_ids": ["ptfe::g25::acme"],
                "blocked_candidates": [],
                "recommendation_artifact": {
                    "candidate_projection": {
                        "candidate_id": "ptfe::g25::acme",
                        "candidate_kind": "manufacturer_grade",
                        "material_family": "PTFE",
                        "grade_name": "G25",
                        "manufacturer_name": "Acme",
                        "evidence_refs": ["fc-1"],
                    }
                },
            },
            "handover": {
                "rfq_confirmed": False,
                "handover_completed": True,
                "rfq_html_report": "<html>rfq</html>",
            },
            "review": {"review_required": True, "review_state": "pending"},
            "cycle": {"analysis_cycle_id": "cycle-2", "state_revision": 3, "phase": "final"},
        },
    }

    case_state = build_case_state(
        state,
        session_id="case-1",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
    )

    assert case_state["case_meta"]["phase"] == "final"
    assert case_state["observed_inputs"]["raw_parameters"]["temperature_raw"] == "120 C"
    assert case_state["normalized_parameters"]["material"] == "PTFE"
    assert case_state["parameter_meta"]["material"]["source"] == "normalizer"
    assert case_state["derived_engineering_values"] == {}
    assert case_state["evidence_state"]["evidence_ref_count"] == 1
    assert case_state["governance_state"]["required_disclaimers"] == ["Manufacturer validation required."]
    assert case_state["matching_state"]["selection_status"] == "shortlisted"
    assert case_state["matching_state"]["matchable"] is False
    assert case_state["matching_state"]["matchability_status"] == "blocked_review_required"
    assert case_state["matching_state"]["blocking_reasons"] == ["review_required", "output_blocked"]
    assert case_state["matching_state"]["recommendation_identity"]["candidate_id"] == "ptfe::g25::acme"
    assert case_state["requirement_class"]["object_type"] == "requirement_class"
    assert case_state["requirement_class"]["requirement_class_id"] == "family::PTFE"
    assert case_state["requirement_class"]["derivation_basis"] == "family"
    assert case_state["requirement_class"]["material_family"] == "PTFE"
    assert case_state["matching_state"]["requirement_class_hint"] == "family::PTFE"
    assert case_state["matching_state"]["requirement_class"]["requirement_class_id"] == "family::PTFE"
    assert case_state["matching_state"]["manufacturer_validation_required"] is True
    assert case_state["matching_state"]["review_required"] is True
    assert case_state["matching_state"]["candidate_summary"]["winner_candidate_id"] == "ptfe::g25::acme"
    assert case_state["matching_state"]["match_candidates"][0]["candidate_id"] == "ptfe::g25::acme"
    assert case_state["matching_state"]["matching_basis_summary"]["evidence_ref_count"] == 1
    assert case_state["matching_state"]["matching_outcome"] is None
    assert case_state["rfq_state"]["rfq_admissibility"] == "provisional"
    assert case_state["rfq_state"]["rfq_confirmed"] is False
    assert case_state["rfq_state"]["rfq_handover_initiated"] is True
    assert case_state["rfq_state"]["rfq_html_report_present"] is True
    assert case_state["rfq_state"]["status"] == "provisional"
    assert case_state["rfq_state"]["blocking_reasons"] == [
        "review_required",
        "critical_review_missing",
        "manufacturer_validation_required",
        "rfq_admissibility_provisional",
        "handover_not_ready",
    ]
    assert case_state["rfq_state"]["open_points"] == ["manufacturer_validation_required", "review_required"]
    assert case_state["rfq_state"]["readiness_basis_summary"]["matchable"] is False
    assert case_state["rfq_state"]["recommendation_identity"]["candidate_id"] == "ptfe::g25::acme"
    assert case_state["rfq_state"]["requirement_class_hint"] == "family::PTFE"
    assert case_state["rfq_state"]["requirement_class"]["requirement_class_id"] == "family::PTFE"
    assert case_state["rfq_state"]["rfq_object"]["requirement_class"]["requirement_class_id"] == "family::PTFE"
    assert case_state["rfq_state"]["rfq_object"]["payload_present"] is False
    assert case_state["recipient_selection"]["object_type"] == "recipient_selection"
    assert case_state["recipient_selection"]["selected_partner_id"] == "partner-1"
    assert case_state["recipient_selection"]["selection_status"] == "candidate_pool_only"
    assert case_state["recipient_selection"]["recipient_selection_ready"] is False
    assert case_state["recipient_selection"]["selected_recipient_refs"] == []
    assert case_state["recipient_selection"]["candidate_recipient_refs"][0]["manufacturer_name"] == "Acme"
    assert case_state["rfq_state"]["recipient_selection"]["selection_status"] == "candidate_pool_only"
    assert case_state["rfq_state"]["rfq_dispatch"]["object_type"] == "rfq_dispatch"
    assert case_state["rfq_state"]["rfq_dispatch"]["dispatch_ready"] is False
    assert case_state["rfq_state"]["rfq_dispatch"]["dispatch_status"] == "not_ready_dispatch_blocked"
    assert case_state["rfq_state"]["rfq_dispatch"]["dispatch_blockers"] == [
        "review_required",
        "critical_review_missing",
        "manufacturer_validation_required",
        "rfq_admissibility_provisional",
        "handover_not_ready",
    ]
    assert case_state["rfq_state"]["rfq_dispatch"]["recipient_basis_summary"]["recipient_count"] == 1
    assert case_state["rfq_state"]["rfq_dispatch"]["recipient_basis_summary"]["selected_recipient_count"] == 0
    assert case_state["rfq_state"]["rfq_dispatch"]["recipient_basis_summary"]["has_selected_manufacturer_ref"] is False
    assert case_state["rfq_state"]["rfq_dispatch"]["recipient_refs"][0]["manufacturer_name"] == "Acme"
    assert case_state["rfq_state"]["rfq_dispatch"]["recipient_selection"]["selection_status"] == "candidate_pool_only"
    assert case_state["rfq_state"]["rfq_dispatch"]["rfq_object_basis"]["payload_present"] is False
    assert case_state["manufacturer_state"]["manufacturer_specific"] is True
    assert case_state["manufacturer_state"]["manufacturer_specificity_status"] == "manufacturer_specific"
    assert case_state["manufacturer_state"]["manufacturer_refs"][0]["manufacturer_name"] == "Acme"
    assert case_state["manufacturer_state"]["manufacturer_refs"][0]["capability_hints"] == ["manufacturer_grade_candidate"]
    assert case_state["manufacturer_state"]["manufacturer_capabilities"][0]["object_type"] == "manufacturer_capability"
    assert case_state["manufacturer_state"]["manufacturer_capabilities"][0]["manufacturer_name"] == "Acme"
    assert case_state["manufacturer_state"]["manufacturer_capabilities"][0]["requirement_class_ids"] == ["family::PTFE"]
    assert case_state["manufacturer_state"]["manufacturer_capabilities"][0]["candidate_kinds"] == ["manufacturer_grade"]
    assert case_state["manufacturer_state"]["manufacturer_capabilities"][0]["evidence_refs"] == ["fc-1"]
    assert case_state["manufacturer_state"]["requirement_class_hint"] == "family::PTFE"
    assert case_state["manufacturer_state"]["requirement_class"]["requirement_class_id"] == "family::PTFE"
    assert case_state["result_contract"]["required_disclaimers"] == ["Manufacturer validation required."]
    assert case_state["result_contract"]["recommendation_identity"]["candidate_id"] == "ptfe::g25::acme"
    assert case_state["result_contract"]["requirement_class_hint"] == "family::PTFE"
    assert case_state["result_contract"]["requirement_class"]["requirement_class_id"] == "family::PTFE"
    assert case_state["sealing_requirement_spec"]["requirement_class_hint"] == "family::PTFE"
    assert case_state["sealing_requirement_spec"]["requirement_class"]["requirement_class_id"] == "family::PTFE"
    assert case_state["sealing_requirement_spec"]["recommendation_identity"]["material_family"] == "PTFE"


def test_build_case_state_prefers_governance_requirement_class_over_legacy_hint_projection():
    state = {
        "sealing_state": {
            "governance": {
                "release_status": "manufacturer_validation_required",
                "rfq_admissibility": "provisional",
                "specificity_level": "family_only",
                "requirement_class": {
                    "class_id": "PTFE10",
                    "description": "PTFE steam sealing class for elevated thermal load.",
                    "seal_type": "gasket",
                },
            },
            "selection": {
                "selection_status": "shortlisted",
                "winner_candidate_id": "ptfe::g25::acme",
                "viable_candidate_ids": ["ptfe::g25::acme"],
                "blocked_candidates": [],
                "recommendation_artifact": {
                    "candidate_projection": {
                        "candidate_id": "ptfe::g25::acme",
                        "candidate_kind": "manufacturer_grade",
                        "material_family": "PTFE",
                        "grade_name": "G25",
                        "manufacturer_name": "Acme",
                    }
                },
            },
            "cycle": {"analysis_cycle_id": "cycle-2", "state_revision": 3, "phase": "final"},
        },
    }

    case_state = build_case_state(
        state,
        session_id="case-governed-rc",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
    )

    assert case_state["requirement_class"]["requirement_class_id"] == "PTFE10"
    assert case_state["requirement_class"]["description"] == "PTFE steam sealing class for elevated thermal load."
    assert case_state["requirement_class"]["seal_type"] == "gasket"
    assert case_state["matching_state"]["requirement_class"]["requirement_class_id"] == "PTFE10"
    assert case_state["rfq_state"]["requirement_class"]["requirement_class_id"] == "PTFE10"
    assert case_state["manufacturer_state"]["requirement_class"]["requirement_class_id"] == "PTFE10"


def test_build_case_state_aligns_rfq_basis_projection_with_specialist_adapter(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        case_state_module,
        "run_manufacturer_rfq_specialist",
        lambda *_, **__: ManufacturerRfqSpecialistResult(
            manufacturer_match_result=None,
            rfq_basis={
                "rfq_object": {
                    "object_type": "rfq_payload_basis",
                    "object_version": "rfq_payload_basis_v1",
                    "qualified_material_ids": ["bounded::candidate"],
                    "qualified_materials": [{"candidate_id": "bounded::candidate", "manufacturer_name": "BoundedCo"}],
                    "confirmed_parameters": {"medium": "BoundedMedium"},
                    "dimensions": {"shaft_diameter_mm": 33.0},
                    "target_system": "rfq_portal",
                },
                "handover_payload": {
                    "qualified_material_ids": ["bounded::candidate"],
                    "qualified_materials": [{"candidate_id": "bounded::candidate", "manufacturer_name": "BoundedCo"}],
                    "confirmed_parameters": {"medium": "BoundedMedium"},
                    "dimensions": {"shaft_diameter_mm": 33.0},
                },
                "target_system": "rfq_portal",
            },
            rfq_send_payload={
                "object_type": "rfq_send_payload",
                "object_version": "rfq_send_payload_v1",
                "send_ready": True,
                "blocking_reasons": [],
                "recipient_refs": [{"manufacturer_name": "BoundedCo", "qualified_for_rfq": True}],
                "selected_manufacturer_ref": {"manufacturer_name": "BoundedCo"},
                "requirement_class": {"requirement_class_id": "PTFE10"},
                "handover_payload": {"qualified_material_ids": ["bounded::candidate"]},
            },
        ),
    )

    state = {
        "sealing_state": {
            "governance": {
                "release_status": "rfq_ready",
                "rfq_admissibility": "ready",
                "specificity_level": "compound_required",
                "critical_review_passed": True,
                "critical_review_status": "passed",
                "requirement_class": {
                    "class_id": "PTFE10",
                    "description": "PTFE steam sealing class",
                    "seal_type": "gasket",
                },
            },
            "selection": {
                "selection_status": "shortlisted",
                "winner_candidate_id": "bounded::candidate",
                "viable_candidate_ids": ["bounded::candidate"],
                "blocked_candidates": [],
                "recommendation_artifact": {
                    "candidate_projection": {
                        "candidate_id": "bounded::candidate",
                        "candidate_kind": "manufacturer_grade",
                        "material_family": "PTFE",
                        "grade_name": "G25",
                        "manufacturer_name": "BoundedCo",
                    }
                },
            },
            "handover": {
                "handover_payload": {
                    "qualified_material_ids": ["legacy::candidate"],
                    "qualified_materials": [{"candidate_id": "legacy::candidate"}],
                    "confirmed_parameters": {"medium": "LegacyMedium"},
                    "dimensions": {"shaft_diameter_mm": 21.0},
                },
                "target_system": "rfq_portal",
            },
        },
    }

    case_state = build_case_state(
        state,
        session_id="case-rfq-basis",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
    )

    assert case_state["rfq_state"]["rfq_object"]["qualified_material_ids"] == ["bounded::candidate"]
    assert case_state["rfq_state"]["rfq_object"]["confirmed_parameters"] == {"medium": "BoundedMedium"}
    assert case_state["rfq_state"]["rfq_object"]["dimensions"] == {"shaft_diameter_mm": 33.0}
    assert case_state["rfq_state"]["rfq_send_payload"]["object_type"] == "rfq_send_payload"
    assert case_state["rfq_state"]["rfq_dispatch"]["dispatch_ready"] is True
    assert case_state["rfq_state"]["rfq_dispatch"]["dispatch_status"] == "dispatch_ready"
    assert case_state["rfq_state"]["rfq_dispatch"]["recipient_refs"][0]["manufacturer_name"] == "BoundedCo"


def test_build_case_state_aligns_blocked_dispatch_projection_with_send_payload(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        case_state_module,
        "run_manufacturer_rfq_specialist",
        lambda *_, **__: ManufacturerRfqSpecialistResult(
            manufacturer_match_result=None,
            rfq_basis={
                "rfq_object": {
                    "object_type": "rfq_payload_basis",
                    "object_version": "rfq_payload_basis_v1",
                    "qualified_material_ids": ["bounded::candidate"],
                },
                "handover_payload": {
                    "qualified_material_ids": ["bounded::candidate"],
                },
            },
            rfq_send_payload={
                "object_type": "rfq_send_payload",
                "object_version": "rfq_send_payload_v1",
                "send_ready": False,
                "blocking_reasons": ["review_required", "no_recipient_refs"],
                "recipient_refs": [],
                "selected_manufacturer_ref": None,
                "requirement_class": {"requirement_class_id": "PTFE10"},
                "handover_payload": {"qualified_material_ids": ["bounded::candidate"]},
            },
        ),
    )

    state = {
        "sealing_state": {
            "governance": {
                "release_status": "rfq_ready",
                "rfq_admissibility": "ready",
                "specificity_level": "compound_required",
                "critical_review_passed": True,
                "critical_review_status": "passed",
                "review_required": True,
                "requirement_class": {
                    "class_id": "PTFE10",
                    "description": "PTFE steam sealing class",
                    "seal_type": "gasket",
                },
            },
            "selection": {
                "selection_status": "shortlisted",
                "winner_candidate_id": "bounded::candidate",
                "viable_candidate_ids": ["bounded::candidate"],
                "blocked_candidates": [],
            },
            "handover": {
                "handover_payload": {
                    "qualified_material_ids": ["legacy::candidate"],
                },
                "target_system": "rfq_portal",
            },
        },
    }

    case_state = build_case_state(
        state,
        session_id="case-rfq-dispatch-blocked",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
    )

    assert case_state["rfq_state"]["rfq_dispatch"]["dispatch_ready"] is False
    assert case_state["rfq_state"]["rfq_dispatch"]["dispatch_status"] == "not_ready_no_recipients"
    assert case_state["rfq_state"]["rfq_dispatch"]["dispatch_blockers"] == ["review_required", "no_recipient_refs"]
    assert case_state["rfq_state"]["rfq_send_payload"]["blocking_reasons"] == ["review_required", "no_recipient_refs"]


def test_build_case_state_narrows_recipient_selection_with_capability_candidate_link():
    state = {
        "sealing_state": {
            "governance": {
                "release_status": "manufacturer_validation_required",
                "rfq_admissibility": "provisional",
                "specificity_level": "compound_required",
            },
            "selection": {
                "selection_status": "shortlisted",
                "winner_candidate_id": "ptfe::g25::acme",
                "viable_candidate_ids": ["ptfe::g25::acme", "ptfe::b99::beta"],
                "blocked_candidates": [],
                "output_blocked": False,
                "candidates": [
                    {
                        "candidate_id": "ptfe::g25::acme",
                        "candidate_kind": "manufacturer_grade",
                        "material_family": "PTFE",
                        "grade_name": "G25",
                        "manufacturer_name": "Acme",
                        "evidence_refs": ["fc-1"],
                    },
                    {
                        "candidate_id": "ptfe::b99::beta",
                        "candidate_kind": "manufacturer_grade",
                        "material_family": "PTFE",
                        "grade_name": "B99",
                        "manufacturer_name": "Beta",
                        "evidence_refs": ["fc-2"],
                    },
                ],
                "recommendation_artifact": {
                    "candidate_projection": {
                        "candidate_id": "ptfe::g25::acme",
                        "candidate_kind": "manufacturer_grade",
                        "material_family": "PTFE",
                        "grade_name": "G25",
                        "manufacturer_name": "Acme",
                    }
                },
            },
            "review": {"review_required": False, "review_state": "approved"},
            "cycle": {"analysis_cycle_id": "cycle-3", "state_revision": 4},
        }
    }

    case_state = build_case_state(
        state,
        session_id="case-2",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
    )

    assert len(case_state["manufacturer_state"]["manufacturer_capabilities"]) == 2
    assert case_state["recipient_selection"]["selection_status"] == "candidate_pool_only"
    assert case_state["recipient_selection"]["candidate_recipient_refs"] == [
        {
            "manufacturer_name": "Acme",
            "candidate_ids": ["ptfe::g25::acme"],
            "material_families": ["PTFE"],
            "grade_names": ["G25"],
            "candidate_kinds": ["manufacturer_grade"],
            "capability_hints": ["manufacturer_grade_candidate"],
            "source_refs": ["recommendation_identity", "match_candidate"],
            "qualified_for_rfq": False,
        }
    ]
    assert case_state["recipient_selection"]["selected_recipient_refs"] == []
    assert case_state["recipient_selection"]["non_selected_recipient_refs"] == [
        {
            "manufacturer_name": "Acme",
            "candidate_ids": ["ptfe::g25::acme"],
            "material_families": ["PTFE"],
            "grade_names": ["G25"],
            "candidate_kinds": ["manufacturer_grade"],
            "capability_hints": ["manufacturer_grade_candidate"],
            "source_refs": ["recommendation_identity", "match_candidate"],
            "qualified_for_rfq": False,
        }
    ]
    assert case_state["recipient_selection"]["selection_basis_summary"]["capability_qualified_candidate_count"] == 1
    assert case_state["recipient_selection"]["selection_basis_summary"]["capability_recommendation_candidate_id"] == "ptfe::g25::acme"
    assert case_state["rfq_state"]["rfq_dispatch"]["recipient_refs"][0]["manufacturer_name"] == "Acme"


def test_build_case_state_carries_full_concurrency_token_in_case_meta():
    case_state = build_case_state(
        {
            "sealing_state": {
                "cycle": {
                    "analysis_cycle_id": "cycle-9",
                    "state_revision": 12,
                    "snapshot_parent_revision": 11,
                }
            }
        },
        session_id="case-9",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
    )

    assert case_state["case_meta"]["analysis_cycle_id"] == "cycle-9"
    assert case_state["case_meta"]["state_revision"] == 12
    assert case_state["case_meta"]["snapshot_parent_revision"] == 11
