"""Fachkarten: typed positive knowledge for L2 grounding.

The affirmative counterpart to the trap catalog: where a trap says "do not claim X", a Fachkarte
says "the grounded fact is Y, per <source>". Same two review states + provenance discipline as the
trap catalog, applied to positive knowledge, plus **per-claim** sourcing (a card can mix reviewed
and draft claims).

P2 guard: provenance records who asserted or reviewed a statement; it never
replaces technical evidence. A declared ``reviewed`` claim without a source is
loaded as ``quarantined``. Quarantined claims remain visible to review tooling
but never reach retrieval, prompts, citations, or a derived vector index.
``draft`` claims remain provisional and never authoritative or corrective.

Pure data + a typed loader - no LLM, no network. The reviewed seed is the version-controlled release
artifact; ``knowledge.bootstrap`` imports it into the authoritative Postgres runtime ledger. Qdrant
is a derived projection and is never a runtime source of truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from sealai_v2.core.knowledge_answer import ANSWER_FACETS, SUBJECT_TYPES

_CATALOG_DIR = Path(__file__).resolve().parent
_DEFAULT_FILE = _CATALOG_DIR / "fachkarten_seed.json"

_DECLARED_REVIEW_STATES = ("reviewed", "draft", "quarantined")
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
# Provenance remains useful audit metadata, but is not evidence.
_OWNER_PROV_PREFIXES = ("owner", "trap-correct:", "trap:")
_SCOPE_DIMS = ("material", "medium", "property", "application")
_UNCERTAINTY_STATES = (
    "bounded",
    "conditional",
    "conflicted",
    "not_sufficiently_supported",
)
_TRANSFERABILITY_STATES = (
    "source_specific",
    "family_level_orientation",
    "application_dependent",
    "not_assessed",
)


@dataclass(frozen=True)
class Claim:
    """One grounded statement on a card, with its own review state + grounding evidence."""

    text: str
    review_state: str  # "reviewed" | "draft" | "quarantined"
    sources: tuple[
        str, ...
    ] = ()  # primary citations; mandatory for authoritative review
    provenance: tuple[
        str, ...
    ] = ()  # path (i): "trap-correct:…"/"owner:…"; path (ii): research origin
    kind: str = "family_tendency"  # epistemics — see _CLAIM_KINDS (default = safe family-level tendency)
    # Deterministic engineering-answer coverage metadata. Unlike ``kind`` (epistemic status), these
    # facets describe where the claim belongs in a professional answer profile.
    answer_facets: tuple[str, ...] = ()
    applicability: dict = field(default_factory=dict)
    uncertainty: str = ""
    transferability: str = ""
    conflicts: tuple[str, ...] = ()
    reviewed_at: str = ""
    reviewed_by: str = ""
    review_expires_at: str = ""
    change_reason: str = ""

    @property
    def reviewed(self) -> bool:
        return (
            self.review_state == "reviewed"
            and bool(self.sources)
            and _human_reviewer(self.reviewed_by)
            and _review_window_current(self.reviewed_at, self.review_expires_at)
        )

    @property
    def quarantined(self) -> bool:
        return self.review_state == "quarantined" or (
            self.review_state == "reviewed" and not self.reviewed
        )

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
        return tuple(c for c in self.claims if c.reviewed)

    def draft_claims(self) -> tuple[Claim, ...]:
        return tuple(c for c in self.claims if c.review_state == "draft")

    def quarantined_claims(self) -> tuple[Claim, ...]:
        return tuple(c for c in self.claims if c.quarantined)

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
    declared_state = str(raw.get("review_state", "")).strip()
    if declared_state not in _DECLARED_REVIEW_STATES:
        raise ValueError(
            f"{card_id}: claim review_state {declared_state!r} not in "
            f"{_DECLARED_REVIEW_STATES}"
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
    applicability = raw.get("applicability", {}) or {}
    if not isinstance(applicability, dict):
        raise ValueError(f"{card_id}: claim applicability must be an object")
    uncertainty = str(raw.get("uncertainty", "")).strip()
    if uncertainty and uncertainty not in _UNCERTAINTY_STATES:
        raise ValueError(f"{card_id}: invalid uncertainty {uncertainty!r}")
    transferability = str(raw.get("transferability", "")).strip()
    if transferability and transferability not in _TRANSFERABILITY_STATES:
        raise ValueError(f"{card_id}: invalid transferability {transferability!r}")
    sources = tuple(str(s).strip() for s in raw.get("sources", []) if str(s).strip())
    c = Claim(
        text=str(raw["text"]).strip(),
        review_state=declared_state,
        sources=sources,
        provenance=tuple(str(p) for p in raw.get("provenance", [])),
        kind=kind,
        answer_facets=answer_facets,
        applicability=applicability,
        uncertainty=uncertainty,
        transferability=transferability,
        conflicts=tuple(str(item) for item in raw.get("conflicts", ())),
        reviewed_at=str(raw.get("reviewed_at", "")).strip(),
        reviewed_by=str(raw.get("reviewed_by", "")).strip(),
        review_expires_at=str(raw.get("review_expires_at", "")).strip(),
        change_reason=str(raw.get("change_reason", "")).strip(),
    )
    if not c.text:
        raise ValueError(f"{card_id}: empty claim text")
    if declared_state == "reviewed" and not c.reviewed:
        return replace(c, review_state="quarantined")
    return c


def _human_reviewer(value: str) -> bool:
    reviewer = value.strip().lower()
    if not reviewer:
        return False
    return not any(marker in reviewer for marker in ("codex", "llm", "model", "agent"))


def _review_window_current(reviewed_at: str, review_expires_at: str) -> bool:
    try:
        reviewed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        expires = datetime.fromisoformat(review_expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if reviewed.tzinfo is None or expires.tzinfo is None or expires <= reviewed:
        return False
    return expires > datetime.now(timezone.utc)


def _card(raw: dict) -> Fachkarte:
    cid = str(raw["id"])
    declared_state = str(raw.get("review_state", "")).strip()
    if declared_state not in _DECLARED_REVIEW_STATES:
        raise ValueError(
            f"{cid}: review_state {declared_state!r} not in "
            f"{_DECLARED_REVIEW_STATES}"
        )
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
    effective_state = "reviewed" if any(claim.reviewed for claim in claims) else "draft"
    card = Fachkarte(
        id=cid,
        scope={d: [str(v) for v in scope.get(d, [])] for d in _SCOPE_DIMS},
        claims=claims,
        review_state=effective_state,
        provenance=tuple(str(p) for p in raw["provenance"]),
        version=str(raw.get("version", "")),
        tags=tuple(str(t) for t in raw.get("tags", [])),
        xrefs=tuple(str(x) for x in raw.get("xrefs", [])),
        subject_type=subject_type,
    )
    return card


def load_fachkarten(path: Path | None = None) -> FachkartenCatalog:
    """Load and validate the Fachkarten seed, quarantining unsupported approvals."""
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
