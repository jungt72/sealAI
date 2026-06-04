from __future__ import annotations

from app.agent.communication.governed_answer_context import (
    build_governed_answer_context,
)
from app.agent.state.models import ConversationStrategyContract, GovernedSessionState
from app.agent.v91.contracts import FinalAnswerContext
from app.agent.v91.final_answer_guard import validate_v91_final_answer


def _context_with_question() -> FinalAnswerContext:
    strategy = ConversationStrategyContract(
        focus_key="medium",
        primary_question="Welches Medium berührt die Dichtung genau?",
        primary_question_reason="Das Medium bestimmt Werkstoff- und Quellrisiken.",
        response_mode="single_question",
    )
    context = build_governed_answer_context(
        GovernedSessionState(),
        strategy=strategy,
        response_class="structured_clarification",
    )
    assert context.v91_final_answer_context is not None
    return context.v91_final_answer_context


def test_v91_final_answer_guard_accepts_planned_single_question() -> None:
    context = _context_with_question()

    result = validate_v91_final_answer(
        "Dafür brauche ich zuerst den Medienanker: Welches Medium berührt die Dichtung genau?",
        context,
    )

    assert result.passed is True


def test_v91_final_answer_guard_rejects_final_suitability_claim() -> None:
    context = _context_with_question()

    result = validate_v91_final_answer(
        "FKM ist sicher geeignet. Welches Medium berührt die Dichtung genau?",
        context,
    )

    assert result.passed is False
    assert any("claim_guard" in finding for finding in result.findings)


def test_v91_final_answer_guard_rejects_unplanned_multi_question() -> None:
    context = _context_with_question()

    result = validate_v91_final_answer(
        "Welches Medium berührt die Dichtung genau? Welche Temperatur liegt an?",
        context,
    )

    assert result.passed is False
    assert "communication_guard:too_many_questions" in result.findings


def test_v91_final_answer_guard_rejects_unknown_evidence_ref() -> None:
    context = _context_with_question()

    result = validate_v91_final_answer(
        "Laut Datenblatt Quelle:doc-404 ist das geklärt. Welches Medium berührt die Dichtung genau?",
        context,
    )

    assert result.passed is False
    assert any("evidence_gate" in finding for finding in result.findings)
