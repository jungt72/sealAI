from __future__ import annotations

import pytest

from app.domain.pre_gate_classification import PreGateClassification
from app.services.pre_gate_classifier import PreGateClassifier


@pytest.fixture
def classifier() -> PreGateClassifier:
    return PreGateClassifier()


@pytest.mark.parametrize(
    "text",
    [
        "Hallo",
        "Moin!",
        "Vielen Dank.",
        "bye",
    ],
)
def test_greeting_examples(classifier: PreGateClassifier, text: str) -> None:
    result = classifier.classify(text)

    assert result.classification is PreGateClassification.GREETING
    assert result.confidence > 0.9
    assert result.escalate_to_graph is False


@pytest.mark.parametrize(
    "text",
    [
        "Was kann SeaLAI?",
        "Wie funktioniert dieses Tool?",
        "Wofür ist SeaLAI gedacht?",
        "What can this tool do?",
    ],
)
def test_meta_question_examples(classifier: PreGateClassifier, text: str) -> None:
    result = classifier.classify(text)

    assert result.classification is PreGateClassification.META_QUESTION
    assert result.confidence > 0.8
    assert result.escalate_to_graph is False


@pytest.mark.parametrize(
    "text",
    [
        "Was ist der Unterschied zwischen FKM und PTFE?",
        "Erkläre mir Radialwellendichtringe.",
        "What is PTFE?",
        "How does a radial shaft seal work?",
    ],
)
def test_knowledge_query_examples(classifier: PreGateClassifier, text: str) -> None:
    result = classifier.classify(text)

    assert result.classification is PreGateClassification.KNOWLEDGE_QUERY
    assert result.confidence > 0.7
    assert result.escalate_to_graph is False


@pytest.mark.parametrize(
    "text",
    [
        "Ich brauche eine Dichtung für meine Pumpe.",
        "Berechne RWDR für 50 mm Welle und 3000 rpm.",
        "Wir haben Leckage am Getriebe.",
        "I need a replacement seal for a pump.",
        "PTFE Dichtung für Welle prüfen.",
    ],
)
def test_domain_inquiry_examples(classifier: PreGateClassifier, text: str) -> None:
    result = classifier.classify(text)

    assert result.classification is PreGateClassification.DOMAIN_INQUIRY
    assert result.confidence > 0.8
    assert result.escalate_to_graph is True


@pytest.mark.parametrize(
    "text",
    [
        "Welchen Hersteller empfiehlst du?",
        "Empfiehl mir eine Dichtung.",
        "Welche Dichtung soll ich kaufen?",
        "you are stupid",
    ],
)
def test_blocked_examples(classifier: PreGateClassifier, text: str) -> None:
    result = classifier.classify(text)

    assert result.classification is PreGateClassification.BLOCKED
    assert result.confidence > 0.8
    assert result.escalate_to_graph is False


@pytest.mark.parametrize("text", ["", "   ", "PTFE?", "passt das?"])
def test_ambiguous_inputs_fail_safe_to_domain_inquiry(
    classifier: PreGateClassifier,
    text: str,
) -> None:
    result = classifier.classify(text)

    assert result.classification is PreGateClassification.DOMAIN_INQUIRY
    assert result.escalate_to_graph is True


def test_classifier_is_deterministic(classifier: PreGateClassifier) -> None:
    first = classifier.classify("Was ist der Unterschied zwischen FKM und PTFE?")
    second = classifier.classify("Was ist der Unterschied zwischen FKM und PTFE?")

    assert second == first


def test_output_is_always_allowed_enum_value(classifier: PreGateClassifier) -> None:
    examples = [
        "Hallo",
        "Was kann SeaLAI?",
        "Was ist FKM?",
        "Ich brauche eine Dichtung.",
        "Welchen Hersteller empfiehlst du?",
        "unklar",
    ]

    for example in examples:
        result = classifier.classify(example)
        assert result.classification in set(PreGateClassification)


def test_classification_helper_returns_enum_only(
    classifier: PreGateClassifier,
) -> None:
    assert (
        classifier.classification("Ich brauche eine Dichtung")
        is PreGateClassification.DOMAIN_INQUIRY
    )


def test_service_has_no_langgraph_or_agent_imports() -> None:
    import app.services.pre_gate_classifier as mod

    assert mod.__file__ is not None
    with open(mod.__file__, encoding="utf-8") as source_file:
        source = source_file.read()

    forbidden = ("langgraph", "from app.agent", "import app.agent")
    assert not [pattern for pattern in forbidden if pattern in source]
