"""M8-A — deterministic provenance binding: remembered case facts → calc-registry inputs.

DETERMINISTIC + DECLARED (build on the owner-confirmed mapping table, 2026-06-10): the agent never
decides which fact feeds which input. v1 binds exactly two facts:

- ``wellendurchmesser`` → ``d1_mm`` — shaft Ø at the running surface, standard direct-on-shaft
  case (sleeve/Laufbuchse parked); unit ``mm`` required.
- ``drehzahl`` → ``rpm`` — accepted unit spellings: U/min, 1/min, min⁻¹ (also ASCII min^-1), rpm.

FAIL-CLOSED everywhere (the kern stays honest): no unit token adjoining the number, ranges,
extra prose, unknown units, or conflicting values for the same feld → the input is NOT bound and
the drop is surfaced as a note — never LLM-resolved, never guessed. German number conventions:
decimal comma; a thousands-dot form ("4.000") counts only WITH an adjoining unit (owner decision).

Origins are preserved per bound input (feld + verbatim wert + user-stated vs user-edited) so the
render/citation stays honest — the V1 "provenance loss on user-entered values" lesson.

druck→p_bar and schnurstaerke/nuttiefe are PARKED (owner decision 3): v1 ships d1/rpm only.
Pure core: no I/O, no LLM.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from sealai_v2.core.contracts import RememberedFact

# German number: thousands-dot groups (only meaningful with a unit, enforced by the full-match
# grammar below) or a plain integer/decimal-comma number.
_NUM = r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)"

# Full-match grammars — anything beyond "number + unit" (ranges, prose, second numbers) fails.
_MM_RE = re.compile(rf"^\s*{_NUM}\s*mm\s*$", re.IGNORECASE)
_RPM_RE = re.compile(
    rf"^\s*{_NUM}\s*(?:U/min|1/min|min⁻¹|min\^-1|rpm)\s*$", re.IGNORECASE
)


def _to_float(num: str) -> float:
    return float(num.replace(".", "").replace(",", "."))


# feld (lowercased) → (calc input name, full-match grammar). The DECLARED mapping table —
# extending it is an owner decision, never an agent judgment call.
_BINDINGS: dict[str, tuple[str, re.Pattern[str]]] = {
    "wellendurchmesser": ("d1_mm", _MM_RE),
    "drehzahl": ("rpm", _RPM_RE),
}


@dataclass(frozen=True)
class BindingResult:
    params: dict[str, float] = field(default_factory=dict)
    origins: dict[str, str] = field(
        default_factory=dict
    )  # input name → human-readable origin
    sources: dict[str, str] = field(
        default_factory=dict
    )  # input name → source case-state feld (M8: derived-fact parent-refs)
    notes: tuple[str, ...] = ()  # surfaced drops — fail-closed is visible, never silent


def _origin(f: RememberedFact) -> str:
    if f.provenance == "user-form":
        return f"vom Nutzer im Formular eingegeben ({f.feld}: »{f.wert}«, user-form)"
    if f.provenance == "user-edited":
        return f"vom Nutzer bestätigt/bearbeitet ({f.feld}: »{f.wert}«, user-edited)"
    return f"vom Nutzer genannt ({f.feld}: »{f.wert}«)"


def bind_params(facts: Iterable[RememberedFact]) -> BindingResult:
    """Bind remembered facts to calc inputs per the declared table. Deterministic; fail-closed."""
    params: dict[str, float] = {}
    origins: dict[str, str] = {}
    sources: dict[str, str] = {}
    notes: list[str] = []
    seen: dict[str, str] = {}  # feld → first wert (conflict detection)
    conflicted: set[str] = set()

    for f in facts:
        # M8 boundary: a kernel-computed value is an OUTPUT, never an input — never bind it back
        # (no feedback loop, no stale-derived-feeds-cascade). It is normally not even in case-state.
        if f.provenance == "kernel_computed":
            continue
        feld = f.feld.strip().lower()
        binding = _BINDINGS.get(feld)
        if binding is None:
            continue  # unmapped felder are simply not calc inputs — no noise
        input_name, grammar = binding

        if feld in seen:
            if f.wert.strip() != seen[feld] and feld not in conflicted:
                conflicted.add(feld)
                params.pop(input_name, None)
                origins.pop(input_name, None)
                sources.pop(input_name, None)
                notes.append(
                    f"{feld}: widersprüchliche Werte (»{seen[feld]}« vs »{f.wert.strip()}«) — "
                    f"nicht gebunden (bitte bestätigen)"
                )
            continue
        seen[feld] = f.wert.strip()

        m = grammar.match(f.wert)
        if m is None:
            notes.append(
                f"{feld}: Wert »{f.wert.strip()}« nicht eindeutig bindbar "
                f"(Zahl + Einheit erforderlich; kein Bereich) — nicht gebunden"
            )
            continue
        params[input_name] = _to_float(m.group(1))
        origins[input_name] = _origin(f)
        sources[input_name] = feld  # parent-ref: which case-state feld fed this input

    return BindingResult(
        params=params, origins=origins, sources=sources, notes=tuple(notes)
    )
