"""Pure Decode parser: a seal designation -> structured spec (Modus G, Dim. 7).

No I/O, no LLM, no mutation. Parses a free-text seal designation ("RWDR 40x62x10 FKM",
"40-62-10 NBR", "O-Ring 40x3 EPDM") into a structured spec: dimensions, material, type.

Two doctrine guards:
- The dimensions are **echoed from the user's own input** (parsed, NOT invented or kernel-
  computed) and live RESULT-SIDE in the structured spec; the narration stays qualitative
  (type/material/equivalence), so no parsed number reaches the answer text as an asserted
  engineering value (parametric-leak-safe).
- Equivalence ("Teil X = Teil Y") is the SHARPEST liability edge (Produkt-Konzept §9.2) and is
  NOT asserted here. The decode gives the structured spec; the operation frames a comparison only
  as "same nominal size + material class — confirm compound/interchangeability with the
  manufacturer", never a guarantee.

Conservative: returns None when neither a dimension group NOR a material/type is recognised; an
ambiguous dimension layout is labelled ``uneindeutig`` rather than mislabelled.
"""

from __future__ import annotations

import re

from sealai_v2.core.seal_spec_extract import _MATERIAL_PATTERNS, _TYPE_PATTERNS

# A dimension group: 2-3 numbers separated by x / × / * / - / (DIN-style "40x62x10", "40-62-10").
_DIM_RE = re.compile(
    r"\b(\d{1,4}(?:[.,]\d+)?)\s*[x×*/\-]\s*(\d{1,4}(?:[.,]\d+)?)"
    r"(?:\s*[x×*/\-]\s*(\d{1,4}(?:[.,]\d+)?))?\b"
)


# The §9.2 equivalence boundary - the single sharpest liability line. 'Teil X = Teil Y' is
# never asserted; a comparison is framed ONLY as same nominal size + material class, with
# compound/tolerances/fit to confirm at the manufacturer. Owner-grounded doctrine wording.
EQUIVALENZ_GRENZE = (
    "Vergleichbar heißt: gleiche Nennmaße + Werkstoffklasse. Compound, Toleranzen und die "
    "tatsächliche Eignung können sich unterscheiden - vor einem Austausch beim Hersteller "
    "bestätigen. Das ist keine Austausch-Garantie; die finale Freigabe liegt beim Hersteller."
)


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def decode_designation(message: str) -> dict | None:
    """Parse a seal designation into a structured spec. Deterministic, conservative.

    Returns a dict with ``raw`` plus any recognised of: ``material``, ``type``, ``dims_mm``
    (the echoed numbers) and — when the layout is unambiguous — labelled ``id_mm``/``od_mm``/
    ``width_mm`` (RWDR ID x OD x Breite) or ``id_mm``/``cord_mm`` (O-Ring). Returns None when
    nothing decodable is present.
    """
    mats: list[str] = []
    for pat, canon in _MATERIAL_PATTERNS:
        if pat.search(message) and canon not in mats:
            mats.append(canon)
    material = mats[0] if len(mats) == 1 else None

    types: list[str] = []
    for pat, t in _TYPE_PATTERNS:
        if pat.search(message) and t not in types:
            types.append(t)
    stype = types[0] if len(types) == 1 else None

    m = _DIM_RE.search(message)
    dims = [_num(g) for g in m.groups() if g is not None] if m else None

    if dims is None and material is None and stype is None:
        return None

    result: dict = {"raw": message.strip()}
    if material:
        result["material"] = material
    if stype:
        result["type"] = stype
    if dims:
        result["dims_mm"] = dims
        is_oring = stype in ("O-Ring", "X-Ring", "V-Ring")
        if len(dims) == 3 and not is_oring:
            result["id_mm"], result["od_mm"], result["width_mm"] = dims
            result["dim_interpretation"] = "id_od_breite"
        elif len(dims) == 2 and is_oring:
            result["id_mm"], result["cord_mm"] = dims
            result["dim_interpretation"] = "id_schnurstaerke"
        else:
            # ambiguous layout (e.g. two numbers, no O-Ring type) — do NOT mislabel id/od vs id/cord
            result["dim_interpretation"] = "uneindeutig"
    return result
