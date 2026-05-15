from __future__ import annotations

from app.agent.communication.governed_answer_context import build_governed_answer_context
from app.agent.state.models import ConversationStrategyContract, GovernedSessionState
from app.agent.v91.question_planner import build_question_plan_from_strategy


def test_question_plan_projects_existing_single_question_strategy() -> None:
    strategy = ConversationStrategyContract(
        focus_key="temperature_c",
        primary_question="Welche maximale Temperatur tritt direkt an der Dichtstelle auf?",
        primary_question_reason="Die Temperatur entscheidet, ob eine Werkstoffhypothese im Prüfrahmen bleibt.",
        response_mode="single_question",
    )

    plan = build_question_plan_from_strategy(
        strategy=strategy,
        state=GovernedSessionState(),
    )

    assert plan is not None
    assert plan.ask_now is True
    assert plan.primary_question == strategy.primary_question
    assert plan.question_need is not None
    assert plan.question_need.target_field == "temperature_c"
    assert plan.question_need.expected_answer_type == "number"
    assert plan.max_questions_policy == "ask_one_highest_leverage_question"


def test_governed_answer_context_contains_v91_question_plan() -> None:
    strategy = ConversationStrategyContract(
        focus_key="medium",
        primary_question="Welches Medium berührt die Dichtung genau?",
        primary_question_reason="Das Medium bestimmt Werkstoff-, Korrosions- und Quellrisiken.",
        response_mode="single_question",
    )

    context = build_governed_answer_context(
        GovernedSessionState(),
        strategy=strategy,
        response_class="structured_clarification",
    )

    assert context.next_best_question == strategy.primary_question
    assert context.v91_question_plan is not None
    assert context.v91_question_plan.ask_now is True
    assert context.v91_question_plan.question_need is not None
    assert context.v91_question_plan.question_need.target_field == "medium"
