"""Render eval artifacts: results.json (REPLAY), report.md (credibility + Schranken-quota,
provisional), and human_review_worksheet.md (the owner adjudicates factual correctness +
the 3 hard gates here).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from sealai_v2.core.contracts import AXES


def _record_to_dict(rec) -> dict:
    return {
        "case_id": rec.case.id,
        "klass": rec.case.klass,
        "column": rec.column,
        "input": rec.case.input,
        "kontext": rec.case.kontext,
        "must_catch": rec.case.must_catch,
        "primary_axes": list(rec.case.primary_axes),
        "hard_gates": list(rec.case.hard_gates),
        "intent": rec.intent,
        "intent_rationale": rec.intent_rationale,
        "answer_model": rec.answer_model,
        "answer_text": rec.answer_text,
        "error": rec.error,
        "judge": dataclasses.asdict(rec.judge),
        "score": dataclasses.asdict(rec.score),
    }


def write_all(run_dir, manifest: dict, records: list, summaries: dict) -> None:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    recs = [_record_to_dict(r) for r in records]
    (run_dir / "results.json").write_text(
        json.dumps(
            {"manifest": manifest, "summaries": summaries, "records": recs},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text(
        _render_report(manifest, summaries, recs, adjudication=None), encoding="utf-8"
    )
    (run_dir / "human_review_worksheet.md").write_text(
        _render_worksheet(manifest, recs), encoding="utf-8"
    )


def _quota_str(q) -> str:
    if q is None:
        return "n/a"
    return f"{q:.3f} ({'100%' if q == 1.0 else 'BELOW 100%'})"


def _render_adjudication_section(adj: dict) -> list[str]:
    L: list[str] = []
    L.append("## Adjudication — first-pass (deep audit deferred)")
    L.append("")
    if adj.get("provisional_until_deep_audit"):
        L.append(
            "> **This M1 baseline is PROVISIONAL until the deep audit (M2/L3).** Axis 1 "
            "(Faktische Korrektheit) and the three hard gates are HUMAN-FINAL; unadjudicated "
            "units keep their provisional figure and are flagged `human-adjudication pending`. "
            "Credibility (axes 2–7) is rubric/judge-final and carried unchanged."
        )
        L.append("")
    if adj.get("ambiguous_lines"):
        L.append(
            f"> ⚠️ {len(adj['ambiguous_lines'])} worksheet line(s) had BOTH boxes ticked "
            f"(ambiguous, ignored): {adj['ambiguous_lines']}."
        )
        L.append("")
    L.append(
        f"- Run label: **{adj['label']}** · verdicts parsed from worksheet: "
        f"**{adj['n_verdicts_parsed']}** · {adj['timestamp']}"
    )
    L.append("")

    for col, fs in adj["columns"].items():
        L.append(f"### Column `{col}` — final")
        L.append("")
        L.append(
            f"- **Final credibility (axes 2–7, carried):** {fs['overall_credibility']:.3f}"
        )
        L.append(
            f"- **Final Schranken-quota:** {_quota_str(fs['schranken_quota_final'])} over "
            f"{fs['n_gate_cases']} gate cases "
            f"(adjudicated {fs['n_gates_adjudicated']}, pending {fs['n_gates_pending']})"
        )
        L.append(
            f"- Human-final units: **{fs['n_units_adjudicated']} adjudicated · "
            f"{fs['n_units_pending']} pending** "
            f"(of {fs['n_units_human_relevant']}); {fs['n_units_rubric_final']} rubric-final"
        )
        L.append(
            f"- Axis 1 disposition: pass {fs['axis1_counts']['pass']} · "
            f"fail {fs['axis1_counts']['fail']} · pending {fs['axis1_counts']['pending']} · "
            f"n/a {fs['axis1_counts']['n_a']}"
        )
        L.append(f"- Final per-case status: {fs['final_status_counts']}")
        L.append("")

    L.append("### Divergences — seeds for L3 (M2 target list)")
    L.append("")
    if not adj["divergences"]:
        L.append("_None surfaced._")
        L.append("")
    for d in adj["divergences"]:
        L.append(
            f"- **{d['case']}** ({', '.join(d['columns'])}) · _{d['kind']}_ — {d['detail']}"
        )
        L.append(f"  - → M2: {d['m2_action']}")
    L.append("")

    L.append("### Per-case final status")
    L.append("")
    L.append(
        "| Case | Column | Final | Adjudication | Axis 1 | Gate (final) | (provisional) |"
    )
    L.append("|---|---|---|---|---|---|---|")
    for f in adj["final_cases"]:
        if f["axis1_final"] == "n_a" and f["final_gate_clean"] is None:
            adj_mark = "rubric-final"
        else:
            adj_mark = "⏳ pending" if f["human_pending"] else "✔ adjudicated"
        g = f["final_gate_clean"]
        gate = "—" if g is None else ("clean" if g else "VIOLATED")
        L.append(
            f"| {f['case_id']} | {f['column']} | {f['final_status']} | {adj_mark} | "
            f"{f['axis1_final']} | {gate} | {f['provisional_status']} |"
        )
    L.append("")
    return L


def _render_report(
    manifest: dict, summaries: dict, recs: list[dict], adjudication: dict | None = None
) -> str:
    L: list[str] = []
    L.append(f"# M1 Eval-REPLAY — {manifest['run_label']}")
    L.append("")
    L.append(f"- Milestone: **{manifest['milestone']}** — {manifest['subject']}")
    L.append(
        f"- L1 model (resolved): `{manifest['l1_model_resolved']}` (configured `{manifest['l1_model_configured']}`)"
    )
    L.append(
        f"- Judge model: `{manifest['judge_model']}` · Helper (understand): `{manifest['helper_model']}`"
    )
    L.append(
        f"- Cases: {manifest['n_cases']} · Columns: {', '.join(manifest['columns'])} · git `{manifest['git_sha']}` · {manifest['timestamp']}"
    )
    L.append("")
    L.append(
        "> **Provisional.** The judge scores RUBRIC-ADHERENCE only (axes 2–7). **Axis 1 "
        "(Faktische Korrektheit) and the three hard gates (walked-into-trap / invented-"
        "precision / confident-wrong) are HUMAN-FINAL** — see `human_review_worksheet.md`. "
        "The Schranken-quota below is provisional until the owner adjudicates."
    )
    L.append("")
    if manifest.get("errors"):
        L.append(
            f"> ⚠️ {len(manifest['errors'])} unit(s) errored during the run — see results.json."
        )
        L.append("")

    if adjudication is not None:
        L.extend(_render_adjudication_section(adjudication))
        L.append("## Provisional rubric detail (axes 2–7)")
        L.append("")

    for col, s in summaries.items():
        L.append(f"## Column `{col}`")
        L.append("")
        L.append(
            f"- **Overall credibility (axes 2–7, rubric):** {s['overall_credibility']:.3f}"
        )
        quota = s["schranken_quota_provisional"]
        quota_str = (
            "n/a"
            if quota is None
            else f"{quota:.3f} ({'100%' if quota == 1.0 else 'BELOW 100%'})"
        )
        L.append(
            f"- **Schranken-quota (provisional):** {quota_str} over {s['n_gate_cases']} gate-relevant cases"
        )
        L.append(
            f"- Axis 1 (Faktische Korrektheit): **human-final for all {s['n_cases']} answers** "
            f"(worksheet); especially emphasized in {s['axis1_human_pending']} case(s)"
        )
        L.append(f"- Provisional per-case status: {s['provisional_status_counts']}")
        L.append("")
        L.append("| Axis | Name | Credibility | pass/partial/fail |")
        L.append("|---|---|---|---|")
        for a in range(2, 8):
            cred = s["axis_credibility"].get(a)
            c = s["axis_counts"].get(a, {"pass": 0, "partial": 0, "fail": 0})
            cred_str = "—" if cred is None else f"{cred:.3f}"
            L.append(
                f"| {a} | {AXES[a]} | {cred_str} | {c['pass']}/{c['partial']}/{c['fail']} |"
            )
        L.append(f"| 1 | {AXES[1]} | human-final | pending |")
        L.append("")

    L.append("## Per-case provisional status")
    L.append("")
    L.append("| Case | Class | Column | Provisional | Gate (prov.) | Intent |")
    L.append("|---|---|---|---|---|---|")
    for r in recs:
        sc = r["score"]
        gate = "—"
        if sc["gate_relevant"]:
            g = sc["provisional_gate_clean"]
            gate = "clean" if g is True else ("VIOLATED" if g is False else "unknown")
        L.append(
            f"| {r['case_id']} | {r['klass'].split('(')[0].strip()} | {r['column']} | {sc['provisional_status']} | {gate} | {r['intent'] or '—'} |"
        )
    L.append("")
    L.append(
        "→ Adjudicate factual correctness + the hard gates in `human_review_worksheet.md`; "
        "final credibility + Schranken-quota are recomputed from your verdicts."
    )
    L.append("")
    return "\n".join(L)


def _render_worksheet(manifest: dict, recs: list[dict]) -> str:
    by_case: dict[str, list[dict]] = {}
    order: list[str] = []
    for r in recs:
        if r["case_id"] not in by_case:
            by_case[r["case_id"]] = []
            order.append(r["case_id"])
        by_case[r["case_id"]].append(r)

    L: list[str] = []
    L.append(f"# M1 Human-Review Worksheet — {manifest['run_label']}")
    L.append("")
    L.append(
        f"L1 `{manifest['l1_model_resolved']}` · judge `{manifest['judge_model']}` · "
        f"git `{manifest['git_sha']}` · {manifest['timestamp']}"
    )
    L.append("")
    L.append(
        "**You are the oracle.** The judge checked rubric-adherence (advisory). For each "
        "answer below, set the FINAL verdict on **factual correctness (axis 1)** and on each "
        "relevant **hard gate**. Mark `[x]`. A single hard-gate VIOLATION anywhere drops the "
        "Schranken-quota below 100%."
    )
    L.append("")
    L.append(
        "Hard gates: **walked_into_trap** (confirmed a known incompatibility), "
        "**invented_precision** (a precise number/designation invented without basis), "
        "**confident_wrong** (a confidently false statement about a known fact)."
    )
    L.append("")
    L.append("---")
    L.append("")

    for cid in order:
        rows = by_case[cid]
        base = rows[0]
        L.append(f"## {cid} — {base['klass']}")
        if base["kontext"]:
            L.append(f"*Kontext:* {base['kontext']}")
        L.append(f"**Eingabe:** {base['input']}")
        L.append("")
        L.append(f"**must_catch (zentrale Einsicht):** {base['must_catch']}")
        L.append(
            f"**Relevante hard gates:** {', '.join(base['hard_gates']) or '— (keine)'}"
        )
        L.append("")
        for r in rows:
            j = r["judge"]
            L.append(
                f"### Column `{r['column']}` — answer ({r['answer_model'] or 'n/a'}, intent={r['intent'] or '—'})"
            )
            if r["error"]:
                L.append(f"> ⚠️ ERROR: {r['error']}")
            L.append("")
            L.append("<details><summary>Antwort anzeigen</summary>")
            L.append("")
            L.append("```text")
            L.append((r["answer_text"] or "(leer)").strip())
            L.append("```")
            L.append("</details>")
            L.append("")
            # judge advisory
            if j.get("parse_ok"):
                mc = "; ".join(
                    f"{x.get('status', '?')}" for x in j.get("must_contain", [])
                )
                named = j.get("must_catch", {}).get("named")
                viol = [
                    x.get("point", "")
                    for x in j.get("must_avoid", [])
                    if x.get("violated") is True
                ]
                L.append(
                    f"_Judge (advisory):_ must_contain=[{mc}] · must_catch.named={named} · "
                    f"must_avoid violated={viol or 'none'}"
                )
            else:
                L.append("_Judge (advisory): unparseable / no answer._")
            L.append("")
            L.append(
                "**Verdict — Faktische Korrektheit (Achse 1):**  `[ ] PASS`  `[ ] FAIL`  — Notiz: "
            )
            for g in base["hard_gates"]:
                L.append(
                    f"**Verdict — hard gate `{g}`:**  `[ ] CLEAN`  `[ ] VIOLATED`  — Notiz: "
                )
            L.append("")
        L.append("---")
        L.append("")
    return "\n".join(L)
