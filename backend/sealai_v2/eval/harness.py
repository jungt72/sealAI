"""Eval harness — runs the seed cases through the pipeline IN-PROCESS and scores them.

M1 measures L1-alone across BOTH flag columns (flags-off floor + flags-default-on production
baseline). Bounded concurrency keeps the run fast; each unit = one pipeline turn (soft
understand + L1 answer) + one judge call. Tenant scope (P0) is threaded as a fixed eval tenant.
Writes results.json + report.md + human_review_worksheet.md.
"""

from __future__ import annotations

import asyncio
import dataclasses
from dataclasses import dataclass

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import Flags, ModelConfig, VerifierVerdict
from sealai_v2.eval import report
from sealai_v2.eval.cases import Case, load_cases
from sealai_v2.eval.judge import JudgeResult, judge_answer
from sealai_v2.eval.scorer import CaseScore, score_case, summarize_column
from sealai_v2.llm.factory import build_llm_client, resolve_l1_model
from sealai_v2.pipeline.pipeline import build_pipeline
from sealai_v2.security.tenant import TenantContext

# Decision #2: the two flag columns measured at M1.
COLUMNS: dict[str, Flags] = {
    "flags_off": Flags(compliance_hint=False, safety_critical=False),
    "flags_on": Flags(compliance_hint=True, safety_critical=True),
}

_EVAL_TENANT = TenantContext(tenant_id="eval-tenant")


@dataclass
class Record:
    case: Case
    column: str
    intent: str | None
    intent_rationale: str | None
    answer_text: str
    answer_model: str
    error: str | None
    judge: JudgeResult
    score: CaseScore
    verifier: VerifierVerdict | None = (
        None  # L3 verdict (M2); None if L3 disabled / errored
    )
    draft_text: str = (
        ""  # first-pass L1 draft (pre-L3); == answer_text when L3 didn't change it
    )
    draft_model: str = ""


async def _run_unit(
    pipeline, judge_cfg: ModelConfig, case: Case, column: str, flags: Flags
) -> Record:
    intent = rationale = None
    answer_text, answer_model, error = "", "", None
    draft_text, draft_model = "", ""
    verifier: VerifierVerdict | None = None
    try:
        result = await pipeline.run(case.input, tenant=_EVAL_TENANT, flags=flags)
        if result.understanding is not None:
            intent = result.understanding.intent.value
            rationale = result.understanding.rationale
        answer_text = result.answer.text
        answer_model = result.answer.model
        verifier = result.verifier
        if result.draft_answer is not None:
            draft_text = result.draft_answer.text
            draft_model = result.draft_answer.model
    except Exception as exc:  # noqa: BLE001 — record the failure, keep the run going
        error = f"{type(exc).__name__}: {exc}"

    if error is None and answer_text:
        judge = await judge_answer(
            pipeline.client, judge_cfg, case, answer_text, column
        )
    else:
        judge = JudgeResult(
            case_id=case.id, column=column, parse_ok=False, raw=f"(no answer: {error})"
        )
    return Record(
        case=case,
        column=column,
        intent=intent,
        intent_rationale=rationale,
        answer_text=answer_text,
        answer_model=answer_model,
        error=error,
        judge=judge,
        score=score_case(case, judge),
        verifier=verifier,
        draft_text=draft_text,
        draft_model=draft_model,
    )


async def run_eval(
    settings: Settings,
    *,
    run_dir,
    run_label: str,
    git_sha: str,
    timestamp: str,
    columns: dict[str, Flags] | None = None,
    smoke_limit: int | None = None,
) -> dict:
    columns = columns or COLUMNS
    cases = load_cases()
    if smoke_limit:
        cases = cases[:smoke_limit]

    client = build_llm_client(settings)
    l1_model = await resolve_l1_model(settings)
    pipeline = build_pipeline(settings, client, l1_model=l1_model)
    judge_cfg = ModelConfig(
        model=settings.judge_model, temperature=settings.judge_temperature
    )

    sem = asyncio.Semaphore(max(1, settings.concurrency))

    async def guarded(case: Case, column: str, flags: Flags) -> Record:
        async with sem:
            return await _run_unit(pipeline, judge_cfg, case, column, flags)

    units = [(c, name, flags) for c in cases for name, flags in columns.items()]
    records: list[Record] = await asyncio.gather(
        *(guarded(c, n, f) for c, n, f in units)
    )

    summaries = {
        name: dataclasses.asdict(
            summarize_column(name, [r.score for r in records if r.column == name])
        )
        for name in columns
    }

    l3_on = settings.verify_enabled
    manifest = {
        "run_label": run_label,
        "git_sha": git_sha,
        "timestamp": timestamp,
        "milestone": "M2" if l3_on else "M1",
        "subject": (
            "L1+L3 (understand→answer→verify; L3 grounds against the trap catalog; ground/cite stubs)"
            if l3_on
            else "L1-alone (understand→answer; ground/verify/cite are inert stubs)"
        ),
        "l1_model_resolved": l1_model,
        "l1_model_configured": settings.l1_model,
        "judge_model": settings.judge_model,
        "helper_model": settings.helper_model,
        "verifier_model": settings.verifier_model if l3_on else None,
        "verify_enabled": l3_on,
        "understand_enabled": settings.understand_enabled,
        "columns": list(columns.keys()),
        "n_cases": len(cases),
        "concurrency": settings.concurrency,
        "scoring_split": (
            "LLM-judge: rubric-adherence only (axes 2-7); axis 1 (Faktische Korrektheit) and the "
            "3 hard gates are HUMAN-FINAL via the worksheet."
        ),
        "errors": [r.error for r in records if r.error],
    }

    report.write_all(run_dir, manifest, records, summaries)
    return {"manifest": manifest, "summaries": summaries}
