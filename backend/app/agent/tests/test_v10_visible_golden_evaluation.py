from __future__ import annotations

from app.agent.communication.governed_answer_context import build_governed_answer_context
from app.agent.state.models import ConversationStrategyContract, GovernedSessionState
from app.agent.v91.contracts import ResponseMove
from app.agent.v91.golden_evaluation import (
    VisibleGoldenExpectation,
    evaluate_visible_golden_answer,
)


def _question_context():
    context = build_governed_answer_context(
        GovernedSessionState(),
        strategy=ConversationStrategyContract(
            focus_key="pressure_bar",
            primary_question="Welcher Druck oder welche Druckdifferenz liegt direkt an der Dichtstelle an?",
            primary_question_reason="Der Dichtstellendruck begrenzt Bauform, Spalt und Extrusionsrisiko.",
            response_mode="single_question",
        ),
        response_class="structured_clarification",
    )
    assert context.v91_final_answer_context is not None
    return context.v91_final_answer_context


def test_visible_golden_answer_checks_answer_first_one_question_and_reason() -> None:
    result = evaluate_visible_golden_answer(
        (
            "Aus den bisherigen Angaben kann ich noch keine Freigabe ableiten. "
            "Der Dichtstellendruck ist wichtig, weil er Bauform, Spalt und Extrusionsrisiko begrenzt: "
            "Welcher Druck oder welche Druckdifferenz liegt direkt an der Dichtstelle an?"
        ),
        _question_context(),
        VisibleGoldenExpectation(question_reason=True),
    )

    assert result.passed is True
    assert result.metrics["answer_first"] is True
    assert result.metrics["one_question"] is True
    assert result.metrics["question_reason"] is True
    assert result.metrics["no_overclaim"] is True


def test_visible_golden_answer_rejects_final_claim_multi_question_and_tab_spam() -> None:
    context = _question_context()
    result = evaluate_visible_golden_answer(
        (
            "Ist FKM final freigegeben? Welche Temperatur liegt an? "
            "Ich aktualisiere Cockpit, Tab, Workspace und Dashboard."
        ),
        context,
        VisibleGoldenExpectation(question_reason=True),
    )

    assert result.passed is False
    assert "communication_guard:too_many_questions" in result.findings
    assert "communication_guard:tab_spam" in result.findings
    assert any(finding.startswith("claim_guard:") for finding in result.findings)


def test_visible_golden_answer_requires_known_evidence_when_expected() -> None:
    context = _question_context().model_copy(update={"evidence_ref_ids": ["evidence_doc_1"]})
    result = evaluate_visible_golden_answer(
        (
            "Die dokumentierte Quelle evidence_doc_1 stützt nur eine Vorprüfung, keine Freigabe. "
            "Der Dichtstellendruck ist wichtig, weil er Bauform und Spalt begrenzt: "
            "Welcher Druck oder welche Druckdifferenz liegt direkt an der Dichtstelle an?"
        ),
        context,
        VisibleGoldenExpectation(question_reason=True, evidence_visible=True),
    )

    assert result.passed is True
    assert result.metrics["evidence_visible"] is True


def test_visible_golden_rfq_boundary_requires_review_and_no_dispatch_claim() -> None:
    context = build_governed_answer_context(
        GovernedSessionState(),
        strategy=ConversationStrategyContract(),
        response_class="rfq_readiness",
    ).v91_final_answer_context
    assert context is not None
    result = evaluate_visible_golden_answer(
        (
            "Ich sende nichts automatisch. Ich kann eine RFQ-Preview vorbereiten; "
            "vor Export oder Herstellerkontakt braucht es Review und deine Zustimmung."
        ),
        context,
        VisibleGoldenExpectation(rfq_boundary=True),
    )

    assert result.passed is True
    assert result.metrics["rfq_boundary"] is True


def test_visible_golden_redirect_does_not_answer_external_utility() -> None:
    context = _question_context()
    plan = context.communication_plan
    assert plan is not None
    redirected = plan.model_copy(
        update={
            "goal": "redirect",
            "response_moves": [ResponseMove.REDIRECT],
            "ask_user_question": False,
            "max_new_questions": 0,
            "question_justification_required": False,
        }
    )
    context = context.model_copy(update={"communication_plan": redirected, "question_plan": None})
    result = evaluate_visible_golden_answer(
        "Dazu gebe ich keine externe Wetterauskunft. Ich bleibe beim Dichtungsfall und den offenen technischen Angaben.",
        context,
        VisibleGoldenExpectation(),
    )

    assert result.passed is True
    assert result.metrics["no_external_utility_answer"] is True


def test_visible_golden_recovery_after_correction_is_measurable() -> None:
    context = _question_context()
    result = evaluate_visible_golden_answer(
        (
            "Verstanden, ich korrigiere den Fallstand und übernehme Salzwasser statt Öl. "
            "Der Dichtstellendruck bleibt wichtig, weil er die Bauform begrenzt: "
            "Welcher Druck oder welche Druckdifferenz liegt direkt an der Dichtstelle an?"
        ),
        context,
        VisibleGoldenExpectation(question_reason=True, recovery=True),
    )

    assert result.passed is True
    assert result.metrics["recovery"] is True
