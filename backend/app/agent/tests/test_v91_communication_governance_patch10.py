from __future__ import annotations

from app.agent.communication.governed_answer_context import build_governed_answer_context
from app.agent.state.models import ConversationStrategyContract, GovernedSessionState
from app.agent.v91.communication_guard import validate_communication_guard
from app.agent.v91.contracts import (
    CaseBinding,
    CommunicationPlan,
    DomainRelevance,
    FinalAnswerContext,
    KnowledgePolicy,
    KnowledgeRagPolicy,
    LLMFreedomDecision,
    LLMFreedomLevel,
    QuestionPlan,
    ResponseAction,
    ResponseMove,
    ResponsePolicy,
    SemanticBoundaryDecision,
    SemanticIntent,
)


def _values(items: list[object]) -> set[str]:
    return {str(getattr(item, "value", item)) for item in items}


def _context(
    *,
    communication_plan: CommunicationPlan,
    question_plan: QuestionPlan | None = None,
) -> FinalAnswerContext:
    return FinalAnswerContext(
        semantic_boundary=SemanticBoundaryDecision(
            intent=SemanticIntent.CASE_INTAKE,
            domain_relevance=DomainRelevance.CONCRETE_SEALING_CASE,
            case_binding=CaseBinding.ACTIVE_CASE_CONTEXT,
        ),
        freedom_decision=LLMFreedomDecision(
            level=LLMFreedomLevel.RESTRICTED_CASE_CLAIMS,
            forbidden_actions=["final_engineering_release"],
            reason="test",
        ),
        response_policy=ResponsePolicy(
            action=(
                ResponseAction.WAIT_FOR_USER
                if communication_plan.ask_user_question
                else ResponseAction.ANSWER_ONLY
            ),
            answer_first=communication_plan.answer_first,
            max_primary_questions=communication_plan.max_new_questions,
            reason="test",
        ),
        knowledge_policy=KnowledgePolicy(
            rag_policy=KnowledgeRagPolicy.NOT_NEEDED,
            reason="test",
        ),
        question_plan=question_plan,
        communication_plan=communication_plan,
    )


def test_communication_plan_has_v91_control_fields() -> None:
    plan = CommunicationPlan()

    assert _values(plan.response_moves) >= {
        ResponseMove.ACKNOWLEDGE.value,
        ResponseMove.ANSWER.value,
    }
    assert plan.answer_first is False
    assert plan.ask_user_question is False
    assert plan.max_new_questions == 1
    assert plan.question_justification_required is False
    assert plan.tab_update_visibility == "silent"
    assert plan.source_disclosure_mode == "none"
    assert plan.max_findings_to_mention == 2


def test_question_plan_builds_answer_then_ask_plan() -> None:
    strategy = ConversationStrategyContract(
        focus_key="medium",
        primary_question="Welches Medium beruehrt die Dichtung genau?",
        primary_question_reason="Das Medium bestimmt Werkstoff- und Quellrisiken.",
        response_mode="single_question",
    )

    governed_context = build_governed_answer_context(
        GovernedSessionState(),
        strategy=strategy,
        response_class="structured_clarification",
    )

    assert governed_context.v91_final_answer_context is not None
    plan = governed_context.v91_final_answer_context.communication_plan
    assert plan is not None
    assert plan.ask_user_question is True
    assert plan.max_new_questions == 1
    assert plan.question_justification_required is True
    assert _values(plan.response_moves) >= {
        ResponseMove.ANSWER.value,
        ResponseMove.JUSTIFY_QUESTION.value,
        ResponseMove.CLARIFY.value,
    }


def test_communication_guard_blocks_too_many_questions() -> None:
    question_plan = QuestionPlan(
        ask_now=True,
        primary_question="Welches Medium beruehrt die Dichtung genau?",
        reason="Das Medium bestimmt Werkstoff- und Quellrisiken.",
    )
    plan = CommunicationPlan(
        ask_user_question=True,
        max_new_questions=1,
        question_justification_required=True,
        primary_question=question_plan.primary_question,
        primary_question_reason=question_plan.reason,
    )

    result = validate_communication_guard(
        "Das Medium ist wichtig. Welches Medium? Welche Temperatur?",
        _context(communication_plan=plan, question_plan=question_plan),
    )

    assert result.passed is False
    assert "communication_guard:too_many_questions" in result.findings


def test_communication_guard_blocks_missing_question_reason() -> None:
    question_plan = QuestionPlan(
        ask_now=True,
        primary_question="Welches Medium beruehrt die Dichtung genau?",
        reason="Das Medium bestimmt Werkstoff- und Quellrisiken.",
    )
    plan = CommunicationPlan(
        ask_user_question=True,
        max_new_questions=1,
        question_justification_required=True,
        primary_question=question_plan.primary_question,
        primary_question_reason=question_plan.reason,
    )

    result = validate_communication_guard(
        "Welches Medium beruehrt die Dichtung genau?",
        _context(communication_plan=plan, question_plan=question_plan),
    )

    assert result.passed is False
    assert "communication_guard:missing_question_reason" in result.findings


def test_communication_guard_allows_question_with_reason() -> None:
    question_plan = QuestionPlan(
        ask_now=True,
        primary_question="Welches Medium beruehrt die Dichtung genau?",
        reason="Das Medium bestimmt Werkstoff- und Quellrisiken.",
    )
    plan = CommunicationPlan(
        ask_user_question=True,
        max_new_questions=1,
        question_justification_required=True,
        primary_question=question_plan.primary_question,
        primary_question_reason=question_plan.reason,
    )

    result = validate_communication_guard(
        "Das Medium ist wichtig fuer Werkstoff- und Quellrisiken. Welches Medium beruehrt die Dichtung genau?",
        _context(communication_plan=plan, question_plan=question_plan),
    )

    assert result.passed is True
    assert "communication_guard:missing_question_reason" not in result.findings


def test_communication_guard_blocks_answer_first_missing() -> None:
    question_plan = QuestionPlan(
        ask_now=True,
        primary_question="Welches Medium beruehrt die Dichtung genau?",
        reason="Das Medium bestimmt Werkstoff- und Quellrisiken.",
    )
    plan = CommunicationPlan(
        answer_first=True,
        ask_user_question=True,
        max_new_questions=1,
        question_justification_required=True,
        user_question_must_be_answered=True,
        primary_question=question_plan.primary_question,
        primary_question_reason=question_plan.reason,
    )

    result = validate_communication_guard(
        "Welches Medium beruehrt die Dichtung genau? Das ist wichtig fuer Werkstoff- und Quellrisiken.",
        _context(communication_plan=plan, question_plan=question_plan),
    )

    assert result.passed is False
    assert "communication_guard:answer_first_missing" in result.findings


def test_communication_guard_blocks_external_utility_answer() -> None:
    plan = CommunicationPlan(
        goal="redirect",
        response_moves=[ResponseMove.REDIRECT],
        ask_user_question=False,
        max_new_questions=0,
    )

    result = validate_communication_guard(
        "Morgen wird es sonnig bei 24 Grad.",
        _context(communication_plan=plan),
    )

    assert result.passed is False
    assert "communication_guard:external_utility_answer" in result.findings


def test_communication_guard_blocks_tab_spam_when_silent() -> None:
    plan = CommunicationPlan(
        ask_user_question=False,
        max_new_questions=0,
        tab_update_visibility="silent",
    )

    result = validate_communication_guard(
        "Ich habe das Cockpit aktualisiert.",
        _context(communication_plan=plan),
    )

    assert result.passed is False
    assert "communication_guard:tab_spam" in result.findings


def test_recovery_wording_allowed_without_overclaim() -> None:
    question_plan = QuestionPlan(
        ask_now=True,
        primary_question="Welches Medium beruehrt die Dichtung genau?",
        reason="Das Medium bestimmt Werkstoff- und Quellrisiken.",
    )
    plan = CommunicationPlan(
        goal="recover",
        response_moves=[
            ResponseMove.RECOVER,
            ResponseMove.JUSTIFY_QUESTION,
            ResponseMove.CLARIFY,
        ],
        ask_user_question=True,
        max_new_questions=1,
        question_justification_required=True,
        primary_question=question_plan.primary_question,
        primary_question_reason=question_plan.reason,
    )

    result = validate_communication_guard(
        "Ich habe dich falsch verstanden. Das Medium ist wichtig fuer Werkstoff- und Quellrisiken. Welches Medium beruehrt die Dichtung genau?",
        _context(communication_plan=plan, question_plan=question_plan),
    )

    assert result.passed is True
