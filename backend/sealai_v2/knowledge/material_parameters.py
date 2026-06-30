"""Structured material-parameter store (V2.2). Pure, no LLM. The KERNEL owns the parameters (operating
limits, Shore hardness, density, chemical resistance, …); L1 only RENDERS them as a table — the numbers
never come from the model (no-fake-precision / "Kernel besitzt die Fakten, L1 erzählt nur"). Each material
carries a ``review_state`` ('reviewed' = owner-grounded | 'draft' = vorläufige Richtwerte): until reviewed
the render shows the vorläufig marker. A missing parameter is NOT invented — the caller renders it as '—'.

The store is data-driven (``material_parameters_seed.json``) so curation = editing JSON + the owner's
multi-LLM review, never code. This module just loads + matches; it asserts no engineering values itself.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_SEED = Path(__file__).resolve().parent / "material_parameters_seed.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    data = json.loads(_SEED.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def lookup(material: str) -> dict | None:
    """The structured parameter block for one material (case-insensitive), or None when not in the store."""
    if not material:
        return None
    for k, v in _load().items():
        if k.lower() == material.lower():
            return {"material": k, **v}
    return None


@lru_cache(maxsize=1)
def _vocab() -> tuple[str, ...]:
    # longest-first so a compound family name wins over a substring (e.g. Glasfaser-PTFE over PTFE)
    return tuple(sorted(_load().keys(), key=len, reverse=True))


def material_parameters_for(text: str) -> list[dict]:
    """The grounded parameter blocks for the materials NAMED in ``text`` (word-boundary, longest-first,
    deduped). Empty when none match / the store has no entry. The render decides table-vs-not. Pure."""
    low = (text or "").lower()
    out: list[dict] = []
    seen: set[str] = set()
    for m in _vocab():
        ml = m.lower()
        if ml in seen:
            continue
        if re.search(rf"\b{re.escape(ml)}\b", low):
            blk = lookup(m)
            if blk:
                out.append(blk)
                seen.add(ml)
    return out
