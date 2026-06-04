"""S1–S3 golden regression for the RWDR comparative-ranking leak surface.

Each scenario is pinned at BOTH guard layers:
  - A.1  ``output_guard.check_fast_path_output``      — live streaming enforcer
  - A.2  ``final_guard.validate_final_output`` on a   — knowledge-turn backstop
         knowledge-route ``NonTechnicalAnswerContext``
"""
from __future__ import annotations

import pytest

from app.agent.runtime.output_guard import check_fast_path_output
from app.agent.v92.contracts import NonTechnicalAnswerContext
from app.agent.v92.final_guard import validate_final_output
from app.services.knowledge.material_comparison import build_material_comparison_answer


def _knowledge_context() -> NonTechnicalAnswerContext:
    return NonTechnicalAnswerContext(
        turn_id="golden",
        route="knowledge_general",
        intent="knowledge_general",
        user_message="Werkstofffrage Heißwasser",
    )


# S1 — conditional comparative → BLOCK at both layers
def test_s1_conditional_comparative_blocked_both_layers() -> None:
    text = "FKM wäre für Heißwasser besser geeignet als NBR"
    safe, category = check_fast_path_output(text)
    assert safe is False
    assert category == "comparative_ranking"
    assert validate_final_output(text, context=_knowledge_context()).decision == "block"


# S2 — superlative suitability → BLOCK at both layers
def test_s2_superlative_suitability_blocked_both_layers() -> None:
    text = "EPDM ist am besten geeignet für Heißwasser"
    safe, category = check_fast_path_output(text)
    assert safe is False
    assert category == "comparative_ranking"
    assert validate_final_output(text, context=_knowledge_context()).decision == "block"


# S3 — neutral deterministic render → PASS at both layers (no false block)
def test_s3_neutral_render_passes_both_layers() -> None:
    answer = build_material_comparison_answer("Vergleiche FKM und EPDM")
    assert answer is not None
    safe, _category = check_fast_path_output(answer.answer)
    assert safe is True
    assert validate_final_output(answer.answer, context=_knowledge_context()).decision == "pass"


# --- A.3: the two ORIGINAL reported leak forms — BLOCK at both layers ----------
# optimum-predicative (#1, #2) + superiority überlegen/übertrifft (#3, #4). Group A
# closed only the geeignet-family; these stayed open at both layers until A.3.

A3_ORIGINAL_LEAKS = (
    "EPDM könnte optimal sein",
    "EPDM könnte für diese Anwendung optimal sein",
    "PTFE ist NBR überlegen",
    "PTFE übertrifft NBR",
)


@pytest.mark.parametrize("text", A3_ORIGINAL_LEAKS)
def test_s4_a3_original_leaks_blocked_both_layers(text: str) -> None:
    safe, category = check_fast_path_output(text)
    assert safe is False
    assert category == "comparative_ranking"
    assert validate_final_output(text, context=_knowledge_context()).decision == "block"


# S5 — application-anchored optimum now blocks at BOTH layers (L2 asymmetry closed).
# L1 already blocked it (suitability category); the knowledge backstop previously passed it.
def test_s5_application_optimum_blocked_both_layers() -> None:
    text = "EPDM ist optimal für diese Anwendung"
    safe, _category = check_fast_path_output(text)
    assert safe is False
    assert validate_final_output(text, context=_knowledge_context()).decision == "block"


# --- A.3 negative boundary: attributive forms & property-subject predicatives --
# must PASS at both layers (a property statement, never a material selection).
A3_FALSE_POSITIVE_NEGATIVES = (
    "PTFE hat überlegene chemische Beständigkeit als NBR",
    "FKM hat optimale Temperaturbeständigkeit",
    "Die Druckverformung von FKM ist optimal",
    "Die chemische Beständigkeit von PTFE ist der von NBR überlegen",
    "die Wärmebeständigkeit von FKM übertrifft die von NBR",
)


@pytest.mark.parametrize("text", A3_FALSE_POSITIVE_NEGATIVES)
def test_s6_a3_false_positive_boundary_passes_both_layers(text: str) -> None:
    safe, _category = check_fast_path_output(text)
    assert safe is True
    assert validate_final_output(text, context=_knowledge_context()).decision == "pass"
