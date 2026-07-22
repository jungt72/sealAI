from __future__ import annotations

from sealai_v2.core.communication_plan import (
    build_communication_plan,
    enforce_communication,
    evaluate_communication,
    render_case_clarification,
    render_case_intake_response,
)


def test_case_intake_plan_acknowledges_goal_and_asks_exactly_one_question() -> None:
    question = (
        "Hallo und guten Morgen, ich möchte eine Dichtungslösung entwickeln. "
        "Was benötigst du von mir?"
    )
    plan = build_communication_plan(question=question, route_name="case_intake_invite")
    answer = render_case_intake_response(question, plan)

    assert plan.answer_first is True
    assert plan.max_questions == 1
    assert answer.count("?") == 1
    assert "Dichtungslösung Schritt für Schritt" in answer
    assert "Welche Anwendung und Dichtstelle" in answer
    assert "Davon hängt ab" in answer
    assert evaluate_communication(answer, plan).passed


def test_intake_guard_rejects_unrelated_evidence_and_question_lists() -> None:
    plan = build_communication_plan(
        question="Ich möchte eine Dichtung entwickeln",
        route_name="case_intake_invite",
    )
    verdict = evaluate_communication(
        "**Belege** Fachkarte X. Welches Medium? Welcher Druck?", plan
    )

    assert verdict.passed is False
    assert "question_budget_exceeded" in verdict.violations
    assert "intake_contains_evidence" in verdict.violations
    assert "planned_question_missing" in verdict.violations


def test_communication_enforcement_keeps_only_planned_question_and_reason() -> None:
    plan = build_communication_plan(
        question="Was brauchst du noch?",
        route_name="engineering_case",
        missing_fields=("Druck", "Drehzahl"),
    )
    repaired = enforce_communication(
        "Der Fall ist erfasst. Welches Medium? Welche Drehzahl?",
        plan,
    )

    assert repaired.count("?") == 1
    assert repaired.endswith(f"{plan.next_question} {plan.question_reason}")
    assert evaluate_communication(repaired, plan).passed


def test_communication_enforcement_removes_questions_from_answer_only_route() -> None:
    plan = build_communication_plan(
        question="Was ist PTFE?",
        route_name="material_knowledge",
    )
    repaired = enforce_communication("PTFE ist ein Fluorpolymer. Warum relevant?", plan)

    assert repaired == "PTFE ist ein Fluorpolymer. Warum relevant."
    assert evaluate_communication(repaired, plan).passed


def test_active_case_plan_uses_only_first_missing_field_with_reason() -> None:
    plan = build_communication_plan(
        question="Was brauchst du noch?",
        route_name="engineering_case",
        case_fields=("dichtungstyp", "medium"),
        missing_fields=("Betriebstemperatur", "Druck", "Drehzahl"),
    )
    answer = render_case_clarification(plan)

    assert plan.case_bound is True
    assert "Welche minimale, normale und maximale Temperatur" in answer
    assert "Druck" not in plan.next_question
    assert answer.count("?") == 1
    assert "Fallkontext" in answer


def test_knowledge_plan_answers_first_and_does_not_invent_case_questions() -> None:
    plan = build_communication_plan(
        question="Was ist PTFE?", route_name="material_knowledge"
    )

    assert plan.goal == "answer_requested_knowledge"
    assert plan.answer_first is True
    assert plan.max_questions == 0
    assert plan.next_question == ""
