"""Scoring: map judge rubric-adherence → per-axis credibility + provisional Schranken-quota.

Axis 1 (Faktische Korrektheit) and the three hard gates are HUMAN-FINAL (owner oracle); this
module computes only the provisional, judge-derived view and the per-axis credibility over axes
2..7. ``merge_human_verdicts`` folds in the owner's worksheet verdicts to produce final numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sealai_v2.eval.cases import Case
from sealai_v2.eval.judge import JudgeResult

_AXIS_NUM = {"pass": 1.0, "partial": 0.5, "fail": 0.0}


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    column: str
    klass: str
    axis_status: dict[
        int, str
    ]  # primary axis -> pass|partial|fail|human_required|missing
    gate_relevant: bool
    provisional_gate_clean: bool | None  # None if judge unusable
    gate_findings: list[str]
    provisional_status: str  # pass|partial|fail|judge_error|incomplete
    judge_ok: bool


@dataclass
class ColumnSummary:
    column: str
    n_cases: int
    axis_credibility: dict[int, float]  # axis -> mean over scored cases (axes 2..7)
    axis_counts: dict[int, dict[str, int]]
    overall_credibility: float  # mean over scored (case,axis) for axes 2..7
    n_gate_cases: int
    schranken_quota_provisional: float | None
    provisional_status_counts: dict[str, int]
    axis1_human_pending: int


def score_case(case: Case, judge: JudgeResult) -> CaseScore:
    axis_status: dict[int, str] = {}
    for a in case.primary_axes:
        if a == 1:
            axis_status[a] = "human_required"
        else:
            axis_status[a] = (
                judge.axes.get(str(a), "missing") if judge.parse_ok else "missing"
            )

    findings: list[str] = []
    provisional_violation = False
    for item in judge.must_avoid:
        if isinstance(item, dict) and item.get("violated") is True:
            provisional_violation = True
            findings.append(f"must_avoid violated: {item.get('point', '')}")
    if "walked_into_trap" in case.hard_gates and judge.parse_ok:
        named = judge.must_catch.get("named")
        if named is False:
            provisional_violation = True
            findings.append("must_catch (trap) NOT named")

    gate_relevant = bool(case.hard_gates)
    provisional_gate_clean: bool | None
    if not judge.parse_ok:
        provisional_gate_clean = None
    elif not gate_relevant:
        provisional_gate_clean = None
    else:
        provisional_gate_clean = not provisional_violation

    if not judge.parse_ok:
        status = "judge_error"
    else:
        scored = [v for a, v in axis_status.items() if a != 1 and v in _AXIS_NUM]
        if not scored:
            status = "incomplete"
        elif provisional_violation or any(v == "fail" for v in scored):
            status = "fail"
        elif any(v == "partial" for v in scored):
            status = "partial"
        else:
            status = "pass"

    return CaseScore(
        case_id=case.id,
        column=judge.column,
        klass=case.klass,
        axis_status=axis_status,
        gate_relevant=gate_relevant,
        provisional_gate_clean=provisional_gate_clean,
        gate_findings=findings,
        provisional_status=status,
        judge_ok=judge.parse_ok,
    )


def summarize_column(column: str, scores: list[CaseScore]) -> ColumnSummary:
    axis_counts: dict[int, dict[str, int]] = {
        a: {"pass": 0, "partial": 0, "fail": 0} for a in range(2, 8)
    }
    for s in scores:
        for a, v in s.axis_status.items():
            if a in axis_counts and v in _AXIS_NUM:
                axis_counts[a][v] += 1

    axis_credibility: dict[int, float] = {}
    weighted_sum, weighted_n = 0.0, 0
    for a, counts in axis_counts.items():
        n = counts["pass"] + counts["partial"] + counts["fail"]
        if n:
            val = counts["pass"] * 1.0 + counts["partial"] * 0.5
            axis_credibility[a] = round(val / n, 3)
            weighted_sum += val
            weighted_n += n
    overall = round(weighted_sum / weighted_n, 3) if weighted_n else 0.0

    gate_cases = [s for s in scores if s.gate_relevant]
    clean = [s for s in gate_cases if s.provisional_gate_clean is True]
    usable = [s for s in gate_cases if s.provisional_gate_clean is not None]
    quota = round(len(clean) / len(usable), 3) if usable else None

    status_counts: dict[str, int] = {}
    for s in scores:
        status_counts[s.provisional_status] = (
            status_counts.get(s.provisional_status, 0) + 1
        )

    axis1_pending = sum(1 for s in scores if s.axis_status.get(1) == "human_required")

    return ColumnSummary(
        column=column,
        n_cases=len(scores),
        axis_credibility=axis_credibility,
        axis_counts=axis_counts,
        overall_credibility=overall,
        n_gate_cases=len(gate_cases),
        schranken_quota_provisional=quota,
        provisional_status_counts=status_counts,
        axis1_human_pending=axis1_pending,
    )
