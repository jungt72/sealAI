from __future__ import annotations

from app.agent.communication.conversation_controller_v7 import (
    ConversationControllerInput,
    ConversationControllerV7,
)
from app.agent.communication.v7_contracts import AnswerMode, MutationPolicy
from app.agent.state.models import PendingQuestion
from app.domain.conversation_intent import (
    ConversationIntent,
    ResponseMode,
    classify_conversation_route,
)
from app.domain.pre_gate_classification import PreGateClassification
from app.services.pre_gate_classifier import PreGateClassifier


def _pending_medium_question() -> PendingQuestion:
    return PendingQuestion(
        target_field="medium",
        expected_answer_type="medium_value",
        question_text="Welches Medium soll abgedichtet werden?",
        ambiguity_policy="clarify_if_broad_or_hazardous",
        source="governed_next_question",
        status="open",
    )


def test_definition_intent_with_modifier_routes_to_knowledge_not_case_intake() -> None:
    message = "Was genau bedeutet HLP 46?"

    pre_gate = PreGateClassifier().classify(message)
    route = classify_conversation_route(
        message,
        pre_gate_classification=pre_gate.classification,
    )

    assert pre_gate.classification is PreGateClassification.KNOWLEDGE_QUERY
    assert pre_gate.escalate_to_graph is False
    assert route.intent is ConversationIntent.general_sealing_question
    assert route.response_mode is ResponseMode.knowledge_answer
    assert route.no_durable_engineering_case_state is True


def test_active_case_definition_intent_becomes_side_question_not_medium_value() -> None:
    message = "Was genau bedeutet HLP 46?"
    pre_gate = PreGateClassifier().classify(message)

    decision = ConversationControllerV7().decide(
        ConversationControllerInput(
            user_message=message,
            pre_gate_classification=pre_gate.classification,
            pre_gate_confidence=pre_gate.confidence,
            pre_gate_reason=pre_gate.reasoning,
            active_case_exists=True,
            pending_question=_pending_medium_question(),
        )
    )

    assert decision.answer_mode == AnswerMode.ACTIVE_CASE_SIDE_QUESTION.value
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN.value
    assert decision.resume_strategy == "reevaluate_after_answer"
