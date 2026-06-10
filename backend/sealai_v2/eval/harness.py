"""Eval harness — runs the seed cases through the pipeline IN-PROCESS and scores them.

M1 measures L1-alone across BOTH flag columns (flags-off floor + flags-default-on production
baseline). Bounded concurrency keeps the run fast; each unit = one pipeline turn (soft
understand + L1 answer) + one judge call. Tenant scope (P0) is threaded as a fixed eval tenant.
Writes results.json + report.md + human_review_worksheet.md.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import Flags, ModelConfig, VerifierVerdict
from sealai_v2.eval import report
from sealai_v2.eval.cases import Case, load_cases, load_edge_cases, load_injection_cases
from sealai_v2.eval.judge import JudgeResult, judge_answer, judge_no_reask
from sealai_v2.eval.multiturn import (
    load_multiturn_cases,
    run_multiturn_case,
    summarize_multiturn,
)
from sealai_v2.eval.scorer import CaseScore, score_case, summarize_column
from sealai_v2.knowledge.fachkarten import load_fachkarten
from sealai_v2.llm.factory import build_llm_client, resolve_l1_model
from sealai_v2.pipeline.pipeline import build_pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.leak_detect import exfiltration_leak
from sealai_v2.security.tenant import TenantContext

# Decision #2: the two flag columns measured at M1.
COLUMNS: dict[str, Flags] = {
    "flags_off": Flags(compliance_hint=False, safety_critical=False),
    "flags_on": Flags(compliance_hint=True, safety_critical=True),
}

_EVAL_TENANT = TenantContext(tenant_id="eval-tenant")
_CALC_FIXTURES_FILE = Path(__file__).resolve().parent / "calc_fixtures.json"


def _load_calc_fixtures() -> dict[str, dict]:
    """Per-case calc params for the measurement (M4: params come from eval fixtures, not intake)."""
    if not _CALC_FIXTURES_FILE.exists():
        return {}
    return json.loads(_CALC_FIXTURES_FILE.read_text(encoding="utf-8")).get(
        "fixtures", {}
    )


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
    grounded: bool = (
        False  # M3: ≥1 reviewed Fachkarte injected; False → answer is "vorläufig"
    )
    n_grounding: int = 0  # number of reviewed grounding facts injected this turn
    n_computed: int = 0  # M4: deterministically computed values injected this turn
    computed_brief: str = ""  # "v_m_s=12.57 m/s; ..." — what the candidate rested on


async def _run_unit(
    pipeline,
    judge_cfg: ModelConfig,
    case: Case,
    column: str,
    flags: Flags,
    params: dict | None = None,
) -> Record:
    intent = rationale = None
    answer_text, answer_model, error = "", "", None
    draft_text, draft_model = "", ""
    grounded, n_grounding = False, 0
    n_computed, computed_brief = 0, ""
    verifier: VerifierVerdict | None = None
    try:
        result = await pipeline.run(
            case.input, tenant=_EVAL_TENANT, flags=flags, params=params
        )
        if result.understanding is not None:
            intent = result.understanding.intent.value
            rationale = result.understanding.rationale
        answer_text = result.answer.text
        answer_model = result.answer.model
        verifier = result.verifier
        grounded = result.grounded
        n_grounding = len(result.grounding_facts)
        n_computed = len(result.computed_values)
        computed_brief = "; ".join(
            f"{c.name}={c.value} {c.unit}" for c in result.computed_values
        )
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
        grounded=grounded,
        n_grounding=n_grounding,
        n_computed=n_computed,
        computed_brief=computed_brief,
    )


async def _run_multiturn(pipeline, judge_cfg: ModelConfig) -> dict | None:
    """Run the class-A multi-turn cases live (memory + memory_fabrication + re-ask both halves).
    Returns a JSON-able block (results + summary) or None when memory is disabled (no measurement)."""
    if pipeline.memory is None:
        return None

    async def _reask_judge(answer_text: str, known: tuple[str, ...]) -> dict[str, bool]:
        return await judge_no_reask(pipeline.client, judge_cfg, answer_text, known)

    cases = load_multiturn_cases()
    results = []
    errors: list[str] = []
    for case in cases:  # sequential — keeps the distiller drop-rate attribution clean
        try:
            results.append(
                await run_multiturn_case(
                    pipeline, case, tenant=_EVAL_TENANT, judge=_reask_judge
                )
            )
        except Exception as exc:  # noqa: BLE001 — record + keep going (mirrors _run_unit), so a
            # single flaky turn never crashes the whole run and loses the single-turn artifacts.
            errors.append(f"{case.id}: {type(exc).__name__}: {exc}")
    drop = pipeline.distiller.stats if pipeline.distiller is not None else None
    summary = summarize_multiturn(results, drop_stats=drop)
    return {
        "summary": dataclasses.asdict(summary),
        "errors": errors,
        "cases": [
            {
                "case_id": r.case_id,
                "memory_gate_clean": r.memory_gate_clean,
                "carry_ok": r.carry_ok,
                "reask_ok": r.reask_ok,
                "turns": [
                    {
                        "index": t.index,
                        "input": t.input,
                        "answer": t.answer,
                        "case_state": [
                            {"feld": f.feld, "wert": f.wert} for f in t.case_state
                        ],
                        "must_carry": list(t.must_carry),
                        "carried_missing": list(t.carried_missing),
                        "must_not_reask": list(t.must_not_reask),
                        "reask_violations": list(t.reask_violations),
                        "memory_fabrication": [
                            {"feld": f.feld, "wert": f.wert}
                            for f in t.memory_fabrication
                        ],
                        "memory_clean": t.memory_clean,
                    }
                    for t in r.turns
                ],
            }
            for r in results
        ],
    }


async def _run_edge(pipeline, judge_cfg: ModelConfig) -> tuple[list[Record], list[str]]:
    """Run the Konversations-Rand (EDGE) class (M6a-B) through the EXISTING single-turn unit + judge
    + scorer (no new runner). One pass (column ``edge``, flags_on — edge behavior is orthogonal to
    the compliance/safety flags). Returns (records, errors); the records are folded into the canonical
    record list so they appear in the worksheet (``edge_overreach`` is HUMAN-FINAL) and the
    adjudication recompute, while the column filter keeps them OUT of the non-edge no-regression."""
    cases = load_edge_cases()
    records: list[Record] = []
    errors: list[str] = []
    for case in cases:
        try:
            records.append(
                await _run_unit(pipeline, judge_cfg, case, "edge", COLUMNS["flags_on"])
            )
        except Exception as exc:  # noqa: BLE001 — record + keep going (mirrors _run_multiturn)
            errors.append(f"{case.id}: {type(exc).__name__}: {exc}")
    return records, errors


async def _run_injection(
    pipeline, judge_cfg: ModelConfig
) -> tuple[list[Record], list[str], dict | None]:
    """Run the Injektion/Sicherheit (INJECTION) class (M6b) through the EXISTING single-turn unit +
    judge + scorer (no new runner) — that path yields the HUMAN-FINAL ``injection_override`` (judge
    must_avoid → owner ticks). PLUS the DETERMINISTIC ``exfiltration`` gate (agent-final): run
    ``leak_detect`` over each answer vs the static system-prompt + the reviewed-claim texts. Returns
    (records, errors, exfiltration-block). Records fold into the canonical list (worksheet +
    adjudicate); exfiltration is reported agent-final (not a worksheet tick)."""
    cases = load_injection_cases()
    if not cases:
        return [], [], None
    # reference for the deterministic leak check: the static doctrine prompt + reviewed claim texts.
    ref_prompt = PromptAssembler().system_prompt(flags=COLUMNS["flags_on"])
    kb_claims = [
        c.text for card in load_fachkarten().cards for c in card.reviewed_claims()
    ]
    records: list[Record] = []
    errors: list[str] = []
    leaks: dict[str, object] = {}
    for case in cases:
        try:
            rec = await _run_unit(
                pipeline, judge_cfg, case, "injection", COLUMNS["flags_on"]
            )
            records.append(rec)
            leaks[case.id] = exfiltration_leak(
                answer=rec.answer_text, system_prompt=ref_prompt, kb_claims=kb_claims
            )
        except Exception as exc:  # noqa: BLE001 — record + keep going (mirrors _run_multiturn)
            errors.append(f"{case.id}: {type(exc).__name__}: {exc}")
    exfil = {
        "n_leaks": sum(1 for v in leaks.values() if v.leaked),
        "schranken_quota": (
            round(sum(1 for v in leaks.values() if not v.leaked) / len(leaks), 3)
            if leaks
            else None
        ),
        "per_case": {
            cid: {
                "system_prompt_leak": v.system_prompt_leak,
                "kb_claims_leaked": v.kb_claims_leaked,
                "leaked": v.leaked,
            }
            for cid, v in leaks.items()
        },
    }
    return records, errors, exfil


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

    fixtures = _load_calc_fixtures()
    sem = asyncio.Semaphore(max(1, settings.concurrency))

    async def guarded(case: Case, column: str, flags: Flags) -> Record:
        async with sem:
            return await _run_unit(
                pipeline, judge_cfg, case, column, flags, params=fixtures.get(case.id)
            )

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

    # M6a — multi-turn / memory measurement (class A). Runs AFTER the single-turn units (which pass
    # no session → memory inert → distiller never called), so the distiller drop counters reflect
    # ONLY this measurement. Sequential per case: each gets its own session (tenant+session isolated)
    # and the few cases keep the drop-rate attribution clean. Memory is orthogonal to the compliance/
    # safety flags, so it runs once (no per-column fan-out).
    multiturn = await _run_multiturn(pipeline, judge_cfg)

    # M6a-B — Konversations-Rand (EDGE) class. Runs after the (frozen) non-edge sets; the non-edge
    # `summaries` above are the no-regression anchor vs the m6a-memory baseline. The edge records are
    # folded into the canonical `records` (column `edge` → excluded from the non-edge summaries, but
    # present in the worksheet for the HUMAN-FINAL `edge_overreach` adjudication + the recompute).
    edge_records, edge_errors = await _run_edge(pipeline, judge_cfg)
    edge = (
        {
            "summary": dataclasses.asdict(
                summarize_column("edge", [r.score for r in edge_records])
            ),
            "n_cases": len(edge_records),
            "errors": edge_errors,
        }
        if edge_records
        else None
    )
    records = list(records) + edge_records

    # M6b — Injektion/Sicherheit class. injection_override is human-final (folds via the worksheet,
    # so the records join the canonical list); exfiltration is agent-final deterministic (the leak
    # sub-block). Excluded from the non-edge no-regression by column.
    inj_records, inj_errors, inj_exfil = await _run_injection(pipeline, judge_cfg)
    injection = (
        {
            "summary": dataclasses.asdict(
                summarize_column("injection", [r.score for r in inj_records])
            ),
            "n_cases": len(inj_records),
            "errors": inj_errors,
            "exfiltration": inj_exfil,
        }
        if inj_records
        else None
    )
    records = list(records) + inj_records

    l3_on = settings.verify_enabled
    l2_on = settings.ground_enabled
    l4_on = settings.compute_enabled
    milestone = (
        "M4"
        if (l3_on and l2_on and l4_on)
        else "M3"
        if (l3_on and l2_on)
        else "M2"
        if l3_on
        else "M1"
    )
    manifest = {
        "run_label": run_label,
        "git_sha": git_sha,
        "timestamp": timestamp,
        "milestone": milestone,
        "subject": (
            "L1+L2+L3+M4-calc (understand→ground→compute→answer→verify; deterministic computed values into L1 + L3; render = M4b)"
            if (l3_on and l2_on and l4_on)
            else "L1+L2+L3 (understand→ground→answer→verify; L2 injects reviewed Fachkarten into L1 + L3; cite stub)"
            if (l3_on and l2_on)
            else "L1+L3 (understand→answer→verify; L3 grounds against the trap catalog; ground/cite stubs)"
            if l3_on
            else "L1-alone (understand→answer; ground/verify/cite are inert stubs)"
        ),
        "l1_model_resolved": l1_model,
        "l1_model_configured": settings.l1_model,
        "judge_model": settings.judge_model,
        "helper_model": settings.helper_model,
        "verifier_model": settings.verifier_model if l3_on else None,
        "verify_enabled": l3_on,
        "ground_enabled": l2_on,
        "compute_enabled": l4_on,
        "understand_enabled": settings.understand_enabled,
        "memory_enabled": settings.memory_enabled,
        "distill_enabled": settings.distill_enabled,
        "n_multiturn_cases": (len(multiturn["cases"]) if multiturn else 0),
        "n_edge_cases": (edge["n_cases"] if edge else 0),
        "n_injection_cases": (injection["n_cases"] if injection else 0),
        "baseline_non_edge": {
            "flags_off": 1.000,
            "flags_on": 0.991,
        },  # m6a-memory no-regression anchor
        "columns": list(columns.keys()),
        "n_cases": len(cases),
        "concurrency": settings.concurrency,
        "scoring_split": (
            "LLM-judge: rubric-adherence only (axes 2-7); axis 1 (Faktische Korrektheit) and the "
            "3 hard gates are HUMAN-FINAL via the worksheet."
        ),
        "errors": [r.error for r in records if r.error]
        + [f"multiturn::{e}" for e in (multiturn or {}).get("errors", [])]
        + [f"edge::{e}" for e in (edge or {}).get("errors", [])]
        + [f"injection::{e}" for e in (injection or {}).get("errors", [])],
    }

    report.write_all(
        run_dir,
        manifest,
        records,
        summaries,
        multiturn=multiturn,
        edge=edge,
        injection=injection,
    )
    return {
        "manifest": manifest,
        "summaries": summaries,
        "multiturn": multiturn,
        "edge": edge,
        "injection": injection,
    }
