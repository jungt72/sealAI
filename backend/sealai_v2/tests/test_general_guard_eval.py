"""P0-B targeted eval — regression-pin the offline overblock measurement for
``response_contract_general_guard_enabled`` (audit Leitbild-V3, L1-Scope-Leak/P0-2). Mirrors
``test_contract_eval.py``'s precision-check pattern, but for ``build_guard_contract()`` +
``evaluate_render(check_sentence_coverage=False)`` — the P0-B code path. NO model, NO tokens.
"""

from __future__ import annotations

from sealai_v2.eval.general_guard_eval import (
    GENERAL_GUARD_EVAL_CASES,
    GENERAL_GUARD_KNOWN_LIMITATION_CASES,
    seed_general_guard_overblock_report,
)


def test_realistic_grounded_answers_never_overblock():
    # The DECISIVE number for the owner's go/no-go: over 10 realistic answers that cite ONLY what
    # their (real, live) grounding facts textually support, the guard must never BLOCK.
    r = seed_general_guard_overblock_report()
    assert r["overblock_rate"] == 0.0, r["unexpected_blocks"]
    assert r["n"] == len(GENERAL_GUARD_EVAL_CASES)
    assert r["blocked"] == 0


def test_open_question_with_no_grounding_and_no_calc_never_builds_a_contract():
    # Zero evidence -> build_guard_contract() returns None -> the guard does not run at all for a
    # pure open-ended question (byte-identical no-guard path, the safest case by construction).
    r = seed_general_guard_overblock_report()
    case = next(c for c in r["per_case"] if c["id"] == "no-grounding-no-calc-open-question")
    assert case["contract_built"] is False
    assert case["action"] == "PASS"


def test_known_limitations_still_correctly_block():
    # The guard must not be a no-op: a genuinely un-grounded comparison material, an illustrative
    # (non-computed, non-grounded) number, and a forbidden hedge phrase must all still BLOCK, each
    # for its documented reason — this is the guard's real safety value, not just its overblock cost.
    r = seed_general_guard_overblock_report()
    assert r["known_limitations_confirmed"] == len(GENERAL_GUARD_KNOWN_LIMITATION_CASES)
    for detail, case in zip(r["known_limitations_detail"], GENERAL_GUARD_KNOWN_LIMITATION_CASES):
        assert detail["action"] == "BLOCK", detail
        kinds = {v["kind"] for v in detail["violations"]}
        assert case["expected_violation_kind"] in kinds, (case["id"], kinds)
