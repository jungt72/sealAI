from app.agent.agent.selection import MANUFACTURER_VALIDATION_REPLY, build_final_reply, build_selection_state


def _qualified_fact_card(evidence_id: str, *, grade_name: str = "F1") -> dict:
    return {
        "evidence_id": evidence_id,
        "topic": "PTFE",
        "content": "PTFE grade F1 hat ein Temperaturlimit von max. 260 C.",
        "retrieval_rank": 1,
        "metadata": {
            "material_family": "PTFE",
            "grade_name": grade_name,
            "manufacturer_name": "Acme",
            "temperature_max_c": 260,
            "pressure_max_bar": 50,
        },
    }


def _full_asserted() -> dict:
    return {
        "medium_profile": {"name": "Wasser"},
        "operating_conditions": {"temperature": 120.0, "pressure": 10.0},
    }


def _green_governance() -> dict:
    return {
        "release_status": "rfq_ready",
        "rfq_admissibility": "ready",
        "specificity_level": "compound_required",
        "unknowns_release_blocking": [],
        "unknowns_manufacturer_validation": [],
        "gate_failures": [],
        "conflicts": [],
    }


def test_governance_block_prevents_direct_rationale_carry_through():
    state = build_selection_state(
        relevant_fact_cards=[_qualified_fact_card("fc_1")],
        cycle_state={"analysis_cycle_id": "cycle-1"},
        governance_state={
            **_green_governance(),
            "release_status": "manufacturer_validation_required",
            "rfq_admissibility": "provisional",
            "specificity_level": "family_only",
            "unknowns_manufacturer_validation": ["specificity_not_compound_confirmed"],
        },
        asserted_state=_full_asserted(),
    )
    state["output_contract_projection"]["output_status"] = "governed_non_binding_result"
    state["output_contract_projection"]["suppress_recommendation_details"] = False
    state["case_summary_projection"]["current_case_status"] = "governed_non_binding_result"
    state["case_summary_projection"]["active_blockers"] = []

    reply = build_final_reply(state, asserted_state=_full_asserted())

    assert reply.startswith(MANUFACTURER_VALIDATION_REPLY)
    assert state["recommendation_artifact"]["rationale_summary"] not in reply


def test_releasable_governed_result_may_still_surface_rationale_summary():
    state = build_selection_state(
        relevant_fact_cards=[_qualified_fact_card("fc_1")],
        cycle_state={"analysis_cycle_id": "cycle-1"},
        governance_state=_green_governance(),
        asserted_state=_full_asserted(),
    )

    reply = build_final_reply(state, asserted_state=_full_asserted())

    assert state["output_contract_projection"]["output_status"] == "governed_non_binding_result"
    assert state["recommendation_artifact"]["rationale_summary"] in reply
