"""A.2 — final_guard knowledge backstop.

For smalltalk/abusive/safety non-technical turns ``validate_final_output`` stays a
no-op (``_empty_guard``). For ``knowledge_*`` routes it must run the
suitability / comparative-ranking / compliance subset and BLOCK leaks — while
reading only the answer text, never the FinalAnswerContext-only fields that a
``NonTechnicalAnswerContext`` does not carry.
"""
from __future__ import annotations

import pytest

from app.agent.v92.contracts import NonTechnicalAnswerContext
from app.agent.v92.final_guard import validate_final_output
from app.services.knowledge.material_comparison import build_material_comparison_answer


def _knowledge_context(route: str = "knowledge_general") -> NonTechnicalAnswerContext:
    return NonTechnicalAnswerContext(
        turn_id="turn-1",
        route=route,  # type: ignore[arg-type]
        intent=route,
        user_message="FKM oder NBR für Heißwasser?",
    )


# --- S1: conditional comparative leak must BLOCK on a knowledge turn ----------


def test_knowledge_turn_blocks_conditional_comparative_leak() -> None:
    result = validate_final_output(
        "FKM wäre für Heißwasser besser geeignet als NBR",
        context=_knowledge_context(),
    )
    assert result.decision == "block"
    assert result.final_stream_allowed is False
    assert "comparative_ranking" in result.detected_forbidden_claims


@pytest.mark.parametrize("route", ["knowledge_general", "knowledge_case_side_question"])
def test_knowledge_routes_block_superlative_suitability(route: str) -> None:
    result = validate_final_output(
        "EPDM ist am besten geeignet für Heißwasser",
        context=_knowledge_context(route),
    )
    assert result.decision == "block"
    assert result.final_stream_allowed is False


# --- NEGATIVE: the neutral deterministic comparison render must PASS ----------


def test_knowledge_turn_passes_neutral_deterministic_render() -> None:
    answer = build_material_comparison_answer("Vergleiche FKM und EPDM")
    assert answer is not None
    result = validate_final_output(answer.answer, context=_knowledge_context())
    assert result.decision == "pass"
    assert result.final_stream_allowed is True
    assert result.detected_forbidden_claims == []


# --- smalltalk / abusive / safety stay empty (no scan, no AttributeError) -----


@pytest.mark.parametrize("route", ["smalltalk", "abusive_or_shit_chat", "unsafe_or_blocked"])
def test_non_knowledge_nontechnical_routes_stay_empty(route: str) -> None:
    # A phrase that WOULD trip the knowledge subset must still pass on these routes.
    result = validate_final_output(
        "FKM wäre für Heißwasser besser geeignet als NBR",
        context=_knowledge_context(route),
    )
    assert result.decision == "pass"
    assert result.final_stream_allowed is True
