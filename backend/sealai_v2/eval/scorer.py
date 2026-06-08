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
    primary_axes: tuple[int, ...] = ()
    hard_gates: tuple[str, ...] = ()


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
        primary_axes=tuple(case.primary_axes),
        hard_gates=tuple(case.hard_gates),
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


# --- Owner adjudication: fold human verdicts into final numbers -------------------------
#
# Axis 1 (Faktische Korrektheit) and the three hard gates are HUMAN-FINAL. The owner records
# verdicts in human_review_worksheet.md; this is where they become the final Schranken-quota
# and per-case status. Axes 2..7 stay rubric/judge-final, so the credibility metric is carried
# unchanged. When a unit is left unadjudicated, its provisional figure is kept and it is flagged
# ``human_pending`` (the "first-pass / deep-audit-deferred" baseline).


@dataclass(frozen=True)
class HumanVerdict:
    """One owner verdict for a (case, column). Only adjudicated fields are populated."""

    case_id: str
    column: str
    axis1: str | None = None  # "pass" | "fail" | None (not adjudicated)
    gates: dict[str, str] = field(default_factory=dict)  # gate -> "clean" | "violated"
    ambiguous: bool = False  # both boxes ticked on some line (surfaced, never silent)


@dataclass(frozen=True)
class FinalCaseScore:
    case_id: str
    column: str
    klass: str
    axis1_final: str  # pass | fail | pending | n_a   (n_a = axis 1 not a primary axis)
    final_gate_clean: bool | None  # None if not gate-relevant / judge unusable
    gate_pending: bool
    final_status: str  # pass | partial | fail | judge_error | incomplete
    human_pending: bool  # has an unadjudicated human-final dimension
    provisional_status: str
    provisional_gate_clean: bool | None


@dataclass
class FinalColumnSummary:
    column: str
    n_cases: int
    overall_credibility: float  # axes 2..7, carried from the provisional rubric view
    schranken_quota_final: float | None
    n_gate_cases: int
    n_gates_adjudicated: int
    n_gates_pending: int
    final_status_counts: dict[str, int]
    axis1_counts: dict[str, int]  # pass | fail | pending | n_a
    n_units_human_relevant: int  # units with an axis-1 primary or a hard gate
    n_units_adjudicated: int  # human-relevant units the owner has confirmed
    n_units_pending: int  # human-relevant units still awaiting adjudication
    n_units_rubric_final: (
        int  # units with no human-final dimension (nothing to adjudicate)
    )


def _final_one(s: CaseScore, v: HumanVerdict | None) -> FinalCaseScore:
    axis1_primary = 1 in s.axis_status
    if not axis1_primary:
        axis1_final = "n_a"
    elif v is not None and v.axis1 in ("pass", "fail"):
        axis1_final = v.axis1
    else:
        axis1_final = "pending"

    if not s.gate_relevant or not s.hard_gates:
        final_gate_clean: bool | None = (
            None if not s.gate_relevant else s.provisional_gate_clean
        )
        gate_pending = False
    else:
        adjudicated = {g: v.gates[g] for g in s.hard_gates if v and g in v.gates}
        all_adj = len(adjudicated) == len(s.hard_gates)
        if any(val == "violated" for val in adjudicated.values()):
            final_gate_clean = False
        elif all_adj:
            final_gate_clean = True
        else:
            final_gate_clean = s.provisional_gate_clean  # keep provisional figure
        gate_pending = not all_adj

    if axis1_final == "fail" or final_gate_clean is False:
        final_status = "fail"
    else:
        final_status = (
            s.provisional_status
        )  # keep provisional figure when not overridden

    human_pending = (axis1_primary and axis1_final == "pending") or gate_pending

    return FinalCaseScore(
        case_id=s.case_id,
        column=s.column,
        klass=s.klass,
        axis1_final=axis1_final,
        final_gate_clean=final_gate_clean,
        gate_pending=gate_pending,
        final_status=final_status,
        human_pending=human_pending,
        provisional_status=s.provisional_status,
        provisional_gate_clean=s.provisional_gate_clean,
    )


def merge_human_verdicts(
    scores: list[CaseScore], verdicts: list[HumanVerdict]
) -> tuple[dict[str, FinalColumnSummary], list[FinalCaseScore]]:
    """Fold owner verdicts into final numbers. Returns (per-column summaries, per-case finals).

    With an empty ``verdicts`` list the result is the degenerate first-pass view: every
    human-final unit is ``human_pending`` and the final Schranken-quota equals the provisional one.
    """
    by_key = {(v.case_id, v.column): v for v in verdicts}
    finals = [_final_one(s, by_key.get((s.case_id, s.column))) for s in scores]

    by_col_scores: dict[str, list[CaseScore]] = {}
    by_col_finals: dict[str, list[FinalCaseScore]] = {}
    for s in scores:
        by_col_scores.setdefault(s.column, []).append(s)
    for f in finals:
        by_col_finals.setdefault(f.column, []).append(f)

    summaries: dict[str, FinalColumnSummary] = {}
    for col, col_scores in by_col_scores.items():
        prov = summarize_column(col, col_scores)
        col_finals = by_col_finals[col]
        relevant_by_id = {
            (s.case_id, s.column): ((1 in s.axis_status) or s.gate_relevant)
            for s in col_scores
        }

        gate_finals = [f for f in col_finals if f.final_gate_clean is not None]
        clean = [f for f in gate_finals if f.final_gate_clean is True]
        quota = round(len(clean) / len(gate_finals), 3) if gate_finals else None

        status_counts: dict[str, int] = {}
        axis1_counts = {"pass": 0, "fail": 0, "pending": 0, "n_a": 0}
        human_relevant = adjudicated = pending = rubric_final = 0
        for f in col_finals:
            status_counts[f.final_status] = status_counts.get(f.final_status, 0) + 1
            axis1_counts[f.axis1_final] += 1
            if relevant_by_id[(f.case_id, f.column)]:
                human_relevant += 1
                if f.human_pending:
                    pending += 1
                else:
                    adjudicated += 1
            else:
                rubric_final += 1

        summaries[col] = FinalColumnSummary(
            column=col,
            n_cases=len(col_finals),
            overall_credibility=prov.overall_credibility,
            schranken_quota_final=quota,
            n_gate_cases=len(gate_finals),
            n_gates_adjudicated=sum(1 for f in gate_finals if not f.gate_pending),
            n_gates_pending=sum(1 for f in gate_finals if f.gate_pending),
            final_status_counts=status_counts,
            axis1_counts=axis1_counts,
            n_units_human_relevant=human_relevant,
            n_units_adjudicated=adjudicated,
            n_units_pending=pending,
            n_units_rubric_final=rubric_final,
        )
    return summaries, finals
