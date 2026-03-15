from __future__ import annotations

from app.agent.case_state import build_case_state
from app.agent.material_core import (
    build_material_provider_contract_snapshot,
    build_material_candidate_source_adapter,
    classify_material_candidate_sources,
    evaluate_material_qualification_core,
    load_promoted_candidate_registry_records,
    resolve_candidate_registry_records_for_material_case,
    resolve_promoted_candidate_records_for_material_case,
)


def _material_candidate() -> list[dict]:
    return [
        {
            "candidate_id": "ptfe",
            "candidate_kind": "family",
            "material_family": "PTFE",
            "evidence_refs": ["fc-1"],
        }
    ]


def _material_fact_cards() -> list[dict]:
    return [
        {
            "id": "fc-1",
            "evidence_id": "fc-1",
            "topic": "PTFE datasheet",
            "content": "PTFE has a temperature limit up to 260 C and a maximum pressure of 50 bar.",
            "source_ref": "datasheet-ptfe-1",
            "metadata": {
                "material_family": "PTFE",
                "temperature_min_c": -20,
                "temperature_max_c": 260,
                "pressure_max_bar": 50,
            },
        }
    ]


def _qualified_material_candidate() -> list[dict]:
    return [
        {
            "candidate_id": "ptfe::g25::acme",
            "candidate_kind": "manufacturer_grade",
            "material_family": "PTFE",
            "grade_name": "G25",
            "manufacturer_name": "Acme",
            "evidence_refs": ["fc-qualified-1"],
        }
    ]


def _qualified_material_fact_cards() -> list[dict]:
    return [
        {
            "id": "fc-qualified-1",
            "evidence_id": "fc-qualified-1",
            "topic": "PTFE G25 Acme datasheet",
            "content": "PTFE grade G25 from Acme has a temperature limit up to 260 C and a maximum pressure of 50 bar.",
            "source_ref": "datasheet-acme-g25",
            "source_type": "manufacturer_datasheet",
            "source_rank": 1,
            "metadata": {
                "material_family": "PTFE",
                "grade_name": "G25",
                "manufacturer_name": "Acme",
                "temperature_min_c": -20,
                "temperature_max_c": 260,
                "pressure_max_bar": 50,
            },
        }
    ]


def _transition_manufacturer_grade_candidate() -> list[dict]:
    return [
        {
            "candidate_id": "ptfe::g99::othercorp",
            "candidate_kind": "manufacturer_grade",
            "material_family": "PTFE",
            "grade_name": "G99",
            "manufacturer_name": "OtherCorp",
            "evidence_refs": ["fc-transition-1"],
        }
    ]


def _transition_manufacturer_grade_fact_cards() -> list[dict]:
    return [
        {
            "id": "fc-transition-1",
            "evidence_id": "fc-transition-1",
            "topic": "PTFE G99 OtherCorp datasheet",
            "content": "PTFE grade G99 from OtherCorp has a temperature limit up to 260 C and a maximum pressure of 50 bar.",
            "source_ref": "datasheet-othercorp-g99",
            "source_type": "manufacturer_datasheet",
            "source_rank": 1,
            "metadata": {
                "material_family": "PTFE",
                "grade_name": "G99",
                "manufacturer_name": "OtherCorp",
                "temperature_min_c": -20,
                "temperature_max_c": 260,
                "pressure_max_bar": 50,
            },
        }
    ]


def test_deterministic_material_qualification_core_outputs():
    result = evaluate_material_qualification_core(
        candidates=_material_candidate(),
        relevant_fact_cards=_material_fact_cards(),
        asserted_state={"operating_conditions": {"temperature": 80.0, "pressure": 10.0}},
        governance_state={
            "release_status": "manufacturer_validation_required",
            "rfq_admissibility": "provisional",
            "specificity_level": "subfamily",
            "conflicts": [],
        },
    )

    assert result.qualification_status == "exploratory_candidate_source_only"
    assert result.output_blocked is True
    assert result.viable_candidate_ids == ["ptfe"]
    assert result.qualified_viable_candidate_ids == []
    assert result.exploratory_candidate_ids == ["ptfe"]
    assert result.candidate_assessments[0].candidate_source_class == "exploratory_candidate_input"
    assert "candidate_source_boundary_requires_manufacturer_grade" in result.open_points


def test_candidate_source_boundary_classifies_candidates_deterministically():
    exploratory = classify_material_candidate_sources(
        candidates=[],
        relevant_fact_cards=[],
    )
    assert exploratory == []

    family_result = classify_material_candidate_sources(
        candidates=[candidate for candidate in _material_candidate()],
        relevant_fact_cards=_material_fact_cards(),
    )
    assert family_result[0].candidate_source_class == "exploratory_candidate_input"
    assert family_result[0].qualified_eligible is False
    assert "candidate_specificity_below_qualified_boundary" in family_result[0].source_gate_reasons

    qualified_result = classify_material_candidate_sources(
        candidates=[candidate for candidate in _transition_manufacturer_grade_candidate()],
        relevant_fact_cards=_transition_manufacturer_grade_fact_cards(),
    )
    assert qualified_result[0].candidate_source_class == "exploratory_candidate_input"
    assert qualified_result[0].source_origin == "retrieval_fact_card_transition_adapter"
    assert qualified_result[0].qualified_eligible is False
    assert "candidate_source_not_promoted_registry" in qualified_result[0].source_gate_reasons

    promoted_result = classify_material_candidate_sources(
        candidates=[candidate for candidate in _qualified_material_candidate()],
        relevant_fact_cards=_qualified_material_fact_cards(),
    )
    assert promoted_result[0].candidate_source_class == "qualified_candidate_input"
    assert promoted_result[0].source_origin == "promoted_candidate_registry_v1"
    assert promoted_result[0].qualified_eligible is True


def test_adapter_builds_deterministic_candidate_source_records_from_current_inputs():
    adapter_output = build_material_candidate_source_adapter(
        relevant_fact_cards=_transition_manufacturer_grade_fact_cards(),
    )

    assert adapter_output.source_adapter == "material_candidate_source_adapter_v1"
    assert adapter_output.source_origin == "retrieval_fact_card_transition_adapter"
    assert len(adapter_output.candidate_source_records) == 1
    record = adapter_output.candidate_source_records[0]
    assert record.candidate_id == "ptfe::g99::othercorp"
    assert record.candidate_source_class == "exploratory_candidate_input"
    assert record.qualified_eligible is False
    assert record.authority_quality == "sufficient"
    assert record.evidence_quality == "qualified_identity"
    assert adapter_output.transition_candidate_records[0].candidate_id == "ptfe::g99::othercorp"
    assert adapter_output.qualified_candidate_records == []


def test_promoted_candidate_source_record_is_accepted_as_qualified_path_input():
    adapter_output = build_material_candidate_source_adapter(
        relevant_fact_cards=_qualified_material_fact_cards(),
    )

    assert adapter_output.source_origin == "promoted_candidate_registry_v1"
    assert adapter_output.source_adapter == "promoted_candidate_registry_provider_v1"
    record = adapter_output.candidate_source_records[0]
    assert record.source_origin == "promoted_candidate_registry_v1"
    assert record.registry_record_id == "registry-ptfe-g25-acme"
    assert record.qualified_eligible is True
    assert adapter_output.qualified_candidate_records[0].candidate_id == "ptfe::g25::acme"
    assert adapter_output.promoted_candidate_records[0].candidate_id == "ptfe::g25::acme"


def test_mixed_candidate_set_separates_transition_and_promoted_records_cleanly():
    adapter_output = build_material_candidate_source_adapter(
        relevant_fact_cards=_transition_manufacturer_grade_fact_cards() + _qualified_material_fact_cards(),
    )

    assert adapter_output.source_origin == "mixed_candidate_source_boundary_v1"
    assert set(adapter_output.source_origins) == {
        "retrieval_fact_card_transition_adapter",
        "promoted_candidate_registry_v1",
    }
    assert len(adapter_output.promoted_candidate_records) == 1
    assert len(adapter_output.transition_candidate_records) == 1


def test_no_silent_hard_qualification_on_insufficient_input():
    result = evaluate_material_qualification_core(
        candidates=_qualified_material_candidate(),
        relevant_fact_cards=_qualified_material_fact_cards(),
        asserted_state={"operating_conditions": {"pressure": 10.0}},
        governance_state={
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
            "conflicts": [],
        },
    )

    assert result.qualification_status == "insufficient_input"
    assert result.output_blocked is True
    assert "temperature_c" in result.missing_required_inputs
    assert result.release_status == "inadmissible"


def test_promoted_provider_records_load_from_governed_source():
    records = load_promoted_candidate_registry_records()

    assert records
    assert records[0].registry_record_id == "registry-ptfe-g25-acme"
    assert records[0].candidate_id == "ptfe::g25::acme"


def test_promoted_provider_resolution_matches_current_material_case():
    resolved = resolve_promoted_candidate_records_for_material_case(_qualified_material_candidate())

    assert "ptfe::g25::acme" in resolved
    assert resolved["ptfe::g25::acme"].registry_record_id == "registry-ptfe-g25-acme"


def test_provider_contract_snapshot_tracks_promoted_registry_provenance():
    snapshot = build_material_provider_contract_snapshot(
        relevant_fact_cards=_qualified_material_fact_cards(),
    )

    assert snapshot.provider_source_adapter == "promoted_candidate_registry_provider_v1"
    assert snapshot.matched_promoted_registry_record_ids == ["registry-ptfe-g25-acme"]
    assert snapshot.matched_promoted_candidate_ids == ["ptfe::g25::acme"]
    assert snapshot.has_promoted_registry_match is True


def test_provider_resolution_keeps_transition_only_candidates_out_of_promoted_registry():
    resolved = resolve_candidate_registry_records_for_material_case(_transition_manufacturer_grade_candidate())

    assert resolved == {}


def test_material_qualification_result_mapping_into_case_state():
    state = {
        "messages": [],
        "sealing_state": {
            "observed": {"raw_parameters": {}, "observed_inputs": []},
            "normalized": {"identity_records": {}, "normalized_parameters": {}},
            "asserted": {
                "medium_profile": {"name": "Wasser"},
                "machine_profile": {"material": "PTFE"},
                "installation_profile": {},
                "operating_conditions": {"temperature": 80.0, "pressure": 10.0},
                "sealing_requirement_spec": {},
            },
            "governance": {
                "release_status": "manufacturer_validation_required",
                "rfq_admissibility": "provisional",
                "specificity_level": "subfamily",
                "scope_of_validity": [],
                "assumptions_active": [],
                "gate_failures": [],
                "unknowns_release_blocking": [],
                "unknowns_manufacturer_validation": ["manufacturer_name_unconfirmed_for_compound"],
                "conflicts": [],
            },
            "cycle": {
                "analysis_cycle_id": "cycle-1",
                "state_revision": 1,
                "contract_obsolete": False,
                "contract_obsolete_reason": None,
            },
            "selection": {
                "selection_status": "winner_selected",
                "candidates": _material_candidate(),
                "viable_candidate_ids": ["ptfe"],
                "blocked_candidates": [],
                "winner_candidate_id": "ptfe",
                "recommendation_artifact": {},
                "release_status": "manufacturer_validation_required",
                "rfq_admissibility": "provisional",
                "specificity_level": "subfamily",
                "output_blocked": True,
            },
        },
        "working_profile": {
            "diameter": 50.0,
            "speed": 1500.0,
            "pressure": 10.0,
            "temperature": 80.0,
            "medium": "Wasser",
            "material": "PTFE",
        },
        "relevant_fact_cards": _material_fact_cards(),
    }

    case_state = build_case_state(
        state,
        session_id="case-material-1",
        runtime_path="structured_graph",
        binding_level="ORIENTATION",
    )

    material_core = case_state["qualification_results"]["material_core"]
    assert material_core["source_type"] == "material_core"
    assert material_core["status"] == "exploratory_candidate_source_only"
    assert material_core["details"]["viable_candidate_ids"] == ["ptfe"]
    assert material_core["details"]["qualified_viable_candidate_ids"] == []
    assert material_core["details"]["exploratory_candidate_ids"] == ["ptfe"]
    assert material_core["details"]["candidate_source_records"][0]["source_adapter"] == "material_candidate_source_adapter_v1"
    assert material_core["details"]["candidate_source_records"][0]["source_origin"] == "retrieval_fact_card_transition_adapter"


def test_case_state_exposes_promoted_vs_transition_origin_explicitly():
    state = {
        "messages": [],
        "sealing_state": {
            "observed": {"raw_parameters": {}, "observed_inputs": []},
            "normalized": {"identity_records": {}, "normalized_parameters": {}},
            "asserted": {
                "medium_profile": {"name": "Wasser"},
                "machine_profile": {"material": "PTFE"},
                "installation_profile": {},
                "operating_conditions": {"temperature": 80.0, "pressure": 10.0},
                "sealing_requirement_spec": {},
            },
            "governance": {
                "release_status": "rfq_ready",
                "rfq_admissibility": "ready",
                "specificity_level": "compound_required",
                "scope_of_validity": [],
                "assumptions_active": [],
                "gate_failures": [],
                "unknowns_release_blocking": [],
                "unknowns_manufacturer_validation": [],
                "conflicts": [],
            },
            "cycle": {
                "analysis_cycle_id": "cycle-2",
                "state_revision": 2,
                "contract_obsolete": False,
                "contract_obsolete_reason": None,
            },
            "selection": {
                "selection_status": "winner_selected",
                "candidates": _qualified_material_candidate(),
                "viable_candidate_ids": ["ptfe::g25::acme"],
                "qualified_candidate_ids": ["ptfe::g25::acme"],
                "promoted_candidate_ids": ["ptfe::g25::acme"],
                "transition_candidate_ids": [],
                "exploratory_candidate_ids": [],
                "blocked_candidates": [],
                "blocked_by_candidate_source": [],
                "winner_candidate_id": "ptfe::g25::acme",
                "recommendation_artifact": {},
                "release_status": "rfq_ready",
                "rfq_admissibility": "ready",
                "specificity_level": "compound_required",
                "output_blocked": False,
                "candidate_source_adapter": "promoted_candidate_registry_provider_v1",
                "candidate_source_origin": "promoted_candidate_registry_v1",
                "candidate_source_origins": ["promoted_candidate_registry_v1"],
                "candidate_source_records": build_material_candidate_source_adapter(
                    relevant_fact_cards=_qualified_material_fact_cards(),
                ).candidate_source_records,
            },
        },
        "working_profile": {
            "pressure": 10.0,
            "temperature": 80.0,
            "medium": "Wasser",
            "material": "PTFE",
        },
        "relevant_fact_cards": _qualified_material_fact_cards(),
    }

    case_state = build_case_state(
        state,
        session_id="case-material-promoted-1",
        runtime_path="structured_graph",
        binding_level="QUALIFIED_PRESELECTION",
    )

    material_core = case_state["qualification_results"]["material_core"]
    selection_projection = case_state["qualification_results"]["material_selection_projection"]
    assert material_core["details"]["has_promoted_candidate_source"] is True
    assert material_core["details"]["candidate_source_origins"] == ["promoted_candidate_registry_v1"]
    assert selection_projection["details"]["candidate_source_origin"] == "promoted_candidate_registry_v1"
    assert selection_projection["details"]["promoted_candidate_ids"] == ["ptfe::g25::acme"]
