import pytest

from app.agent.material_core import (
    PROMOTED_SOURCE_ORIGIN,
    TRANSITION_SOURCE_ORIGIN,
    PromotedCandidateRegistryRecordDTO,
    build_material_provider_contract_snapshot,
    classify_material_candidate_sources,
    evaluate_material_qualification_core,
    load_promoted_candidate_registry_records,
    resolve_candidate_registry_records_for_material_case,
    resolve_promoted_candidate_records_for_material_case,
)


_CANDIDATE = [{"candidate_id": "ptfe::g25::acme", "material_family": "PTFE", "grade_name": "G25", "manufacturer_name": "Acme", "candidate_kind": "manufacturer_grade", "evidence_refs": []}]
_FACT_CARD = {"evidence_id": "fc-1", "metadata": {"material_family": "PTFE", "grade_name": "G25", "manufacturer_name": "Acme"}}


def test_registry_authority_default_is_demo_only():
    assert PromotedCandidateRegistryRecordDTO(registry_record_id="r1", material_family="PTFE").registry_authority == "demo_only"


def test_unknown_registry_authority_is_rejected():
    with pytest.raises(ValueError):
        PromotedCandidateRegistryRecordDTO(registry_record_id="r1", material_family="PTFE", registry_authority="bad")


def test_registry_json_entry_has_demo_only_authority():
    assert load_promoted_candidate_registry_records()[0].registry_authority == "demo_only"


def test_demo_only_entry_not_resolved_as_promoted_trust_anchor():
    assert resolve_promoted_candidate_records_for_material_case(_CANDIDATE) == {}


def test_demo_only_entry_still_loads_for_auditability():
    resolved = resolve_candidate_registry_records_for_material_case(_CANDIDATE)
    assert resolved["ptfe::g25::acme"].registry_authority == "demo_only"


def test_demo_only_candidate_gets_transition_source_origin():
    assessment = classify_material_candidate_sources(candidates=_CANDIDATE, relevant_fact_cards=[])[0]
    assert assessment.source_origin == TRANSITION_SOURCE_ORIGIN
    assert assessment.qualified_eligible is False


def test_material_core_output_is_exploratory_with_demo_only_registry():
    core_output = evaluate_material_qualification_core(relevant_fact_cards=[_FACT_CARD], asserted_state={}, governance_state={})
    assert core_output.has_promoted_candidate_source is False
    assert core_output.qualification_status == "exploratory_candidate_source_only"
    assert core_output.output_blocked is True


def test_provider_contract_snapshot_excludes_demo_only_from_promoted_matches():
    snapshot = build_material_provider_contract_snapshot(candidates=_CANDIDATE)
    assert snapshot["matched_promoted_registry_record_ids"] == []
    assert snapshot["registry_records"][0]["registry_authority"] == "demo_only"
