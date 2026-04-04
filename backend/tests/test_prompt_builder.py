"""
Tests for PromptBuilder — verifies persona injection, template branching,
product-law inclusion, and output quality invariants.
"""
from __future__ import annotations

import pytest

from prompts.builder import PromptBuilder


@pytest.fixture()
def builder() -> PromptBuilder:
    return PromptBuilder()


def test_persona_always_present(builder: PromptBuilder) -> None:
    prompt = builder.fast_brain({}, missing_params=["medium"])
    assert "Thomas Reiter" in prompt
    assert "22 Jahre" in prompt


def test_missing_params_branch(builder: PromptBuilder) -> None:
    with_missing = builder.fast_brain({}, missing_params=["medium"])
    all_present = builder.fast_brain(
        {"medium": {"value": "Wasser", "unit": "", "source": "user"}},
        missing_params=[],
    )
    assert "Alle Kernparameter" in all_present
    assert "Alle Kernparameter" not in with_missing


def test_no_empty_params_section(builder: PromptBuilder) -> None:
    prompt = builder.fast_brain({}, missing_params=["medium"])
    assert "ERFASSTE PARAMETER" not in prompt


def test_fact_cards_rendered(builder: PromptBuilder) -> None:
    cards = [{"title": "PTFE Eignung", "specificity": 4, "content": "PTFE eignet sich für..."}]
    prompt = builder.governed({}, [], cards)
    assert "PTFE Eignung" in prompt
    assert "AUS DEINER WISSENSBASIS" in prompt


def test_no_fact_cards_fallback(builder: PromptBuilder) -> None:
    prompt = builder.governed({}, [], [])
    assert "Allgemeine Praxis" in prompt


def test_product_laws_in_governed(builder: PromptBuilder) -> None:
    prompt = builder.governed({}, [], [])
    assert "manufacturer-final" in prompt.lower()


def test_product_laws_absent_in_fast_brain(builder: PromptBuilder) -> None:
    prompt = builder.fast_brain({}, missing_params=["medium"])
    assert "PRODUKTGESETZE" not in prompt


def test_product_laws_in_final_answer(builder: PromptBuilder) -> None:
    prompt = builder.final_answer(
        parameters={},
        assumptions=[],
        req_class="B",
        open_points=["Druckklasse prüfen"],
        rfq_admissible=False,
    )
    assert "PRODUKTGESETZE" in prompt


def test_no_double_blank_lines(builder: PromptBuilder) -> None:
    prompt = builder.governed(
        {"druck": {"value": 5, "unit": "bar", "source": "user"}},
        [],
        [],
    )
    assert "\n\n\n" not in prompt


def test_conversation_no_laws(builder: PromptBuilder) -> None:
    prompt = builder.conversation()
    assert "Thomas Reiter" in prompt
    assert "PRODUKTGESETZE" not in prompt


def test_conversation_with_case_summary(builder: PromptBuilder) -> None:
    prompt = builder.conversation(case_summary="User fragt nach PTFE-Dichtung.")
    assert "BISHERIGER GESPRÄCHSKONTEXT" in prompt
    assert "PTFE-Dichtung" in prompt


def test_rfq_admissible_branch(builder: PromptBuilder) -> None:
    admissible = builder.final_answer(
        parameters={}, assumptions=[], req_class="A",
        open_points=[], rfq_admissible=True,
    )
    not_admissible = builder.final_answer(
        parameters={}, assumptions=[], req_class="A",
        open_points=["Druck fehlt"], rfq_admissible=False,
    )
    assert "RFQ-ADMISSIBLE" in admissible
    assert "NOCH NICHT RFQ-READY" in not_admissible


def test_prompt_version_constant(builder: PromptBuilder) -> None:
    assert PromptBuilder.PROMPT_VERSION == "v2.0"


def test_open_points_rendered_in_final_answer(builder: PromptBuilder) -> None:
    prompt = builder.final_answer(
        parameters={},
        assumptions=[],
        req_class="C",
        open_points=["Temperaturklasse offen", "Werkstoffzertifikat fehlt"],
        rfq_admissible=False,
    )
    assert "Temperaturklasse offen" in prompt
    assert "Werkstoffzertifikat fehlt" in prompt


def test_req_class_in_governed(builder: PromptBuilder) -> None:
    prompt = builder.governed({}, [], [], req_class="B")
    assert "REQUIREMENT CLASS" in prompt
    assert "B" in prompt


def test_no_trigger_slow_brain_in_fast_brain(builder: PromptBuilder) -> None:
    """Token-based routing is removed — fast_brain prompt must not contain the legacy token."""
    prompt = builder.fast_brain({}, missing_params=["medium"])
    assert "TRIGGER_SLOW_BRAIN" not in prompt


def test_submit_claim_present_when_include_tools(builder: PromptBuilder) -> None:
    prompt = builder.governed({}, [], [], include_tools=True)
    assert "submit_claim" in prompt


def test_submit_claim_absent_when_no_tools(builder: PromptBuilder) -> None:
    prompt = builder.governed({}, [], [], include_tools=False)
    assert "submit_claim" not in prompt
