from __future__ import annotations

import pytest

from app.agent.domain.normalization import normalize_sealing_type_value
from app.agent.graph import GraphState
from app.agent.graph import output_contract_assembly as output_assembly
import app.agent.graph.nodes.intake_observe_node as intake_module
from app.agent.graph.nodes.assert_node import assert_node
from app.agent.graph.nodes.governance_node import governance_node
from app.agent.graph.nodes.normalize_node import normalize_node
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    ConversationMessage,
    ObservedExtraction,
    ObservedState,
    PendingQuestion,
    UserOverride,
)
from app.agent.state.reducers import (
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)


def _claim(field: str, value, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field, asserted_value=value, confidence=confidence)


def _strategy(state: GraphState):
    return output_assembly.build_governed_conversation_strategy_contract(
        state,
        "structured_clarification",
    )


async def _run_pipeline(state: GraphState) -> GraphState:
    for node in (
        intake_module.intake_observe_node,
        normalize_node,
        assert_node,
        governance_node,
    ):
        state = await node(state)
    response_class = output_assembly._determine_response_class(state)
    strategy = output_assembly.build_governed_conversation_strategy_contract(
        state,
        response_class,
    )
    pending_question = output_assembly._pending_question_from_strategy(
        state=state,
        response_class=response_class,
        strategy=strategy,
    )
    return state.model_copy(
        update={
            "output_response_class": response_class,
            "pending_question": pending_question,
        }
    )


@pytest.fixture(autouse=True)
def _disable_llm_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intake_module, "_ENABLE_LLM_EXTRACTION", False)


def test_temperature_known_not_reasked() -> None:
    normalized = reduce_observed_to_normalized(
        ObservedState().with_extraction(
            ObservedExtraction(
                field_name="temperature_c",
                raw_value=30.0,
                raw_unit="°C",
                source="user",
                confidence=0.92,
                turn_index=2,
            )
        )
    )
    state = GraphState(
        normalized=normalized,
        asserted=AssertedState(
            assertions={
                "medium": _claim("medium", "Wasser"),
                "pressure_bar": _claim("pressure_bar", 2.0),
            },
            blocking_unknowns=["temperature_c", "sealing_type"],
        ),
    )

    strategy = _strategy(state)

    assert normalized.parameters["temperature_c"].value == 30.0
    assert strategy.focus_key != "temperature_c"
    assert strategy.primary_question is not None
    assert "Temperatur" not in strategy.primary_question


def test_placeholder_medium_not_known() -> None:
    normalized = reduce_observed_to_normalized(
        ObservedState().with_override(
            UserOverride(
                field_name="medium",
                override_value="das medium",
                turn_index=1,
            )
        )
    )
    asserted = reduce_normalized_to_asserted(normalized)
    medium_param = normalized.parameters["medium"]

    assert medium_param.value is None
    assert medium_param.confidence == "requires_confirmation"
    assert medium_param.status == "invalid"
    assert "medium" not in asserted.assertions
    assert "medium" in asserted.blocking_unknowns

    strategy = _strategy(
        GraphState(
            normalized=normalized,
            asserted=asserted,
        )
    )

    assert strategy.focus_key == "medium"
    assert strategy.primary_question == "Welches Medium soll abgedichtet werden?"


@pytest.mark.asyncio
async def test_rwdr_closes_sealing_type_pending_question() -> None:
    state = await _run_pipeline(
        GraphState(
            pending_message="einen RWDR",
            pending_question=PendingQuestion(
                target_field="sealing_type",
                expected_answer_type="seal_type_value",
                question_text="Um welchen Dichtungstyp oder welches Dichtprinzip geht es?",
                asked_at_turn_id=1,
                source="governed_next_question",
                ambiguity_policy="clarify_if_broad_or_hazardous",
                status="open",
            ),
            conversation_messages=[
                ConversationMessage(
                    role="assistant",
                    content="Um welchen Dichtungstyp geht es?",
                ),
                ConversationMessage(role="user", content="einen RWDR"),
            ],
            user_turn_index=2,
        )
    )

    assert state.last_slot_answer_binding is not None
    assert state.last_slot_answer_binding.target_field == "sealing_type"
    assert state.last_slot_answer_binding.normalized_value == "rwdr"
    assert state.asserted.assertions["sealing_type"].asserted_value == "rwdr"
    assert "sealing_type" not in state.asserted.blocking_unknowns
    assert state.pending_question is None or state.pending_question.target_field != "sealing_type"


@pytest.mark.parametrize(
    "alias",
    [
        "RWDR",
        "einen RWDR",
        "Radialwellendichtring",
        "Wellendichtring",
        "Simmerring",
        "Simmering",
    ],
)
def test_rwdr_aliases_normalize_consistently(alias: str) -> None:
    assert normalize_sealing_type_value(alias) == "rwdr"


def test_one_mandatory_question_with_reason() -> None:
    strategy = _strategy(
        GraphState(
            asserted=AssertedState(
                blocking_unknowns=["medium", "temperature_c", "sealing_type"]
            ),
        )
    )

    assert strategy.response_mode == "single_question"
    assert strategy.primary_question is not None
    assert strategy.primary_question_reason is not None
    assert strategy.primary_question_reason.strip()
