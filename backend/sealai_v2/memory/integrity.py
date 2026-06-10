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

_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def numerics(text: str) -> set[float]:
    """Numeric tokens in ``text`` as floats (comma decimal normalized) — the unit of traceability."""
    out: set[float] = set()
    for tok in _NUM_RE.findall(text or ""):
        try:
            out.add(float(tok.replace(",", ".")))
        except ValueError:
            continue
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
