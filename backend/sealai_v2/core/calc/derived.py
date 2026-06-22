"""M8 trust-spine completion — the derived-fact recompute (pure, I/O-free).

One function projects the kernel's CalcResult into persistable ``kernel_computed`` DerivedFacts:
bind the current case-state inputs → evaluate the reviewed registry → map each computed value to a
DerivedFact carrying its parent input felder (v ← wellendurchmesser, drehzahl) and per-input
provenance. The full CalcResult (incl. ``not_computed`` + notes) is returned alongside so the read
surface (/compute, the panel) can show the honest "nicht berechenbar" reasons too.

No I/O, no LLM. Reuses ``bind_params`` (the declared, fail-closed binding) and the injected
``CalcEngine`` — no new calc logic lives here. Recompute is ALWAYS the whole set from current
inputs, so the persisted slice can never carry a stale value.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sealai_v2.core.calc.binding import BindClarification, bind_params
from sealai_v2.core.contracts import (
    CalcEngine,
    CalcResult,
    DerivedFact,
    RememberedFact,
)


@dataclass(frozen=True)
class DerivedComputation:
    """The result of one recompute: the ``kernel_computed`` facts to PERSIST + the full CalcResult
    (computed + not_computed + notes) for the READ surface, plus the binder's fail-closed
    ``clarifications`` (structured unit-recovery hints — the panel's confirm surface)."""

    derived: tuple[DerivedFact, ...]
    calc: CalcResult
    clarifications: tuple[BindClarification, ...] = ()


# Case-state felder that carry the seal TYPE — fed to the engine as the ``seal_type`` condition
# context (NOT a numeric calc input), so type-specific calc-defs gate correctly (RWDR-only calcs are
# "nicht anwendbar" on a hydraulic case and vice versa). Absent ⇒ no gate (condition keys that are
# absent pass) ⇒ byte-identical to the pre-wiring behaviour for cases without a stated type.
_SEAL_TYPE_FELDER = ("dichtungstyp", "seal_type")


def _seal_type(facts: Iterable[RememberedFact]) -> str | None:
    """The stated seal type (lowercased) from a type feld, if any. Deterministic, last-wins."""
    found: str | None = None
    for f in facts:
        if f.feld.strip().lower() in _SEAL_TYPE_FELDER and f.wert.strip():
            found = f.wert.strip().lower()
    return found


def recompute_derived(
    input_facts: Iterable[RememberedFact], engine: CalcEngine
) -> DerivedComputation:
    """Bind current case-state inputs and evaluate the kernel. Returns the persistable DerivedFacts
    (one per computed value, tagged ``kernel_computed`` with parent-refs) + the full CalcResult."""
    facts = tuple(input_facts)
    bound = bind_params(facts)
    params: dict = dict(bound.params)
    seal_type = _seal_type(facts)
    if seal_type:
        params["seal_type"] = (
            seal_type  # string param → engine context → condition gate
        )
    calc = engine.evaluate(params=params or {}, param_origins=bound.origins or None)
    # surface the binder's fail-closed drops in the notes (visible, never silent) — mirrors pipeline.run
    if bound.notes:
        calc = CalcResult(
            computed=calc.computed,
            not_computed=calc.not_computed,
            notes=calc.notes + bound.notes,
        )
    derived = tuple(
        DerivedFact(
            calc_id=c.calc_id,
            name=c.name,
            value=c.value,
            unit=c.unit,
            formula=c.formula,
            parent_fields=tuple(
                bound.sources[i] for i in c.inputs_used if i in bound.sources
            ),
            input_origins=c.input_origins,
            provenance="kernel_computed",
        )
        for c in calc.computed
    )
    return DerivedComputation(
        derived=derived, calc=calc, clarifications=bound.clarifications
    )
