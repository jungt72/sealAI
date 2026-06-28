"""Fachkarten — L2's grounded POSITIVE-knowledge cards (build-spec §3/§5/§8).

The affirmative counterpart to the trap catalog: where a trap says "do not claim X", a Fachkarte
says "the grounded fact is Y, per <source>". Same two review states + provenance discipline as the
trap catalog, applied to positive knowledge, plus **per-claim** sourcing (a card can mix reviewed
and draft claims).

Circularity guard (build-spec §8 — "no LLM erdet LLM"). A claim may reach ``reviewed`` by EITHER:
  (i)  OWNER-CONFIRMED — provenance names the owner / a reviewed trap-correct
       (``owner:…`` or ``trap-correct:…``); no external primary source required (the owner is the
       domain authority); OR
  (ii) DEEP-RESEARCH — the claim carries at least one PRIMARY ``source`` (norm/datasheet/literature)
       that the owner verified.
A ``reviewed`` claim with NEITHER an owner/trap provenance NOR a primary source is a load error.
``draft`` claims are flag-only (never authoritative, never corrective) and carry no such constraint.

Pure data + a typed loader — no LLM, no network (``core`` stays I/O-free; retrieval is a separate
seam). The seed file is canonical for M3 (git = provenance/version/audit), mirroring trap_catalog.json;
Postgres/Qdrant are deferred runtime adapters behind the Retriever seam.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_CATALOG_DIR = Path(__file__).resolve().parent
_DEFAULT_FILE = _CATALOG_DIR / "fachkarten_seed.json"

_REVIEW_STATES = ("reviewed", "draft")
# provenance markers that establish path (i) owner-grounding (no external source needed)
_OWNER_PROV_PREFIXES = ("owner", "trap-correct:", "trap:")
_SCOPE_DIMS = ("material", "medium", "property", "application")


@dataclass(frozen=True)
class Claim:
    """One grounded statement on a card, with its own review state + grounding evidence."""

    text: str
    review_state: str  # "reviewed" | "draft"
    sources: tuple[
        str, ...
    ] = ()  # PRIMARY citations (path ii); may be empty for path (i)
    provenance: tuple[
        str, ...
    ] = ()  # path (i): "trap-correct:…"/"owner:…"; path (ii): research origin

    @property
    def reviewed(self) -> bool:
        return self.review_state == "reviewed"

    @property
    def owner_grounded(self) -> bool:
        return any(p.lower().startswith(_OWNER_PROV_PREFIXES) for p in self.provenance)


@dataclass(frozen=True)
class Fachkarte:
    id: str
    scope: dict  # {material:[...], medium:[...], property:[...], application:[...]} — retrieval tags
    claims: tuple[Claim, ...]
    review_state: str  # "reviewed" (≥1 reviewed claim) | "draft" (all draft)
    provenance: tuple[str, ...]  # card-level origin (names the source trap / owner)
    version: str = ""
    matrix_crosscheck: str = "unchecked"  # "unchecked" | "agree" | "conflict"
    tags: tuple[str, ...] = ()
    xrefs: tuple[str, ...] = ()

    def reviewed_claims(self) -> tuple[Claim, ...]:
        return tuple(c for c in self.claims if c.review_state == "reviewed")

    def draft_claims(self) -> tuple[Claim, ...]:
        return tuple(c for c in self.claims if c.review_state == "draft")

    def scope_tokens(self) -> frozenset[str]:
        """All scope-tag tokens (lower-cased), for the in-process retriever's overlap match."""
        toks: set[str] = set()
        for dim in _SCOPE_DIMS:
            for v in self.scope.get(dim, []) or []:
                toks.add(str(v).strip().lower())
        return frozenset(t for t in toks if t)


@dataclass(frozen=True)
class FachkartenCatalog:
    cards: tuple[Fachkarte, ...]
    version: str = ""
    source: str = ""

    def reviewed(self) -> tuple[Fachkarte, ...]:
        return tuple(c for c in self.cards if c.review_state == "reviewed")

    def by_id(self, card_id: str) -> Fachkarte | None:
        for c in self.cards:
            if c.id == card_id:
                return c
        return None


def _claim(raw: dict, card_id: str) -> Claim:
    state = str(raw.get("review_state", "")).strip()
    if state not in _REVIEW_STATES:
        raise ValueError(
            f"{card_id}: claim review_state {state!r} not in {_REVIEW_STATES}"
        )
    c = Claim(
        text=str(raw["text"]).strip(),
        review_state=state,
        sources=tuple(str(s) for s in raw.get("sources", [])),
        provenance=tuple(str(p) for p in raw.get("provenance", [])),
    )
    if not c.text:
        raise ValueError(f"{card_id}: empty claim text")
    # Circularity guard — a REVIEWED claim must be path (i) owner-grounded OR path (ii) primary-sourced.
    if c.reviewed and not (c.owner_grounded or c.sources):
        raise ValueError(
            f"{card_id}: reviewed claim has neither owner/trap provenance (path i) nor a primary "
            f"source (path ii) — 'no LLM erdet LLM': {c.text[:60]!r}"
        )
    return c


def _card(raw: dict) -> Fachkarte:
    cid = str(raw["id"])
    state = str(raw.get("review_state", "")).strip()
    if state not in _REVIEW_STATES:
        raise ValueError(f"{cid}: review_state {state!r} not in {_REVIEW_STATES}")
    scope = raw.get("scope", {}) or {}
    if not isinstance(scope, dict) or not any(scope.get(d) for d in _SCOPE_DIMS):
        raise ValueError(f"{cid}: scope must set at least one of {_SCOPE_DIMS}")
    claims = tuple(_claim(c, cid) for c in raw.get("claims", []))
    if not claims:
        raise ValueError(f"{cid}: at least one claim required")
    if not raw.get("provenance"):
        raise ValueError(f"{cid}: provenance is mandatory (owner-grounding audit)")
    card = Fachkarte(
        id=cid,
        scope={d: [str(v) for v in scope.get(d, [])] for d in _SCOPE_DIMS},
        claims=claims,
        review_state=state,
        provenance=tuple(str(p) for p in raw["provenance"]),
        version=str(raw.get("version", "")),
        matrix_crosscheck=str(raw.get("matrix_crosscheck", "unchecked")),
        tags=tuple(str(t) for t in raw.get("tags", [])),
        xrefs=tuple(str(x) for x in raw.get("xrefs", [])),
    )
    # a reviewed card must actually carry a reviewed claim (else it cannot ground anything)
    if card.review_state == "reviewed" and not card.reviewed_claims():
        raise ValueError(f"{cid}: review_state=reviewed but no reviewed claim present")
    return card


def load_fachkarten(path: Path | None = None) -> FachkartenCatalog:
    """Load + validate the Fachkarten seed. Raises on any circularity-guard / schema violation."""
    data = json.loads((path or _DEFAULT_FILE).read_text(encoding="utf-8"))
    cards: list[Fachkarte] = []
    seen: set[str] = set()
    for raw in data.get("cards", []):
        c = _card(raw)
        if c.id in seen:
            raise ValueError(f"duplicate Fachkarte id: {c.id}")
        seen.add(c.id)
        cards.append(c)
    if not cards:
        raise ValueError("Fachkarten catalog is empty")
    return FachkartenCatalog(
        cards=tuple(cards),
        version=str(data.get("version", "")),
        source=str(data.get("source", "")),
    )
