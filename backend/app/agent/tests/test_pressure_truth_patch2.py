from __future__ import annotations

import pytest

from app.agent.domain.checks_registry import build_registered_check_results
from app.agent.domain.normalization import extract_parameters
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
)
from app.agent.state.reducers import reduce_observed_to_normalized


def _claim(field: str, value, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field, asserted_value=value, confidence=confidence)


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


def _strategy(state: GraphState):
    return output_assembly.build_governed_conversation_strategy_contract(
        state,
        "structured_clarification",
    )


@pytest.fixture(autouse=True)
def _disable_llm_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intake_module, "_ENABLE_LLM_EXTRACTION", False)


@pytest.mark.asyncio
async def test_pressure_system_answer_sets_system_pressure_only() -> None:
    state = await _run_pipeline(
        GraphState(
            pending_message="5 bar Systemdruck",
            pending_question=PendingQuestion(
                target_field="pressure_bar",
                expected_answer_type="pressure_value_or_context",
                question_text="Wie hoch ist der Druck und worauf bezieht er sich?",
                asked_at_turn_id=1,
                source="governed_next_question",
                ambiguity_policy="clarify_if_broad_or_hazardous",
                status="open",
            ),
            conversation_messages=[
                ConversationMessage(
                    role="assistant", content="Wie hoch ist der Druck?"
                ),
                ConversationMessage(role="user", content="5 bar Systemdruck"),
            ],
            user_turn_index=2,
        )
    )

    assert state.last_slot_answer_binding is not None
    assert state.last_slot_answer_binding.target_field == "pressure_system_bar"
    assert state.asserted.assertions["pressure_system_bar"].asserted_value == 5.0
    assert "pressure_at_seal_bar" not in state.asserted.assertions
    assert "pressure_delta_bar" not in state.asserted.assertions


@pytest.mark.asyncio
async def test_ambiguous_pressure_requires_role_clarification() -> None:
    state = await _run_pipeline(
        GraphState(
            pending_message="5 bar",
            conversation_messages=[ConversationMessage(role="user", content="5 bar")],
            user_turn_index=1,
        )
    )

    assert state.normalized.parameters["ambiguous_pressure_bar"].value == 5.0

    strategy = _strategy(
        state.model_copy(
            update={
                "asserted": AssertedState(
                    assertions={
                        "medium": _claim("medium", "Wasser"),
                        "temperature_c": _claim("temperature_c", 30.0),
                    },
                    blocking_unknowns=["pressure_bar"],
                )
            }
        )
    )

    assert strategy.focus_key == "pressure_bar"
    assert strategy.primary_question is not None
    assert "Systemdruck" in strategy.primary_question
    assert "Druck direkt an der Dichtung" in strategy.primary_question
    assert "Differenzdruck" in strategy.primary_question
    assert strategy.primary_question_reason is not None
    assert "Dichtungsdruck" in strategy.primary_question_reason


@pytest.mark.asyncio
async def test_direct_seal_pressure_closes_pressure_role() -> None:
    state = await _run_pipeline(
        GraphState(
            pending_message="5 bar direkt an der Dichtung",
            conversation_messages=[
                ConversationMessage(role="user", content="5 bar direkt an der Dichtung")
            ],
            user_turn_index=1,
        )
    )

    assert state.normalized.parameters["pressure_at_seal_bar"].value == 5.0

    strategy = _strategy(
        state.model_copy(
            update={
                "asserted": AssertedState(
                    assertions={
                        "medium": _claim("medium", "Wasser"),
                        "temperature_c": _claim("temperature_c", 30.0),
                    },
                    blocking_unknowns=["pressure_bar"],
                )
            }
        )
    )

    assert strategy.focus_key != "pressure_bar"
    assert (
        strategy.primary_question is None
        or "Systemdruck" not in strategy.primary_question
    )


@pytest.mark.asyncio
async def test_differential_pressure_maps_to_pressure_delta() -> None:
    state = await _run_pipeline(
        GraphState(
            pending_message="1,5 bar Differenzdruck über der Dichtung",
            conversation_messages=[
                ConversationMessage(
                    role="user",
                    content="1,5 bar Differenzdruck über der Dichtung",
                )
            ],
            user_turn_index=1,
        )
    )

    assert state.normalized.parameters["pressure_delta_bar"].value == 1.5
    assert "pressure_system_bar" not in state.normalized.parameters


def test_checks_do_not_use_system_pressure_as_seal_pressure() -> None:
    checks = build_registered_check_results(
        profile={
            "shaft_diameter_mm": 40.0,
            "speed_rpm": 1450,
            "sealing_type": "rwdr",
            "pressure_system_bar": 5.0,
        },
        engineering_path="rwdr",
        technical_derivations=[
            {
                "calc_type": "rwdr",
                "pv_value_mpa_m_s": 99.0,
                "pressure_window": "must not be exposed",
                "status": "ok",
            }
        ],
    )
    by_id = {item["calc_id"]: item for item in checks}

    assert by_id["rwdr_pv_precheck"]["status"] == "blocked"
    assert by_id["rwdr_pv_precheck"]["value"] is None
    assert "pressure_at_seal_bar" in by_id["rwdr_pv_precheck"]["missing_inputs"]
    assert by_id["rwdr_pressure_window"]["status"] == "blocked"
    assert by_id["rwdr_pressure_window"]["value"] is None


@pytest.mark.parametrize(
    ("raw_value", "expected_field"),
    [
        ("5 bar system_pressure", "pressure_system_bar"),
        ("5 bar direct_at_seal", "pressure_at_seal_bar"),
        ("5 bar differential", "pressure_delta_bar"),
    ],
)
def test_legacy_pressure_bar_interpretation_adapter(
    raw_value: str,
    expected_field: str,
) -> None:
    normalized = reduce_observed_to_normalized(
        ObservedState().with_extraction(
            ObservedExtraction(
                field_name="pressure_bar",
                raw_value=raw_value,
                source="user",
                confidence=0.92,
                turn_index=1,
            )
        )
    )

    assert normalized.parameters[expected_field].value == 5.0


def test_extract_parameters_maps_pressure_roles() -> None:
    assert extract_parameters("5 bar Systemdruck")["pressure_system_bar"] == 5.0
    assert (
        extract_parameters("5 bar direkt an der Dichtung")["pressure_at_seal_bar"]
        == 5.0
    )
    assert (
        extract_parameters("1,5 bar Differenzdruck über der Dichtung")[
            "pressure_delta_bar"
        ]
        == 1.5
    )
    assert extract_parameters("5 bar")["ambiguous_pressure_bar"] == 5.0
