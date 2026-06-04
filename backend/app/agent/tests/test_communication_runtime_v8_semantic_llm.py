from __future__ import annotations

import json

import pytest

from app.agent.communication.communication_runtime_v8 import CommunicationRuntimeV8
from app.agent.communication.conversation_controller_v7 import (
    ConversationControllerInput,
)
from app.agent.communication.v7_contracts import AnswerMode, MutationPolicy
from app.agent.state.models import PendingQuestion, SlotAnswerBinding
from app.domain.pre_gate_classification import PreGateClassification


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.requests: list[dict] = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)

        class Message:
            pass

        class Choice:
            pass

        class Response:
            pass

        message = Message()
        message.content = self.content
        choice = Choice()
        choice.message = message
        response = Response()
        response.choices = [choice]

        return response


class _FakeResponses:
    def __init__(self, content: str, *, fail_first: bool = False) -> None:
        self.content = content
        self.fail_first = fail_first
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.fail_first and len(self.requests) == 1:
            raise BadRequestError("unsupported model")

        class Response:
            pass

        response = Response()
        response.output_text = self.content
        return response


class BadRequestError(Exception):
    pass


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeClient:
    def __init__(
        self, completions: _FakeCompletions, responses: _FakeResponses
    ) -> None:
        self.chat = _FakeChat(completions)
        self.responses = responses


def _pending_medium_question() -> PendingQuestion:
    return PendingQuestion(
        target_field="medium",
        expected_answer_type="medium_value",
        question_text="Welches Medium soll abgedichtet werden?",
        ambiguity_policy="clarify_if_broad_or_hazardous",
        status="open",
    )


def _medium_slot(raw: str, normalized: str | None = None) -> SlotAnswerBinding:
    return SlotAnswerBinding(
        target_field="medium",
        raw_value=raw,
        normalized_value=normalized or raw,
        confidence=0.72,
        ambiguity=True,
        needs_clarification=True,
        turn_index=3,
    )


async def _decide_with_fake_llm(
    monkeypatch: pytest.MonkeyPatch,
    llm_json: dict,
    *,
    slot_binding: SlotAnswerBinding | None,
    message: str = "priiima",
    fail_first: bool = False,
):
    monkeypatch.setenv("SEALAI_ENABLE_COMMUNICATION_RUNTIME_LLM", "true")
    content = json.dumps(llm_json)
    completions = _FakeCompletions(content)
    responses = _FakeResponses(content, fail_first=fail_first)
    client = _FakeClient(completions, responses)
    monkeypatch.setattr(
        "app.llm.factory.get_async_llm",
        lambda _role: (client, "gpt-5.4-nano"),
    )

    decision = await CommunicationRuntimeV8().decide(
        ConversationControllerInput(
            user_message=message,
            pre_gate_classification=PreGateClassification.DOMAIN_INQUIRY,
            pre_gate_confidence=0.84,
            pre_gate_reason="forced_domain_for_semantic_runtime",
            active_case_exists=True,
            pending_question=_pending_medium_question(),
            slot_answer_binding=slot_binding,
        )
    )
    return decision, completions, responses


@pytest.mark.asyncio
async def test_semantic_llm_can_veto_deterministic_pending_slot_social_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision, completions, responses = await _decide_with_fake_llm(
        monkeypatch,
        {
            "intent": "smalltalk",
            "confidence": 0.94,
            "reason": "positive acknowledgement, not a sealing medium",
        },
        slot_binding=_medium_slot("priiima", "Priiima"),
    )

    assert decision.answer_mode == AnswerMode.SMALLTALK
    assert decision.mutation_policy == MutationPolicy.FORBIDDEN
    assert decision.state_actions == []

    assert completions.requests == []
    sent_payload = json.loads(responses.requests[0]["input"][0]["content"][0]["text"])
    assert sent_payload["pending_question"]["target_field"] == "medium"
    assert sent_payload["deterministic_slot_binding"]["raw_value"] == "priiima"


@pytest.mark.asyncio
async def test_semantic_llm_preserves_true_pending_slot_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision, completions, responses = await _decide_with_fake_llm(
        monkeypatch,
        {
            "intent": "pending_slot_answer",
            "confidence": 0.97,
            "reason": "the message denotes the requested medium",
        },
        slot_binding=_medium_slot("Wasser", "Wasser"),
        message="Wasser",
    )

    assert decision.answer_mode == AnswerMode.PENDING_SLOT_ANSWER
    assert decision.mutation_policy == MutationPolicy.PROPOSED
    assert decision.state_actions[0].field == "medium"
    assert decision.state_actions[0].value == "Wasser"
    assert responses.requests[0]["model"] == "gpt-5.4-nano"
    assert completions.requests == []


@pytest.mark.asyncio
async def test_semantic_llm_retries_registry_default_when_configured_model_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision, completions, responses = await _decide_with_fake_llm(
        monkeypatch,
        {
            "intent": "smalltalk",
            "confidence": 0.94,
            "reason": "positive acknowledgement, not a sealing medium",
        },
        slot_binding=_medium_slot("priiima", "Priiima"),
        fail_first=True,
    )

    assert decision.answer_mode == AnswerMode.SMALLTALK
    assert [request["model"] for request in responses.requests] == ["gpt-5.4-nano"]
    assert [request["model"] for request in completions.requests] == [
        "gpt-4o-mini",
    ]
