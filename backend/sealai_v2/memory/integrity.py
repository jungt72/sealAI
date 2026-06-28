"""Memory-integrity primitive (M6a (c)) — the numeric-trace check shared by the runtime distiller
guard and the eval-side hard gate (``memory_fabrication``).

A remembered fact's numerics must trace to user-STATED content. A distilled/remembered number that
does not appear in the user's turns is a fabrication/distortion (e.g. 150→1500 °C) — the memory
analogue of confident-false. Deterministic for NUMBERS; qualitative-fact support stays judged /
human-final on dispute (build-spec §7 honesty discipline). Pure: no I/O, no LLM.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from sealai_v2.core.contracts import RememberedFact

# German-locale aware: a dot is a THOUSANDS separator (groups of exactly 3 digits), a comma the decimal.
# The first alternative captures the thousands form ('1.500' / '1.500.000' / '1.500,5'); the second a
# plain/decimal number ('0.5' English-decimal or '1,5' German-decimal). Matching '1.500' as ONE thousands
# token is the fix for the prior ``float('1.500') == 1.5`` mis-parse, which could wrongly drop a traceable
# distilled number as a fabrication (this primitive backs the memory_fabrication hard gate).
_THOUSANDS = r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?"
_NUM_RE = re.compile(_THOUSANDS + r"|-?\d+(?:[.,]\d+)?")
_THOUSANDS_RE = re.compile(_THOUSANDS)


def _to_float(tok: str) -> float | None:
    if _THOUSANDS_RE.fullmatch(tok):
        norm = tok.replace(".", "").replace(
            ",", "."
        )  # thousands dots out; decimal comma -> dot
    else:
        norm = tok.replace(
            ",", "."
        )  # decimal comma -> dot; a lone dot is a decimal point
    try:
        return float(norm)
    except ValueError:
        return None


def numerics(text: str) -> set[float]:
    """Numeric tokens in ``text`` as floats (German thousands/decimal aware) — the unit of traceability."""
    out: set[float] = set()
    for tok in _NUM_RE.findall(text or ""):
        v = _to_float(tok)
        if v is not None:
            out.add(v)
    return out


def untraceable_numeric_facts(
    case_state: Sequence[RememberedFact], user_turns: Sequence[str]
) -> tuple[RememberedFact, ...]:
    """Facts whose numerics are NOT a subset of the union of the user turns' numerics — i.e. a
    fabricated/distorted 'zuvor genannt' number reached the case-state. Empty tuple = clean."""
    src: set[float] = set()
    for t in user_turns:
        src |= numerics(t)
    return tuple(f for f in case_state if not (numerics(f.wert) <= src))


def memory_integrity_clean(
    case_state: Sequence[RememberedFact], user_turns: Sequence[str]
) -> bool:
    """True iff no remembered fact carries a number untraceable to the user turns (gate clean)."""
    return not untraceable_numeric_facts(case_state, user_turns)
