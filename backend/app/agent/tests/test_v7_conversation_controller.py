from __future__ import annotations

from app.agent.communication.conversation_controller_v7 import (
    ConversationControllerInput,
    ConversationControllerV7,
)
from app.agent.communication.v7_contracts import AnswerMode, MutationPolicy, ResumeStrategy
from app.agent.graph.slot_answer_binding import resolve_slot_answer_binding
from app.agent.state.models import PendingQuestion
from app.services.pre_gate_classifier import PreGateClassifier


def _decide(message: str, *, active_case: bool = False, pending_question: PendingQuestion | None = None):
    pre_gate = PreGateClassifier().classify(message)
    binding = resolve_slot_answer_binding(
        pending_question=pending_question,
        message=message,
        turn_index=1,
    )
    return ConversationControllerV7().decide(
        ConversationControllerInput(
            user_message=message,
            pre_gate_classification=pre_gate.classification,
            pre_gate_confidence=pre_gate.confidence,
            pre_gate_reason=pre_gate.reasoning,
            active_case_exists=active_case,
            pending_question=pending_question,
            slot_answer_binding=binding,
        )
    )


def _medium_pending_question() -> PendingQuestion:
    return PendingQuestion(
        target_field="medium",
        expected_answer_type="medium_value",
        question_text="Welches Medium soll abgedichtet werden?",
        ambiguity_policy="clarify_if_broad_or_hazardous",
        status="open",
    )


def test_no_case_material_comparison_becomes_answer_only_turn_decision() -> None:
    decision = _decide("Vergleiche FKM und EPDM fuer Dichtungen.")

    assert decision.answer_mode == AnswerMode.MATERIAL_COMPARISON
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN
    assert decision.case_relevance == "no_case"
    assert "do_not_create_case" in decision.answer_obligations


def test_active_case_material_comparison_becomes_side_question_not_intake() -> None:
    pending = _medium_pending_question()
    decision = _decide("und FKM mit NBR?", active_case=True, pending_question=pending)

    assert decision.answer_mode == AnswerMode.ACTIVE_CASE_SIDE_QUESTION
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN
    assert decision.resume_strategy == ResumeStrategy.RESTORE_TO_PENDING_QUESTION_V1
    assert decision.resume_target_candidate is not None
    assert decision.resume_target_candidate.target_field == "medium"


def test_pending_medium_short_answer_becomes_pending_slot_turn_decision() -> None:
    pending = _medium_pending_question()
    decision = _decide("chlor", active_case=True, pending_question=pending)

    assert decision.answer_mode == AnswerMode.PENDING_SLOT_ANSWER
    assert decision.mutation_policy == MutationPolicy.PROPOSED
    assert decision.state_actions[0].field == "medium"
    assert decision.state_actions[0].needs_clarification is True
    assert "do_not_claim_material_suitability" in decision.answer_obligations


def test_smalltalk_is_answer_only_even_with_active_case_context() -> None:
    decision = _decide("moin, wie laeufts bei dir?", active_case=True, pending_question=_medium_pending_question())

    assert decision.answer_mode == AnswerMode.SMALLTALK
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN
    assert decision.resume_strategy == ResumeStrategy.NONE


def test_process_question_preserves_pending_resume_target() -> None:
    pending = _medium_pending_question()
    decision = _decide("Warum fragst du das?", active_case=True, pending_question=pending)

    assert decision.answer_mode == AnswerMode.ACTIVE_CASE_PROCESS_QUESTION
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN
    assert decision.resume_strategy == ResumeStrategy.REEVALUATE_AFTER_ANSWER
    assert decision.resume_target_candidate is not None
    assert decision.resume_target_candidate.target_field == "medium"


def test_active_case_help_question_classifies_as_process_question_with_pending_medium() -> None:
    pending = _medium_pending_question()
    decision = _decide(
        "Wie kannst du mir bei meiner Dichtungssituation helfen?",
        active_case=True,
        pending_question=pending,
    )

    assert decision.answer_mode == AnswerMode.ACTIVE_CASE_PROCESS_QUESTION
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN
    assert decision.resume_strategy == ResumeStrategy.REEVALUATE_AFTER_ANSWER
    assert "answer_latest_user_question_first" in decision.answer_obligations
    assert "do_not_mutate_case_state" in decision.answer_obligations


def test_pending_medium_answer_wasser_still_binds_as_slot_answer() -> None:
    pending = _medium_pending_question()
    decision = _decide("Wasser", active_case=True, pending_question=pending)

    assert decision.answer_mode == AnswerMode.PENDING_SLOT_ANSWER
    assert decision.answer_mode != AnswerMode.ACTIVE_CASE_PROCESS_QUESTION
    assert decision.mutation_policy in {
        MutationPolicy.PROPOSED,
        MutationPolicy.ALLOWED_BY_VALIDATOR,
    }


def test_pending_medium_explicit_answer_still_binds_as_slot_answer() -> None:
    pending = _medium_pending_question()
    decision = _decide("Das Medium ist Wasser.", active_case=True, pending_question=pending)

    assert decision.answer_mode == AnswerMode.PENDING_SLOT_ANSWER
    assert decision.answer_mode != AnswerMode.ACTIVE_CASE_PROCESS_QUESTION
    assert decision.state_actions[0].field == "medium"
    assert decision.state_actions[0].value == "Wasser"


def test_mixed_medium_value_and_why_question_routes_as_process_question_for_resume_reevaluation() -> None:
    pending = _medium_pending_question()
    decision = _decide(
        "Das Medium ist Wasser. Warum ist das wichtig?",
        active_case=True,
        pending_question=pending,
    )

    assert decision.answer_mode == AnswerMode.ACTIVE_CASE_PROCESS_QUESTION
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN
    assert decision.resume_strategy == ResumeStrategy.REEVALUATE_AFTER_ANSWER


def test_concrete_application_remains_governed_intake() -> None:
    decision = _decide("Ich habe eine rotierende Welle mit 80 mm Durchmesser, 1500 rpm und Oel bei 90 Grad.")

    assert decision.answer_mode == AnswerMode.GOVERNED_INTAKE
    assert decision.mutation_policy == MutationPolicy.PROPOSED
    assert decision.case_relevance == "new_case_candidate"
