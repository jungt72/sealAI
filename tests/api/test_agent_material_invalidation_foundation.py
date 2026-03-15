from __future__ import annotations

import anyio
from langchain_core.messages import AIMessage

from app.agent.api.models import ChatRequest
from app.agent.api.router import chat_endpoint
from app.agent.case_state import (
    build_case_state,
    get_material_input_snapshot_and_fingerprint,
    get_material_provider_snapshot_and_fingerprint,
)
from app.agent.cli import create_initial_state
from app.agent.material_core import PromotedCandidateRegistryRecordDTO


def _build_material_state(*, temperature: float, pressure: float, revision: int) -> dict:
    sealing_state = create_initial_state()
    sealing_state["asserted"]["medium_profile"] = {
        "name": "Wasser",
        "resistance_rating": "A",
    }
    sealing_state["asserted"]["machine_profile"] = {
        "material": "PTFE",
    }
    sealing_state["asserted"]["operating_conditions"] = {
        "temperature": temperature,
        "pressure": pressure,
    }
    sealing_state["normalized"]["identity_records"] = {
        "material_family": {
            "raw_value": "PTFE",
            "normalized_value": "PTFE",
            "identity_class": "identity_confirmed",
            "source_fact_ids": ["fc-1"],
        }
    }
    sealing_state["governance"].update(
        {
            "release_status": "manufacturer_validation_required",
            "rfq_admissibility": "provisional",
            "specificity_level": "subfamily",
            "gate_failures": [],
            "unknowns_release_blocking": [],
            "unknowns_manufacturer_validation": ["manufacturer_name_unconfirmed_for_compound"],
            "conflicts": [],
        }
    )
    sealing_state["selection"] = {
        "selection_status": "winner_selected",
        "candidates": [
            {
                "candidate_id": "ptfe",
                "candidate_kind": "family",
                "material_family": "PTFE",
                "evidence_refs": ["fc-1"],
                "viability_status": "viable",
                "block_reason": None,
            }
        ],
        "viable_candidate_ids": ["ptfe"],
        "blocked_candidates": [],
        "winner_candidate_id": "ptfe",
        "recommendation_artifact": {
            "selection_status": "winner_selected",
            "winner_candidate_id": "ptfe",
            "candidate_ids": ["ptfe"],
            "viable_candidate_ids": ["ptfe"],
            "blocked_candidates": [],
            "evidence_basis": ["fc-1"],
            "release_status": "manufacturer_validation_required",
            "rfq_admissibility": "provisional",
            "specificity_level": "subfamily",
            "output_blocked": True,
            "trace_provenance_refs": ["fc-1", f"cycle-{revision}"],
        },
        "release_status": "manufacturer_validation_required",
        "rfq_admissibility": "provisional",
        "specificity_level": "subfamily",
        "output_blocked": True,
    }
    sealing_state["cycle"].update(
        {
            "analysis_cycle_id": f"cycle-{revision}",
            "state_revision": revision,
            "contract_obsolete": False,
            "contract_obsolete_reason": None,
        }
    )
    return {
        "messages": [AIMessage(content=f"Structured reply rev {revision}")],
        "sealing_state": sealing_state,
        "working_profile": {
            "diameter": 50.0,
            "speed": 1500.0,
            "pressure": pressure,
            "temperature": temperature,
            "medium": "Wasser",
            "material": "PTFE",
            "v_m_s": 3.927,
            "pv_value": 39.27,
        },
        "relevant_fact_cards": [
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
        ],
    }


def _build_provider_material_state(*, revision: int) -> dict:
    sealing_state = create_initial_state()
    sealing_state["asserted"]["medium_profile"] = {
        "name": "Wasser",
        "resistance_rating": "A",
    }
    sealing_state["asserted"]["machine_profile"] = {
        "material": "PTFE",
    }
    sealing_state["asserted"]["operating_conditions"] = {
        "temperature": 120.0,
        "pressure": 10.0,
    }
    sealing_state["normalized"]["identity_records"] = {
        "material_family": {
            "raw_value": "PTFE",
            "normalized_value": "PTFE",
            "identity_class": "identity_confirmed",
            "source_fact_ids": ["fc-qualified-1"],
        },
        "grade_name": {
            "raw_value": "G25",
            "normalized_value": "G25",
            "identity_class": "identity_confirmed",
            "source_fact_ids": ["fc-qualified-1"],
        },
        "manufacturer_name": {
            "raw_value": "Acme",
            "normalized_value": "Acme",
            "identity_class": "identity_confirmed",
            "source_fact_ids": ["fc-qualified-1"],
        },
    }
    sealing_state["governance"].update(
        {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
            "gate_failures": [],
            "unknowns_release_blocking": [],
            "unknowns_manufacturer_validation": [],
            "conflicts": [],
        }
    )
    sealing_state["selection"] = {
        "selection_status": "winner_selected",
        "candidates": [
            {
                "candidate_id": "ptfe::g25::acme",
                "candidate_kind": "manufacturer_grade",
                "material_family": "PTFE",
                "grade_name": "G25",
                "manufacturer_name": "Acme",
                "evidence_refs": ["fc-qualified-1"],
                "viability_status": "viable",
                "block_reason": None,
            }
        ],
        "viable_candidate_ids": ["ptfe::g25::acme"],
        "qualified_candidate_ids": ["ptfe::g25::acme"],
        "exploratory_candidate_ids": [],
        "promoted_candidate_ids": ["ptfe::g25::acme"],
        "transition_candidate_ids": [],
        "blocked_candidates": [],
        "blocked_by_candidate_source": [],
        "winner_candidate_id": "ptfe::g25::acme",
        "candidate_source_adapter": "promoted_candidate_registry_provider_v1",
        "candidate_source_origin": "promoted_candidate_registry_v1",
        "candidate_source_origins": ["promoted_candidate_registry_v1"],
        "recommendation_artifact": {
            "selection_status": "winner_selected",
            "winner_candidate_id": "ptfe::g25::acme",
            "candidate_ids": ["ptfe::g25::acme"],
            "viable_candidate_ids": ["ptfe::g25::acme"],
            "blocked_candidates": [],
            "evidence_basis": ["fc-qualified-1"],
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
            "output_blocked": False,
            "trace_provenance_refs": ["fc-qualified-1", f"cycle-{revision}"],
        },
        "release_status": "rfq_ready",
        "rfq_admissibility": "ready",
        "specificity_level": "compound_required",
        "output_blocked": False,
    }
    sealing_state["cycle"].update(
        {
            "analysis_cycle_id": f"cycle-{revision}",
            "state_revision": revision,
            "contract_obsolete": False,
            "contract_obsolete_reason": None,
        }
    )
    return {
        "messages": [AIMessage(content=f"Provider reply rev {revision}")],
        "sealing_state": sealing_state,
        "working_profile": {
            "diameter": 50.0,
            "speed": 1500.0,
            "pressure": 10.0,
            "temperature": 120.0,
            "medium": "Wasser",
            "material": "PTFE",
            "v_m_s": 3.927,
            "pv_value": 39.27,
        },
        "relevant_fact_cards": [
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
        ],
    }


def test_relevant_material_input_change_triggers_recompute_metadata_in_structured_response(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    router_mod.SESSION_STORE.clear()
    states = [
        _build_material_state(temperature=80.0, pressure=10.0, revision=3),
        _build_material_state(temperature=120.0, pressure=10.0, revision=4),
    ]

    async def _fake_execute_agent(_state):
        return states.pop(0)

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)

    async def _first_turn():
        return await chat_endpoint(
            ChatRequest(
                message="Bitte strukturiere den ersten Materialfall.",
                session_id="material-cycle-1",
            ),
            current_user=agent_request_user,
        )

    async def _second_turn():
        return await chat_endpoint(
            ChatRequest(
                message="Temperatur jetzt 120 C.",
                session_id="material-cycle-1",
            ),
            current_user=agent_request_user,
        )

    anyio.run(_first_turn)
    response = anyio.run(_second_turn)

    payload = response.model_dump()
    invalidation = payload["case_state"]["invalidation_state"]
    assert payload["case_state"]["case_meta"]["state_revision"] == 4
    assert invalidation["requires_recompute"] is False
    assert invalidation["recompute_completed"] is True
    assert "temperature_c_changed" in invalidation["recompute_reasons"]
    assert invalidation["material_input_revision"] == 4
    assert invalidation["previous_material_input_fingerprint"] != invalidation["current_material_input_fingerprint"]


def test_stale_material_qualification_state_is_marked_and_not_silently_reused():
    stale_state = _build_material_state(temperature=120.0, pressure=10.0, revision=4)
    previous_state = _build_material_state(temperature=80.0, pressure=10.0, revision=3)
    previous_snapshot, previous_fingerprint = get_material_input_snapshot_and_fingerprint(previous_state)

    stale_state["sealing_state"]["cycle"]["material_input_snapshot"] = previous_snapshot
    stale_state["sealing_state"]["cycle"]["material_input_fingerprint"] = previous_fingerprint
    stale_state["sealing_state"]["cycle"]["material_input_revision"] = 3

    case_state = build_case_state(
        stale_state,
        session_id="material-stale-1",
        runtime_path="structured_graph",
        binding_level="ORIENTATION",
    )

    invalidation = case_state["invalidation_state"]
    material_core = case_state["qualification_results"]["material_core"]
    selection_projection = case_state["qualification_results"]["material_selection_projection"]

    assert invalidation["requires_recompute"] is True
    assert "qualification_results.material_core" in invalidation["stale_sections"]
    assert "temperature_c_changed" in invalidation["recompute_reasons"]
    assert material_core["status"] == "stale_requires_recompute"
    assert material_core["details"]["stale"] is True
    assert selection_projection["status"] == "stale_requires_recompute"
    assert selection_projection["details"]["stale"] is True
    assert selection_projection["details"]["candidate_source_adapter"] == "material_candidate_source_adapter_v1"


def test_unchanged_inputs_do_not_trigger_false_invalidation():
    state = _build_material_state(temperature=80.0, pressure=10.0, revision=3)
    snapshot, fingerprint = get_material_input_snapshot_and_fingerprint(state)
    state["sealing_state"]["cycle"]["material_input_snapshot"] = snapshot
    state["sealing_state"]["cycle"]["material_input_fingerprint"] = fingerprint
    state["sealing_state"]["cycle"]["material_input_revision"] = 3

    case_state = build_case_state(
        state,
        session_id="material-stable-1",
        runtime_path="structured_graph",
        binding_level="ORIENTATION",
    )

    invalidation = case_state["invalidation_state"]
    assert invalidation["requires_recompute"] is False
    assert invalidation["recompute_completed"] is False
    assert invalidation["recompute_reasons"] == []
    assert invalidation["previous_material_input_fingerprint"] == invalidation["current_material_input_fingerprint"]


def test_provider_fingerprint_change_invalidates_material_qualification(monkeypatch):
    state = _build_provider_material_state(revision=4)
    provider_snapshot, provider_fingerprint = get_material_provider_snapshot_and_fingerprint(state)
    state["sealing_state"]["cycle"]["provider_contract_snapshot"] = provider_snapshot
    state["sealing_state"]["cycle"]["provider_contract_fingerprint"] = provider_fingerprint
    state["sealing_state"]["cycle"]["provider_contract_revision"] = 4
    state["sealing_state"]["cycle"]["matched_promoted_registry_record_ids"] = ["registry-ptfe-g25-acme"]

    monkeypatch.setattr(
        "app.agent.material_core.load_promoted_candidate_registry_records",
        lambda: (
            PromotedCandidateRegistryRecordDTO(
                registry_record_id="registry-ptfe-g25-acme",
                material_family="PTFE",
                grade_name="G25",
                manufacturer_name="Acme",
                source_refs=["registry:ptfe:g25:acme:v2"],
                evidence_refs=[],
            ),
        ),
    )

    case_state = build_case_state(
        state,
        session_id="provider-fingerprint-1",
        runtime_path="structured_graph",
        binding_level="QUALIFIED_PRESELECTION",
    )

    invalidation = case_state["invalidation_state"]
    assert invalidation["requires_recompute"] is True
    assert "provider_contract_fingerprint_changed" in invalidation["recompute_reasons"]
    assert case_state["qualification_results"]["material_core"]["status"] == "stale_requires_recompute"


def test_missing_promoted_registry_record_invalidates_previously_qualified_case(monkeypatch):
    state = _build_provider_material_state(revision=4)
    provider_snapshot, provider_fingerprint = get_material_provider_snapshot_and_fingerprint(state)
    state["sealing_state"]["cycle"]["provider_contract_snapshot"] = provider_snapshot
    state["sealing_state"]["cycle"]["provider_contract_fingerprint"] = provider_fingerprint
    state["sealing_state"]["cycle"]["provider_contract_revision"] = 4
    state["sealing_state"]["cycle"]["matched_promoted_registry_record_ids"] = ["registry-ptfe-g25-acme"]

    monkeypatch.setattr("app.agent.material_core.load_promoted_candidate_registry_records", lambda: ())

    case_state = build_case_state(
        state,
        session_id="provider-missing-1",
        runtime_path="structured_graph",
        binding_level="QUALIFIED_PRESELECTION",
    )

    invalidation = case_state["invalidation_state"]
    assert invalidation["requires_recompute"] is True
    assert "promoted_registry_record_missing:registry-ptfe-g25-acme" in invalidation["recompute_reasons"]
    assert case_state["qualification_results"]["material_selection_projection"]["status"] == "stale_requires_recompute"
    assert case_state["qualified_action_gate"]["allowed"] is False
    assert "requires_recompute" in case_state["qualified_action_gate"]["block_reasons"]


def test_promotion_state_downgrade_invalidates_previously_qualified_case(monkeypatch):
    state = _build_provider_material_state(revision=4)
    provider_snapshot, provider_fingerprint = get_material_provider_snapshot_and_fingerprint(state)
    state["sealing_state"]["cycle"]["provider_contract_snapshot"] = provider_snapshot
    state["sealing_state"]["cycle"]["provider_contract_fingerprint"] = provider_fingerprint
    state["sealing_state"]["cycle"]["provider_contract_revision"] = 4
    state["sealing_state"]["cycle"]["matched_promoted_registry_record_ids"] = ["registry-ptfe-g25-acme"]

    monkeypatch.setattr(
        "app.agent.material_core.load_promoted_candidate_registry_records",
        lambda: (
            PromotedCandidateRegistryRecordDTO(
                registry_record_id="registry-ptfe-g25-acme",
                material_family="PTFE",
                grade_name="G25",
                manufacturer_name="Acme",
                promotion_state="draft",
                source_refs=["registry:ptfe:g25:acme"],
                evidence_refs=[],
            ),
        ),
    )

    case_state = build_case_state(
        state,
        session_id="provider-downgrade-1",
        runtime_path="structured_graph",
        binding_level="QUALIFIED_PRESELECTION",
    )

    invalidation = case_state["invalidation_state"]
    assert invalidation["requires_recompute"] is True
    assert "promoted_registry_record_promotion_state_changed:registry-ptfe-g25-acme" in invalidation["recompute_reasons"]
    assert "registry-ptfe-g25-acme" not in invalidation["matched_promoted_registry_record_ids"]
    assert case_state["qualified_action_gate"]["allowed"] is False
