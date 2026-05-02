from __future__ import annotations

import pytest

from app.agent.graph import output_contract_assembly as output_assembly
from app.agent.graph import GraphState
from app.agent.graph.nodes.assert_node import assert_node
from app.agent.graph.nodes.governance_node import governance_node
import app.agent.graph.nodes.intake_observe_node as intake_module
from app.agent.graph.nodes.normalize_node import normalize_node
from app.agent.state.models import ConversationMessage, PendingQuestion
from app.domain.pre_gate_classification import PreGateClassification
from app.services.pre_gate_classifier import PreGateClassifier


async def _run_pipeline(state: GraphState, *, include_output: bool = True) -> GraphState:
    nodes = [
        intake_module.intake_observe_node,
        normalize_node,
        assert_node,
        governance_node,
    ]
    for node in nodes:
        state = await node(state)
    if include_output:
        response_class = output_assembly._determine_response_class(state)
        strategy = output_assembly.build_governed_conversation_strategy_contract(state, response_class)
        reply = await output_assembly._build_reply(state, response_class, strategy=strategy)
        pending_question = output_assembly._pending_question_from_strategy(
            state=state,
            response_class=response_class,
            strategy=strategy,
        )
        state = state.model_copy(
            update={
                "output_response_class": response_class,
                "output_reply": reply,
                "pending_question": pending_question,
            }
        )
    return state


def _pending_medium_question(*, question_text: str | None = "Bitte nenne das abzudichtende Fluid?") -> PendingQuestion:
    return PendingQuestion(
        target_field="medium",
        expected_answer_type="medium_value",
        question_text=question_text,
        asked_at_turn_id=1,
        source="governed_next_question",
        ambiguity_policy="clarify_if_broad_or_hazardous",
        status="open",
    )


async def _run_answer_to_pending_medium(message: str) -> GraphState:
    return await _run_pipeline(
        GraphState(
            pending_message=message,
            pending_question=_pending_medium_question(),
            conversation_messages=[
                ConversationMessage(role="assistant", content="Andere Formulierung ohne Slot-Schlüsselwort."),
                ConversationMessage(role="user", content=message),
            ],
            user_turn_index=2,
        )
    )


@pytest.fixture(autouse=True)
def _disable_llm_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intake_module, "_ENABLE_LLM_EXTRACTION", False)


def test_pending_question_state_model_carries_structured_slot_metadata() -> None:
    pending = _pending_medium_question(question_text="Welcher Stoff liegt an?")

    assert pending.target_field == "medium"
    assert pending.expected_answer_type == "medium_value"
    assert pending.status == "open"
    assert pending.source == "governed_next_question"
    assert pending.question_text == "Welcher Stoff liegt an?"


@pytest.mark.asyncio
async def test_pending_question_is_written_from_structured_next_question_decision() -> None:
    message = "ich möchte mit dir eine dichtungslösung erarbeiten"
    state = await _run_pipeline(
        GraphState(
            pending_message=message,
            conversation_messages=[ConversationMessage(role="user", content=message)],
            user_turn_index=1,
        )
    )

    assert state.pending_question is not None
    assert state.pending_question.target_field == "medium"
    assert state.pending_question.expected_answer_type == "medium_value"
    assert state.pending_question.source == "governed_next_question"
    assert state.pending_question.status == "open"
    assert state.pending_question.question_text == "Welches Medium soll abgedichtet werden?"


@pytest.mark.asyncio
async def test_short_answer_binds_through_pending_question_without_assistant_text_dependency() -> None:
    state = await _run_answer_to_pending_medium("chlor")

    assert state.last_slot_answer_binding is not None
    assert state.last_slot_answer_binding.target_field == "medium"
    assert state.last_slot_answer_binding.source == "pending_question"
    assert state.pending_question is None or state.pending_question.target_field != "medium"
    assert state.asserted.assertions["medium"].asserted_value == "Chlor"


@pytest.mark.asyncio
async def test_changed_assistant_wording_does_not_break_pending_medium_binding() -> None:
    state = await _run_pipeline(
        GraphState(
            pending_message="chlor",
            pending_question=_pending_medium_question(question_text="Welcher Stoff liegt direkt an?"),
            conversation_messages=[
                ConversationMessage(role="assistant", content="Kurz gesagt: nenne mir bitte den Stoff."),
                ConversationMessage(role="user", content="chlor"),
            ],
            user_turn_index=2,
        )
    )

    assert state.last_slot_answer_binding is not None
    assert state.last_slot_answer_binding.target_field == "medium"
    assert state.asserted.assertions["medium"].asserted_value == "Chlor"


@pytest.mark.asyncio
async def test_pending_medium_chlor_binds_as_ambiguous_and_asks_specific_clarification() -> None:
    state = await _run_answer_to_pending_medium("chlor")

    assert state.last_slot_answer_binding is not None
    assert state.last_slot_answer_binding.ambiguity is True
    assert state.last_slot_answer_binding.needs_clarification is True
    assert state.asserted.assertions["medium"].asserted_value == "Chlor"
    assert "medium" not in state.asserted.blocking_unknowns
    assert "Medium angeben" not in state.output_reply
    assert "Chlor" in state.output_reply
    assert "Chlorgas" in state.output_reply
    assert "Chlorwasser" in state.output_reply
    assert "Natriumhypochlorit" in state.output_reply
    assert state.output_response_class == "structured_clarification"
    assert state.rfq.rfq_ready is False
    assert "geeignet" not in state.output_reply.casefold()
    assert "freigegeben" not in state.output_reply.casefold()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("wasser", "Wasser"),
        ("öl", "Öl"),
        ("salzwasser", "Salzwasser"),
        ("dampf", "Dampf"),
        ("natronlauge", "Natronlauge"),
    ],
)
async def test_pending_medium_short_answer_binds_supported_media(message: str, expected: str) -> None:
    state = await _run_answer_to_pending_medium(message)

    assert state.last_slot_answer_binding is not None
    assert state.last_slot_answer_binding.target_field == "medium"
    assert state.last_slot_answer_binding.source == "pending_question"
    assert state.asserted.assertions["medium"].asserted_value == expected
    assert "medium" not in state.asserted.blocking_unknowns
    assert "Medium angeben" not in state.output_reply
    assert state.rfq.rfq_ready is False


@pytest.mark.asyncio
async def test_short_answer_without_pending_question_does_not_bind_chlor() -> None:
    state = await _run_pipeline(
        GraphState(
            pending_message="chlor",
            conversation_messages=[ConversationMessage(role="user", content="chlor")],
            user_turn_index=1,
        )
    )

    assert state.last_slot_answer_binding is None
    assert "medium" not in state.normalized.parameters
    assert "medium" not in state.asserted.assertions
    assert "medium" in state.asserted.blocking_unknowns


def test_existing_routing_boundaries_remain_unchanged() -> None:
    classifier = PreGateClassifier()

    assert classifier.classify(
        "Ich habe eine rotierende Welle mit 80 mm Durchmesser, 1500 rpm und Öl bei 90 Grad."
    ).classification == PreGateClassification.DOMAIN_INQUIRY
    assert classifier.classify("Was bedeutet PFAS für Dichtungen?").classification == PreGateClassification.KNOWLEDGE_QUERY
    assert classifier.classify("Was ist bei Salzwasser und Dichtungen kritisch?").classification == PreGateClassification.KNOWLEDGE_QUERY
    assert classifier.classify("Vergleiche FKM und EPDM für Dichtungen.").classification == PreGateClassification.KNOWLEDGE_QUERY
    assert classifier.classify("Hallo, wie geht es dir?").classification == PreGateClassification.GREETING
