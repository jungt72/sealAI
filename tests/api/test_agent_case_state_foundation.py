from __future__ import annotations

import anyio
from langchain_core.messages import AIMessage

from app.agent.api.models import ChatRequest
from app.agent.api.router import chat_endpoint
from app.agent.cli import create_initial_state


def _build_structured_state_with_material_projection():
    sealing_state = create_initial_state()
    sealing_state["observed"]["raw_parameters"] = {
        "medium": "Wasser",
        "pressure_bar": 10.0,
    }
    sealing_state["observed"]["observed_inputs"] = [
        {
            "source": "user",
            "raw_text": "10 bar Wasser",
            "claim_type": "fact_observed",
            "confidence": 1.0,
            "source_fact_ids": ["fc-1"],
        }
    ]
    sealing_state["normalized"]["identity_records"] = {
        "material_family": {
            "raw_value": "PTFE",
            "normalized_value": "PTFE",
            "identity_class": "identity_confirmed",
            "source_fact_ids": ["fc-1"],
        }
    }
    sealing_state["asserted"]["medium_profile"] = {
        "name": "Wasser",
        "resistance_rating": "A",
    }
    sealing_state["asserted"]["machine_profile"] = {
        "material": "PTFE",
    }
    sealing_state["asserted"]["operating_conditions"] = {
        "pressure": 10.0,
        "temperature": 80.0,
    }
    sealing_state["governance"].update(
        {
            "release_status": "manufacturer_validation_required",
            "rfq_admissibility": "provisional",
            "specificity_level": "subfamily",
            "gate_failures": [],
            "unknowns_release_blocking": [],
            "unknowns_manufacturer_validation": ["manufacturer_name_unconfirmed_for_compound"],
            "conflicts": [{"severity": "MANUFACTURER_SCOPE", "type": "manufacturer_scope"}],
        }
    )
    sealing_state["selection"] = {
        "selection_status": "blocked_missing_required_inputs",
        "candidates": [
            {
                "candidate_id": "ptfe",
                "candidate_kind": "family",
                "material_family": "PTFE",
                "evidence_refs": ["fc-1"],
                "viability_status": "blocked_missing_required_inputs",
                "block_reason": "blocked_missing_required_inputs",
            }
        ],
        "viable_candidate_ids": [],
        "blocked_candidates": [{"candidate_id": "PTFE", "block_reason": "blocked_missing_required_inputs"}],
        "winner_candidate_id": None,
        "recommendation_artifact": {
            "selection_status": "blocked_missing_required_inputs",
            "winner_candidate_id": None,
            "candidate_ids": ["PTFE"],
            "viable_candidate_ids": [],
            "blocked_candidates": [{"candidate_id": "PTFE", "block_reason": "blocked_missing_required_inputs"}],
            "evidence_basis": ["fc-1"],
            "release_status": "manufacturer_validation_required",
            "rfq_admissibility": "provisional",
            "specificity_level": "subfamily",
            "output_blocked": True,
            "trace_provenance_refs": ["fc-1", "cycle-1"],
        },
        "release_status": "manufacturer_validation_required",
        "rfq_admissibility": "provisional",
        "specificity_level": "subfamily",
        "output_blocked": True,
    }
    sealing_state["cycle"].update(
        {
            "analysis_cycle_id": "cycle-1",
            "state_revision": 3,
            "contract_obsolete": False,
            "contract_obsolete_reason": None,
        }
    )
    return {
        "messages": [AIMessage(content="Structured material reply")],
        "sealing_state": sealing_state,
        "working_profile": {
            "diameter": 50.0,
            "speed": 1500.0,
            "pressure": 10.0,
            "temperature": 80.0,
            "medium": "Wasser",
            "material": "PTFE",
            "v_m_s": 3.927,
            "pv_value": 39.27,
            "risk_warning": "PTFE requires validation for this case.",
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


def _build_structured_state_with_rwdr_projection():
    state = _build_structured_state_with_material_projection()
    state["sealing_state"]["rwdr"] = {
        "flow": {
            "active": True,
            "stage": "stage_3",
            "missing_fields": [],
            "ready_for_decision": True,
            "decision_executed": True,
        },
        "input": {
            "motion_type": "single_direction_rotation",
            "shaft_diameter_mm": 50.0,
            "max_speed_rpm": 1500.0,
            "pressure_profile": "constant_pressure_above_0_5_bar",
            "inner_lip_medium_scenario": "water_or_aqueous",
            "maintenance_mode": "used_shaft",
            "external_contamination_class": "splash_water_or_outdoor_dust",
            "available_width_mm": 8.0,
            "confidence": {},
        },
        "derived": {
            "surface_speed_mps": 3.927,
            "surface_speed_class": "medium",
            "tribology_risk_level": "critical",
            "pressure_risk_level": "high",
            "exclusion_level": "medium",
            "geometry_fit_status": "tight",
            "ptfe_candidate_flag": True,
            "pressure_profile_required_flag": True,
            "dust_lip_required_flag": True,
            "heavy_duty_candidate_flag": False,
            "additional_exclusion_required_flag": False,
            "repair_sleeve_flag": True,
            "lip_offset_check_flag": True,
            "installation_sleeve_required_flag": False,
            "sensitive_profiles_restricted_flag": False,
            "review_due_to_water_pressure": True,
            "review_due_to_dry_run_high_speed": False,
            "review_due_to_geometry": False,
            "review_due_to_uncertainty": False,
            "reverse_rotation_requires_directionless_profile": False,
            "auto_release_allowed_flag": True,
            "confidence_score": 0.92,
            "critical_unknown_count": 0,
        },
        "output": {
            "type_class": "engineering_review_required",
            "modifiers": ["repair_sleeve_or_lip_offset_check"],
            "warnings": ["installation_path_damage_risk"],
            "review_flags": ["review_water_with_pressure"],
            "hard_stop": None,
            "reasoning": ["Water or aqueous medium combined with pressure requires deterministic engineering review."],
        },
    }
    state["messages"] = [AIMessage(content="Structured RWDR reply")]
    return state


def _build_structured_state_with_promoted_material_projection():
    state = _build_structured_state_with_material_projection()
    state["sealing_state"]["normalized"]["identity_records"].update(
        {
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
    )
    state["sealing_state"]["governance"].update(
        {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
            "unknowns_manufacturer_validation": [],
            "conflicts": [],
        }
    )
    state["sealing_state"]["selection"] = {
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
            "trace_provenance_refs": ["fc-qualified-1", "cycle-1"],
        },
        "release_status": "rfq_ready",
        "rfq_admissibility": "ready",
        "specificity_level": "compound_required",
        "output_blocked": False,
    }
    state["relevant_fact_cards"] = [
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
    state["messages"] = [AIMessage(content="Structured qualified material reply")]
    return state


def test_structured_response_contains_case_state(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    router_mod.SESSION_STORE.clear()

    async def _fake_execute_agent(_state):
        return _build_structured_state_with_material_projection()

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)
    async def _call():
        return await chat_endpoint(
            ChatRequest(
                message="Bitte empfehle ein geeignetes Material fuer diese Dichtung bei 10 bar und 80 C.",
                session_id="case-1",
            ),
            current_user=agent_request_user,
        )

    response = anyio.run(_call)

    payload = response.model_dump()
    case_state = payload["case_state"]
    assert payload["has_case_state"] is True
    assert case_state is not None
    assert set(case_state.keys()) == {
        "case_meta",
        "active_domain",
        "raw_inputs",
        "derived_calculations",
        "engineering_signals",
        "qualification_results",
        "result_contract",
        "candidate_clusters",
        "sealing_requirement_spec",
        "qualified_action_gate",
        "qualified_action_status",
        "qualified_action_history",
        "readiness",
        "evidence_trace",
        "invalidation_state",
        "audit_trail",
    }


def test_case_state_maps_deterministic_calculations(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    router_mod.SESSION_STORE.clear()

    async def _fake_execute_agent(_state):
        return _build_structured_state_with_material_projection()

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)
    async def _call():
        return await chat_endpoint(
            ChatRequest(
                message="Bitte empfehle ein geeignetes Material fuer diese Dichtung bei 10 bar.",
                session_id="case-2",
            ),
            current_user=agent_request_user,
        )

    response = anyio.run(_call)

    derived = response.model_dump()["case_state"]["derived_calculations"]
    assert derived["surface_speed_mps"]["value"] == 3.927
    assert derived["pv_value_bar_mps"]["value"] == 39.27
    assert derived["surface_speed_mps"]["source_type"] == "deterministic_foundation"
    assert derived["surface_speed_mps"]["formula_id"] == "surface_speed_from_diameter_and_rpm_v1"


def test_case_state_maps_rwdr_and_material_qualification(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    router_mod.SESSION_STORE.clear()

    async def _fake_execute_agent(_state):
        return _build_structured_state_with_rwdr_projection()

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)
    async def _call():
        return await chat_endpoint(
            ChatRequest(
                message="Bitte qualifiziere den RWDR Fall.",
                session_id="case-3",
            ),
            current_user=agent_request_user,
        )

    response = anyio.run(_call)

    payload = response.model_dump()
    case_state = payload["case_state"]
    qualification_results = case_state["qualification_results"]
    assert case_state["active_domain"] == "rwdr_preselection"
    assert qualification_results["material_governance"]["status"] == "manufacturer_validation_required"
    assert qualification_results["material_core"]["status"] == "exploratory_candidate_source_only"
    assert qualification_results["material_core"]["details"]["viable_candidate_ids"] == ["ptfe"]
    assert qualification_results["material_core"]["details"]["qualified_viable_candidate_ids"] == []
    assert qualification_results["material_core"]["details"]["exploratory_candidate_ids"] == ["ptfe"]
    assert qualification_results["rwdr_preselection"]["details"]["type_class"] == "engineering_review_required"
    assert case_state["engineering_signals"]["rwdr_pressure_risk_level"]["value"] == "high"
    assert case_state["derived_calculations"]["rwdr_surface_speed_mps"]["value"] == 3.927
    assert case_state["derived_calculations"]["rwdr_confidence_score"]["value"] == 0.92


def test_case_state_foundation_sections_have_minimal_semantics(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    router_mod.SESSION_STORE.clear()

    async def _fake_execute_agent(_state):
        return _build_structured_state_with_material_projection()

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)
    async def _call():
        return await chat_endpoint(
            ChatRequest(
                message="Bitte strukturiere den Fall.",
                session_id="case-4",
            ),
            current_user=agent_request_user,
        )

    response = anyio.run(_call)

    case_state = response.model_dump()["case_state"]
    assert case_state["readiness"]["has_structured_case"] is True
    assert "manufacturer_name_unconfirmed_for_compound" in case_state["readiness"]["missing_review_inputs"]
    assert "fc-1" in case_state["evidence_trace"]["used_evidence_refs"]
    assert case_state["invalidation_state"]["requires_recompute"] is False
    assert case_state["audit_trail"][0]["event_type"] == "case_state_projection_built"
    assert case_state["audit_trail"][1]["details"]["missing_review_inputs"] == ["manufacturer_name_unconfirmed_for_compound"]
    assert case_state["audit_trail"][2]["details"]["result_statuses"]["material_core"] == "exploratory_candidate_source_only"


def test_case_state_engineering_signals_reflect_foundation(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    router_mod.SESSION_STORE.clear()

    async def _fake_execute_agent(_state):
        state = _build_structured_state_with_material_projection()
        state["working_profile"]["pressure"] = 250.0
        state["working_profile"]["material"] = "PTFE"
        state["sealing_state"]["asserted"]["operating_conditions"]["pressure"] = 250.0
        state["sealing_state"]["governance"]["unknowns_release_blocking"] = ["shaft_diameter_unresolved"]
        return state

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)
    async def _call():
        return await chat_endpoint(
            ChatRequest(
                message="Bitte strukturiere den kritischen PTFE Fall.",
                session_id="case-5",
            ),
            current_user=agent_request_user,
        )

    response = anyio.run(_call)

    signals = response.model_dump()["case_state"]["engineering_signals"]
    assert signals["material_risk_warning"]["source_type"] == "deterministic_foundation"
    assert signals["release_blocking_unknowns_present"]["value"] == 1


def test_case_state_qualified_action_gate_blocks_exploratory_material_case(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    router_mod.SESSION_STORE.clear()

    async def _fake_execute_agent(_state):
        return _build_structured_state_with_material_projection()

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)

    async def _call():
        return await chat_endpoint(
            ChatRequest(
                message="Bitte qualifiziere den explorativen Materialfall.",
                session_id="case-6",
            ),
            current_user=agent_request_user,
        )

    response = anyio.run(_call)

    gate = response.model_dump()["case_state"]["qualified_action_gate"]
    assert gate["allowed"] is False
    assert "exploratory_candidate_source_only" in gate["block_reasons"]
    assert response.rfq_ready is False


def test_case_state_qualified_action_gate_enables_promoted_fresh_qualified_case(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    router_mod.SESSION_STORE.clear()

    async def _fake_execute_agent(_state):
        return _build_structured_state_with_promoted_material_projection()

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)

    async def _call():
        return await chat_endpoint(
            ChatRequest(
                message="Bitte qualifiziere den provider-backed Materialfall.",
                session_id="case-7",
            ),
            current_user=agent_request_user,
        )

    response = anyio.run(_call)

    payload = response.model_dump()
    gate = payload["case_state"]["qualified_action_gate"]
    assert gate["allowed"] is True
    assert gate["rfq_ready"] is True
    assert gate["binding_level"] == "RFQ_BASIS"
    assert gate["block_reasons"] == []
    assert payload["qualified_action_gate"]["allowed"] is True
    assert payload["rfq_ready"] is True
    assert payload["binding_level"] == "RFQ_BASIS"
    assert payload["case_state"]["case_meta"]["binding_level"] == "RFQ_BASIS"
    assert payload["case_state"]["result_contract"]["binding_level"] == "RFQ_BASIS"
    assert payload["case_state"]["qualified_action_status"]["last_status"] == "none"
    assert payload["case_state"]["qualified_action_status"]["current_gate_allows_action"] is True
    assert payload["case_state"]["qualified_action_status"]["binding_level"] == "RFQ_BASIS"
    assert payload["case_state"]["qualified_action_history"] == []


def test_case_state_keeps_gate_and_last_action_status_semantically_distinct(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    router_mod.SESSION_STORE.clear()

    async def _fake_execute_agent(_state):
        state = _build_structured_state_with_promoted_material_projection()
        state["case_state"] = {
            "qualified_action_status": {
                "action": "download_rfq",
                "last_status": "blocked",
                "allowed_at_execution_time": False,
                "executed": False,
                "block_reasons": ["selection_output_blocked"],
                "timestamp": "2026-03-13T00:00:00+00:00",
                "binding_level": "QUALIFIED_PRESELECTION",
                "runtime_path": "STRUCTURED_QUALIFICATION",
                "source_ref": "api.agent.actions.download_rfq_action",
                "action_payload_stub": None,
                "current_gate_allows_action": False,
            }
        }
        return state

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)

    async def _call():
        return await chat_endpoint(
            ChatRequest(
                message="Bitte evaluiere die aktuelle RFQ-Lage erneut.",
                session_id="case-8",
            ),
            current_user=agent_request_user,
        )

    response = anyio.run(_call)

    case_state = response.model_dump()["case_state"]
    assert case_state["qualified_action_gate"]["allowed"] is True
    assert case_state["qualified_action_status"]["last_status"] == "blocked"
    assert case_state["qualified_action_status"]["executed"] is False
    assert case_state["qualified_action_status"]["current_gate_allows_action"] is True
    assert case_state["qualified_action_history"] == []
