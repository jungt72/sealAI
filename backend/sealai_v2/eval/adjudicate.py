"""Owner adjudication / recompute pass for an eval REPLAY run.

Reads a committed run's ``results.json`` + the owner's ``human_review_worksheet.md``, folds the
human verdicts (axis 1 + the three hard gates) into final numbers via
``scorer.merge_human_verdicts``, re-renders ``report.md`` with a first-pass / deep-audit-deferred
section, and writes the adjudication block back into ``results.json`` (additive).

Pure recompute — no LLM calls, no ``OPENAI_API_KEY`` needed:

    python -m sealai_v2.eval --adjudicate --label m1-baseline
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

from sealai_v2.eval.report import _render_report
from sealai_v2.eval.scorer import CaseScore, HumanVerdict, merge_human_verdicts

_CASE_RE = re.compile(r"^##\s+(?P<cid>\S+)\s+—\s+")
_COL_RE = re.compile(r"^###\s+Column\s+`(?P<col>[^`]+)`")
_AXIS1_RE = re.compile(r"Faktische Korrektheit \(Achse 1\)")
_GATE_RE = re.compile(r"hard gate `(?P<gate>[^`]+)`")


def _ticked(line: str, label: str) -> bool:
    """True iff the ``[ ]``/``[x]`` box immediately before ``label`` carries an x."""
    m = re.search(r"\[([ xX])\]\s*" + label, line)
    return bool(m and m.group(1).lower() == "x")


def parse_worksheet(text: str) -> list[HumanVerdict]:
    """Parse owner verdicts from a rendered human_review_worksheet.md.

    Keyed to the exact strings emitted by ``report._render_worksheet`` (a round-trip test guards
    against drift). Only (case, column) units that carry at least one mark are returned; an empty
    worksheet yields ``[]`` (the degenerate first-pass case). Both boxes ticked → ``ambiguous``.
    """
    slots: dict[tuple[str, str], dict] = {}
    cur_case: str | None = None
    cur_col: str | None = None

    def slot(cid: str, col: str) -> dict:
        return slots.setdefault(
            (cid, col), {"axis1": None, "gates": {}, "ambiguous": False}
        )

    for line in text.splitlines():
        mcase = _CASE_RE.match(line)
        if mcase:
            cur_case, cur_col = mcase.group("cid"), None
            continue
        mcol = _COL_RE.match(line)
        if mcol:
            cur_col = mcol.group("col")
            continue
        if cur_case is None or cur_col is None:
            continue
        if not line.lstrip().startswith("**Verdict"):
            continue
        if _AXIS1_RE.search(line):
            s = slot(cur_case, cur_col)
            p, f = _ticked(line, "PASS"), _ticked(line, "FAIL")
            if p and f:
                s["ambiguous"] = True
            elif p:
                s["axis1"] = "pass"
            elif f:
                s["axis1"] = "fail"
            continue
        mgate = _GATE_RE.search(line)
        if mgate:
            s = slot(cur_case, cur_col)
            c, v = _ticked(line, "CLEAN"), _ticked(line, "VIOLATED")
            if c and v:
                s["ambiguous"] = True
            elif c:
                s["gates"][mgate.group("gate")] = "clean"
            elif v:
                s["gates"][mgate.group("gate")] = "violated"

    out: list[HumanVerdict] = []
    for (cid, col), d in slots.items():
        if d["axis1"] or d["gates"] or d["ambiguous"]:
            out.append(
                HumanVerdict(
                    case_id=cid,
                    column=col,
                    axis1=d["axis1"],
                    gates=d["gates"],
                    ambiguous=d["ambiguous"],
                )
            )
    return out


def load_run(run_dir) -> tuple[dict, list[CaseScore]]:
    """Read results.json and rebuild CaseScore objects from the stored ``score`` dicts."""
    data = json.loads((Path(run_dir) / "results.json").read_text(encoding="utf-8"))
    scores: list[CaseScore] = []
    for rec in data["records"]:
        sc = rec["score"]
        scores.append(
            CaseScore(
                case_id=rec["case_id"],
                column=rec["column"],
                klass=rec["klass"],
                axis_status={int(k): v for k, v in sc["axis_status"].items()},
                gate_relevant=sc["gate_relevant"],
                provisional_gate_clean=sc["provisional_gate_clean"],
                gate_findings=sc["gate_findings"],
                provisional_status=sc["provisional_status"],
                judge_ok=sc["judge_ok"],
                primary_axes=tuple(rec["primary_axes"]),
                hard_gates=tuple(rec["hard_gates"]),
            )
        )
    return data, scores


def build_divergences(scores: list[CaseScore]) -> list[dict]:
    """Surface divergences seen so far (no fresh deep audit): rubric-flagged/partial cases
    (auto-derived) plus a curated human-spotted factual issue. Seeds for L3's M2 target list."""
    by_case: dict[str, dict] = {}
    for s in scores:
        partials = sorted(
            str(a)
            for a, v in s.axis_status.items()
            if a != 1 and v in ("partial", "fail")
        )
        if not (
            s.provisional_status == "fail"
            or s.provisional_gate_clean is False
            or partials
        ):
            continue
        e = by_case.setdefault(
            s.case_id,
            {
                "columns": [],
                "axis_partials": set(),
                "gate_violated": False,
                "findings": [],
            },
        )
        e["columns"].append(s.column)
        e["axis_partials"].update(partials)
        e["gate_violated"] = e["gate_violated"] or (s.provisional_gate_clean is False)
        for f in s.gate_findings:
            if f not in e["findings"]:
                e["findings"].append(f)

    divs: list[dict] = []
    for cid, e in sorted(by_case.items()):
        divs.append(
            {
                "id": f"rubric-flag::{cid}",
                "case": cid,
                "columns": sorted(e["columns"]),
                "kind": "rubric_flag",
                "detail": (
                    f"Provisional FAIL; hard gate {'VIOLATED' if e['gate_violated'] else 'clean'}; "
                    f"axis partials {sorted(e['axis_partials']) or 'none'}; "
                    f"judge findings {e['findings'] or 'none'}."
                ),
                "m2_action": (
                    "Owner/L3 adjudication: true Schranken-violation (M1 has not cleared the hard "
                    "gate → L3 must catch it) vs. rubric false-flag (then final quota → 1.0)."
                ),
            }
        )

    # Curated factual divergence — spotted on read; deep audit deferred, framed as a candidate.
    divs.append(
        {
            "id": "factual::TRAP-02-epdm-polarity",
            "case": "TRAP-02",
            "columns": ["flags_off", "flags_on"],
            "kind": "factual_judge_passed",
            "detail": (
                'Both answers label EPDM a "polarer Kautschuk" — EPDM is non-polar; the '
                "swelling-mechanism text is internally inconsistent (calls EPDM polar yet has "
                "non-polar oil dissolve it). The conclusion (EPDM swells in mineral oil) is "
                "correct, but the stated mechanism is wrong, and the rubric judge passed it "
                "(must_catch named, must_contain met)."
            ),
            "m2_action": (
                "L3 verifier + Fallen-Katalog must catch confidently-stated mechanism errors; "
                "candidate axis-1 issue (human-final, deep audit deferred)."
            ),
        }
    )
    return divs


def adjudicate_run(
    run_dir, *, run_label: str, timestamp: str, deep_audit_deferred: bool = True
) -> dict:
    """Recompute final numbers from the worksheet and rewrite report.md + results.json."""
    run_dir = Path(run_dir)
    data, scores = load_run(run_dir)
    worksheet = (run_dir / "human_review_worksheet.md").read_text(encoding="utf-8")
    verdicts = parse_worksheet(worksheet)

    final_summaries, finals = merge_human_verdicts(scores, verdicts)
    divergences = build_divergences(scores)
    ambiguous = [[v.case_id, v.column] for v in verdicts if v.ambiguous]

    # The M6a memory check (memory_fabrication) is AGENT-FINAL — carried verbatim from results.json,
    # NOT re-adjudicated (deterministic untraceable_numeric_facts() output). It folds into the final
    # gate: Schranken-incl-memory holds iff every column's human-final quota = 1.0 AND it = 1.0.
    multiturn = data.get("multiturn")
    edge = data.get("edge")
    injection = data.get("injection")
    parametric = data.get("parametric")
    memory_quota = (multiturn or {}).get("summary", {}).get("memory_schranken_quota")
    exfil_quota = (injection or {}).get("exfiltration", {}).get("schranken_quota")
    # M8 parametric Schranke — AGENT-FINAL, deterministic detector verdicts carried verbatim
    # (per-turn over the multiturn cases + the run-wide sweep over single-turn finals).
    param_quota_mt = (
        (multiturn or {}).get("summary", {}).get("parametric_schranken_quota")
    )
    param_quota_st = (parametric or {}).get("schranken_quota")

    adjudication = {
        "label": "first-pass adjudication — deep audit deferred"
        if deep_audit_deferred
        else run_label,
        "deep_audit": "deferred" if deep_audit_deferred else "complete",
        "provisional_until_deep_audit": deep_audit_deferred,
        "timestamp": timestamp,
        "n_verdicts_parsed": len(verdicts),
        "ambiguous_lines": ambiguous,
        "columns": {col: dataclasses.asdict(fs) for col, fs in final_summaries.items()},
        "final_cases": [dataclasses.asdict(f) for f in finals],
        "divergences": divergences,
        "memory_schranken_quota": memory_quota,  # agent-final, verbatim
        "exfiltration_schranken_quota": exfil_quota,  # M6b agent-final, deterministic
        "parametric_schranken_quota_multiturn": param_quota_mt,  # M8 agent-final
        "parametric_schranken_quota_singleturn": param_quota_st,  # M8 agent-final
    }

    data["adjudication"] = adjudication
    (run_dir / "results.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "report.md").write_text(
        _render_report(
            data["manifest"],
            data["summaries"],
            data["records"],
            adjudication=adjudication,
            multiturn=multiturn,
            edge=edge,
            injection=injection,
            parametric=parametric,
        ),
        encoding="utf-8",
    )
    return adjudication
