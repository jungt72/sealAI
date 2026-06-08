"""Typed loader for the eval seed cases (build-spec §9: the Eval is the acceptance ruler).

The cases are transcribed from the prose seed-set into ``seed_cases/seed_set_v0.json``; this
module loads them into validated ``Case`` objects. ``holdout`` is carried now (full set runs
at M1; the held-back/rotating split is introduced from M2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sealai_v2.core.contracts import AXES, HARD_GATES

_SEED_DIR = Path(__file__).resolve().parent / "seed_cases"
_DEFAULT_FILE = _SEED_DIR / "seed_set_v0.json"


@dataclass(frozen=True)
class Case:
    id: str
    klass: str
    input: str
    must_contain: tuple[str, ...]
    must_catch: str
    must_avoid: tuple[str, ...]
    primary_axes: tuple[int, ...]
    hard_gates: tuple[str, ...]
    tags: tuple[str, ...] = ()
    kontext: str = ""
    notiz: str = ""
    holdout: bool = False


def load_cases(path: Path | None = None) -> list[Case]:
    data = json.loads((path or _DEFAULT_FILE).read_text(encoding="utf-8"))
    cases: list[Case] = []
    seen: set[str] = set()
    for c in data["cases"]:
        cid = c["id"]
        if cid in seen:
            raise ValueError(f"duplicate case id: {cid}")
        seen.add(cid)
        axes = tuple(int(a) for a in c["primary_axes"])
        if not all(a in AXES for a in axes):
            raise ValueError(f"{cid}: primary_axes {axes} outside 1..7")
        gates = tuple(c.get("hard_gates", []))
        if not all(g in HARD_GATES for g in gates):
            raise ValueError(f"{cid}: hard_gates {gates} not in {HARD_GATES}")
        cases.append(
            Case(
                id=cid,
                klass=c["klass"],
                input=c["input"],
                must_contain=tuple(c["must_contain"]),
                must_catch=c["must_catch"],
                must_avoid=tuple(c["must_avoid"]),
                primary_axes=axes,
                hard_gates=gates,
                tags=tuple(c.get("tags", [])),
                kontext=c.get("kontext", ""),
                notiz=c.get("notiz", ""),
                holdout=bool(c.get("holdout", False)),
            )
        )
    return cases
