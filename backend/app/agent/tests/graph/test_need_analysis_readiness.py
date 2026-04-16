from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.assert_node import assert_node
from app.agent.graph.nodes.compute_node import compute_node
from app.agent.graph.nodes.governance_node import governance_node
from app.agent.graph.nodes.intake_observe_node import intake_observe_node
from app.agent.graph.nodes.normalize_node import normalize_node
from app.agent.graph.nodes.output_contract_node import output_contract_node


async def _run_governed_turn(message: str) -> GraphState:
    state = GraphState(pending_message=message)
    with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
        state = await intake_observe_node(state)
    state = await normalize_node(state)
    state = await assert_node(state)
    state = await compute_node(state)
    state = await governance_node(state)
    state = await output_contract_node(state)
    return state


@pytest.mark.asyncio
async def test_gleitring_salzwasser_turn_does_not_jump_to_preselection() -> None:
    state = await _run_governed_turn(
        "Ich brauche eine Gleitringdichtung fuer 80°C Salzwasser, 50 mm Welle, 6000 U/min."
    )

    assert "sealing_type" in state.asserted.assertions
    assert state.asserted.assertions["sealing_type"].asserted_value == "mechanical_seal"
    assert state.output_response_class == "structured_clarification"
    assert state.output_response_class != "technical_preselection"
    assert "pressure_bar" in state.output_public["missing_fields"]


@pytest.mark.asyncio
async def test_chemical_pump_uses_duty_profile_but_blocks_on_missing_sealing_type() -> None:
    state = await _run_governed_turn(
        "Dichtung fuer chemische Pumpe, 10 bar, 90°C, Medium Salzsaeure, Betrieb 24/7."
    )

    assert state.asserted.assertions["duty_profile"].asserted_value == "continuous"
    assert "sealing_type" in state.governance.preselection_blockers
    assert state.output_response_class == "structured_clarification"
    assert state.output_reply.count("?") == 1
    assert state.output_response_class != "technical_preselection"


@pytest.mark.asyncio
async def test_rwdr_turn_tracks_contamination_and_duty_without_preselection_overclaim() -> None:
    state = await _run_governed_turn(
        "RWDR fuer 40 mm Welle, Oel, 3 bar, gelegentlicher Betrieb, etwas Schmutz."
    )

    assert state.asserted.assertions["sealing_type"].asserted_value == "rwdr"
    assert state.asserted.assertions["duty_profile"].asserted_value == "intermittent"
    assert state.asserted.assertions["contamination"].asserted_value == "solids_or_particles"
    assert state.output_response_class == "structured_clarification"
    assert "temperature_c" in state.output_public["missing_fields"]


@pytest.mark.asyncio
async def test_food_industry_turn_tracks_industry_and_avoids_false_preselection() -> None:
    state = await _run_governed_turn("Welche Dichtung eignet sich fuer Lebensmittelbereich bei 120°C?")

    assert state.asserted.assertions["industry"].asserted_value == "food_pharma"
    assert state.output_response_class == "structured_clarification"
    assert state.output_response_class != "technical_preselection"
    assert "medium" in state.output_public["missing_fields"]
