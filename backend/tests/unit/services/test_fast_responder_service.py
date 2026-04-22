from __future__ import annotations

import time

import pytest

from app.domain.pre_gate_classification import PreGateClassification
from app.services.fast_responder_service import (
    FastResponderMetrics,
    FastResponderService,
    SessionContext,
    UnsupportedFastResponderClassification,
)


@pytest.mark.parametrize(
    "classification,text,expected",
    [
        (PreGateClassification.GREETING, "Hallo", "Hallo"),
        (PreGateClassification.META_QUESTION, "Was kann SeaLAI?", "SeaLAI"),
        (PreGateClassification.BLOCKED, "Welchen Hersteller empfiehlst du?", "Dabei kann ich nicht helfen"),
    ],
)
def test_fast_responder_handles_only_non_case_pre_gate_classes(
    classification: PreGateClassification,
    text: str,
    expected: str,
) -> None:
    response = FastResponderService().respond(text, classification)

    assert response.output_class == "conversational_answer"
    assert response.source_classification is classification
    assert response.no_case_created is True
    assert expected in response.content


@pytest.mark.parametrize(
    "classification",
    [
        PreGateClassification.KNOWLEDGE_QUERY,
        PreGateClassification.DOMAIN_INQUIRY,
    ],
)
def test_fast_responder_rejects_full_graph_classifications(
    classification: PreGateClassification,
) -> None:
    with pytest.raises(UnsupportedFastResponderClassification):
        FastResponderService().respond("Was ist PTFE?", classification)


def test_fast_responder_uses_bounded_prompt_llm_when_injected() -> None:
    class LLM:
        def complete(self, *, system_prompt, user_input, classification, timeout_seconds):
            assert "Do not create or imply a case" in system_prompt
            assert user_input == "Hello"
            assert classification is PreGateClassification.GREETING
            assert timeout_seconds == 1.5
            return "Hello. How can I help?"

    response = FastResponderService(llm=LLM()).respond(
        "Hello",
        PreGateClassification.GREETING,
        SessionContext(language_hint="en"),
    )

    assert response.content == "Hello. How can I help?"


def test_meta_question_can_return_registration_prompt_without_case_creation() -> None:
    response = FastResponderService().respond(
        "Wie funktioniert SeaLAI?",
        PreGateClassification.META_QUESTION,
    )

    assert response.registration_prompt is not None
    assert response.registration_prompt.reason == "case_creation_requires_registration"
    assert response.no_case_created is True


def test_fast_responder_records_metrics_without_persistence() -> None:
    metrics = FastResponderMetrics()
    service = FastResponderService(metrics=metrics)

    service.respond("Hallo", PreGateClassification.GREETING)

    assert metrics.invocations_total == {PreGateClassification.GREETING.value: 1}
    assert len(metrics.latency_seconds) == 1
    assert metrics.escalated_to_graph_total == 0


def test_fast_responder_p95_latency_under_budget() -> None:
    service = FastResponderService()
    durations = []

    for _ in range(40):
        start = time.perf_counter()
        service.respond("Hallo", PreGateClassification.GREETING)
        durations.append(time.perf_counter() - start)

    p95 = sorted(durations)[int(len(durations) * 0.95) - 1]
    assert p95 < 1.5


def test_service_has_no_langgraph_or_agent_imports() -> None:
    import app.services.fast_responder_service as mod

    assert mod.__file__ is not None
    with open(mod.__file__, encoding="utf-8") as source_file:
        source = source_file.read()

    forbidden = ("langgraph", "from app.agent", "import app.agent")
    assert not [pattern for pattern in forbidden if pattern in source]
