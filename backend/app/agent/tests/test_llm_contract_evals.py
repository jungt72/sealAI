from app.agent.evals.llm_contract import (
    EvalCategory,
    REQUIRED_EVAL_CATEGORIES,
    evaluate_text_contract,
)


def test_adr_011_exposes_all_required_eval_categories() -> None:
    assert set(REQUIRED_EVAL_CATEGORIES) == {
        EvalCategory.TONE_COMPLIANCE,
        EvalCategory.SAFETY_LANGUAGE,
        EvalCategory.BEST_NEXT_QUESTION_QUALITY,
        EvalCategory.DELTA_EXTRACTION_ACCURACY,
        EvalCategory.NO_UNAUTHORIZED_STATE_CLAIMS,
        EvalCategory.DEEP_DIVE_GROUNDING,
    }


def test_eval_flags_unsafe_final_approval_language() -> None:
    result_by_category = {
        result.category: result
        for result in evaluate_text_contract("Diese Dichtung ist garantiert passend und final freigegeben.")
    }

    assert result_by_category[EvalCategory.SAFETY_LANGUAGE].passed is False
    assert "unsafe_final_approval_language" in result_by_category[EvalCategory.SAFETY_LANGUAGE].findings


def test_eval_accepts_single_grounded_next_question() -> None:
    results = evaluate_text_contract(
        "Ich sehe Medium und Temperatur als offen. Welche maximale Temperatur tritt an der Dichtstelle auf?"
    )

    assert all(result.passed for result in results)
