from __future__ import annotations

import pytest

from app.agent.api import loaders
from app.agent.graph import GraphState
from app.agent.state.models import (
    PendingQuestion,
    SlotAnswerBinding,
    GovernedSessionState,
)


@pytest.mark.asyncio
async def test_post_graph_commit_persists_pending_question_and_slot_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = GovernedSessionState(user_turn_index=4)
    pending = PendingQuestion(
        target_field="medium",
        expected_answer_type="medium_value",
        question_text="Welches Medium soll abgedichtet werden?",
        asked_at_turn_id=4,
        source="governed_next_question",
        ambiguity_policy="clarify_if_broad_or_hazardous",
        status="open",
    )
    binding = SlotAnswerBinding(
        target_field="medium",
        raw_value="chlor",
        normalized_value="Chlor",
        source="pending_question",
        confidence=0.72,
        ambiguity=True,
        needs_clarification=True,
        turn_index=5,
    )
    result_state = GraphState(
        pending_question=pending,
        last_slot_answer_binding=binding,
        governed_answer_context={
            "pending_question": pending.model_dump(mode="python"),
            "slot_answer_bindings": [binding.model_dump(mode="python")],
        },
        user_turn_index=5,
    )
    persisted: list[GovernedSessionState] = []

    async def fake_load_live_governed_state(**_: object) -> GovernedSessionState:
        return initial

    async def fake_persist_live_governed_state(**kwargs: object) -> None:
        persisted.append(kwargs["state"])  # type: ignore[index]

    monkeypatch.setattr(
        loaders, "_load_live_governed_state", fake_load_live_governed_state
    )
    monkeypatch.setattr(
        loaders, "_persist_live_governed_state", fake_persist_live_governed_state
    )

    updated = await loaders._update_governed_state_post_graph(
        current_user=object(),  # type: ignore[arg-type]
        session_id="COMP-TEST",
        result_state=result_state,
        pre_gate_classification="DOMAIN_INQUIRY",
    )

    assert persisted == [updated]
    assert updated.pending_question is not None
    assert updated.pending_question.target_field == "medium"
    assert updated.pending_question.status == "open"
    assert updated.last_slot_answer_binding is not None
    assert updated.last_slot_answer_binding.raw_value == "chlor"
    assert (
        updated.governed_answer_context["pending_question"]["target_field"] == "medium"
    )
    assert (
        updated.governed_answer_context["slot_answer_bindings"][0]["target_field"]
        == "medium"
    )
    assert updated.user_turn_index == 6
