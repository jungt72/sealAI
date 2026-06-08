from __future__ import annotations

from sealai_v2.eval.cases import load_cases
from sealai_v2.eval.judge import JudgeResult
from sealai_v2.eval.scorer import score_case, summarize_column


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
