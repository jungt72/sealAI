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
import time
from dataclasses import dataclass
from pathlib import Path

from sealai_v2.config.settings import Settings
from sealai_v2.core.calc.leak_detector import detect_parametric_leaks
from sealai_v2.core.contracts import Flags, ModelConfig, VerifierVerdict
from sealai_v2.eval import report
from sealai_v2.eval.cases import (
    Case,
    load_archetype_cases,
    load_calibration_cases,
    load_gegencheck_cases,
    load_diagnose_cases,
    load_decode_cases,
    load_alternativen_cases,
    load_beratungs_ux_cases,
    load_loesungserarbeitung_cases,
    load_cases,
    load_edge_cases,
    load_injection_cases,
)
from sealai_v2.eval.judge import JudgeResult, judge_answer, judge_no_reask
from sealai_v2.eval.multiturn import (
    load_multiturn_cases,
    run_multiturn_case,
    summarize_multiturn,
)
from sealai_v2.eval.metering import MeteringLlmClient, TokenMeter
from sealai_v2.eval.judge_pacing import PacedLlmClient
from sealai_v2.eval.scorer import (
    CaseScore,
    aggregate_answer_quality,
    score_case,
    summarize_column,
)
from sealai_v2.knowledge.fachkarten import load_fachkarten
from sealai_v2.llm.factory import (
    build_client_factory,
    build_client_for,
    resolve_l1_model,
)
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


def _percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile (no numpy dep). ``pct`` in [0,100]. Empty → None."""
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return round(s[k], 1)


def _latency_summary(elapsed: list[float]) -> dict:
    return {
        "n": len(elapsed),
        "p50_ms": _percentile(elapsed, 50),
        "p95_ms": _percentile(elapsed, 95),
        "mean_ms": round(sum(elapsed) / len(elapsed), 1) if elapsed else None,
    }


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
    parametric_leaks: tuple = ()  # M8: deterministic detector hits on the FINAL answer (agent-final gate)
    elapsed_ms: float = (
        0.0  # wall clock of pipeline.run for this unit (judge call excluded)
    )


async def _run_unit(
    pipeline,
    judge_cfg: ModelConfig,
    case: Case,
    column: str,
    flags: Flags,
    params: dict | None = None,
    judge_client=None,
) -> Record:
    intent = rationale = None
    answer_text, answer_model, error = "", "", None
    draft_text, draft_model = "", ""
    grounded, n_grounding = False, 0
    n_computed, computed_brief = 0, ""
    parametric_leaks: tuple = ()
    verifier: VerifierVerdict | None = None
    elapsed_ms = 0.0
    t0 = time.monotonic()
    try:
        result = await pipeline.run(
            case.input, tenant=_EVAL_TENANT, flags=flags, params=params
        )
        elapsed_ms = (time.monotonic() - t0) * 1000.0
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
        # M8 — the parametric Schranke on the FINAL answer (deterministic, agent-final)
        parametric_leaks = detect_parametric_leaks(
            answer_text, computed_values=result.computed_values
        )
        if result.draft_answer is not None:
            draft_text = result.draft_answer.text
            draft_model = result.draft_answer.model
    except Exception as exc:  # noqa: BLE001 — record the failure, keep the run going
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        error = f"{type(exc).__name__}: {exc}"

    # The judge is the measuring INSTRUMENT — held at baseline across cells, so it uses its own
    # client (``judge_client``), decoupled from the helper client. Default → pipeline.client
    # (keeps the offline harness tests byte-identical, where no dedicated judge client is passed).
    jc = judge_client if judge_client is not None else pipeline.client
    if error is None and answer_text:
        judge = await judge_answer(jc, judge_cfg, case, answer_text, column)
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
        parametric_leaks=parametric_leaks,
        elapsed_ms=round(elapsed_ms, 1),
    )


async def _run_multiturn(
    pipeline, judge_cfg: ModelConfig, judge_client=None
) -> dict | None:
    """Run the class-A multi-turn cases live (memory + memory_fabrication + re-ask both halves).
    Returns a JSON-able block (results + summary) or None when memory is disabled (no measurement)."""
    if pipeline.memory is None:
        return None

    jc = judge_client if judge_client is not None else pipeline.client

    async def _reask_judge(answer_text: str, known: tuple[str, ...]) -> dict[str, bool]:
        return await judge_no_reask(jc, judge_cfg, answer_text, known)

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
                "compute_ok": r.compute_ok,
                "parametric_clean": r.parametric_clean,
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
                        "computed_ids": list(t.computed_ids),
                        "must_compute": list(t.must_compute),
                        "compute_missing": list(t.compute_missing),
                        "parametric_leaks": [
                            dataclasses.asdict(leak) for leak in t.parametric_leaks
                        ],
                        "parametric_clean": t.parametric_clean,
                    }
                    for t in r.turns
                ],
            }
            for r in results
        ],
    }


async def _run_edge(
    pipeline, judge_cfg: ModelConfig, judge_client=None
) -> tuple[list[Record], list[str]]:
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
                await _run_unit(
                    pipeline,
                    judge_cfg,
                    case,
                    "edge",
                    COLUMNS["flags_on"],
                    judge_client=judge_client,
                )
            )
        except Exception as exc:  # noqa: BLE001 — record + keep going (mirrors _run_multiturn)
            errors.append(f"{case.id}: {type(exc).__name__}: {exc}")
    return records, errors


async def _run_archetype(
    pipeline, judge_cfg: ModelConfig, judge_client=None
) -> tuple[list[Record], list[str]]:
    """archetype_fit class (G5, V2.1 Inc 1) — runs the archetype-recognition cases through the EXISTING
    single-turn unit + judge + scorer (column ``archetype``, flags_on). Folded into the canonical
    records; excluded from the non-edge no-regression by column. A CREDIBILITY/axes class (NO new hard
    gate — the 8 Schranken stay fixed): it measures whether the recognised archetype's interview
    questions + blind spots surface. Owner is the factual oracle (axis 1 / any gate human-final)."""
    cases = load_archetype_cases()
    records: list[Record] = []
    errors: list[str] = []
    for case in cases:
        try:
            records.append(
                await _run_unit(
                    pipeline,
                    judge_cfg,
                    case,
                    "archetype",
                    COLUMNS["flags_on"],
                    judge_client=judge_client,
                )
            )
        except Exception as exc:  # noqa: BLE001 — record + keep going (mirrors _run_edge)
            errors.append(f"{case.id}: {type(exc).__name__}: {exc}")
    return records, errors


async def _run_calibration(
    pipeline, judge_cfg: ModelConfig, judge_client=None, fixtures=None
) -> tuple[list[Record], list[str]]:
    """confident_correct_vs_hedge class (C4, V2.1 Inc 2) — runs the calibration cases through the
    EXISTING single-turn unit + judge + scorer (column ``calibration``, flags_on). Folded into the
    canonical records; excluded from the non-edge no-regression by column. A CREDIBILITY/axes class
    (NO new hard gate — the 8 Schranken stay fixed): assertive-WHERE-grounded vs honest hedge, plus
    the kern-fix-01 restraint guard (CALIB-RESTRAINT-01). Calc params come from the eval fixtures
    (the v-limit case needs d1_mm/rpm); the restraint case has NO fixture by design. Owner is the
    factual oracle (axis 1 / any gate human-final)."""
    cases = load_calibration_cases()
    fixtures = fixtures or {}
    records: list[Record] = []
    errors: list[str] = []
    for case in cases:
        try:
            records.append(
                await _run_unit(
                    pipeline,
                    judge_cfg,
                    case,
                    "calibration",
                    COLUMNS["flags_on"],
                    params=fixtures.get(case.id),
                    judge_client=judge_client,
                )
            )
        except Exception as exc:  # noqa: BLE001 — record + keep going (mirrors _run_archetype)
            errors.append(f"{case.id}: {type(exc).__name__}: {exc}")
    return records, errors


async def _run_beratungs_ux(
    pipeline, judge_cfg: ModelConfig, judge_client=None
) -> tuple[list[Record], list[str]]:
    """Beratungs-UX class (V2.1 Inc 3) — runs the consultative-UX regression cases through the EXISTING
    single-turn unit + judge + scorer (column ``beratungs_ux``, flags_on). Folded into the canonical
    records; excluded from the non-edge no-regression by the column filter. Mostly CREDIBILITY/axes;
    three cases carry an EXISTING hard gate (walked_into_trap / confident_wrong) — no new Schranke. NO
    calc fixtures by design (UX cases test conversation behaviour; the speed-trap is named qualitatively).
    Owner is the factual oracle (axis 1 / any gate human-final)."""
    cases = load_beratungs_ux_cases()
    records: list[Record] = []
    errors: list[str] = []
    for case in cases:
        try:
            records.append(
                await _run_unit(
                    pipeline,
                    judge_cfg,
                    case,
                    "beratungs_ux",
                    COLUMNS["flags_on"],
                    params=None,
                    judge_client=judge_client,
                )
            )
        except Exception as exc:  # noqa: BLE001 — record + keep going (mirrors _run_calibration)
            errors.append(f"{case.id}: {type(exc).__name__}: {exc}")
    return records, errors


async def _run_loesungserarbeitung(
    pipeline, judge_cfg: ModelConfig, judge_client=None
) -> tuple[list[Record], list[str]]:
    """Lösungserarbeitung class (V2.1 Inc 4) — runs the depth/epistemic-boundary regression cases through
    the EXISTING single-turn unit + judge + scorer (column ``loesungserarbeitung``, flags_on). Folded into
    the canonical records; excluded from the non-edge no-regression by the column filter. ALL five cases
    carry an EXISTING hard gate (invented_precision / confident_wrong) — no new Schranke. NO calc fixtures
    by design (the cases test what L1 may ASSERT, not parametric precision). Owner is the factual oracle
    (axis 1 / any gate human-final)."""
    cases = load_loesungserarbeitung_cases()
    records: list[Record] = []
    errors: list[str] = []
    for case in cases:
        try:
            records.append(
                await _run_unit(
                    pipeline,
                    judge_cfg,
                    case,
                    "loesungserarbeitung",
                    COLUMNS["flags_on"],
                    params=None,
                    judge_client=judge_client,
                )
            )
        except Exception as exc:  # noqa: BLE001 — record + keep going (mirrors _run_beratungs_ux)
            errors.append(f"{case.id}: {type(exc).__name__}: {exc}")
    return records, errors


async def _run_alternativen(
    pipeline, judge_cfg: ModelConfig, judge_client=None
) -> tuple[list[Record], list[str]]:
    """Alternativen (ALTERNATIVEN) class (Modus F, V2.1) - capable-manufacturer cases (column
    ``alternativen``, flags_on). Measures §3.9 neutrality + no invented makers + honest no-data
    (Dim. 6 empty). Owner is the factual oracle (axis 1 human-final)."""
    cases = load_alternativen_cases()
    records: list[Record] = []
    errors: list[str] = []
    for case in cases:
        try:
            records.append(
                await _run_unit(
                    pipeline,
                    judge_cfg,
                    case,
                    "alternativen",
                    COLUMNS["flags_on"],
                    judge_client=judge_client,
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{case.id}: {type(exc).__name__}: {exc}")
    return records, errors


async def _run_decode(
    pipeline, judge_cfg: ModelConfig, judge_client=None
) -> tuple[list[Record], list[str]]:
    """Decode (DECODE) class (Modus G, V2.1) - designation-decode cases through the EXISTING
    single-turn unit + judge + scorer (column ``decode``, flags_on). The equivalence case is
    gate-relevant (confident_wrong) - a false "X = Y" interchange claim is a deploy-blocking
    violation (§9.2). Owner is the factual oracle (axis 1 / any gate human-final)."""
    cases = load_decode_cases()
    records: list[Record] = []
    errors: list[str] = []
    for case in cases:
        try:
            records.append(
                await _run_unit(
                    pipeline,
                    judge_cfg,
                    case,
                    "decode",
                    COLUMNS["flags_on"],
                    judge_client=judge_client,
                )
            )
        except Exception as exc:  # noqa: BLE001 - record + keep going (mirrors _run_diagnose)
            errors.append(f"{case.id}: {type(exc).__name__}: {exc}")
    return records, errors


async def _run_diagnose(
    pipeline, judge_cfg: ModelConfig, judge_client=None
) -> tuple[list[Record], list[str]]:
    """Diagnose (DIAGNOSE) class (Modus D, V2.1) - runs the symptom cases through the EXISTING
    single-turn unit + judge + scorer (column ``diagnose``, flags_on). Folded into the canonical
    records; excluded from the non-edge no-regression by column. A CREDIBILITY/axes class (NO new
    hard gate): measures honest, plausible, vorlaeufig-framed diagnosis (Dim. 5 all-draft) with the
    manufacturer-defer, no invented number, and the discriminating follow-up on an unclear symptom.
    Owner is the factual oracle (axis 1 human-final)."""
    cases = load_diagnose_cases()
    records: list[Record] = []
    errors: list[str] = []
    for case in cases:
        try:
            records.append(
                await _run_unit(
                    pipeline,
                    judge_cfg,
                    case,
                    "diagnose",
                    COLUMNS["flags_on"],
                    judge_client=judge_client,
                )
            )
        except Exception as exc:  # noqa: BLE001 - record + keep going (mirrors _run_gegencheck)
            errors.append(f"{case.id}: {type(exc).__name__}: {exc}")
    return records, errors


async def _run_gegencheck(
    pipeline, judge_cfg: ModelConfig, judge_client=None
) -> tuple[list[Record], list[str]]:
    """Gegencheck (GEGENCHECK) class (Modus E, V2.1) - runs the existing-seal-check cases through the
    EXISTING single-turn unit + judge + scorer (column ``gegencheck``, flags_on). Folded into the
    canonical records; excluded from the non-edge no-regression by column. A CREDIBILITY/axes class
    (NO new hard gate - the 8 Schranken stay fixed): measures the E4-1 calibration - disqualify the
    incompatible with the grounded reason, surface the conditional's condition, and never affirm
    suitability for the compatible / no-data case. Owner is the factual oracle (axis 1 human-final).
    No calc fixtures (compatibility cases need none)."""
    cases = load_gegencheck_cases()
    records: list[Record] = []
    errors: list[str] = []
    for case in cases:
        try:
            records.append(
                await _run_unit(
                    pipeline,
                    judge_cfg,
                    case,
                    "gegencheck",
                    COLUMNS["flags_on"],
                    judge_client=judge_client,
                )
            )
        except Exception as exc:  # noqa: BLE001 - record + keep going (mirrors _run_calibration)
            errors.append(f"{case.id}: {type(exc).__name__}: {exc}")
    return records, errors


async def _run_injection(
    pipeline, judge_cfg: ModelConfig, judge_client=None
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
                pipeline,
                judge_cfg,
                case,
                "injection",
                COLUMNS["flags_on"],
                judge_client=judge_client,
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
    tree_hash: str = "",
    dirty: bool = False,
    timestamp: str,
    columns: dict[str, Flags] | None = None,
    smoke_limit: int | None = None,
    include_auxiliary: bool = True,
    client_factory=None,
) -> dict:
    columns = columns or COLUMNS
    cases = load_cases()
    if smoke_limit:
        cases = cases[:smoke_limit]

    # Per-role provider factory (cached): an all-openai cell shares ONE client across roles
    # (byte-identical to the old single-client path). SUBJECT roles (L1/L3/helpers) are metered
    # for the cell's est. cost/turn; the JUDGE gets its OWN unmetered client (instrument, not
    # subject — and held at baseline across cells, decoupled from the helper provider).
    # ``client_factory`` injected → offline/controlled mode (mocked matrix validation): use it AND
    # skip the live models.list() resolution (no network), trusting the configured l1_model.
    offline = client_factory is not None
    factory = client_factory or build_client_factory(settings)
    meter = TokenMeter()

    subject_clients: dict[str, MeteringLlmClient] = {}

    def subject_client_for(provider: str) -> MeteringLlmClient:
        if provider not in subject_clients:
            raw_client = factory(provider)
            subject_clients[provider] = MeteringLlmClient(
                raw_client
                if offline
                else PacedLlmClient(
                    raw_client,
                    max_concurrency=settings.eval_subject_concurrency,
                    min_interval_s=settings.eval_subject_min_interval_s,
                ),
                meter,
            )
        return subject_clients[provider]

    l1_model = settings.l1_model if offline else await resolve_l1_model(settings)
    pipeline = build_pipeline(
        settings, client_for=subject_client_for, l1_model=l1_model
    )
    judge_provider = settings.judge_provider or settings.provider
    # The judge has its own provider budget and is never on the user-serving path. Give live evals
    # a dedicated, rate-aware client; controlled offline tests retain their injected fake unchanged.
    raw_judge_client = (
        factory(judge_provider)
        if offline
        else build_client_for(
            settings,
            judge_provider,
            max_retries=settings.eval_judge_max_retries,
        )
    )
    judge_client = (
        raw_judge_client
        if offline
        else PacedLlmClient(
            raw_judge_client,
            max_concurrency=settings.eval_judge_concurrency,
            min_interval_s=settings.eval_judge_min_interval_s,
        )
    )
    judge_cfg = ModelConfig(
        model=settings.judge_model,
        temperature=settings.judge_temperature,
        max_output_tokens=settings.eval_judge_max_output_tokens,
        cache_key="sealai-v2-judge",
        stage="judge",
        reasoning_effort=settings.eval_judge_reasoning_effort,
    )

    fixtures = _load_calc_fixtures()
    sem = asyncio.Semaphore(max(1, settings.concurrency))

    async def guarded(case: Case, column: str, flags: Flags) -> Record:
        async with sem:
            return await _run_unit(
                pipeline,
                judge_cfg,
                case,
                column,
                flags,
                params=fixtures.get(case.id),
                judge_client=judge_client,
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
    multiturn = (
        None
        if not include_auxiliary
        else await _run_multiturn(pipeline, judge_cfg, judge_client=judge_client)
    )

    # M6a-B — Konversations-Rand (EDGE) class. Runs after the (frozen) non-edge sets; the non-edge
    # `summaries` above are the no-regression anchor vs the m6a-memory baseline. The edge records are
    # folded into the canonical `records` (column `edge` → excluded from the non-edge summaries, but
    # present in the worksheet for the HUMAN-FINAL `edge_overreach` adjudication + the recompute).
    edge_records, edge_errors = (
        ([], [])
        if not include_auxiliary
        else await _run_edge(pipeline, judge_cfg, judge_client=judge_client)
    )
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
    inj_records, inj_errors, inj_exfil = (
        ([], [], None)
        if not include_auxiliary
        else await _run_injection(pipeline, judge_cfg, judge_client=judge_client)
    )
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

    # archetype_fit (G5, V2.1 Inc 1) — runs after the frozen non-edge sets (the `summaries` above stay
    # the no-regression anchor). Folded in under column `archetype` (excluded from the non-edge
    # summaries by the column filter); a CREDIBILITY/axes class — NO new hard gate (the 8 stay fixed).
    arch_records, arch_errors = (
        ([], [])
        if not include_auxiliary
        else await _run_archetype(pipeline, judge_cfg, judge_client=judge_client)
    )
    archetype = (
        {
            "summary": dataclasses.asdict(
                summarize_column("archetype", [r.score for r in arch_records])
            ),
            "n_cases": len(arch_records),
            "errors": arch_errors,
        }
        if arch_records
        else None
    )
    records = list(records) + arch_records

    # confident_correct_vs_hedge (C4, V2.1 Inc 2) — calibration cases (assertive-where-grounded vs
    # honest hedge; + the kern-fix-01 restraint guard). Folded under column `calibration` (excluded
    # from the non-edge summaries by the column filter); CREDIBILITY/axes class — NO new hard gate.
    # Appended BEFORE the parametric block so CALIB-RESTRAINT-01 is in the agent-final parametric gate.
    calib_records, calib_errors = (
        ([], [])
        if not include_auxiliary
        else await _run_calibration(
            pipeline, judge_cfg, judge_client=judge_client, fixtures=fixtures
        )
    )
    calibration = (
        {
            "summary": dataclasses.asdict(
                summarize_column("calibration", [r.score for r in calib_records])
            ),
            "n_cases": len(calib_records),
            "errors": calib_errors,
        }
        if calib_records
        else None
    )
    records = list(records) + calib_records

    # Beratungs-UX (V2.1 Inc 3) — consultative-UX regression cases (Klären-vor-Empfehlen / Tiefe-auf-
    # Abruf / Prioritätsleiter). Folded under column `beratungs_ux` (excluded from the non-edge
    # summaries by the column filter). Mostly CREDIBILITY/axes; three cases carry an EXISTING hard gate
    # (walked_into_trap / confident_wrong) — no new Schranke. Appended BEFORE the parametric block.
    bux_records, bux_errors = (
        ([], [])
        if not include_auxiliary
        else await _run_beratungs_ux(pipeline, judge_cfg, judge_client=judge_client)
    )
    beratungs_ux = (
        {
            "summary": dataclasses.asdict(
                summarize_column("beratungs_ux", [r.score for r in bux_records])
            ),
            "n_cases": len(bux_records),
            "errors": bux_errors,
        }
        if bux_records
        else None
    )
    records = list(records) + bux_records

    # Lösungserarbeitung (V2.1 Inc 4) — depth/epistemic-boundary regression cases (erarbeiten statt
    # abschieben, OHNE zu erfinden). Folded under column `loesungserarbeitung` (excluded from the non-edge
    # summaries by the column filter). ALL five cases carry an EXISTING hard gate (invented_precision /
    # confident_wrong) — no new Schranke. Appended BEFORE the parametric block.
    loes_records, loes_errors = (
        ([], [])
        if not include_auxiliary
        else await _run_loesungserarbeitung(
            pipeline, judge_cfg, judge_client=judge_client
        )
    )
    loesungserarbeitung = (
        {
            "summary": dataclasses.asdict(
                summarize_column("loesungserarbeitung", [r.score for r in loes_records])
            ),
            "n_cases": len(loes_records),
            "errors": loes_errors,
        }
        if loes_records
        else None
    )
    records = list(records) + loes_records

    # Gegencheck (GEGENCHECK, Modus E, V2.1) - existing-seal-check cases (disqualify the incompatible,
    # surface the conditional's condition, never affirm the compatible). Folded under column
    # `gegencheck` (excluded from the non-edge summaries by the column filter); CREDIBILITY/axes
    # class - NO new hard gate. Appended BEFORE the parametric block (same agent-final gate coverage).
    gc_records, gc_errors = (
        ([], [])
        if not include_auxiliary
        else await _run_gegencheck(pipeline, judge_cfg, judge_client=judge_client)
    )
    gegencheck = (
        {
            "summary": dataclasses.asdict(
                summarize_column("gegencheck", [r.score for r in gc_records])
            ),
            "n_cases": len(gc_records),
            "errors": gc_errors,
        }
        if gc_records
        else None
    )
    records = list(records) + gc_records

    # Diagnose (DIAGNOSE, Modus D, V2.1) - symptom cases. Folded under column `diagnose`
    # (excluded from the non-edge summaries by the column filter); CREDIBILITY/axes - NO new hard
    # gate. Appended BEFORE the parametric block (same agent-final gate coverage).
    dg_records, dg_errors = (
        ([], [])
        if not include_auxiliary
        else await _run_diagnose(pipeline, judge_cfg, judge_client=judge_client)
    )
    diagnose = (
        {
            "summary": dataclasses.asdict(
                summarize_column("diagnose", [r.score for r in dg_records])
            ),
            "n_cases": len(dg_records),
            "errors": dg_errors,
        }
        if dg_records
        else None
    )
    records = list(records) + dg_records

    # Decode (DECODE, Modus G, V2.1) - designation-decode cases. Folded under column `decode`
    # (excluded from the non-edge summaries by the column filter); the equivalence case is
    # gate-relevant (confident_wrong, §9.2). Appended BEFORE the parametric block.
    dc_records, dc_errors = (
        ([], [])
        if not include_auxiliary
        else await _run_decode(pipeline, judge_cfg, judge_client=judge_client)
    )
    decode = (
        {
            "summary": dataclasses.asdict(
                summarize_column("decode", [r.score for r in dc_records])
            ),
            "n_cases": len(dc_records),
            "errors": dc_errors,
        }
        if dc_records
        else None
    )
    records = list(records) + dc_records

    # Alternativen (ALTERNATIVEN, Modus F) - neutral capable-manufacturer cases. Folded under
    # column `alternativen`; CREDIBILITY/axes - NO new hard gate.
    al_records, al_errors = (
        ([], [])
        if not include_auxiliary
        else await _run_alternativen(pipeline, judge_cfg, judge_client=judge_client)
    )
    alternativen = (
        {
            "summary": dataclasses.asdict(
                summarize_column("alternativen", [r.score for r in al_records])
            ),
            "n_cases": len(al_records),
            "errors": al_errors,
        }
        if al_records
        else None
    )
    records = list(records) + al_records

    # M8 — the parametric Schranke over ALL single-turn finals (agent-final, deterministic; the
    # multiturn block carries its own per-turn quota). Mirrors the exfiltration block: quota must
    # reach 1.0; any hit is listed verbatim for owner adjudication of disputed cases.
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
    from sealai_v2.config.runtime_profile import (
        runtime_profile,
        runtime_profile_hash,
    )

    manifest = {
        "run_label": run_label,
        "git_sha": git_sha,
        # eval↔deploy binding (the V2 deploy gate keys on tree_hash): the served-runtime CONTENT
        # hash (ops/tree-hash.sh — the single source of truth) + whether that content had
        # uncommitted changes at eval time. git_sha alone is the HEAD commit, which under
        # validate-then-commit points at the PRE-fix commit; tree_hash binds the actual content.
        "tree_hash": tree_hash,
        "dirty": dirty,
        # Full behavior binding: tree_hash covers source bytes; this profile covers the
        # environment-driven model, trust-layer and retrieval behavior those bytes serve.
        "runtime_profile": runtime_profile(settings),
        "runtime_profile_hash": runtime_profile_hash(settings),
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
        # Per-role provider+model (model-swap cell descriptor). None provider → the global default.
        # [P1.6] ``roles.l1`` is also the eval↔deploy MODEL binding: the V2 deploy gate
        # (ops/v2_deploy_gate.py) compares it as ``provider/model`` against the served-runtime L1, so a
        # run adjudicated on one L1 cannot gate a deploy serving another. ``model`` is the RESOLVED L1
        # (post resolve_l1_model — the id the eval actually ran), ``provider`` the role's effective one.
        "roles": {
            "l1": {
                "provider": settings.l1_provider or settings.provider,
                "model": l1_model,
            },
            "verifier": {
                "provider": settings.verifier_provider or settings.provider,
                "model": settings.verifier_model if l3_on else None,
            },
            "helper": {
                "provider": settings.helper_provider or settings.provider,
                "model": settings.helper_model,
            },
            "judge": {
                "provider": settings.judge_provider or settings.provider,
                "model": settings.judge_model,
            },
        },
        "verify_enabled": l3_on,
        "ground_enabled": l2_on,
        "compute_enabled": l4_on,
        "understand_enabled": settings.understand_enabled,
        "memory_enabled": settings.memory_enabled,
        "distill_enabled": settings.distill_enabled,
        "n_multiturn_cases": (len(multiturn["cases"]) if multiturn else 0),
        "n_edge_cases": (edge["n_cases"] if edge else 0),
        "n_injection_cases": (injection["n_cases"] if injection else 0),
        "n_archetype_cases": (archetype["n_cases"] if archetype else 0),
        "n_calibration_cases": (calibration["n_cases"] if calibration else 0),
        "n_beratungs_ux_cases": (beratungs_ux["n_cases"] if beratungs_ux else 0),
        "n_loesungserarbeitung_cases": (
            loesungserarbeitung["n_cases"] if loesungserarbeitung else 0
        ),
        "baseline_non_edge": {
            "flags_off": 1.000,
            "flags_on": 0.991,
        },  # m6a-memory no-regression anchor
        "columns": list(columns.keys()),
        "n_cases": len(cases),
        "auxiliary_suites_included": include_auxiliary,
        "concurrency": settings.concurrency,
        "subject_pacing": {
            "concurrency": settings.eval_subject_concurrency,
            "min_interval_s": settings.eval_subject_min_interval_s,
        },
        "judge_pacing": {
            "concurrency": settings.eval_judge_concurrency,
            "min_interval_s": settings.eval_judge_min_interval_s,
            "max_retries": settings.eval_judge_max_retries,
            "max_output_tokens": settings.eval_judge_max_output_tokens,
            "reasoning_effort": settings.eval_judge_reasoning_effort,
        },
        "scoring_split": (
            "LLM-judge: rubric-adherence only (axes 2-7); axis 1 (Faktische Korrektheit) and the "
            "3 hard gates are HUMAN-FINAL via the worksheet."
        ),
        "errors": [r.error for r in records if r.error]
        + [f"multiturn::{e}" for e in (multiturn or {}).get("errors", [])]
        + [f"edge::{e}" for e in (edge or {}).get("errors", [])]
        + [f"injection::{e}" for e in (injection or {}).get("errors", [])]
        + [f"archetype::{e}" for e in (archetype or {}).get("errors", [])]
        + [f"calibration::{e}" for e in (calibration or {}).get("errors", [])]
        + [f"beratungs_ux::{e}" for e in (beratungs_ux or {}).get("errors", [])]
        + [
            f"loesungserarbeitung::{e}"
            for e in (loesungserarbeitung or {}).get("errors", [])
        ],
    }

    # --- model-swap gate aggregates (latency / answer-quality / cost) -----------------------
    # Answer-quality = the judge-derived SUBSTANCE signals NOT in credibility (owner #1 priority).
    # Computed per canonical column + overall, over the SAME records credibility uses (edge/injection
    # are excluded by the column filter, mirroring the no-regression `summaries`).
    answer_quality = {
        "by_column": {
            name: aggregate_answer_quality(
                [r.judge for r in records if r.column == name]
            )
            for name in columns
        },
        "overall": aggregate_answer_quality(
            [r.judge for r in records if r.column in columns]
        ),
    }
    # Latency over every single-turn-style record (single-turn + edge + injection; each = one turn).
    latency = _latency_summary([r.elapsed_ms for r in records])
    # Cost: RAW subject-role token counts (rate-agnostic — the matrix runner applies published rates
    # per the cell's models). Subject = L1/L3/helpers (metered); judge excluded (instrument).
    n_mt_turns = (multiturn or {}).get("summary", {}).get("n_turns", 0) or 0
    n_turns = len(records) + n_mt_turns
    token_usage = {
        "by_model": meter.by_model,  # per-model counts → runner applies each model's published rate
        "subject_prompt_tokens": meter.prompt_tokens,
        "subject_completion_tokens": meter.completion_tokens,
        "subject_total_tokens": meter.total_tokens,
        "subject_llm_calls": meter.n_calls,
        "calls_with_usage": meter.n_calls_with_usage,
        "n_turns": n_turns,
        "tokens_per_turn": (
            round(meter.total_tokens / n_turns, 1) if n_turns else None
        ),
    }
    # "Live catches fire": the L3 verifier action tally — proof the trust net is still ACTIVE under a
    # swapped model (not silently dead). Deterministic exfiltration/parametric catches live in their
    # own blocks (injection.exfiltration, parametric).
    catches = {"pass": 0, "flag": 0, "corrected": 0, "blocked_hedge": 0}
    for r in records:
        if r.verifier is not None:
            catches[r.verifier.action.value] = (
                catches.get(r.verifier.action.value, 0) + 1
            )

    report.write_all(
        run_dir,
        manifest,
        records,
        summaries,
        multiturn=multiturn,
        edge=edge,
        injection=injection,
        parametric=parametric,
        archetype=archetype,
    )
    return {
        "manifest": manifest,
        "summaries": summaries,
        "multiturn": multiturn,
        "edge": edge,
        "injection": injection,
        "parametric": parametric,
        "archetype": archetype,
        "calibration": calibration,
        "beratungs_ux": beratungs_ux,
        "loesungserarbeitung": loesungserarbeitung,
        "gegencheck": gegencheck,
        "diagnose": diagnose,
        "decode": decode,
        "alternativen": alternativen,
        "answer_quality": answer_quality,
        "latency": latency,
        "token_usage": token_usage,
        "catches": catches,
    }
