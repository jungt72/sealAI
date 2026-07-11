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

Pure data + a typed loader - no LLM, no network. The reviewed seed is the version-controlled release
artifact; ``knowledge.bootstrap`` imports it into the authoritative Postgres runtime ledger. Qdrant
is a derived projection and is never a runtime source of truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sealai_v2.core.knowledge_answer import ANSWER_FACETS, SUBJECT_TYPES

_CATALOG_DIR = Path(__file__).resolve().parent
_DEFAULT_FILE = _CATALOG_DIR / "fachkarten_seed.json"

_REVIEW_STATES = ("reviewed", "draft")
# claim EPISTEMICS (audit 2026-06-28; taxonomy 4→8 after the re-challenge 2026-06-28): the structural
# answer to "a datasheet value is NOT a material-family truth". Every claim declares what KIND of
# statement it is, so the product frames it correctly and never oversells a value as a family limit.
# The re-challenge showed the first 4 kinds were too coarse (safety_nogo overloaded with positive
# standards + qualification rules; regulatory/definitional statements had no home), so 4 were added:
#   family_tendency        — a qualitative family-level tendency (the safe default for grounding)
#   example_value          — a compound-/test-specific datasheet number; NEVER a family limit
#   system_dependent       — depends on geometry/groove/gap/hardness/support-ring/medium/PV/pairing/processing
#   safety_nogo            — a HARD safety exclusion ONLY ("darf nicht …"); never a positive standard or rule
#   definition             — a classification/definitional statement (e.g. an ISO 1629 short code, what X is)
#   regulatory_status      — a normative/legal status (norm framework; conformity is grade-/batch-specific)
#   qualification_required — a procedural obligation: test/qualify/obtain a manufacturer-or-system release
#   safety_caution         — a known dangerous failure mode under conditions; softer than safety_nogo
_CLAIM_KINDS = (
    "family_tendency",
    "example_value",
    "system_dependent",
    "safety_nogo",
    "definition",
    "regulatory_status",
    "qualification_required",
    "safety_caution",
)
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
    kind: str = "family_tendency"  # epistemics — see _CLAIM_KINDS (default = safe family-level tendency)
    # Deterministic engineering-answer coverage metadata. Unlike ``kind`` (epistemic status), these
    # facets describe where the claim belongs in a professional answer profile.
    answer_facets: tuple[str, ...] = ()

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
    tags: tuple[str, ...] = ()
    xrefs: tuple[str, ...] = ()
    subject_type: str = "general"

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
    kind = str(raw.get("kind", "family_tendency")).strip() or "family_tendency"
    if kind not in _CLAIM_KINDS:
        raise ValueError(f"{card_id}: claim kind {kind!r} not in {_CLAIM_KINDS}")
    answer_facets = tuple(
        dict.fromkeys(
            str(f).strip() for f in raw.get("answer_facets", ()) if str(f).strip()
        )
    )
    unknown_facets = tuple(f for f in answer_facets if f not in ANSWER_FACETS)
    if unknown_facets:
        raise ValueError(f"{card_id}: unknown answer_facets {unknown_facets!r}")
    c = Claim(
        text=str(raw["text"]).strip(),
        review_state=state,
        sources=tuple(str(s) for s in raw.get("sources", [])),
        provenance=tuple(str(p) for p in raw.get("provenance", [])),
        kind=kind,
        answer_facets=answer_facets,
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
    subject_type = str(raw.get("subject_type", "general")).strip() or "general"
    if subject_type not in SUBJECT_TYPES:
        raise ValueError(
            f"{cid}: subject_type {subject_type!r} not in {sorted(SUBJECT_TYPES)}"
        )
    card = Fachkarte(
        id=cid,
        scope={d: [str(v) for v in scope.get(d, [])] for d in _SCOPE_DIMS},
        claims=claims,
        review_state=state,
        provenance=tuple(str(p) for p in raw["provenance"]),
        version=str(raw.get("version", "")),
        tags=tuple(str(t) for t in raw.get("tags", [])),
        xrefs=tuple(str(x) for x in raw.get("xrefs", [])),
        subject_type=subject_type,
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
