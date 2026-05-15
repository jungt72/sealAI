from __future__ import annotations

from app.agent.communication.governed_answer_context import build_governed_answer_context
from app.agent.state.models import ConversationStrategyContract, GovernedSessionState
from app.agent.v91.contracts import ResponseAction


def test_governed_answer_context_carries_v91_final_answer_context() -> None:
    strategy = ConversationStrategyContract(
        focus_key="pressure_bar",
        primary_question="Welcher Druck liegt direkt an der Dichtstelle an?",
        primary_question_reason="Der Druck begrenzt Bauform, Spaltmaß und Herstellerprüfung.",
        response_mode="single_question",
    )

    context = build_governed_answer_context(
        GovernedSessionState(),
        strategy=strategy,
        response_class="structured_clarification",
    )

    final_context = context.v91_final_answer_context
    assert final_context is not None
    assert final_context.question_plan == context.v91_question_plan
    assert final_context.response_policy.action == ResponseAction.WAIT_FOR_USER.value
    assert final_context.response_policy.graph_allowed is False
    assert "final_material_recommendation" in final_context.freedom_decision.forbidden_actions
    assert "planned_next_question" in final_context.allowed_claim_levels


def test_v91_final_answer_context_without_question_is_answer_only() -> None:
    context = build_governed_answer_context(
        GovernedSessionState(),
        strategy=ConversationStrategyContract(),
        response_class="governed_state_update",
    )

    assert context.v91_final_answer_context is not None
    assert context.v91_final_answer_context.question_plan is not None
    assert context.v91_final_answer_context.question_plan.ask_now is False
    assert context.v91_final_answer_context.response_policy.action == ResponseAction.ANSWER_ONLY.value
