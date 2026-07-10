# -*- coding: utf-8 -*-
"""TARGETED eval-REPLAY runner for INC-BASELINE-HARDENING (eval-only; outside ops/tree-hash.sh).

Runs ONLY the edited dimensions (default: beratungs_ux + loesungserarbeitung + calibration as the
speed-trap no-regression watcher) through the SAME single-turn unit + judge + scorer the canonical
harness uses — reusing ``harness._run_*`` verbatim, so the pipeline / judge / parametric Schranke are
identical to a full run, just scoped. Writes results.json + human_review_worksheet.md (owner
adjudicates axis-1 + hard gates — TRAP-02; NEVER auto-ticked) + a short targeted_report.md.

Honors the prod model cell + the baseline-hardening flag straight from the environment
(``ops/run_eval.sh`` sources the keys/models from .env.prod; export SEALAI_V2_BASELINE_HARDENING_ENABLED
before calling). Hermetic: no DATABASE_URL → in-process stores, no prod-DB write.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
from datetime import datetime, timezone
from pathlib import Path

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import ModelConfig
from sealai_v2.eval import harness, report
from sealai_v2.eval.scorer import summarize_column
from sealai_v2.llm.factory import build_client_factory, resolve_l1_model
from sealai_v2.pipeline.pipeline import build_pipeline

_RUNS_DIR = Path(__file__).resolve().parent / "runs"

_DIM_RUNNERS = {
    "beratungs_ux": harness._run_beratungs_ux,
    "loesungserarbeitung": harness._run_loesungserarbeitung,
    "calibration": harness._run_calibration,
}


async def _amain(args) -> None:
    settings = Settings()
    factory = build_client_factory(settings)
    meter = harness.TokenMeter()

    def subject_client_for(provider: str):
        return harness.MeteringLlmClient(factory(provider), meter)

    l1_model = await resolve_l1_model(settings)
    pipeline = build_pipeline(
        settings, client_for=subject_client_for, l1_model=l1_model
    )
    judge_client = factory(settings.judge_provider or settings.provider)
    judge_cfg = ModelConfig(
        model=settings.judge_model,
        temperature=settings.judge_temperature,
        max_output_tokens=settings.eval_judge_max_output_tokens,
        cache_key="sealai-v2-judge",
        stage="judge",
        reasoning_effort=settings.eval_judge_reasoning_effort,
    )
    fixtures = harness._load_calc_fixtures()

    dims = [d.strip() for d in args.dims.split(",") if d.strip()]
    records = []
    for dim in dims:
        runner = _DIM_RUNNERS[dim]
        if dim == "calibration":
            recs, errs = await runner(
                pipeline, judge_cfg, judge_client=judge_client, fixtures=fixtures
            )
        else:
            recs, errs = await runner(pipeline, judge_cfg, judge_client=judge_client)
        records.extend(recs)
        for e in errs:
            print(f"[{dim}] ERROR {e}")

    summaries = {
        dim: dataclasses.asdict(
            summarize_column(dim, [r.score for r in records if r.column == dim])
        )
        for dim in dims
    }
    leak_records = [r for r in records if r.parametric_leaks]
    parametric = {
        "n_records": len(records),
        "n_leak_records": len(leak_records),
        "schranken_quota": (
            round((len(records) - len(leak_records)) / len(records), 3)
            if records
            else None
        ),
        "per_case": {
            f"{r.case.id}/{r.column}": [
                dataclasses.asdict(leak) for leak in r.parametric_leaks
            ]
            for r in leak_records
        },
    }
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "run_label": args.label,
        "milestone": "BASELINE-HARDENING (targeted)",
        "subject": "INC-BASELINE-HARDENING targeted replay — beratungs_ux + loesungserarbeitung (+ calibration no-regression)",
        "git_sha": "uncommitted",
        "timestamp": timestamp,
        "l1_model_resolved": l1_model,
        "l1_model_configured": settings.l1_model,
        "judge_model": settings.judge_model,
        "helper_model": settings.helper_model,
        "verifier_model": settings.verifier_model,
        "columns": dims,
        "n_cases": len({r.case.id for r in records}),
        "baseline_hardening_enabled": settings.baseline_hardening_enabled,
        "scoring_split": (
            "judge = rubric-adherence only (axes 2-7); axis 1 + hard gates HUMAN-FINAL (worksheet)."
        ),
        "errors": [r.error for r in records if r.error],
    }

    run_dir = _RUNS_DIR / args.label
    report.write_all(run_dir, manifest, records, summaries, parametric=parametric)

    print(f"\n=== TARGETED baseline-hardening replay: {args.label} ===")
    print(
        f"L1 {l1_model} · baseline_hardening_enabled={settings.baseline_hardening_enabled}"
    )
    for dim in dims:
        s = summaries[dim]
        print(
            f"[{dim}] cases={sum(1 for r in records if r.column == dim)} "
            f"credibility(2-7)={s['overall_credibility']:.3f} "
            f"status={s['provisional_status_counts']}"
        )
    schranken_quota = parametric["schranken_quota"]
    schranken_quota_text = (
        "n/a" if schranken_quota is None else f"{schranken_quota:.3f}"
    )
    print(
        f"[parametric] Schranken-quota(agent-final)={schranken_quota_text} "
        f"({parametric['n_leak_records']} leak record(s))"
    )
    # advisory judge read on the two narrator-replay target cases
    targets = {"BUX-SPEED-TRAP-FIRSTTURN-01", "LOES-UNKLARES-MEDIUM-KEIN-MATERIAL-01"}
    print("\n--- target cases (judge advisory; owner adjudicates hard gates) ---")
    for r in records:
        if r.case.id in targets:
            j = report._record_to_dict(r)["judge"]  # same dict form the worksheet uses
            named = (j.get("must_catch") or {}).get("named")
            viol = [
                x.get("point", "")
                for x in (j.get("must_avoid") or [])
                if x.get("violated") is True
            ]
            print(
                f"{r.case.id}: must_catch.named={named} · must_avoid_violated={viol or 'none'} · "
                f"computed=[{r.computed_brief or '-'}] · parametric_leaks={len(r.parametric_leaks)}"
            )
    print(f"\nArtifacts: {run_dir}")
    print(
        "-> Owner adjudicates axis-1 + hard gates in human_review_worksheet.md (TRAP-02)."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="targeted baseline-hardening eval-REPLAY")
    ap.add_argument("--label", default="baseline-hardening-replay")
    ap.add_argument("--dims", default="beratungs_ux,loesungserarbeitung,calibration")
    args = ap.parse_args()
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
