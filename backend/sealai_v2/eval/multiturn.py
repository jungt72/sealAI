"""Multi-turn eval runner (M6a) — threads a session through ``pipeline.run`` so memory accumulates,
and applies the deterministic memory-integrity gate per turn (build-spec §7/§9).

This is the distiller's first real measurement — the single-turn REPLAY deliberately can't exercise
memory. Two deterministic checks live here (no LLM):
  • **must_carry** — a prior STATED fact reached the case-state (and thus the prompt, by
    construction: ``pipeline.run`` builds ``case_context`` from ``memory.recall().case_state``).
  • **memory_fabrication** gate — every remembered number must trace to the user turns (c)(ii).
The answer-level judge checks (must_not_reask / must_avoid / must_contain) layer on top in the
harness; they are not computed here. Pure orchestration over the injected pipeline.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from sealai_v2.core.contracts import RememberedFact, SessionContext
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
    must_carry: tuple[str, ...] = ()  # facts that must be in case-state by now (re-ask fix; deterministic)
    must_not_reask: tuple[str, ...] = ()  # topics the answer must NOT re-ask (judge — harness layer)
    must_avoid: tuple[str, ...] = ()  # edge: no domain claim / no briefing dump (hard must_avoid)
    must_contain: tuple[str, ...] = ()  # expected content (e.g. capability redirect)


@dataclass(frozen=True)
class MultiTurnCase:
    id: str
    klass: str
    turns: tuple[TurnSpec, ...]
    primary_axes: tuple[int, ...] = ()
    hard_gates: tuple[str, ...] = ()
    holdout: bool = False


@dataclass
class TurnResult:
    index: int
    input: str
    answer: str
    case_state: tuple[RememberedFact, ...]
    carried_missing: tuple[str, ...]  # must_carry items NOT found in case-state (deterministic miss)
    memory_fabrication: tuple[RememberedFact, ...]  # untraceable numeric facts (gate violation)
    must_carry: tuple[str, ...] = ()  # asserted carry topics (denominator for the carry quota)
    must_not_reask: tuple[str, ...] = ()  # asserted no-reask topics (denominator for the reask quota)
    reask_violations: tuple[str, ...] = ()  # topics the judge says the answer re-asked anyway

    @property
    def carry_ok(self) -> bool:
        return not self.carried_missing

    @property
    def memory_clean(self) -> bool:
        return not self.memory_fabrication

    @property
    def reask_ok(self) -> bool:
        return not self.reask_violations


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
    reask_quota: float | None  # turns with no re-ask / turns with a must_not_reask assertion
    n_reask_violations: int
    drop: DistillStats | None = None


def _carried(item: str, case_state: tuple[RememberedFact, ...]) -> bool:
    blob = " ".join(f"{f.feld} {f.wert}" for f in case_state).lower()
    return item.lower() in blob


async def run_multiturn_case(
    pipeline, case: MultiTurnCase, *, tenant: TenantContext, judge: ReaskJudge | None = None
) -> MultiTurnResult:
    """Run an ordered turn list through one session; capture answers + the deterministic checks +
    (when a ``judge`` is wired) the re-ask judge-half.

    Each case gets its own session (``mt-<id>``) → tenant+session isolation. After each turn the
    accumulated case-state is read back from the store (== what reaches the next prompt) for the
    must_carry + memory_fabrication checks. The re-ask keystone keeps BOTH halves: ``must_carry``
    proves the fact is PRESENT in the prompt (deterministic); ``must_not_reask`` (judge) confirms the
    answer HONORED it — the deterministic half alone does not prove the LLM won't re-ask."""
    session = SessionContext(session_id=f"mt-{case.id}")
    user_turns: list[str] = []
    results: list[TurnResult] = []
    for i, spec in enumerate(case.turns):
        user_turns.append(spec.input)
        res = await pipeline.run(spec.input, tenant=tenant, session=session)
        case_state: tuple[RememberedFact, ...] = ()
        if pipeline.memory is not None:
            case_state = pipeline.memory.recall(
                tenant_id=tenant.tenant_id, session_id=session.session_id
            ).case_state
        carried_missing = tuple(c for c in spec.must_carry if not _carried(c, case_state))
        fabricated = untraceable_numeric_facts(case_state, user_turns)
        reask_violations: tuple[str, ...] = ()
        if judge is not None and spec.must_not_reask:
            verdicts = await judge(res.answer.text, spec.must_not_reask)
            reask_violations = tuple(t for t, reasked in verdicts.items() if reasked)
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
            )
            for t in c["turns"]
        )
        cases.append(
            MultiTurnCase(
                id=cid,
                klass=c["klass"],
                turns=turns,
                primary_axes=tuple(int(a) for a in c.get("primary_axes", [])),
                hard_gates=tuple(c.get("hard_gates", [])),
                holdout=bool(c.get("holdout", False)),
            )
        )
    return cases
