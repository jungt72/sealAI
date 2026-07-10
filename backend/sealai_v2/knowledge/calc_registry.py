"""Calc registry — curated, owner-reviewed DETERMINISTIC calc-defs (build-spec §4).

Metadata canonical in ``calc_seed.json`` (git = provenance/version/audit), mirroring
``trap_catalog.json`` / ``fachkarten_seed.json``. The FORMULA itself is reviewed CODE bound by id
from ``core.calc.formulas.FORMULAS`` — never eval()'d from the JSON, never LLM-derived.

Loader rule (the CALC-trap / circularity lesson for formulas): a ``reviewed`` calc-def MUST have a
non-empty ``source``, a non-empty ``provenance``, a ``validity`` domain, AND a bound implementation
in ``FORMULAS``; otherwise it is a load error. ``draft`` defs carry no such constraint (and are not
evaluated as authoritative).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sealai_v2.core.calc.formulas import FORMULAS

_REGISTRY_DIR = Path(__file__).resolve().parent
_DEFAULT_FILE = _REGISTRY_DIR / "calc_seed.json"

_REVIEW_STATES = ("reviewed", "draft")


@dataclass(frozen=True)
class CalcInput:
    name: str
    unit: str


@dataclass(frozen=True)
class CalcLimit:
    """A one-sided material limit on a calc value, read from ``calc_seed.json`` — the SINGLE source of
    the threshold (never duplicated in the evaluator or L3; both READ it from here). ``applies_to`` is
    the value name it bounds (e.g. ``v_m_s``); ``max`` is the upper limit; ``label`` is the human label
    of the limited solution (e.g. ``Standard-NBR-Lippe``); ``source_ref`` is the provenance. Fact only —
    NO material direction (DD-5: the direction comes from the §4 matrix, never from this limit)."""

    applies_to: str
    max: float
    caution_ratio: float | None = None
    label: str = ""
    source_ref: str = ""


@dataclass(frozen=True)
class CalcDef:
    id: str
    formula: str  # human-readable text, for the cited render (not executed)
    inputs: tuple[CalcInput, ...]
    output: CalcInput
    validity: dict  # {input_name: [min, max]} — numeric applicability domain
    conditions: (
        dict  # {context_key: [allowed, ...]} — e.g. {"seal_type": ["rwdr", ...]}
    )
    assumptions: tuple[str, ...]
    source: str
    review_state: str  # "reviewed" | "draft"
    provenance: tuple[str, ...]
    version: str = ""
    typical_band: tuple[float, float] | None = None  # output band → out-of-band warning
    limit: CalcLimit | None = (
        None  # one-sided material limit on a value → over-limit warning (C1)
    )
    impl: Callable[..., float] | None = field(default=None, compare=False)

    @property
    def reviewed(self) -> bool:
        return self.review_state == "reviewed"

    @property
    def input_names(self) -> tuple[str, ...]:
        return tuple(i.name for i in self.inputs)


@dataclass(frozen=True)
class CalcRegistry:
    defs: tuple[CalcDef, ...]
    version: str = ""
    source: str = ""

    def reviewed(self) -> tuple[CalcDef, ...]:
        return tuple(d for d in self.defs if d.review_state == "reviewed")

    def by_id(self, calc_id: str) -> CalcDef | None:
        for d in self.defs:
            if d.id == calc_id:
                return d
        return None


def _calc_def(raw: dict) -> CalcDef:
    cid = str(raw["id"])
    state = str(raw.get("review_state", "")).strip()
    if state not in _REVIEW_STATES:
        raise ValueError(f"{cid}: review_state {state!r} not in {_REVIEW_STATES}")
    out = raw.get("output") or {}
    band = raw.get("typical_band")
    lim = raw.get("limit")
    limit = (
        CalcLimit(
            applies_to=str(lim["applies_to"]),
            max=float(lim["max"]),
            caution_ratio=(
                float(lim["caution_ratio"])
                if lim.get("caution_ratio") is not None
                else None
            ),
            label=str(lim.get("label", "")),
            source_ref=str(lim.get("source_ref", "")),
        )
        if lim
        else None
    )
    d = CalcDef(
        id=cid,
        formula=str(raw.get("formula", "")),
        inputs=tuple(
            CalcInput(str(i["name"]), str(i.get("unit", "")))
            for i in raw.get("inputs", [])
        ),
        output=CalcInput(str(out.get("name", "")), str(out.get("unit", ""))),
        validity={
            k: [float(v[0]), float(v[1])]
            for k, v in (raw.get("validity") or {}).items()
        },
        conditions={
            k: [str(x) for x in v] for k, v in (raw.get("conditions") or {}).items()
        },
        assumptions=tuple(str(a) for a in raw.get("assumptions", [])),
        source=str(raw.get("source", "")),
        review_state=state,
        provenance=tuple(str(p) for p in raw.get("provenance", [])),
        version=str(raw.get("version", "")),
        typical_band=(float(band[0]), float(band[1])) if band else None,
        limit=limit,
        impl=FORMULAS.get(cid),
    )
    if not d.output.name:
        raise ValueError(f"{cid}: output name required")
    if d.limit and d.limit.caution_ratio is not None and not (
        0 < d.limit.caution_ratio <= 1
    ):
        raise ValueError(f"{cid}: limit.caution_ratio must be in (0, 1]")
    if d.reviewed:
        # circularity guard for formulas — reviewed = sourced + provenanced + validated + bound code
        if not d.source.strip():
            raise ValueError(f"{cid}: reviewed calc-def needs a non-empty source")
        if not d.provenance:
            raise ValueError(f"{cid}: provenance is mandatory (owner-grounding audit)")
        if not d.validity:
            raise ValueError(f"{cid}: reviewed calc-def needs a validity domain")
        if d.impl is None:
            raise ValueError(
                f"{cid}: reviewed calc-def has no bound implementation in FORMULAS "
                "(formulas are reviewed CODE, not data)"
            )
        missing = [n for n in d.input_names if n not in d.validity]
        if missing:
            raise ValueError(f"{cid}: inputs {missing} lack a validity range")
    return d


def load_calc_registry(path: Path | None = None) -> CalcRegistry:
    data = json.loads((path or _DEFAULT_FILE).read_text(encoding="utf-8"))
    defs: list[CalcDef] = []
    seen: set[str] = set()
    for raw in data.get("calcs", []):
        d = _calc_def(raw)
        if d.id in seen:
            raise ValueError(f"duplicate calc id: {d.id}")
        seen.add(d.id)
        defs.append(d)
    if not defs:
        raise ValueError("calc registry is empty")
    return CalcRegistry(
        defs=tuple(defs),
        version=str(data.get("version", "")),
        source=str(data.get("source", "")),
    )
