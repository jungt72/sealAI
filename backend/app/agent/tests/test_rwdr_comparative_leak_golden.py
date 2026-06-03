"""S1–S3 golden regression for the RWDR comparative-ranking leak surface.

Each scenario is pinned at BOTH guard layers:
  - A.1  ``output_guard.check_fast_path_output``      — live streaming enforcer
  - A.2  ``final_guard.validate_final_output`` on a   — knowledge-turn backstop
         knowledge-route ``NonTechnicalAnswerContext``
"""
from __future__ import annotations

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
