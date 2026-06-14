"""Trap catalog (Fallen-Katalog) — L3's grounded failure-mode list (build-spec §4).

Derived from the OWNER-AUTHORED ground truth (eval ``must_catch``/``must_avoid`` + principles §2
+ the documented M1 divergences). Two review states with a hard discipline (build-spec §8 — no
"LLM erdet LLM"):

- ``reviewed`` — owner-grounded; MAY drive a block/correction (its ``correct`` fact is asserted).
- ``draft``   — model-proposed, UNREVIEWED; may only FLAG, NEVER correct.

The JSON keeps the two sets in separate blocks (``reviewed`` / ``draft_for_review``); the loader
stamps ``review_state`` from the block it came from, so a draft entry can never claim ``reviewed``.
This module is pure data + a typed loader — no LLM, no network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sealai_v2.core.contracts import HARD_GATES

_CATALOG_DIR = Path(__file__).resolve().parent
_DEFAULT_FILE = _CATALOG_DIR / "trap_catalog.json"

_REVIEW_STATES = ("reviewed", "draft")


@dataclass(frozen=True)
class TrapEntry:
    id: str
    trigger: str  # human-readable activation condition (selection is server-side, not Jinja logic)
    wrong: tuple[str, ...]  # the wrong claim(s)/mechanism(s) to catch
    correct: str  # the correct fact (owner-grounded for reviewed entries)
    gates: tuple[
        str, ...
    ]  # which hard gate(s) this trap can trip (subset of HARD_GATES)
    provenance: tuple[
        str, ...
    ]  # authored origin (eval:… / principles:§2 / divergence:…)
    review_state: str  # "reviewed" | "draft" — stamped from the JSON block
    tags: tuple[str, ...] = ()
    xrefs: tuple[str, ...] = ()

    @property
    def reviewed(self) -> bool:
        return self.review_state == "reviewed"


@dataclass(frozen=True)
class TrapCatalog:
    entries: tuple[TrapEntry, ...]
    version: str = ""
    source: str = ""

    def reviewed(self) -> tuple[TrapEntry, ...]:
        return tuple(e for e in self.entries if e.review_state == "reviewed")

    def drafts(self) -> tuple[TrapEntry, ...]:
        return tuple(e for e in self.entries if e.review_state == "draft")

    def by_id(self, trap_id: str) -> TrapEntry | None:
        for e in self.entries:
            if e.id == trap_id:
                return e
        return None


def _entry(raw: dict, review_state: str) -> TrapEntry:
    return TrapEntry(
        id=str(raw["id"]),
        trigger=str(raw["trigger"]),
        wrong=tuple(str(w) for w in raw["wrong"]),
        correct=str(raw.get("correct", "")),
        gates=tuple(str(g) for g in raw["gates"]),
        provenance=tuple(str(p) for p in raw["provenance"]),
        review_state=review_state,
        tags=tuple(str(t) for t in raw.get("tags", [])),
        xrefs=tuple(str(x) for x in raw.get("xrefs", [])),
    )


def load_traps(path: Path | None = None) -> TrapCatalog:
    """Load + validate the catalog. ``review_state`` is taken from the BLOCK (``reviewed`` vs
    ``draft_for_review``) — never from inside an entry — so the discipline cannot be bypassed."""
    data = json.loads((path or _DEFAULT_FILE).read_text(encoding="utf-8"))
    entries: list[TrapEntry] = []
    seen: set[str] = set()
    for block, state in (("reviewed", "reviewed"), ("draft_for_review", "draft")):
        for raw in data.get(block, []):
            e = _entry(raw, state)
            if e.id in seen:
                raise ValueError(f"duplicate trap id: {e.id}")
            seen.add(e.id)
            if not all(g in HARD_GATES for g in e.gates):
                raise ValueError(f"{e.id}: gates {e.gates} not all in {HARD_GATES}")
            if not e.gates:
                raise ValueError(f"{e.id}: at least one gate required")
            if not e.wrong:
                raise ValueError(f"{e.id}: at least one 'wrong' pattern required")
            if not e.provenance:
                raise ValueError(
                    f"{e.id}: provenance is mandatory (owner-grounding audit)"
                )
            # Integrity: a reviewed entry MUST carry a correct fact (it may assert/correct);
            # a draft entry must NOT be relied on to correct, so its correct fact is optional.
            if e.review_state == "reviewed" and not e.correct.strip():
                raise ValueError(
                    f"{e.id}: reviewed entry must have a non-empty 'correct' fact"
                )
            entries.append(e)
    if not entries:
        raise ValueError("trap catalog is empty")
    return TrapCatalog(
        entries=tuple(entries),
        version=str(data.get("version", "")),
        source=str(data.get("source", "")),
    )
