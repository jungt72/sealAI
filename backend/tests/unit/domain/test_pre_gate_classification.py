from __future__ import annotations

import json

import pytest

from app.domain.pre_gate_classification import PreGateClassification


def test_pre_gate_classification_contains_exactly_authority_values() -> None:
    expected = {
        "GREETING",
        "META_QUESTION",
        "KNOWLEDGE_QUERY",
        "BLOCKED",
        "DOMAIN_INQUIRY",
    }

    assert {member.value for member in PreGateClassification} == expected
    assert len(PreGateClassification) == 5


def test_pre_gate_classification_string_values_are_stable() -> None:
    assert PreGateClassification.GREETING.value == "GREETING"
    assert PreGateClassification.META_QUESTION.value == "META_QUESTION"
    assert PreGateClassification.KNOWLEDGE_QUERY.value == "KNOWLEDGE_QUERY"
    assert PreGateClassification.BLOCKED.value == "BLOCKED"
    assert PreGateClassification.DOMAIN_INQUIRY.value == "DOMAIN_INQUIRY"


def test_unknown_pre_gate_classification_value_fails() -> None:
    with pytest.raises(ValueError):
        PreGateClassification("FAST_PATH")


def test_pre_gate_classification_serializes_as_string_value() -> None:
    payload = {"classification": PreGateClassification.DOMAIN_INQUIRY}

    assert isinstance(PreGateClassification.DOMAIN_INQUIRY, str)
    assert json.loads(json.dumps(payload)) == {
        "classification": "DOMAIN_INQUIRY",
    }
