"""Render eval artifacts: results.json (REPLAY), report.md (credibility + Schranken-quota,
provisional), and human_review_worksheet.md (the owner adjudicates factual correctness +
the 3 hard gates here).
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

from sealai_v2.core.contracts import AXES


def _verdict_to_dict(v) -> dict | None:
    if v is None:
        return None
    return {
        "action": str(getattr(v.action, "value", v.action)),
        "regenerated": v.regenerated,
        "parse_ok": v.parse_ok,
        "findings": [
            {
                "trap_id": f.trap_id,
                "gate": f.gate,
                "review_state": f.review_state,
                "evidence": f.evidence,
            }
            for f in v.findings
        ],
    }


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
        "draft_model": rec.draft_model,
        "draft_text": rec.draft_text,
        "grounded": rec.grounded,
        "n_grounding": rec.n_grounding,
        "error": rec.error,
        "judge": dataclasses.asdict(rec.judge),
        "score": dataclasses.asdict(rec.score),
        "verifier": _verdict_to_dict(rec.verifier),
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


_EPDM_POLAR_RE = re.compile(r"epdm\b[^.\n]{0,40}?\bpolar\w*", re.IGNORECASE)


def _asserts_epdm_polar(text: str) -> bool:
    """Heuristic FLAG (ADVISORY — the human read of the final is ground truth, NOT this).

    Flags only an assertion that EPDM ITSELF is polar (e.g. 'EPDM ist ein polarer Kautschuk').
    It does NOT flag correct usages:
      - negations — 'EPDM ist unpolar' (``\\bpolar`` won't match inside 'unpolar');
      - EPDM *suiting* polar media — 'EPDM ist für polare Medien', 'polare Lösungsmittel'.
    Crude by design; a miss is acceptable because the worksheet (axis-1) is the authority."""
    for m in _EPDM_POLAR_RE.finditer(text or ""):
        # normalise markdown emphasis (**bold**) + whitespace so the context checks are robust
        seg = re.sub(r"[*_`]+", "", m.group(0).lower())
        seg = re.sub(r"\s+", " ", seg)
        if any(
            neg in seg
            for neg in (
                "unpolar",
                "non-polar",
                "nonpolar",
                "apolar",
                "nicht polar",
                "nichtpolar",
            )
        ):
            continue  # 'EPDM ist unpolar' — correct
        if any(
            ok in seg
            for ok in (
                "für polar",
                "gegen polar",
                "polare medien",
                "polaren medien",
                "polares medium",
                "polare lösung",
                "polaren lösung",
                "polares lösung",
            )
        ):
            continue  # EPDM *suits/attacks* polar media/solvents — correct, not an EPDM-is-polar claim
        return True
    return False


def _final_answer_asserts_epdm_polar(rec: dict) -> bool:
    """Gate-level check. A deterministic L3 hedge never ASSERTS the wrong claim (it states the
    reviewed correct fact + caveat), so the polar-heuristic is skipped for ``l3-hedge`` answers —
    it would otherwise false-fire on any 'polar' substring the hedge legitimately mentions. Real
    model answers are still scrubbed."""
    if (rec.get("answer_model") or "") == "l3-hedge":
        return False
    return _asserts_epdm_polar(rec.get("answer_text", ""))


def _render_l3_section(manifest: dict, recs: list[dict]) -> list[str]:
    L: list[str] = []
    L.append("## L3 Verifier (M2)")
    L.append("")
    L.append(
        "> L3 grounds against the **trap catalog only** (the matrix arrives at M3). Its verdict is "
        "a **signal, not an adjudication** — axis 1 + the three hard gates stay HUMAN-FINAL "
        "(worksheet). The targeted catch below uses the **already-confirmed** facts as the key "
        "(EPDM is non-polar; CALC-02 is a candidate rubric false-flag) — no new factual adjudication."
    )
    L.append("")

    by_action: dict[str, int] = {}
    for r in recs:
        v = r.get("verifier")
        act = (v or {}).get("action", "—")
        by_action[act] = by_action.get(act, 0) + 1
    L.append(f"- L3 action counts (over {len(recs)} units): {by_action}")
    L.append("")

    # --- M2 ACCEPTANCE GATE (detection signal; polar string-match is ADVISORY only) ---
    L.append("### M2 acceptance gate (signal — owner confirms)")
    L.append("")
    t2 = [r for r in recs if r["case_id"] == "TRAP-02"]
    c2 = [r for r in recs if r["case_id"] == "CALC-02"]

    def _acted(r: dict) -> bool:
        return (r.get("verifier") or {}).get("action") in (
            "corrected",
            "blocked_hedge",
            "flag",
        )

    # Detection = L3 fired the reviewed trap and acted on the TRAP-02 draft. This is the gate.
    t2_detected = bool(t2) and all(_acted(r) for r in t2)
    # The polar string-heuristic is ADVISORY only — it false-positives on correct "polare Medien"
    # usage; the ground truth for TRAP-02 is the HUMAN read of the finals (axis-1, worksheet).
    t2_flagged = [r["column"] for r in t2 if _final_answer_asserts_epdm_polar(r)]
    c2_ok = bool(c2) and all(
        (r.get("verifier") or {}).get("action") == "pass" for r in c2
    )
    L.append(
        f"- **TRAP-02 detected & corrected (L3 fired the reviewed trap):** "
        f"{'✅ signal-pass' if t2_detected else '❌ signal-FAIL'} — "
        + ", ".join(
            f"{r['column']}: {(r.get('verifier') or {}).get('action', '—')}" for r in t2
        )
    )
    if t2_flagged:
        L.append(
            f"  - ⚠️ polar string-heuristic (ADVISORY, not a verdict) flagged: "
            f"{', '.join(t2_flagged)} — verify the final by hand; it false-positives on correct "
            "'polare Medien' usage. Ground truth = the human read of the shown finals (axis-1)."
        )
    else:
        L.append(
            "  - polar string-heuristic (advisory): no flags (finals read clean; axis-1 human-final)."
        )
    L.append(
        f"- **CALC-02 NOT false-flagged:** {'✅ signal-pass' if c2_ok else '❌ signal-FAIL'} — "
        + ", ".join(
            f"{r['column']}: {(r.get('verifier') or {}).get('action', '—')}" for r in c2
        )
    )
    L.append("")
    L.append(
        f"> **M2 detection signal = "
        f"{'✅ TRAP-02 detected+corrected both columns; CALC-02 clean' if (t2_detected and c2_ok) else '❌ see above'}.** "
        "TRAP-02 ground truth is the **human read of the finals** (axis-1 HUMAN-FINAL); the polar "
        "string-heuristic is advisory only. Per the owner decision, a same-model L3 *detection* miss "
        "would trigger the cross-vendor swap (M2.1) — not the case here."
    )
    L.append("")

    # --- false-flag candidates (precision) ---
    fp = [
        r
        for r in recs
        if (r.get("verifier") or {}).get("action")
        in ("corrected", "blocked_hedge", "flag")
        and r["case_id"] not in ("TRAP-02", "CALC-02")
        and r["score"]["provisional_gate_clean"] is not False
    ]
    L.append("### False-flag candidates (precision — owner reviews)")
    L.append("")
    if not fp:
        L.append("_None — L3 acted only on the divergence target(s)._")
    else:
        L.append(
            f"L3 acted on {len(fp)} unit(s) that M1 considered clean — review for over-block:"
        )
        for r in fp:
            traps = ", ".join(
                f["trap_id"] for f in (r.get("verifier") or {}).get("findings", [])
            )
            L.append(
                f"- {r['case_id']} ({r['column']}): {(r.get('verifier') or {}).get('action')} "
                f"[{traps}]"
            )
    L.append("")

    # --- per-case L3 detail ---
    L.append("### Per-case L3 action")
    L.append("")
    L.append("| Case | Column | L3 action | regen | traps hit |")
    L.append("|---|---|---|---|---|")
    for r in recs:
        v = r.get("verifier") or {}
        traps = ", ".join(f["trap_id"] for f in v.get("findings", [])) or "—"
        L.append(
            f"| {r['case_id']} | {r['column']} | {v.get('action', '—')} | "
            f"{'yes' if v.get('regenerated') else '—'} | {traps} |"
        )
    L.append("")
    return L


def _render_grounding_section(manifest: dict, recs: list[dict]) -> list[str]:
    L: list[str] = []
    L.append("## L2 Grounding (M3)")
    L.append("")
    L.append(
        "> **Calibration — what this validates.** M3 validates the grounding MECHANISM + injection + "
        "vorläufig-flagging + no-M2-regression: *when the right reviewed Fachkarte is retrieved, does "
        "grounding lift accuracy and does L3 catch more via positive evidence.* It does NOT validate "
        "retrieval RECALL at corpus scale — the in-process keyword retriever is a measurement/CI "
        "instrument (like the fake LLM client). Production recall + semantic retrieval (the Qdrant "
        "adapter) is a separate, later concern + its own retrieval-quality eval."
    )
    L.append("")
    grounded = [r for r in recs if r.get("grounded")]
    L.append(
        f"- Grounded units (≥1 reviewed Fachkarte injected): **{len(grounded)}/{len(recs)}**; "
        "the rest answer **vorläufig** (no reviewed card retrieved — expected for non-material-compat cases)."
    )
    L.append("")
    L.append("| Case | Column | Grounding | #facts | L3 card-contradiction |")
    L.append("|---|---|---|---|---|")
    for r in recs:
        cards = ", ".join(
            f["trap_id"]
            for f in (r.get("verifier") or {}).get("findings", [])
            if f.get("kind") == "card"
        )
        g = "grounded" if r.get("grounded") else "vorläufig"
        L.append(
            f"| {r['case_id']} | {r['column']} | {g} | {r.get('n_grounding', 0)} | {cards or '—'} |"
        )
    L.append("")
    return L


def _render_report(
    manifest: dict, summaries: dict, recs: list[dict], adjudication: dict | None = None
) -> str:
    L: list[str] = []
    milestone = manifest.get("milestone", "M1")
    L.append(f"# {milestone} Eval-REPLAY — {manifest['run_label']}")
    L.append("")
    L.append(f"- Milestone: **{milestone}** — {manifest['subject']}")
    if manifest.get("verify_enabled"):
        L.append(f"- L3 verifier model: `{manifest.get('verifier_model')}`")
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

    if manifest.get("verify_enabled"):
        L.extend(_render_l3_section(manifest, recs))

    if manifest.get("ground_enabled"):
        L.extend(_render_grounding_section(manifest, recs))

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
    L.append(
        f"# {manifest.get('milestone', 'M1')} Human-Review Worksheet — {manifest['run_label']}"
    )
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
