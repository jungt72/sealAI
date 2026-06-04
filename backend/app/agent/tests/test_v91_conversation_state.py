from __future__ import annotations

from app.agent.communication.governed_answer_context import (
    build_governed_answer_context,
)
from app.agent.state.models import ConversationStrategyContract, GovernedSessionState
from app.agent.v91.conversation_state import (
    build_conversation_task_state,
    build_dialogue_debt,
)


def test_conversation_task_and_dialogue_debt_track_one_next_question() -> None:
    strategy = ConversationStrategyContract(
        focus_key="medium",
        primary_question="Welches Medium berührt die Dichtung genau?",
        primary_question_reason="Das Medium entscheidet Werkstoff- und Korrosionsrisiken.",
        response_mode="single_question",
    )
    state = GovernedSessionState()
    context = build_governed_answer_context(
        state,
        strategy=strategy,
        response_class="structured_clarification",
    )

    task = build_conversation_task_state(
        state=state,
        governed_context=context,
        response_class="structured_clarification",
    )
    debt = build_dialogue_debt(
        state=state,
        governed_context=context,
        conversation_task=task,
    )

    assert task.active_intent == "case_intake"
    assert task.pause_resume_status == "waiting_for_user"
    assert task.last_asked_question == strategy.primary_question
    assert debt.pending_questions == [strategy.primary_question]
    assert debt.repeated_question_count == 1


def test_dialogue_debt_counts_repeated_question_without_raw_chat_truth() -> None:
    question = "Welches Medium berührt die Dichtung genau?"
    previous_task = build_conversation_task_state(
        state=GovernedSessionState(),
        governed_context=build_governed_answer_context(
            GovernedSessionState(),
            strategy=ConversationStrategyContract(
                focus_key="medium",
                primary_question=question,
                primary_question_reason="Medium fehlt.",
                response_mode="single_question",
            ),
            response_class="structured_clarification",
        ),
        response_class="structured_clarification",
    )
    previous_debt = build_dialogue_debt(
        state=GovernedSessionState(),
        governed_context=build_governed_answer_context(GovernedSessionState()),
        conversation_task=previous_task,
    )
    state = GovernedSessionState(v91_dialogue_debt=previous_debt)

    debt = build_dialogue_debt(
        state=state,
        governed_context=build_governed_answer_context(state),
        conversation_task=previous_task,
    )

    assert debt.pending_questions == [question]
    assert debt.repeated_question_count == 2
