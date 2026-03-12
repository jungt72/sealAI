import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.agent.graph import (
    app,
    evidence_tool_node,
    final_response_node,
    router,
    selection_node,
)
from app.agent.cli import create_initial_state
from app.agent.evidence.models import ClaimType


def test_graph_compilation_includes_patch1_nodes():
    assert app is not None
    nodes = app.nodes
    assert "reasoning_node" in nodes
    assert "evidence_tool_node" in nodes
    assert "selection_node" in nodes
    assert "final_response_node" in nodes


def test_graph_router_to_tools():
    tool_call = {"name": "submit_claim", "args": {}, "id": "1"}
    state = {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "sealing_state": create_initial_state(),
    }
    assert router(state) == "evidence_tool_node"


def test_graph_routes_to_selection_node_when_no_tool_calls():
    state = {
        "messages": [AIMessage(content="Kein Tool", tool_calls=[])],
        "sealing_state": create_initial_state(),
    }
    assert router(state) == "selection_node"


def test_selection_node_writes_recommendation_artifact():
    state = {
        "messages": [AIMessage(content="Finale Intake-Antwort", tool_calls=[])],
        "sealing_state": create_initial_state(),
        "relevant_fact_cards": [
                {
                    "id": "fc-1",
                    "evidence_id": "fc-1",
                    "source_ref": "ptfe-card",
                    "topic": "PTFE Properties",
                    "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                    "tags": ["ptfe"],
                    "retrieval_rank": 1,
                    "retrieval_score": 0.9,
                    "metadata": {},
                }
        ],
    }
    state["sealing_state"]["governance"]["release_status"] = "rfq_ready"
    state["sealing_state"]["governance"]["rfq_admissibility"] = "ready"
    state["sealing_state"]["governance"]["specificity_level"] = "compound_required"
    state["sealing_state"]["asserted"]["operating_conditions"] = {"temperature": 200.0}

    result = selection_node(state)
    selection = result["sealing_state"]["selection"]
    assert selection["selection_status"] == "winner_selected"
    assert selection["release_status"] == "rfq_ready"
    assert selection["rfq_admissibility"] == "ready"
    assert selection["winner_candidate_id"] == "ptfe"
    assert selection["viable_candidate_ids"] == ["ptfe"]
    assert selection["output_blocked"] is False
    assert selection["recommendation_artifact"] is not None
    assert selection["recommendation_artifact"]["winner_candidate_id"] == "ptfe"


def test_selection_node_withholds_release_when_governance_is_inadmissible():
    state = {
        "sealing_state": create_initial_state(),
        "relevant_fact_cards": [
                {
                    "id": "fc-1",
                    "evidence_id": "fc-1",
                    "source_ref": "ptfe-card",
                    "topic": "PTFE Properties",
                    "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                    "tags": ["ptfe"],
                    "retrieval_rank": 1,
                    "retrieval_score": 0.9,
                    "metadata": {},
                }
        ],
    }
    state["sealing_state"]["governance"]["release_status"] = "inadmissible"
    state["sealing_state"]["asserted"]["operating_conditions"] = {"temperature": 200.0}

    result = selection_node(state)
    selection = result["sealing_state"]["selection"]
    assert selection["winner_candidate_id"] == "ptfe"
    assert selection["release_status"] == "inadmissible"
    assert selection["recommendation_artifact"]["release_status"] == "inadmissible"


def test_selection_node_blocks_candidate_on_limit_conflict():
    state = {
        "sealing_state": create_initial_state(),
        "relevant_fact_cards": [
            {
                "id": "fc-1",
                "evidence_id": "fc-1",
                "source_ref": "ptfe-card",
                "topic": "PTFE Properties",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                "tags": ["ptfe"],
                "retrieval_rank": 1,
                "retrieval_score": 0.9,
                "metadata": {},
            }
        ],
    }
    state["sealing_state"]["governance"]["release_status"] = "rfq_ready"
    state["sealing_state"]["governance"]["rfq_admissibility"] = "ready"
    state["sealing_state"]["asserted"]["operating_conditions"] = {"temperature": 300.0}

    result = selection_node(state)
    selection = result["sealing_state"]["selection"]
    assert selection["selection_status"] == "blocked_no_viable_candidates"
    assert selection["winner_candidate_id"] is None
    assert selection["release_status"] == "rfq_ready"
    assert selection["output_blocked"] is True
    assert selection["blocked_candidates"][0]["block_reason"] == "blocked_temperature_conflict"


def test_selection_node_blocks_candidate_on_pressure_conflict():
    state = {
        "sealing_state": create_initial_state(),
        "relevant_fact_cards": [
            {
                "id": "fc-1",
                "evidence_id": "fc-1",
                "source_ref": "ptfe-card",
                "topic": "PTFE Properties",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C und einen maximalen Druck von 50 bar.",
                "tags": ["ptfe"],
                "retrieval_rank": 1,
                "retrieval_score": 0.9,
                "metadata": {},
            }
        ],
    }
    state["sealing_state"]["governance"]["release_status"] = "rfq_ready"
    state["sealing_state"]["governance"]["rfq_admissibility"] = "ready"
    state["sealing_state"]["asserted"]["operating_conditions"] = {"temperature": 200.0, "pressure": 80.0}

    result = selection_node(state)
    selection = result["sealing_state"]["selection"]
    assert selection["selection_status"] == "blocked_no_viable_candidates"
    assert selection["winner_candidate_id"] is None
    assert selection["release_status"] == "rfq_ready"
    assert selection["output_blocked"] is True
    assert selection["blocked_candidates"][0]["block_reason"] == "blocked_pressure_conflict"
    assert selection["candidates"][0]["viability_status"] == "blocked_pressure_conflict"


def test_final_response_node_uses_selection_artifact():
    state = {
        "sealing_state": {
            "selection": {
                "selection_status": "blocked_no_candidates",
                "candidates": [],
                "viable_candidate_ids": [],
                "blocked_candidates": [],
                "winner_candidate_id": None,
                "recommendation_artifact": {
                    "selection_status": "blocked_no_candidates",
                    "winner_candidate_id": None,
                    "candidate_ids": [],
                    "viable_candidate_ids": [],
                    "blocked_candidates": [],
                    "evidence_basis": [],
                    "release_status": "inadmissible",
                    "rfq_admissibility": "inadmissible",
                    "specificity_level": "family_only",
                    "output_blocked": True,
                    "trace_provenance_refs": [],
                },
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "output_blocked": True,
            }
        }
    }

    result = final_response_node(state)
    assert result["messages"][0].content == "No governed recommendation can be released from the current evidence."


def test_evidence_tool_node_integration_conflict():
    sealing_state = create_initial_state()
    sealing_state["asserted"]["medium_profile"] = {"name": "Wasser"}
    sealing_state["governance"]["release_status"] = "rfq_ready"
    sealing_state["governance"]["rfq_admissibility"] = "ready"
    sealing_state["cycle"]["state_revision"] = 5

    tool_call = {
        "name": "submit_claim",
        "args": {
            "claim_type": ClaimType.FACT_OBSERVED,
            "statement": "Der Kunde sagt, das Medium ist Öl.",
            "confidence": 1.0,
            "source_fact_ids": ["input_2"],
        },
        "id": "call_999",
    }

    state = {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "sealing_state": sealing_state,
    }

    result = evidence_tool_node(state)
    new_sealing_state = result["sealing_state"]

    assert new_sealing_state["cycle"]["state_revision"] == 6
    conflicts = new_sealing_state["governance"]["conflicts"]
    assert len(conflicts) == 1
    assert conflicts[0]["severity"] == "CRITICAL"
    assert new_sealing_state["governance"]["release_status"] == "inadmissible"


def test_evidence_tool_node_persists_contract_ready_evidence_snapshot():
    sealing_state = create_initial_state()
    sealing_state["cycle"]["state_revision"] = 1

    tool_call = {
        "name": "submit_claim",
        "args": {
            "claim_type": ClaimType.FACT_OBSERVED,
            "statement": "Material ist PTFE, Grade G461, Hersteller Acme. Medium ist Wasser.",
            "confidence": 1.0,
            "source_fact_ids": ["fc-ready"],
        },
        "id": "call_ready",
    }
    state = {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "sealing_state": sealing_state,
        "relevant_fact_cards": [
            {
                "evidence_id": "fc-ready",
                "source_ref": "SRC-G461",
                "source_type": "manufacturer_datasheet",
                "source_rank": 1,
                "topic": "Acme G461",
                "content": "PTFE grade G461 fuer Acme.",
                "metadata": {
                    "material_family": "PTFE",
                    "grade_name": "G461",
                    "manufacturer_name": "Acme",
                    "product_line": "G-Series",
                    "revision_date": "2024-01-15",
                    "document_revision": "Rev. 3",
                    "temperature_max_c": 260,
                    "evidence_scope": ["grade_identity", "temperature_limit"],
                },
            }
        ],
    }

    result = evidence_tool_node(state)
    new_sealing_state = result["sealing_state"]

    assert new_sealing_state["governance"]["release_status"] == "rfq_ready"
    assert new_sealing_state["governance"]["rfq_admissibility"] == "ready"
    assert new_sealing_state["relevant_evidence"][0]["normalized_evidence"]["datasheet_contract"]["selection_readiness"]["rfq_ready_eligible"] is True


def test_evidence_tool_node_persists_contract_blockers_in_state_snapshot():
    sealing_state = create_initial_state()
    sealing_state["cycle"]["state_revision"] = 1

    tool_call = {
        "name": "submit_claim",
        "args": {
            "claim_type": ClaimType.FACT_OBSERVED,
            "statement": "Material ist PTFE, Grade G25, Hersteller Acme. Medium ist Wasser.",
            "confidence": 1.0,
            "source_fact_ids": ["fc-distributor"],
        },
        "id": "call_distributor",
    }
    state = {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "sealing_state": sealing_state,
        "relevant_fact_cards": [
            {
                "evidence_id": "fc-distributor",
                "source_ref": "SRC-DISTRIBUTOR",
                "source_type": "distributor_sheet",
                "source_rank": 1,
                "topic": "PTFE G25",
                "content": "PTFE grade G25 fuer Acme.",
                "metadata": {
                    "material_family": "PTFE",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "revision_date": "2024-01-15",
                    "document_revision": "Rev. 2",
                    "temperature_max_c": 260,
                    "evidence_scope": ["grade_identity"],
                },
            }
        ],
    }

    result = evidence_tool_node(state)
    new_sealing_state = result["sealing_state"]

    assert new_sealing_state["governance"]["release_status"] == "manufacturer_validation_required"
    assert new_sealing_state["governance"]["specificity_level"] != "compound_required"
    assert "distributor_sheet_ceiling_without_manufacturer_grade_sheet" in new_sealing_state["governance"]["unknowns_manufacturer_validation"]
    assert (
        "distributor_sheet_ceiling_without_manufacturer_grade_sheet"
        in new_sealing_state["relevant_evidence"][0]["normalized_evidence"]["datasheet_contract"]["selection_readiness"]["blocking_reasons"]
    )
