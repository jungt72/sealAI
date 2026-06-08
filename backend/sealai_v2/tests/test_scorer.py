from __future__ import annotations

from sealai_v2.eval.cases import load_cases
from sealai_v2.eval.judge import JudgeResult
from sealai_v2.eval.scorer import (
    HumanVerdict,
    merge_human_verdicts,
    score_case,
    summarize_column,
)


def _case(cid: str):
    return next(c for c in load_cases() if c.id == cid)


def test_clean_trap_case_is_provisionally_clean():
    c = _case("TRAP-01")
    j = JudgeResult(
        case_id=c.id,
        column="x",
        must_contain=[{"point": p, "status": "met"} for p in c.must_contain],
        must_catch={"named": True},
        must_avoid=[{"point": p, "violated": False} for p in c.must_avoid],
        axes={str(a): "pass" for a in c.primary_axes if a != 1},
        parse_ok=True,
    )
    s = score_case(c, j)
    assert s.provisional_gate_clean is True
    assert s.provisional_status == "pass"
    assert (
        1 not in s.axis_status
    )  # TRAP-01 does not exercise axis 1 (primary axes 2,5,4)


def test_axis1_is_human_required_when_it_is_a_primary_axis():
    c = _case("CALC-01")  # primary axes [1, 4, 3]
    j = JudgeResult(
        case_id=c.id,
        column="x",
        must_catch={"named": True},
        must_avoid=[],
        axes={"3": "pass", "4": "pass"},
        parse_ok=True,
    )
    s = score_case(c, j)
    assert (
        s.axis_status[1] == "human_required"
    )  # judge never scores factual correctness


def test_violated_must_avoid_flags_gate_and_fails():
    c = _case("TRAP-01")
    j = JudgeResult(
        case_id=c.id,
        column="x",
        must_catch={"named": False},
        must_avoid=[{"point": "FKM bestätigt", "violated": True}],
        axes={"2": "fail"},
        parse_ok=True,
    )
    s = score_case(c, j)
    assert s.provisional_gate_clean is False
    assert s.provisional_status == "fail"


def test_unparseable_judge_yields_judge_error_and_no_gate_verdict():
    c = _case("TRAP-01")
    s = score_case(c, JudgeResult(case_id=c.id, column="x", parse_ok=False))
    assert s.provisional_status == "judge_error"
    assert s.provisional_gate_clean is None


def test_column_quota_all_clean_is_one():
    c = _case("TRAP-01")
    clean = score_case(
        c,
        JudgeResult(
            case_id=c.id,
            column="x",
            must_catch={"named": True},
            must_avoid=[],
            axes={"2": "pass"},
            parse_ok=True,
        ),
    )
    summary = summarize_column("x", [clean])
    assert summary.schranken_quota_provisional == 1.0
    assert summary.n_gate_cases == 1


# --- merge_human_verdicts (owner adjudication) ------------------------------------------


def _clean(cid: str):
    """A provisionally-clean score for a case (passing judge, trap named, no violations)."""
    c = _case(cid)
    return score_case(
        c,
        JudgeResult(
            case_id=c.id,
            column="x",
            must_catch={"named": True},
            must_avoid=[{"point": p, "violated": False} for p in c.must_avoid],
            axes={str(a): "pass" for a in c.primary_axes if a != 1},
            parse_ok=True,
        ),
    )


def _flagged(cid: str):
    """A provisionally-violated score (a must_avoid violation flags the gate + fails the case)."""
    c = _case(cid)
    return score_case(
        c,
        JudgeResult(
            case_id=c.id,
            column="x",
            must_catch={"named": True},
            must_avoid=[{"point": "omission", "violated": True}],
            axes={str(a): "pass" for a in c.primary_axes if a != 1},
            parse_ok=True,
        ),
    )


def test_empty_verdicts_keep_provisional_and_flag_all_pending():
    scores = [_clean("TRAP-01"), _flagged("CALC-02")]
    prov = summarize_column("x", scores)
    summaries, finals = merge_human_verdicts(scores, [])
    fs = summaries["x"]

    # final == provisional in the degenerate (no-verdict) recompute
    assert fs.schranken_quota_final == prov.schranken_quota_provisional == 0.5
    assert fs.overall_credibility == prov.overall_credibility
    # both gate cases are human-relevant and unadjudicated → pending, nothing adjudicated
    assert fs.n_units_adjudicated == 0
    assert fs.n_units_pending == 2
    assert all(f.human_pending for f in finals)
    by_id = {f.case_id: f for f in finals}
    assert by_id["TRAP-01"].final_status == "pass"  # provisional figure kept
    assert by_id["CALC-02"].final_status == "fail"  # provisional figure kept
    assert by_id["CALC-02"].final_gate_clean is False  # fallback to provisional


def test_clean_verdict_on_flagged_gate_lifts_quota_to_one():
    scores = [_clean("TRAP-01"), _flagged("CALC-02")]
    calc = _case("CALC-02")
    verdict = HumanVerdict(
        case_id="CALC-02",
        column="x",
        gates={g: "clean" for g in calc.hard_gates},
    )
    summaries, finals = merge_human_verdicts(scores, [verdict])
    fs = summaries["x"]
    assert fs.schranken_quota_final == 1.0
    calc_final = next(f for f in finals if f.case_id == "CALC-02")
    assert calc_final.final_gate_clean is True
    assert calc_final.gate_pending is False


def test_axis1_fail_fails_case_even_when_rubric_passes():
    c = _case("CALC-01")  # primary axes include 1
    score = _clean("CALC-01")
    assert score.provisional_status == "pass"
    verdict = HumanVerdict(
        case_id="CALC-01",
        column="x",
        axis1="fail",
        gates={g: "clean" for g in c.hard_gates},
    )
    _, finals = merge_human_verdicts([score], [verdict])
    f = finals[0]
    assert f.axis1_final == "fail"
    assert f.final_status == "fail"
    assert f.human_pending is False  # fully adjudicated
