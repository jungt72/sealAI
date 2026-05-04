from __future__ import annotations

import pytest

from app.agent.communication.communication_runtime_v8 import (
    CommunicationRuntimeV8,
    CommunicationRuntimeV8DecisionProposal,
)
from app.agent.communication.conversation_controller_v7 import ConversationControllerInput
from app.agent.communication.v7_contracts import AnswerMode, MutationPolicy
from app.domain.pre_gate_classification import PreGateClassification


@pytest.mark.asyncio
async def test_v8_llm_proposal_can_rescue_colloquial_smalltalk_from_domain_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def propose(self, payload, deterministic):  # noqa: ANN001
        return CommunicationRuntimeV8DecisionProposal(
            intent="smalltalk",
            confidence=0.93,
            reason="colloquial greeting",
        )

    monkeypatch.setattr(CommunicationRuntimeV8, "_llm_decision_proposal", propose)
    decision = await CommunicationRuntimeV8().decide(
        ConversationControllerInput(
            user_message="moin, wie laeufts heute bei dir?",
            pre_gate_classification=PreGateClassification.DOMAIN_INQUIRY,
            pre_gate_confidence=0.55,
            pre_gate_reason="forced_domain_for_runtime_rescue",
            active_case_exists=True,
        )
    )

    assert decision.answer_mode == AnswerMode.SMALLTALK
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN


@pytest.mark.asyncio
async def test_v8_llm_smalltalk_proposal_cannot_override_concrete_case_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def propose(self, payload, deterministic):  # noqa: ANN001
        return CommunicationRuntimeV8DecisionProposal(
            intent="smalltalk",
            confidence=0.99,
            reason="bad proposal",
        )

    monkeypatch.setattr(CommunicationRuntimeV8, "_llm_decision_proposal", propose)
    decision = await CommunicationRuntimeV8().decide(
        ConversationControllerInput(
            user_message="Ich habe eine Welle mit 80 mm und Oel bei 90 Grad.",
            pre_gate_classification=PreGateClassification.DOMAIN_INQUIRY,
            pre_gate_confidence=0.85,
            pre_gate_reason="deterministic_domain",
            active_case_exists=False,
        )
    )

    assert decision.answer_mode == AnswerMode.GOVERNED_INTAKE
    assert decision.mutation_policy == MutationPolicy.PROPOSED
