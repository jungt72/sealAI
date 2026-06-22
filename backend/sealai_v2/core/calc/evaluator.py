"""Cascade evaluator — the deterministic CalcEngine (build-spec §4, §2 of the M4 plan).

Topological fixpoint over the reviewed calc registry: compute every def whose inputs are present AND
in validity/applicability domain; outputs feed downstream defs, so the dependency DAG's depth IS the
cascade "stage". FAIL-CLOSED: missing inputs / outside validity / not-applicable / a raising formula
→ a ``NotComputed`` reason, never a misleading number. Pure / I/O-free.

Cross-layer (M4 reads M3, Q1 = qualitative): a reviewed Fachkarte swelling claim in ``grounding_facts``
sets a ``swelling`` flag → a Nutfüllung over-fill warning + a result note. Numeric Fachkarte
properties are deferred to the content-track.
"""

from __future__ import annotations

from dataclasses import dataclass

from sealai_v2.core.contracts import (
    CalcResult,
    ComputedValue,
    GroundingFact,
    NotComputed,
)
from sealai_v2.knowledge.calc_registry import CalcRegistry, load_calc_registry

_SWELL_KEYS = ("quillt", "quellung", "swell", "aufquell")


@dataclass
class _Val:
    value: float
    unit: str
    depth: int


class CascadeCalcEngine:
    """Implements the ``CalcEngine`` Protocol over an in-memory ``CalcRegistry`` (reviewed defs only)."""

    def __init__(self, registry: CalcRegistry | None = None) -> None:
        self._reg = registry or load_calc_registry()

    def evaluate(
        self,
        *,
        params: dict,
        grounding_facts: tuple[GroundingFact, ...] = (),
        context: dict | None = None,
        param_origins: dict | None = None,
    ) -> CalcResult:
        ctx = dict(context or {})
        # M8-A: per-input origin (user-stated via binding / explicit Parameter); cascade outputs
        # get a derived origin below so user-entered never silently becomes "derived" or vice versa.
        origins: dict[str, str] = dict(param_origins or {})
        # qualitative swelling flag from reviewed grounding facts (Q1)
        if any(
            any(k in (f.text or "").lower() for k in _SWELL_KEYS)
            for f in grounding_facts
        ):
            ctx.setdefault("swelling", True)

        # numeric params → calc inputs (env); non-numeric params → context
        env: dict[str, _Val] = {}
        for name, val in (params or {}).items():
            if isinstance(val, bool):
                ctx.setdefault(name, val)
            elif isinstance(val, (int, float)):
                env[name] = _Val(float(val), "", 0)
            else:
                ctx.setdefault(name, val)

        computed: list[ComputedValue] = []
        reasons: dict[str, str] = {}
        done: set[str] = set()
        reviewed = self._reg.reviewed()

        progressed = True
        while progressed:
            progressed = False
            for d in reviewed:
                if d.id in done:
                    continue
                # condition gate: an explicit non-matching context value disqualifies; an ABSENT
                # key passes (we don't block a kinematic calc just because seal_type is unknown).
                bad = next(
                    (
                        f"{k}={ctx[k]}"
                        for k, allowed in d.conditions.items()
                        if k in ctx
                        and str(ctx[k]).lower() not in [a.lower() for a in allowed]
                    ),
                    None,
                )
                if bad is not None:
                    reasons[d.id] = f"nicht anwendbar ({bad})"
                    done.add(d.id)
                    continue
                missing = [n for n in d.input_names if n not in env]
                if missing:
                    reasons[d.id] = (
                        "nicht berechenbar: Eingaben fehlen ("
                        + ", ".join(missing)
                        + ")"
                    )
                    continue  # may become available later in the cascade
                oob = next(
                    (
                        f"{n}={env[n].value} außerhalb {d.validity[n]}"
                        for n in d.input_names
                        if not (d.validity[n][0] <= env[n].value <= d.validity[n][1])
                    ),
                    None,
                )
                if oob is not None:
                    reasons[d.id] = f"nicht berechenbar (außerhalb Gültigkeit: {oob})"
                    done.add(d.id)
                    continue
                try:
                    out = float(d.impl(**{n: env[n].value for n in d.input_names}))
                except Exception as exc:  # noqa: BLE001 — fail-closed, never a misleading number
                    reasons[d.id] = (
                        f"nicht berechenbar (Rechenfehler: {type(exc).__name__})"
                    )
                    done.add(d.id)
                    continue
                depth = 1 + max((env[n].depth for n in d.input_names), default=0)
                warnings: list[str] = []
                if d.typical_band and not (
                    d.typical_band[0] <= out <= d.typical_band[1]
                ):
                    warnings.append(
                        f"außerhalb des typischen Bereichs {d.typical_band[0]}–{d.typical_band[1]} {d.output.unit}"
                    )
                if (
                    d.limit
                    and d.limit.applies_to == d.output.name
                    and out > d.limit.max
                ):
                    # C1 (DD-1/DD-5): one-sided material limit → a FACT-ONLY, QUALITATIVE warning. The
                    # threshold (d.limit.max) drives the comparison but is NOT stated — a non-kern m/s
                    # number echoed into the answer would trip the parametric-leak Schranke (kern-fix-01).
                    # NO material direction (no FKM/PTFE): naming a fit material is the §4 matrix's job,
                    # never this velocity signal (the number stays single-sourced in calc_seed.json).
                    warnings.append(
                        f"über der Belastungsgrenze der {d.limit.label} → "
                        f"{d.limit.label} bei diesem Wert unzureichend, höher belastbare Lösung nötig"
                    )
                if ctx.get("swelling") and d.id == "verpressung_prozent":
                    warnings.append(
                        "Quellung erkannt: Nutfüllung mit Reserve auslegen — Über-Füllung/Quetschung vermeiden"
                    )
                computed.append(
                    ComputedValue(
                        calc_id=d.id,
                        name=d.output.name,
                        value=round(out, 4),
                        unit=d.output.unit,
                        stage=depth,  # DAG depth = cascade stage
                        derivation_depth=depth,
                        formula=d.formula,
                        source=d.source,
                        assumptions=d.assumptions,
                        inputs_used=d.input_names,
                        input_origins=tuple(
                            origins.get(n, "Parameter") for n in d.input_names
                        ),
                        warnings=tuple(warnings),
                        estimate=depth
                        >= 2,  # derived-of-derived → estimate-with-assumptions
                    )
                )
                env[d.output.name] = _Val(out, d.output.unit, depth)
                origins[d.output.name] = f"abgeleitet ({d.id})"
                done.add(d.id)
                progressed = True

        computed_ids = {c.calc_id for c in computed}
        not_computed = tuple(
            NotComputed(cid, reason)
            for cid, reason in reasons.items()
            if cid not in computed_ids
        )
        notes: list[str] = []
        if ctx.get("swelling"):
            notes.append(
                "Quellungshinweis: das Medium quillt den Werkstoff — bei Nut-/Verpressungs-"
                "auslegung Reserve für Quellung/Wärmedehnung lassen (Über-Füllung vermeiden)."
            )
        return CalcResult(
            computed=tuple(computed), not_computed=not_computed, notes=tuple(notes)
        )
