"""CLI for the M1 eval-REPLAY:  python -m sealai_v2.eval [--smoke N] [--label L] [--columns ...]

Runs the seed cases through the pipeline in-process (no HTTP) and writes
``eval/runs/<label>/{results.json,report.md,human_review_worksheet.md}``. Needs OPENAI_API_KEY
in the environment for the live run.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sealai_v2.config.settings import Settings
from sealai_v2.eval.harness import COLUMNS, run_eval

_RUNS_DIR = Path(__file__).resolve().parent / "runs"


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[3]),
            text=True,
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser(description="sealai_v2 M1 eval-REPLAY (L1-alone)")
    ap.add_argument("--label", default="m1-baseline", help="run label / output subdir")
    ap.add_argument(
        "--smoke", type=int, default=None, help="run only the first N cases (dry-run)"
    )
    ap.add_argument(
        "--columns",
        default="flags_off,flags_on",
        help="comma list of flag columns to run (subset of: flags_off, flags_on)",
    )
    ap.add_argument(
        "--run-dir", default=None, help="output dir (default eval/runs/<label>)"
    )
    ap.add_argument(
        "--adjudicate",
        action="store_true",
        help="recompute final numbers from human_review_worksheet.md (no LLM call) and "
        "re-render report.md; does not run the eval",
    )
    args = ap.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else (_RUNS_DIR / args.label)

    if args.adjudicate:
        from sealai_v2.eval.adjudicate import adjudicate_run

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        adj = adjudicate_run(run_dir, run_label=args.label, timestamp=timestamp)
        print(f"\n=== M1 adjudication (recompute): {args.label} ===")
        print(f"label: {adj['label']}  ·  verdicts parsed: {adj['n_verdicts_parsed']}")
        for col, fs in adj["columns"].items():
            q = fs["schranken_quota_final"]
            print(
                f"[{col}] final credibility(2-7)={fs['overall_credibility']:.3f}  "
                f"Schranken-quota(final)={'n/a' if q is None else f'{q:.3f}'}  "
                f"adjudicated {fs['n_units_adjudicated']}/{fs['n_units_human_relevant']}  "
                f"pending {fs['n_units_pending']}"
            )
        mq = adj.get("memory_schranken_quota")
        if mq is not None:
            print(
                f"[memory] memory_fabrication-Schranken(agent-final, not adjudicated)={mq:.3f}"
            )
        print(f"\nArtifacts: {run_dir}")
        return

    settings = Settings()
    columns = {k: COLUMNS[k] for k in args.columns.split(",") if k in COLUMNS}
    if not columns:
        raise SystemExit(
            f"no valid columns in {args.columns!r}; choose from {list(COLUMNS)}"
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    out = asyncio.run(
        run_eval(
            settings,
            run_dir=run_dir,
            run_label=args.label,
            git_sha=_git_sha(),
            timestamp=timestamp,
            columns=columns,
            smoke_limit=args.smoke,
        )
    )
    print(f"\n=== M1 eval-REPLAY: {args.label} ===")
    print(
        f"L1 model: {out['manifest']['l1_model_resolved']}  ·  cases: {out['manifest']['n_cases']}"
    )
    for col, s in out["summaries"].items():
        quota = s["schranken_quota_provisional"]
        print(
            f"[{col}] credibility(2-7)={s['overall_credibility']:.3f}  "
            f"Schranken-quota(prov)={'n/a' if quota is None else f'{quota:.3f}'}  "
            f"status={s['provisional_status_counts']}"
        )
    mt = out.get("multiturn")
    if mt:
        ms = mt["summary"]
        drop = ms.get("drop")
        rate = (
            (drop["dropped"] / drop["proposed"] if drop["proposed"] else 0.0)
            if drop
            else None
        )
        mq = ms["memory_schranken_quota"]
        print(
            f"[memory] memory_fabrication-Schranken(agent-final)="
            f"{'n/a' if mq is None else f'{mq:.3f}'} over {ms['n_turns']} turns  "
            f"drop-rate={'n/a' if rate is None else f'{rate:.3f}'}  "
            f"re-ask: carry_miss={ms['n_carry_misses']} reask_viol={ms['n_reask_violations']}"
        )
    edge = out.get("edge")
    if edge:
        es = edge["summary"]
        eq = es["schranken_quota_provisional"]
        print(
            f"[edge] cases={edge['n_cases']}  credibility(2-7)={es['overall_credibility']:.3f}  "
            f"edge_overreach-Schranken(prov)={'n/a' if eq is None else f'{eq:.3f}'}  "
            f"(non-edge no-regression vs baseline 1.000/0.991 — see report.md)"
        )
    inj = out.get("injection")
    if inj:
        xq = (inj.get("exfiltration") or {}).get("schranken_quota")
        iq = inj["summary"]["schranken_quota_provisional"]
        print(
            f"[injection] cases={inj['n_cases']}  "
            f"exfiltration-Schranken(agent-final)={'n/a' if xq is None else f'{xq:.3f}'}  "
            f"injection_override-Schranken(prov)={'n/a' if iq is None else f'{iq:.3f}'}"
        )
    print(f"\nArtifacts: {run_dir}")
    print("→ Adjudicate factual correctness + hard gates in human_review_worksheet.md")


if __name__ == "__main__":
    main()
