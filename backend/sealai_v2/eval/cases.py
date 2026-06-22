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
_EDGE_FILE = _SEED_DIR / "edge_v0.json"
_INJECTION_FILE = _SEED_DIR / "injection_v0.json"
_ARCHETYPE_FILE = _SEED_DIR / "archetype_v0.json"
_CALIBRATION_FILE = _SEED_DIR / "calibration_v0.json"


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


def load_edge_cases(path: Path | None = None) -> list[Case]:
    """Konversations-Rand (EDGE) class (M6a-B) — same validated ``Case`` shape, separate seed file
    so the frozen 25-case ``seed_set_v0.json`` stays the no-regression anchor."""
    return load_cases(path or _EDGE_FILE)


def load_injection_cases(path: Path | None = None) -> list[Case]:
    """Injektion / Sicherheit (INJECTION) class (M6b) — same validated ``Case`` shape, separate seed
    file so the frozen non-edge anchor stays untouched. Gate-relevant on ``injection_override``
    (human-final); the deterministic ``exfiltration`` gate is computed over the answers, not here."""
    return load_cases(path or _INJECTION_FILE)


def load_archetype_cases(path: Path | None = None) -> list[Case]:
    """archetype_fit class (G5, V2.1 Inc 1) — archetype-recognition cases; same validated ``Case``
    shape, separate seed so the frozen non-edge anchor stays untouched. A CREDIBILITY/axes class
    (no new hard gate — the 8 Schranken stay fixed): it measures whether the recognised archetype's
    interview questions + blind spots surface in the answer."""
    return load_cases(path or _ARCHETYPE_FILE)


def load_calibration_cases(path: Path | None = None) -> list[Case]:
    """confident_correct_vs_hedge class (C4, V2.1 Inc 2) — calibration cases; same validated ``Case``
    shape, separate seed so the frozen non-edge anchor stays untouched. A CREDIBILITY/axes class (no
    new hard gate — the 8 Schranken stay fixed): it measures assertive-WHERE-grounded (kernel v-limit
    fact, §4 matrix) vs an honest hedge at the ungrounded edge, and guards the kern-fix-01 restraint.
    DD-5: specific material names only when matrix-/Fachkarte-grounded, never from the v>limit signal."""
    return load_cases(path or _CALIBRATION_FILE)
