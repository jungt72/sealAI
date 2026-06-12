"""Multi-turn eval runner (M6a) — threads a session through ``pipeline.run`` so memory accumulates,
and applies the deterministic memory-integrity gate per turn (build-spec §7/§9).

This is the distiller's first real measurement — the single-turn REPLAY deliberately can't exercise
memory. Deterministic checks live here (no LLM):
  • **must_carry** — a prior STATED fact reached the case-state (and thus the prompt, by
    construction: ``pipeline.run`` builds ``case_context`` from ``memory.recall().case_state``).
  • **memory_fabrication** gate — every remembered number must trace to the user turns (c)(ii).
  • **must_compute** (M8) — the kern FIRED for the named calc-ids this turn (the binder fed it
    from remembered facts); the deterministic half of CALC-MEM-01.
  • **parametric_computation** gate (M8) — the FINAL (post-L3) answer asserts no value for a
    kern-owned quantity the kern didn't compute (``core/calc/leak_detector.py``; agent-final,
    mirrors ``memory_fabrication``).
The answer-level judge checks (must_not_reask / must_avoid / must_contain) layer on top in the
harness; they are not computed here. Pure orchestration over the injected pipeline.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from sealai_v2.core.calc.leak_detector import LeakFinding, detect_parametric_leaks
from sealai_v2.core.contracts import ComputedValue, RememberedFact, SessionContext
from sealai_v2.memory.distiller import DistillStats
from sealai_v2.memory.integrity import untraceable_numeric_facts
from sealai_v2.security.tenant import TenantContext

# A re-ask judge: given an answer + the already-known topics, returns {topic: reasked?}. Decoupled
# from the LLM client so offline tests can inject a fake; the harness binds it over judge.judge_no_reask.
ReaskJudge = Callable[[str, "tuple[str, ...]"], Awaitable["dict[str, bool]"]]

_SEED_DIR = Path(__file__).resolve().parent / "seed_cases"
_DEFAULT_MULTITURN_FILE = _SEED_DIR / "multiturn_v0.json"


@dataclass(frozen=True)
class TurnSpec:
    """One turn of a multi-turn case + its per-turn assertions (build-spec §9 / owner decision (a))."""

    input: str
    must_carry: tuple[
        str, ...
    ] = ()  # facts that must be in case-state by now (re-ask fix; deterministic)
    must_not_reask: tuple[
        str, ...
    ] = ()  # topics the answer must NOT re-ask (judge — harness layer)
    must_avoid: tuple[
        str, ...
    ] = ()  # edge: no domain claim / no briefing dump (hard must_avoid)
    must_contain: tuple[str, ...] = ()  # expected content (e.g. capability redirect)
    must_compute: tuple[
        str, ...
    ] = ()  # M8: calc-ids the kern must have computed this turn (deterministic)


@dataclass(frozen=True)
class MultiTurnCase:
    id: str
    klass: str
    turns: tuple[TurnSpec, ...]
    primary_axes: tuple[int, ...] = ()
    hard_gates: tuple[str, ...] = ()
    holdout: bool = False
    # Form-path seed (M8 user-form provenance): case-state facts written BEFORE any turn, via the
    # exact method the parameter form uses (edit_fact + explicit provenance). The only way to
    # exercise the user-form origin in eval — chat turns distill (distilled-from-conversation),
    # they never produce user-form. The seeded values are user-STATED content (typed in the form),
    # so they also feed the memory-fabrication trace corpus.
    seed_facts: tuple[RememberedFact, ...] = ()


@dataclass
class TurnResult:
    index: int
    input: str
    answer: str
    case_state: tuple[RememberedFact, ...]
    carried_missing: tuple[
        str, ...
    ]  # must_carry items NOT found in case-state (deterministic miss)
    memory_fabrication: tuple[
        RememberedFact, ...
    ]  # untraceable numeric facts (gate violation)
    must_carry: tuple[
        str, ...
    ] = ()  # asserted carry topics (denominator for the carry quota)
    must_not_reask: tuple[
        str, ...
    ] = ()  # asserted no-reask topics (denominator for the reask quota)
    reask_violations: tuple[
        str, ...
    ] = ()  # topics the judge says the answer re-asked anyway
    # M8 — the deterministic calc halves of this turn:
    computed_ids: tuple[str, ...] = ()  # calc-ids the kern actually computed this turn
    must_compute: tuple[
        str, ...
    ] = ()  # asserted calc-ids (denominator for the compute quota)
    compute_missing: tuple[str, ...] = ()  # asserted calc-ids the kern did NOT compute
    parametric_leaks: tuple[
        LeakFinding, ...
    ] = ()  # detector hits on the FINAL answer (gate violation)
    computed_values: tuple[
        ComputedValue, ...
    ] = ()  # full kern results this turn — carries input_origins (provenance attribution)

    @property
    def carry_ok(self) -> bool:
        return not self.carried_missing

    @property
    def memory_clean(self) -> bool:
        return not self.memory_fabrication

    @property
    def reask_ok(self) -> bool:
        return not self.reask_violations

    @property
    def compute_ok(self) -> bool:
        return not self.compute_missing

    @property
    def parametric_clean(self) -> bool:
        return not self.parametric_leaks


@dataclass
class MultiTurnResult:
    case_id: str
    turns: list[TurnResult]

    @property
    def memory_gate_clean(self) -> bool:
        return all(t.memory_clean for t in self.turns)

    @property
    def carry_ok(self) -> bool:
        return all(t.carry_ok for t in self.turns)

    @property
    def reask_ok(self) -> bool:
        return all(t.reask_ok for t in self.turns)

    @property
    def compute_ok(self) -> bool:
        return all(t.compute_ok for t in self.turns)

    @property
    def parametric_clean(self) -> bool:
        return all(t.parametric_clean for t in self.turns)


@dataclass(frozen=True)
class MultiTurnSummary:
    """Aggregate over the multi-turn run. ``memory_schranken_quota`` is AGENT-FINAL — the verbatim
    deterministic ``untraceable_numeric_facts()`` verdict per turn (no tolerance, no discretion);
    it is NOT human-adjudicated. carry (deterministic) + reask (judge) are the two re-ask halves;
    ``drop`` is the distiller's raw fabrication-rate instrument."""

    n_cases: int
    n_turns: int
    memory_schranken_quota: float | None  # clean turns / total turns; gate requires 1.0
    n_memory_violations: int
    carry_quota: float | None  # turns fully carried / turns with a must_carry assertion
    n_carry_misses: int
    reask_quota: (
        float | None
    )  # turns with no re-ask / turns with a must_not_reask assertion
    n_reask_violations: int
    # M8 — parametric Schranke (AGENT-FINAL, deterministic detector verdict per turn; gate
    # requires 1.0) + the compute half (kern fired where asserted).
    parametric_schranken_quota: float | None = None
    n_parametric_violations: int = 0
    compute_quota: float | None = (
        None  # turns fully computed / turns with a must_compute
    )
    n_compute_misses: int = 0
    drop: DistillStats | None = None


def _carried(item: str, case_state: tuple[RememberedFact, ...]) -> bool:
    blob = " ".join(f"{f.feld} {f.wert}" for f in case_state).lower()
    return item.lower() in blob


async def run_multiturn_case(
    pipeline,
    case: MultiTurnCase,
    *,
    tenant: TenantContext,
    judge: ReaskJudge | None = None,
) -> MultiTurnResult:
    """Run an ordered turn list through one session; capture answers + the deterministic checks +
    (when a ``judge`` is wired) the re-ask judge-half.

    Each case gets its own session (``mt-<id>``) → tenant+session isolation. After each turn the
    accumulated case-state is read back from the store (== what reaches the next prompt) for the
    must_carry + memory_fabrication checks. The re-ask keystone keeps BOTH halves: ``must_carry``
    proves the fact is PRESENT in the prompt (deterministic); ``must_not_reask`` (judge) confirms the
    answer HONORED it — the deterministic half alone does not prove the LLM won't re-ask."""
    # Mirror prod: the multiturn suite runs under the production flag baseline (flags_on =
    # Flags(True, True)). Local import — harness imports multiturn at module load, so a top-level
    # import would be circular; COLUMNS is reused, never redefined.
    from sealai_v2.eval.harness import COLUMNS

    session = SessionContext(session_id=f"mt-{case.id}")
    # Form-path seed: pre-write the case-state via edit_fact (the parameter form's exact method) so a
    # user-form provenance reaches the binder/kern before any chat turn. The seeded values are
    # user-STATED (typed in the form), so they join the memory-fabrication trace corpus — a form-
    # entered number is never a "fabrication" (it would otherwise false-trip the gate, which only
    # knows chat turns).
    seed_texts: list[str] = []
    if case.seed_facts and pipeline.memory is not None:
        for sf in case.seed_facts:
            pipeline.memory.edit_fact(
                tenant_id=tenant.tenant_id,
                session_id=session.session_id,
                feld=sf.feld,
                wert=sf.wert,
                provenance=sf.provenance,
            )
            seed_texts.append(sf.wert)
    user_turns: list[str] = []
    results: list[TurnResult] = []
    for i, spec in enumerate(case.turns):
        user_turns.append(spec.input)
        res = await pipeline.run(
            spec.input, tenant=tenant, session=session, flags=COLUMNS["flags_on"]
        )
        case_state: tuple[RememberedFact, ...] = ()
        if pipeline.memory is not None:
            case_state = pipeline.memory.recall(
                tenant_id=tenant.tenant_id, session_id=session.session_id
            ).case_state
        carried_missing = tuple(
            c for c in spec.must_carry if not _carried(c, case_state)
        )
        fabricated = untraceable_numeric_facts(case_state, seed_texts + user_turns)
        reask_violations: tuple[str, ...] = ()
        if judge is not None and spec.must_not_reask:
            verdicts = await judge(res.answer.text, spec.must_not_reask)
            reask_violations = tuple(t for t, reasked in verdicts.items() if reasked)
        # M8 — the deterministic calc halves: did the kern fire where asserted, and does the
        # FINAL answer leak a value the kern doesn't back (agent-final detector verdict)?
        computed_ids = tuple(c.calc_id for c in res.computed_values)
        compute_missing = tuple(
            cid for cid in spec.must_compute if cid not in computed_ids
        )
        leaks = detect_parametric_leaks(
            res.answer.text, computed_values=res.computed_values
        )
        results.append(
            TurnResult(
                index=i,
                input=spec.input,
                answer=res.answer.text,
                case_state=case_state,
                carried_missing=carried_missing,
                memory_fabrication=fabricated,
                must_carry=spec.must_carry,
                must_not_reask=spec.must_not_reask,
                reask_violations=reask_violations,
                computed_ids=computed_ids,
                must_compute=spec.must_compute,
                compute_missing=compute_missing,
                parametric_leaks=leaks,
                computed_values=tuple(res.computed_values),
            )
        )
    return MultiTurnResult(case_id=case.id, turns=results)


def summarize_multiturn(
    results: list[MultiTurnResult], *, drop_stats: DistillStats | None = None
) -> MultiTurnSummary:
    """Fold the per-turn checks into the M6a quotas. The memory_fabrication quota is AGENT-FINAL —
    the verbatim deterministic verdict, never adjudicated; carry + reask are the two re-ask halves."""
    turns = [t for r in results for t in r.turns]
    n = len(turns)
    n_mem_viol = sum(1 for t in turns if not t.memory_clean)

    carry_turns = [t for t in turns if t.must_carry]
    n_carry_misses = sum(1 for t in carry_turns if not t.carry_ok)
    reask_turns = [t for t in turns if t.must_not_reask]
    n_reask_viol = sum(1 for t in reask_turns if not t.reask_ok)
    n_param_viol = sum(1 for t in turns if not t.parametric_clean)
    compute_turns = [t for t in turns if t.must_compute]
    n_compute_misses = sum(1 for t in compute_turns if not t.compute_ok)

    return MultiTurnSummary(
        n_cases=len(results),
        n_turns=n,
        memory_schranken_quota=round((n - n_mem_viol) / n, 3) if n else None,
        n_memory_violations=n_mem_viol,
        carry_quota=round((len(carry_turns) - n_carry_misses) / len(carry_turns), 3)
        if carry_turns
        else None,
        n_carry_misses=n_carry_misses,
        reask_quota=round((len(reask_turns) - n_reask_viol) / len(reask_turns), 3)
        if reask_turns
        else None,
        n_reask_violations=n_reask_viol,
        parametric_schranken_quota=round((n - n_param_viol) / n, 3) if n else None,
        n_parametric_violations=n_param_viol,
        compute_quota=round(
            (len(compute_turns) - n_compute_misses) / len(compute_turns), 3
        )
        if compute_turns
        else None,
        n_compute_misses=n_compute_misses,
        drop=drop_stats,
    )


def load_multiturn_cases(path: Path | None = None) -> list[MultiTurnCase]:
    """Typed loader for the class-A multi-turn seed cases (mirrors ``cases.load_cases``)."""
    data = json.loads((path or _DEFAULT_MULTITURN_FILE).read_text(encoding="utf-8"))
    cases: list[MultiTurnCase] = []
    seen: set[str] = set()
    for c in data["cases"]:
        cid = c["id"]
        if cid in seen:
            raise ValueError(f"duplicate multi-turn case id: {cid}")
        seen.add(cid)
        turns = tuple(
            TurnSpec(
                input=t["input"],
                must_carry=tuple(t.get("must_carry", [])),
                must_not_reask=tuple(t.get("must_not_reask", [])),
                must_avoid=tuple(t.get("must_avoid", [])),
                must_contain=tuple(t.get("must_contain", [])),
                must_compute=tuple(t.get("must_compute", [])),
            )
            for t in c["turns"]
        )
        seed_facts = tuple(
            RememberedFact(
                feld=s["feld"],
                wert=s["wert"],
                provenance=s.get("provenance", "user-form"),
            )
            for s in c.get("seed_facts", [])
        )
        cases.append(
            MultiTurnCase(
                id=cid,
                klass=c["klass"],
                turns=turns,
                primary_axes=tuple(int(a) for a in c.get("primary_axes", [])),
                hard_gates=tuple(c.get("hard_gates", [])),
                holdout=bool(c.get("holdout", False)),
                seed_facts=seed_facts,
            )
        )
    return cases
