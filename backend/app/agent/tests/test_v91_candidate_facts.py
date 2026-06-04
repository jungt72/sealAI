from __future__ import annotations

import pytest

from app.agent.graph import GraphState
import app.agent.graph.nodes.intake_observe_node as observe_module
from app.agent.graph.nodes.assert_node import assert_node
from app.agent.graph.nodes.intake_observe_node import intake_observe_node
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    NormalizedParameter,
    NormalizedState,
    ObservedExtraction,
)
from app.agent.v91.candidate_facts import (
    append_candidate_facts,
    build_field_governance_decisions,
    candidate_fact_from_observed_extraction,
)


def test_candidate_fact_adapter_keeps_source_quote_and_confirmation_boundary() -> None:
    extraction = ObservedExtraction(
        field_name="medium",
        raw_value="Wasser-Glykol",
        source="llm",
        confidence=0.82,
        turn_index=4,
    )

    candidate = candidate_fact_from_observed_extraction(
        extraction,
        source_message="Medium ist Wasser-Glykol bei 80 °C.",
        source_message_id="user_turn:4",
        extraction_method="regex",
    )

    assert candidate.field_id == "medium"
    assert candidate.value == "Wasser-Glykol"
    assert candidate.source_message_id == "user_turn:4"
    assert candidate.source_quote == "Wasser-Glykol"
    assert candidate.extraction_method == "regex"
    assert candidate.requires_user_confirmation is True


def test_append_candidate_facts_dedupes_exact_same_source_candidate() -> None:
    extraction = ObservedExtraction(
        field_name="pressure_bar",
        raw_value=5,
        raw_unit="bar",
        confidence=0.92,
        turn_index=1,
    )
    candidate = candidate_fact_from_observed_extraction(
        extraction,
        source_message="5 bar",
        source_message_id="user_turn:1",
        extraction_method="regex",
    )

    merged = append_candidate_facts([candidate], [candidate])

    assert len(merged) == 1
    assert merged[0].unit == "bar"


@pytest.mark.asyncio
async def test_intake_observe_node_records_v91_candidate_facts(monkeypatch) -> None:
    monkeypatch.setattr(observe_module, "_ENABLE_LLM_EXTRACTION", False)
    state = GraphState(
        pending_message="Medium Wasser, Druck 5 bar, Temperatur 80 °C.",
        user_turn_index=3,
    )

    result = await intake_observe_node(state)

    assert result.v91_candidate_facts
    pressure = next(
        fact for fact in result.v91_candidate_facts if fact.field_id == "pressure_bar"
    )
    assert pressure.value == 5
    assert pressure.unit == "bar"
    assert pressure.source_message_id == "user_turn:3"
    assert pressure.extraction_method == "regex"
    assert pressure.requires_user_confirmation is True


def test_field_governance_decision_explains_asserted_case_update() -> None:
    candidate = candidate_fact_from_observed_extraction(
        ObservedExtraction(
            field_name="medium",
            raw_value="Wasser-Glykol",
            source="user",
            confidence=1.0,
            turn_index=5,
        ),
        source_message="Medium Wasser-Glykol",
        source_message_id="user_turn:5",
        extraction_method="manual",
    )
    normalized = NormalizedState(
        parameters={
            "medium": NormalizedParameter(
                field_name="medium",
                value="Wasser-Glykol",
                confidence="confirmed",
                source="user_override",
                status="user_stated",
                provenance="user_stated",
            )
        }
    )
    asserted = AssertedState(
        assertions={
            "medium": AssertedClaim(
                field_name="medium",
                asserted_value="Wasser-Glykol",
                confidence="confirmed",
                status="confirmed",
                provenance="user_stated",
            )
        }
    )

    decisions = build_field_governance_decisions(
        candidates=[candidate],
        normalized=normalized,
        asserted=asserted,
    )

    assert len(decisions) == 1
    assert decisions[0].field_id == "medium"
    assert decisions[0].decision == "accepted_to_case_state"
    assert decisions[0].case_revision_event_type == "new_value"
    assert decisions[0].requires_recompute is True


@pytest.mark.asyncio
async def test_assert_node_stores_v91_field_governance_decisions() -> None:
    candidate = candidate_fact_from_observed_extraction(
        ObservedExtraction(
            field_name="temperature_c",
            raw_value=80,
            raw_unit="°C",
            source="user",
            confidence=1.0,
            turn_index=1,
        ),
        source_message="Temperatur 80 °C",
        source_message_id="user_turn:1",
        extraction_method="manual",
    )
    state = GraphState(
        normalized=NormalizedState(
            parameters={
                "temperature_c": NormalizedParameter(
                    field_name="temperature_c",
                    value=80.0,
                    unit="°C",
                    confidence="confirmed",
                    source="user_override",
                    status="user_stated",
                    provenance="user_stated",
                )
            }
        ),
        v91_candidate_facts=[candidate],
    )

    result = await assert_node(state)

    decision = next(
        item
        for item in result.v91_field_governance_decisions
        if item.field_id == "temperature_c"
    )
    assert decision.decision == "accepted_to_case_state"
    assert decision.requires_user_confirmation is False
