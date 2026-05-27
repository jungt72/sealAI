from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.domain.pre_gate_classification import PreGateClassification
from app.services.pre_gate_classifier import ClassificationResult
from app.services.semantic_intent_router import (
    refine_pre_gate_classification,
    semantic_pre_gate_candidate,
)


class _FakeChatCompletions:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(self.payload))
                )
            ]
        )


class _FakeOpenAIClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.completions = _FakeChatCompletions(payload)
        self.chat = SimpleNamespace(completions=self.completions)


def _deterministic(
    classification: PreGateClassification,
    *,
    reasoning: str = "deterministic_fixture",
) -> ClassificationResult:
    return ClassificationResult(
        classification=classification,
        confidence=0.55,
        reasoning=reasoning,
        escalate_to_graph=classification is PreGateClassification.DOMAIN_INQUIRY,
    )


@pytest.mark.asyncio
async def test_semantic_router_overrides_ambiguous_material_info_to_knowledge(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER", "true")
    fake_client = _FakeOpenAIClient(
        {
            "intent": "knowledge_explain",
            "confidence": 0.93,
            "case_facts_present": False,
            "materials": ["PTFE"],
            "compared_entities": [],
            "needs_history_resolution": False,
            "reason": "casual material knowledge request",
        }
    )
    monkeypatch.setattr(
        "app.services.semantic_intent_router.get_async_llm",
        lambda role: (fake_client, "gpt-4o-mini"),
    )

    deterministic = _deterministic(
        PreGateClassification.DOMAIN_INQUIRY,
        reasoning="ambiguous_fail_safe_domain_inquiry",
    )
    decision = await refine_pre_gate_classification(
        message="kannste mir mal was zu dem weissen PTFE zeug erzählen",
        deterministic=deterministic,
    )

    routed = decision.classification_result(deterministic)
    assert fake_client.completions.calls
    assert decision.applied is True
    assert decision.intent == "knowledge_explain"
    assert routed.classification is PreGateClassification.KNOWLEDGE_QUERY
    assert routed.escalate_to_graph is False
    assert routed.reasoning.startswith("semantic_intent_router:knowledge_explain")


@pytest.mark.asyncio
async def test_semantic_router_resolves_history_anaphora_to_knowledge_followup(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER", "true")
    fake_client = _FakeOpenAIClient(
        {
            "intent": "knowledge_followup",
            "confidence": 0.9,
            "case_facts_present": False,
            "materials": ["PTFE"],
            "compared_entities": [],
            "needs_history_resolution": True,
            "reason": "darueber resolves to PTFE from recent history",
        }
    )
    monkeypatch.setattr(
        "app.services.semantic_intent_router.get_async_llm",
        lambda role: (fake_client, "gpt-4o-mini"),
    )

    deterministic = _deterministic(PreGateClassification.META_QUESTION)
    decision = await refine_pre_gate_classification(
        message="was kannst du mir darüber erzählen?",
        deterministic=deterministic,
        recent_history=(
            {"role": "user", "content": "ich brauche informationen zu PTFE"},
            {"role": "assistant", "content": "PTFE ist ein Fluorpolymer."},
        ),
    )

    assert decision.applied is True
    assert decision.needs_history_resolution is True
    assert decision.materials == ("PTFE",)
    assert decision.classification_result(deterministic).classification is (
        PreGateClassification.KNOWLEDGE_QUERY
    )


@pytest.mark.asyncio
async def test_semantic_router_does_not_run_for_hard_case_facts(monkeypatch) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER", "true")
    deterministic = _deterministic(PreGateClassification.DOMAIN_INQUIRY)

    assert (
        semantic_pre_gate_candidate(
            "Ich habe Hydrauliköl, 90 °C, rotierende Welle, 8 bar",
            deterministic,
        )
        is False
    )
    decision = await refine_pre_gate_classification(
        message="Ich habe Hydrauliköl, 90 °C, rotierende Welle, 8 bar",
        deterministic=deterministic,
    )

    assert decision.applied is False
    assert decision.classification is PreGateClassification.DOMAIN_INQUIRY


@pytest.mark.asyncio
async def test_semantic_router_keeps_low_confidence_deterministic_route(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER", "true")
    fake_client = _FakeOpenAIClient(
        {
            "intent": "knowledge_explain",
            "confidence": 0.61,
            "case_facts_present": False,
            "materials": ["PTFE"],
            "compared_entities": [],
            "needs_history_resolution": False,
            "reason": "not confident enough",
        }
    )
    monkeypatch.setattr(
        "app.services.semantic_intent_router.get_async_llm",
        lambda role: (fake_client, "gpt-4o-mini"),
    )
    deterministic = _deterministic(PreGateClassification.DOMAIN_INQUIRY)

    decision = await refine_pre_gate_classification(
        message="ptfe?",
        deterministic=deterministic,
    )

    assert decision.applied is False
    assert decision.classification_result(deterministic).classification is (
        PreGateClassification.DOMAIN_INQUIRY
    )
