"""INC-3a — deterministischer Inline-Extractor: <Zahl> <Einheit> → RememberedFact.

Reine Funktion: kein I/O, kein LLM, keine Mutation, keine Float-Literale.
Verdrahtung in die Pipeline = INC-3b.

Scan-Grammatik: _NUM aus binding.py (Zahl), danach mindestens ein Leerzeichen,
danach ein Nicht-Leerzeichen-Token (Einheit). Trailing-Satzzeichen werden entfernt.
Normalisierung über binding._normalize_unit (intra-package, kein Re-Implement).

Multiplizitaets-Guard (owner-ratifiziert, fail-closed): hat ein Feld mehr als ein
Vorkommen (akzeptiert + known-other derselben Dimension zusammengezaehlt) → kein
Emit (defer an LLM-Distiller). Genau ein Vorkommen, aber nur known-other → kein
Emit (defer). Nackte Zahl ohne Einheit → kein Vorkommen → nichts.
"""

from __future__ import annotations

import re

from sealai_v2.core.calc.binding import (
    _BINDINGS,
    _KNOWN_UNITS,
    _NUM,
    _UNIT_SYNONYMS,
    _normalize_unit,
)
from sealai_v2.core.contracts import RememberedFact

# <Zahl> (mindestens ein Whitespace) <Einheit-Token>
# Lookbehind (?<!\d): Zahl beginnt nicht mitten in einer Ziffernfolge.
_SCAN_RE = re.compile(rf"(?<!\d){_NUM}\s+(\S+)")

_TRAIL_PUNCT = ".,;:!?)"


def _strip_punct(s: str) -> str:
    return s.rstrip(_TRAIL_PUNCT)


def extract_inline(message: str) -> tuple[RememberedFact, ...]:
    """Scannt ``message`` und gibt fuer jedes der vier Felder (druck, drehzahl,
    wellendurchmesser, geschwindigkeit) genau dann ein ``RememberedFact`` zurueck,
    wenn genau EIN Vorkommen existiert UND dessen Einheit akzeptiert ist.

    Eigentuemer-ratifizierte Regeln (INC-3a):
    - Vorkommen = akzeptiertes Synonym ODER known-other derselben Dimension.
    - >1 Vorkommen → kein Emit (Multiplizitaets-Guard, fail-closed).
    - 1 Vorkommen, aber known-other → kein Emit (defer an LLM-Distiller).
    - Nackte Zahl ohne Einheit → kein Vorkommen.
    - provenance = "chat-inline".
    """
    results: list[RememberedFact] = []

    for feld, bind in _BINDINGS.items():
        accepted_syn = _UNIT_SYNONYMS[bind.unit_key]
        field_dim = bind.dimension
        # (num_str, unit_raw_stripped, is_accepted)
        occurrences: list[tuple[str, str, bool]] = []

        for m in _SCAN_RE.finditer(message):
            num_str = m.group(1)
            unit_raw = _strip_punct(m.group(2))
            if not unit_raw:
                continue
            norm = _normalize_unit(unit_raw)
            if norm in accepted_syn:
                occurrences.append((num_str, unit_raw, True))
            elif _KNOWN_UNITS.get(norm, "") == field_dim:
                # Zaehlt als Vorkommen (Multiplizitaets-Guard), wird aber nicht emittiert
                occurrences.append((num_str, unit_raw, False))

        if len(occurrences) != 1:
            # 0 Vorkommen: kein Treffer; >1: Multiplizitaets-Guard greift
            continue
        num_str, unit_raw, is_accepted = occurrences[0]
        if not is_accepted:
            # known-other allein → defer an LLM-Distiller
            continue
        results.append(
            RememberedFact(
                feld=feld, wert=f"{num_str} {unit_raw}", provenance="chat-inline"
            )
        )

    return tuple(results)


def merge_inline(
    case_state: tuple[RememberedFact, ...],
    inline: tuple[RememberedFact, ...],
) -> tuple[RememberedFact, ...]:
    """Overlay ``inline`` facts on ``case_state``: fresh beats recalled, field by field.

    Pure, no mutation.  Fields absent from ``inline`` keep their ``case_state`` value.
    Fields in ``inline`` but absent from ``case_state`` are appended.
    """
    if not inline:
        return case_state
    inline_by_feld = {f.feld: f for f in inline}
    result = [inline_by_feld.get(f.feld, f) for f in case_state]
    existing_felder = {f.feld for f in case_state}
    result.extend(f for f in inline if f.feld not in existing_felder)
    return tuple(result)
