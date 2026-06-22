from __future__ import annotations

import json
import shutil
from pathlib import Path

from sealai_v2.eval import report
from sealai_v2.eval.adjudicate import adjudicate_run, parse_worksheet

_BASELINE = Path(__file__).resolve().parents[1] / "eval" / "runs" / "m1-baseline"


def _render_one_unit_worksheet() -> str:
    """Render a 1-case/1-column worksheet with the production renderer (round-trip source)."""
    manifest = {
        "run_label": "t",
        "l1_model_resolved": "x",
        "judge_model": "j",
        "git_sha": "g",
        "timestamp": "ts",
    }
    rec = {
        "case_id": "TRAP-01",
        "klass": "Fallen/Inkompatibilität (TRAP)",
        "kontext": "k",
        "input": "i",
        "must_catch": "mc",
        "hard_gates": ["walked_into_trap", "confident_wrong"],
        "column": "flags_off",
        "answer_model": "m",
        "intent": "fallarbeit",
        "error": None,
        "answer_text": "a",
        "judge": {"parse_ok": False},
    }
    return report._render_worksheet(manifest, [rec])


def test_parse_unticked_worksheet_yields_no_verdicts():
    ws = _render_one_unit_worksheet()
    assert parse_worksheet(ws) == []


def test_parse_roundtrip_with_renderer():
    ws = _render_one_unit_worksheet()
    ws = ws.replace("`[ ] PASS`", "`[x] PASS`", 1)
    ws = ws.replace(
        "**Verdict — hard gate `confident_wrong`:**  `[ ] CLEAN`  `[ ] VIOLATED`",
        "**Verdict — hard gate `confident_wrong`:**  `[ ] CLEAN`  `[x] VIOLATED`",
    )
    verdicts = parse_worksheet(ws)
    assert len(verdicts) == 1
    v = verdicts[0]
    assert (v.case_id, v.column) == ("TRAP-01", "flags_off")
    assert v.axis1 == "pass"
    assert v.gates == {"confident_wrong": "violated"}
    assert v.ambiguous is False


def test_parse_handles_uppercase_x():
    ws = _render_one_unit_worksheet().replace("`[ ] FAIL`", "`[X] FAIL`", 1)
    v = parse_worksheet(ws)[0]
    assert v.axis1 == "fail"


def test_parse_flags_both_boxes_ticked_as_ambiguous():
    ws = _render_one_unit_worksheet()
    ws = ws.replace("`[ ] PASS`", "`[x] PASS`", 1).replace(
        "`[ ] FAIL`", "`[x] FAIL`", 1
    )
    v = parse_worksheet(ws)[0]
    assert v.ambiguous is True
    assert v.axis1 is None  # ambiguous is never coerced to a verdict


def test_adjudicate_run_degenerate_baseline(tmp_path):
    """The committed baseline (zero verdicts) → final == provisional, all pending, labelled."""
    run = tmp_path / "m1-baseline"
    shutil.copytree(_BASELINE, run)
    prov = json.loads((run / "results.json").read_text(encoding="utf-8"))["summaries"]

    adj = adjudicate_run(run, run_label="m1-baseline", timestamp="2026-06-08T00:00:00Z")

    assert adj["n_verdicts_parsed"] == 0
    assert adj["deep_audit"] == "deferred"
    for col, fs in adj["columns"].items():
        assert fs["overall_credibility"] == prov[col]["overall_credibility"]
        assert fs["schranken_quota_final"] == prov[col]["schranken_quota_provisional"]
        assert fs["n_units_adjudicated"] == 0
        assert fs["n_units_pending"] == fs["n_units_human_relevant"] > 0

    # CALC-02 is surfaced as a divergence seed for M2
    assert any(d["case"] == "CALC-02" for d in adj["divergences"])

    report_md = (run / "report.md").read_text(encoding="utf-8")
    assert "first-pass adjudication — deep audit deferred" in report_md
    assert "PROVISIONAL until the deep audit" in report_md
    assert "Divergences — seeds for L3" in report_md
    assert "human-adjudication pending" in report_md

    # the adjudication block is persisted additively (REPLAY-friendly)
    persisted = json.loads((run / "results.json").read_text(encoding="utf-8"))
    assert "adjudication" in persisted
    assert persisted["summaries"] == prov  # provisional view preserved
