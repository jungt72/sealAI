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


def test_v8_deterministic_routes_information_request_as_active_side_question() -> None:
    decision = CommunicationRuntimeV8().decide_deterministic(
        ConversationControllerInput(
            user_message="Bitte gebe mir detaillierte Informationen über PTFE",
            pre_gate_classification=PreGateClassification.DOMAIN_INQUIRY,
            pre_gate_confidence=0.55,
            pre_gate_reason="forced_domain_for_regression",
            active_case_exists=True,
        )
    )

    assert decision.answer_mode == AnswerMode.ACTIVE_CASE_SIDE_QUESTION
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN


def test_v8_deterministic_routes_explicit_case_challenge_to_challenge_mode() -> None:
    decision = CommunicationRuntimeV8().decide_deterministic(
        ConversationControllerInput(
            user_message=(
                "Analysiere diese direkt eingegebenen Dichtungsparameter als vorbereiteten technischen Fall. "
                "Medium: Salzwasser; Druck: 2 bar; Drehzahl: 3000 rpm; Wellendurchmesser: 40 mm; "
                "Dichtungstyp-Richtung: RWDR. Bitte keine stumpfe Parameterabfrage. Challenge den Dichtungsfall."
            ),
            pre_gate_classification=PreGateClassification.DOMAIN_INQUIRY,
            pre_gate_confidence=0.84,
            pre_gate_reason="deterministic_domain",
            active_case_exists=False,
        )
    )

    assert decision.answer_mode == AnswerMode.TECHNICAL_CASE_CHALLENGE
    assert decision.mutation_policy == MutationPolicy.PROPOSED


def test_v8_deterministic_keeps_ptfe_fkm_comparison_in_knowledge_mode() -> None:
    decision = CommunicationRuntimeV8().decide_deterministic(
        ConversationControllerInput(
            user_message="Was ist der Unterschied zwischen PTFE und FKM?",
            pre_gate_classification=PreGateClassification.KNOWLEDGE_QUERY,
            pre_gate_confidence=0.86,
            pre_gate_reason="deterministic_material_comparison",
            active_case_exists=False,
        )
    )

    assert decision.answer_mode == AnswerMode.MATERIAL_COMPARISON
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN


def test_v8_deterministic_routes_short_material_info_as_active_side_question() -> None:
    decision = CommunicationRuntimeV8().decide_deterministic(
        ConversationControllerInput(
            user_message="infos zu NBR",
            pre_gate_classification=PreGateClassification.KNOWLEDGE_QUERY,
            pre_gate_confidence=0.81,
            pre_gate_reason="deterministic_standalone_technical_knowledge",
            active_case_exists=True,
        )
    )

    assert decision.answer_mode == AnswerMode.ACTIVE_CASE_SIDE_QUESTION
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN


def test_v8_deterministic_routes_material_limits_as_active_side_question() -> None:
    decision = CommunicationRuntimeV8().decide_deterministic(
        ConversationControllerInput(
            user_message="ich benötige die grenzwerte von PTFE",
            pre_gate_classification=PreGateClassification.KNOWLEDGE_QUERY,
            pre_gate_confidence=0.83,
            pre_gate_reason="deterministic_material_limits_knowledge",
            active_case_exists=True,
        )
    )

    assert decision.answer_mode == AnswerMode.ACTIVE_CASE_SIDE_QUESTION
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN


def test_v8_deterministic_routes_context_recall_as_active_process_question() -> None:
    decision = CommunicationRuntimeV8().decide_deterministic(
        ConversationControllerInput(
            user_message="Was wollte ich von dir?",
            pre_gate_classification=PreGateClassification.META_QUESTION,
            pre_gate_confidence=0.9,
            pre_gate_reason="deterministic_meta_question",
            active_case_exists=True,
        )
    )

    assert decision.answer_mode == AnswerMode.ACTIVE_CASE_PROCESS_QUESTION
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN


@pytest.mark.asyncio
async def test_v8_llm_knowledge_proposal_can_rescue_technical_subject_without_case_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def propose(self, payload, deterministic):  # noqa: ANN001
        return CommunicationRuntimeV8DecisionProposal(
            intent="knowledge",
            confidence=0.91,
            reason="technical subject without operating data",
        )

    monkeypatch.setattr(CommunicationRuntimeV8, "_llm_decision_proposal", propose)
    decision = await CommunicationRuntimeV8().decide(
        ConversationControllerInput(
            user_message="PTFE",
            pre_gate_classification=PreGateClassification.DOMAIN_INQUIRY,
            pre_gate_confidence=0.55,
            pre_gate_reason="ambiguous_fail_safe_domain_inquiry",
            active_case_exists=False,
        )
    )

    assert decision.answer_mode == AnswerMode.NO_CASE_KNOWLEDGE
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN
