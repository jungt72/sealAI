import importlib
from pathlib import Path

from app.agent.agent.selection import (
    MANUFACTURER_VALIDATION_REPLY,
    MISSING_INPUTS_REPLY,
    NO_CANDIDATES_REPLY,
    NO_VIABLE_CANDIDATES_REPLY,
    NEUTRAL_SCOPE_REPLY,
    PRECHECK_ONLY_REPLY,
    SAFEGUARDED_WITHHELD_REPLY,
    build_final_reply,
    build_selection_state,
)


def test_selection_module_resolves_to_canonical_agent_path():
    module = importlib.import_module("app.agent.agent.selection")
    module_path = Path(module.__file__).resolve()

    assert str(module_path).endswith("/backend/app/agent/agent/selection.py")


def test_no_release_without_recommendation_artifact():
    selection_state = {
        "selection_status": "blocked_no_candidates",
        "candidates": [],
        "viable_candidate_ids": [],
        "blocked_candidates": [],
        "winner_candidate_id": None,
        "recommendation_artifact": None,
        "release_status": "inadmissible",
        "rfq_admissibility": "inadmissible",
        "specificity_level": "family_only",
        "output_blocked": True,
    }

    reply = build_final_reply(selection_state)
    assert reply == SAFEGUARDED_WITHHELD_REPLY


def test_no_release_without_winner_candidate():
    selection_state = build_selection_state([], {"analysis_cycle_id": "cycle-1"})
    assert selection_state["release_status"] == "inadmissible"
    assert selection_state["winner_candidate_id"] is None
    assert selection_state["recommendation_artifact"]["release_status"] == "inadmissible"
    assert selection_state["viable_candidate_ids"] == []
    assert selection_state["blocked_candidates"] == []


def test_blocked_selection_sets_release_status_withheld():
    selection_state = build_selection_state([], {"analysis_cycle_id": "cycle-1"})
    assert selection_state["selection_status"] == "blocked_no_candidates"
    assert selection_state["release_status"] == "inadmissible"
    assert build_final_reply(selection_state) == NO_CANDIDATES_REPLY


def test_candidate_exists_but_governance_inadmissible_blocks_release():
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-1",
                "topic": "PTFE",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 1,
                "metadata": {},
            }
        ],
        {"analysis_cycle_id": "cycle-1"},
        {"release_status": "inadmissible", "conflicts": []},
        {"operating_conditions": {"temperature": 200.0}},
    )

    assert selection_state["winner_candidate_id"] == "ptfe"
    assert selection_state["selection_status"] == "winner_selected"
    assert selection_state["release_status"] == "inadmissible"
    assert selection_state["recommendation_artifact"]["release_status"] == "inadmissible"
    assert build_final_reply(selection_state) == SAFEGUARDED_WITHHELD_REPLY


def test_critical_conflict_blocks_release_but_keeps_winner():
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-1",
                "topic": "PTFE",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 1,
                "metadata": {},
            }
        ],
        {"analysis_cycle_id": "cycle-1"},
        {"release_status": "rfq_ready", "rfq_admissibility": "ready", "conflicts": [{"severity": "CRITICAL"}]},
        {"operating_conditions": {"temperature": 200.0}},
    )

    assert selection_state["winner_candidate_id"] == "ptfe"
    assert selection_state["release_status"] == "rfq_ready"
    assert selection_state["output_blocked"] is True
    assert selection_state["recommendation_artifact"]["release_status"] == selection_state["release_status"]
    assert build_final_reply(selection_state) == SAFEGUARDED_WITHHELD_REPLY


def test_release_withheld_when_required_inputs_missing():
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-1",
                "topic": "PTFE",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 1,
                "metadata": {},
            }
        ],
        {"analysis_cycle_id": "cycle-1"},
        {"release_status": "rfq_ready", "rfq_admissibility": "ready", "conflicts": []},
        {"operating_conditions": {}},
    )

    assert selection_state["selection_status"] == "blocked_missing_required_inputs"
    assert selection_state["release_status"] == "rfq_ready"
    assert selection_state["viable_candidate_ids"] == []
    assert selection_state["blocked_candidates"][0]["block_reason"] == "blocked_missing_required_inputs"
    assert build_final_reply(selection_state) == MISSING_INPUTS_REPLY


def test_candidate_with_limit_conflict_is_not_viable():
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-1",
                "topic": "PTFE",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 1,
                "metadata": {},
            }
        ],
        {"analysis_cycle_id": "cycle-1"},
        {"release_status": "rfq_ready", "rfq_admissibility": "ready", "conflicts": []},
        {"operating_conditions": {"temperature": 300.0}},
    )

    assert selection_state["selection_status"] == "blocked_no_viable_candidates"
    assert selection_state["winner_candidate_id"] is None
    assert selection_state["release_status"] == "rfq_ready"
    assert selection_state["blocked_candidates"][0]["block_reason"] == "blocked_temperature_conflict"
    assert build_final_reply(selection_state) == NO_VIABLE_CANDIDATES_REPLY


def test_candidate_with_pressure_conflict_is_not_viable():
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-1",
                "topic": "PTFE",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C und einen maximalen Druck von 50 bar.",
                "retrieval_rank": 1,
                "metadata": {},
            }
        ],
        {"analysis_cycle_id": "cycle-1"},
        {"release_status": "rfq_ready", "rfq_admissibility": "ready", "conflicts": []},
        {"operating_conditions": {"temperature": 200.0, "pressure": 80.0}},
    )

    assert selection_state["selection_status"] == "blocked_no_viable_candidates"
    assert selection_state["winner_candidate_id"] is None
    assert selection_state["release_status"] == "rfq_ready"
    assert selection_state["blocked_candidates"][0]["block_reason"] == "blocked_pressure_conflict"
    assert selection_state["candidates"][0]["viability_status"] == "blocked_pressure_conflict"


def test_candidate_with_demo_only_registry_becomes_exploratory():
    """0B.1: A candidate matched only against a demo_only registry entry must NOT reach
    qualified/promoted status.  The physical viability check still passes (temperature
    within limits), but without a governed promoted trust anchor the candidate is
    exploratory — output_blocked is True and no NEUTRAL_SCOPE_REPLY is produced.
    """
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-1",
                "topic": "PTFE G25 Acme datasheet",
                "content": "PTFE grade G25 from Acme hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 1,
                "source_ref": "datasheet-acme-g25",
                "source_type": "manufacturer_datasheet",
                "source_rank": 1,
                "metadata": {
                    "material_family": "PTFE",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                },
            }
        ],
        {"analysis_cycle_id": "cycle-1"},
        {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
            "conflicts": [],
        },
        {"operating_conditions": {"temperature": 200.0}},
    )

    # Physical viability still holds — candidate is within temperature limits
    assert selection_state["selection_status"] == "winner_selected"
    assert selection_state["winner_candidate_id"] == "ptfe::g25::acme"
    assert selection_state["viable_candidate_ids"] == ["ptfe::g25::acme"]
    assert selection_state["candidates"][0]["viability_status"] == "viable"
    assert selection_state["candidates"][0]["block_reason"] is None

    # 0B.1: demo_only registry entry does NOT grant promoted trust anchor status
    assert selection_state["candidates"][0]["candidate_source_class"] == "exploratory_candidate_input"
    assert selection_state["promoted_candidate_ids"] == []
    assert selection_state["qualified_candidate_ids"] == []
    assert selection_state["exploratory_candidate_ids"] == ["ptfe::g25::acme"]
    assert selection_state["candidate_source_origin"] == "retrieval_fact_card_transition_adapter"

    # output is blocked — exploratory source does not satisfy release gate
    assert selection_state["output_blocked"] is True
    assert build_final_reply(selection_state) == SAFEGUARDED_WITHHELD_REPLY


def test_subfamily_governance_never_releases_rfq_reply():
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-1",
                "topic": "PTFE",
                "content": "PTFE grade G25 hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 1,
                "metadata": {"material_family": "PTFE", "grade_name": "G25"},
            }
        ],
        {"analysis_cycle_id": "cycle-1"},
        {
            "release_status": "manufacturer_validation_required",
            "rfq_admissibility": "provisional",
            "specificity_level": "subfamily",
            "unknowns_manufacturer_validation": [
                "specificity_not_compound_confirmed",
                "manufacturer_name_unconfirmed_for_compound",
            ],
            "conflicts": [],
        },
        {"operating_conditions": {"temperature": 200.0}},
    )

    assert selection_state["winner_candidate_id"] == "ptfe::g25"
    assert selection_state["release_status"] == "manufacturer_validation_required"
    assert selection_state["rfq_admissibility"] == "provisional"
    assert selection_state["specificity_level"] == "subfamily"
    assert selection_state["output_blocked"] is True
    assert build_final_reply(selection_state) == MANUFACTURER_VALIDATION_REPLY


def test_contextual_final_reply_surfaces_direction_binding_and_limits():
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-1",
                "topic": "PTFE grade G25 from Acme",
                "content": "PTFE grade G25 from Acme hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 1,
                "metadata": {
                    "material_family": "PTFE",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                },
            }
        ],
        {"analysis_cycle_id": "cycle-1"},
        {
            "release_status": "manufacturer_validation_required",
            "rfq_admissibility": "provisional",
            "specificity_level": "subfamily",
            "conflicts": [],
        },
        {"operating_conditions": {"temperature": 200.0}},
    )

    reply = build_final_reply(
        selection_state,
        {
            "rwdr_type_class": "engineering_review_required",
            "review_flags": ["review_water_with_pressure"],
            "blockers": ["manufacturer_name_unconfirmed_for_compound"],
        },
    )

    assert "Aktuelle technische Richtung" in reply
    assert "ptfe::g25::acme" in reply
    assert "Bindungsgrad: Belastbare Vorqualifikation" in reply
    assert "RFQ: provisional" in reply
    assert "Review-pflichtig: review_water_with_pressure" in reply


def test_contextual_final_reply_surfaces_scope_assumptions_and_recompute_boundary():
    selection_state = build_selection_state(
        [],
        {"analysis_cycle_id": "cycle-1"},
        {
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "conflicts": [],
        },
    )

    reply = build_final_reply(
        selection_state,
        {
            "scope_of_validity": ["specificity_level:family_only", "medium_profile:water"],
            "assumptions_active": ["temperature_estimated"],
            "blockers": ["pressure_bar_missing"],
            "obsolescence_state": "active",
            "recompute_requirement": "required",
        },
    )

    assert "Geltungsgrenze: specificity_level:family_only, medium_profile:water" in reply
    assert "Annahmen: temperature_estimated" in reply
    assert "Obsoleszenz: active" in reply
    assert "Recompute: required" in reply


def test_unknowns_release_blocking_prevents_governed_release():
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-1",
                "topic": "PTFE",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 1,
                "metadata": {},
            }
        ],
        {"analysis_cycle_id": "cycle-1"},
        {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "family_only",
            "unknowns_release_blocking": ["medium_identity_unresolved"],
            "conflicts": [],
        },
        {"operating_conditions": {"temperature": 200.0}},
    )

    assert selection_state["winner_candidate_id"] == "ptfe"
    assert selection_state["release_status"] == "rfq_ready"
    assert selection_state["output_blocked"] is True
    assert build_final_reply(selection_state) == SAFEGUARDED_WITHHELD_REPLY


def test_selection_mirrors_governance_manufacturer_validation_without_releasing():
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-1",
                "topic": "PTFE",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 1,
                "metadata": {},
            }
        ],
        {"analysis_cycle_id": "cycle-1"},
        {
            "release_status": "manufacturer_validation_required",
            "rfq_admissibility": "provisional",
            "specificity_level": "family_only",
            "unknowns_manufacturer_validation": ["specificity_not_compound_confirmed"],
            "conflicts": [],
        },
        {"operating_conditions": {"temperature": 200.0}},
    )

    assert selection_state["winner_candidate_id"] == "ptfe"
    assert selection_state["release_status"] == "manufacturer_validation_required"
    assert selection_state["rfq_admissibility"] == "provisional"
    assert selection_state["output_blocked"] is True
    assert build_final_reply(selection_state) == MANUFACTURER_VALIDATION_REPLY


def test_precheck_reply_remains_neutral():
    selection_state = {
        "selection_status": "not_started",
        "candidates": [],
        "viable_candidate_ids": [],
        "blocked_candidates": [],
        "winner_candidate_id": None,
        "recommendation_artifact": {
            "selection_status": "not_started",
            "winner_candidate_id": None,
            "candidate_ids": [],
            "viable_candidate_ids": [],
            "blocked_candidates": [],
            "evidence_basis": [],
            "release_status": "precheck_only",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "output_blocked": True,
            "trace_provenance_refs": [],
        },
        "release_status": "precheck_only",
        "rfq_admissibility": "inadmissible",
        "specificity_level": "family_only",
        "output_blocked": True,
    }

    assert build_final_reply(selection_state) == PRECHECK_ONLY_REPLY


def test_candidate_identity_prefers_metadata_over_text_heuristics():
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-1",
                "topic": "NBR brochure",
                "content": "NBR hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 1,
                "metadata": {
                    "material_family": "PTFE",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "temperature_max_c": 260,
                },
            }
        ],
        {"analysis_cycle_id": "cycle-1"},
        {"release_status": "rfq_ready", "rfq_admissibility": "ready", "conflicts": []},
        {"operating_conditions": {"temperature": 200.0}},
    )

    candidate = selection_state["candidates"][0]
    assert candidate["material_family"] == "PTFE"
    assert candidate["candidate_kind"] == "manufacturer_grade"
    assert candidate["grade_name"] == "G25"
    assert candidate["manufacturer_name"] == "Acme"
    assert candidate["candidate_id"] == "ptfe::g25::acme"
    assert selection_state["winner_candidate_id"] == "ptfe::g25::acme"


def test_selection_uses_normalized_metadata_limits_over_text_fallback():
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-1",
                "topic": "PTFE",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C und einen maximalen Druck von 80 bar.",
                "retrieval_rank": 1,
                "metadata": {
                    "material_family": "PTFE",
                    "temperature_max_c": 260,
                    "pressure_max_bar": 40,
                },
            }
        ],
        {"analysis_cycle_id": "cycle-1"},
        {"release_status": "rfq_ready", "rfq_admissibility": "ready", "conflicts": []},
        {"operating_conditions": {"temperature": 200.0, "pressure": 50.0}},
    )

    assert selection_state["selection_status"] == "blocked_no_viable_candidates"
    assert selection_state["winner_candidate_id"] is None
    assert selection_state["blocked_candidates"][0]["block_reason"] == "blocked_pressure_conflict"
    assert selection_state["candidates"][0]["viability_status"] == "blocked_pressure_conflict"


def test_winner_can_only_come_from_viable_candidate_ids():
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-2",
                "topic": "NBR",
                "content": "NBR hat ein Temperaturlimit von max. 120 C.",
                "retrieval_rank": 1,
                "metadata": {},
            },
            {
                "evidence_id": "fc-1",
                "topic": "PTFE",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 2,
                "metadata": {},
            },
        ],
        {"analysis_cycle_id": "cycle-1"},
        {"release_status": "rfq_ready", "rfq_admissibility": "ready", "conflicts": []},
        {"operating_conditions": {"temperature": 200.0}},
    )

    assert selection_state["viable_candidate_ids"] == ["ptfe"]
    assert selection_state["winner_candidate_id"] == "ptfe"
    assert selection_state["winner_candidate_id"] in selection_state["viable_candidate_ids"]
    blocked = {entry["candidate_id"]: entry["block_reason"] for entry in selection_state["blocked_candidates"]}
    assert blocked["nbr"] == "blocked_temperature_conflict"


def test_selection_release_fields_only_mirror_governance():
    governance_state = {
        "release_status": "manufacturer_validation_required",
        "rfq_admissibility": "provisional",
        "specificity_level": "family_only",
        "unknowns_manufacturer_validation": ["specificity_not_compound_confirmed"],
        "conflicts": [],
    }
    selection_state = build_selection_state(
        [
            {
                "evidence_id": "fc-1",
                "topic": "PTFE",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 1,
                "metadata": {},
            }
        ],
        {"analysis_cycle_id": "cycle-1"},
        governance_state,
        {"operating_conditions": {"temperature": 200.0}},
    )

    assert selection_state["release_status"] == governance_state["release_status"]
    assert selection_state["rfq_admissibility"] == governance_state["rfq_admissibility"]
    assert selection_state["specificity_level"] == governance_state["specificity_level"]
    assert selection_state["recommendation_artifact"]["release_status"] == governance_state["release_status"]
