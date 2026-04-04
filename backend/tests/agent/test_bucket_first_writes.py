from app.agent.agent.graph import evidence_tool_node
from app.agent.agent.state import AgentState, SealingAIState
from app.agent.evidence.models import ClaimType
from langchain_core.messages import AIMessage
from unittest.mock import patch


def _base_sealing_state(*, revision: int = 5) -> SealingAIState:
    return {
        "observed": {"observed_inputs": [], "raw_parameters": {}},
        "normalized": {"identity_records": {}, "normalized_parameters": {}},
        "asserted": {
            "medium_profile": {"name": "Wasser"},
            "machine_profile": {},
            "installation_profile": {},
            "operating_conditions": {},
            "sealing_requirement_spec": {},
        },
        "governance": {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "family_only",
            "scope_of_validity": [],
            "assumptions_active": [],
            "gate_failures": [],
            "unknowns_release_blocking": [],
            "unknowns_manufacturer_validation": [],
            "conflicts": [],
        },
        "cycle": {
            "analysis_cycle_id": "c1",
            "snapshot_parent_revision": 0,
            "contract_obsolete": False,
            "contract_obsolete_reason": None,
            "superseded_by_cycle": None,
            "state_revision": revision,
        },
        "selection": {
            "selection_status": "not_started",
            "candidates": [],
            "viable_candidate_ids": [],
            "blocked_candidates": [],
            "winner_candidate_id": None,
            "recommendation_artifact": None,
            "candidate_clusters": [],
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "output_blocked": True,
        },
    }


def test_submit_claim_updates_canonical_case_state_buckets():
    tool_call = {
        "name": "submit_claim",
        "args": {
            "claim_type": ClaimType.FACT_OBSERVED,
            "statement": "Der Kunde sagt, das Medium ist Öl.",
            "confidence": 1.0,
            "source_fact_ids": ["input_2"],
        },
        "id": "call_submit_1",
    }
    state: AgentState = {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "sealing_state": _base_sealing_state(),
        "working_profile": {},
    }

    result = evidence_tool_node(state)

    assert result["sealing_state"]["cycle"]["state_revision"] == 6
    assert result["case_state"]["case_meta"]["state_revision"] == 6
    assert result["case_state"]["case_meta"]["snapshot_parent_revision"] == 5
    assert result["case_state"]["case_meta"]["analysis_cycle_id"] == "c1"
    assert result["case_state"]["case_meta"]["version"] == 6
    assert result["case_state"]["parameter_meta"]["medium"]["mapping_reason"].startswith("normalized_medium")
    assert result["case_state"]["governance_state"]["release_status"] == "inadmissible"
    assert result["case_state"]["evidence_state"]["evidence_ref_count"] == 0


def test_submit_claim_ignores_direct_validated_param_shortcut_and_derives_from_observed_claim():
    tool_call = {
        "name": "submit_claim",
        "args": {
            "claim_type": ClaimType.FACT_OBSERVED,
            "statement": "Temperatur ist 120 C.",
            "confidence": 1.0,
            "source_fact_ids": [],
        },
        "id": "call_submit_temp_1",
    }
    state: AgentState = {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "sealing_state": _base_sealing_state(),
        "working_profile": {},
    }

    with patch(
        "app.agent.agent.graph.evaluate_claim_conflicts",
        return_value=([], {"temperature": 999.0}),
    ):
        result = evidence_tool_node(state)

    observed_inputs = result["sealing_state"]["observed"]["observed_inputs"]
    assert observed_inputs[-1]["raw_text"] == "Temperatur ist 120 C."
    assert result["sealing_state"]["normalized"]["normalized_parameters"]["temperature_c"] == 120.0
    assert result["sealing_state"]["asserted"]["operating_conditions"]["temperature"] == 120.0
    assert result["case_state"]["normalized_parameters"]["temperature_c"] == 120.0


def test_rwdr_tool_results_are_preserved_in_canonical_derived_bucket():
    tool_call = {
        "name": "calculate_rwdr_specifications",
        "args": {
            "shaft_diameter_mm": 50.0,
            "rpm": 1500.0,
            "pressure_bar": 5.0,
            "elastomer_material": "NBR",
        },
        "id": "call_rwdr_1",
    }
    state: AgentState = {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "sealing_state": _base_sealing_state(),
        "working_profile": {},
    }

    result = evidence_tool_node(state)

    observed_runs = result["sealing_state"]["observed"]["raw_parameters"]["rwdr_tool_runs"]
    assert len(observed_runs) == 1
    assert observed_runs[0]["inputs"]["shaft_diameter_mm"] == 50.0
    rwdr_runs = result["case_state"]["derived_engineering_values"]["rwdr_tool_runs"]
    assert len(rwdr_runs) == 1
    assert rwdr_runs[0]["inputs"]["shaft_diameter_mm"] == 50.0
    assert rwdr_runs[0]["result"]["status"] in {"ok", "warning", "critical", "insufficient_data"}
    assert rwdr_runs == observed_runs
    assert result["case_state"]["derived_calculations"]["rwdr_tool_runs"] == rwdr_runs


def test_rwdr_conflict_path_aligns_case_meta_token_same_step():
    tool_call = {
        "name": "calculate_rwdr_specifications",
        "args": {
            "shaft_diameter_mm": 50.0,
            "rpm": 1500.0,
            "pressure_bar": 5.0,
            "elastomer_material": "NBR",
        },
        "id": "call_rwdr_conflict_1",
    }
    state: AgentState = {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "sealing_state": _base_sealing_state(),
        "working_profile": {},
        "case_state": {
            "case_meta": {
                "state_revision": 5,
                "snapshot_parent_revision": 0,
                "analysis_cycle_id": "c1",
                "version": 5,
            }
        },
    }

    with patch("app.agent.services.compound.validate_claim_against_matrix", return_value=[{"type": "DOMAIN_LIMIT_VIOLATION", "message": "blocked", "claim_statement": "rwdr"}]):
        result = evidence_tool_node(state)

    assert result["sealing_state"]["cycle"]["state_revision"] == 6
    assert result["case_state"]["case_meta"]["state_revision"] == 6
    assert result["case_state"]["case_meta"]["snapshot_parent_revision"] == 5
    assert result["case_state"]["case_meta"]["analysis_cycle_id"] == "c1"
    assert result["case_state"]["case_meta"]["version"] == 6
