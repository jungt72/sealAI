"""L2 retrieval — the in-process Fachkarten retriever (build-spec §5 grounden).

Deterministic scope-tag/keyword match over the loaded seed cards: an offline measurement/CI
instrument (mirrors the fake LLM client). It validates the grounding MECHANISM, NOT corpus-scale
recall — a Qdrant embeddings adapter (semantic recall) is the deferred production path behind the
same ``Retriever`` Protocol (build-spec §3). Pure: no network, no embeddings, no LLM.

Tenant scope is a mandatory parameter (P0). Seed cards are GLOBAL knowledge (not tenant-owned), so
``tenant_id`` is threaded but does not filter here; tenant-scoped cards filter server-side once the
Postgres/Qdrant adapters land.
"""

from __future__ import annotations

from sealai_v2.core.contracts import GroundingFact, RetrievalResult
from sealai_v2.core.text_match import query_tokens, tag_matches
from sealai_v2.knowledge.fachkarten import Fachkarte, FachkartenCatalog, load_fachkarten

# A card is retrieved when at least this many of its scope tags appear in the query. Two keeps it
# precise (one material + its medium/application), avoiding a single shared material (e.g. "FKM")
# pulling every card. Deliberately simple; semantic recall is the deferred Qdrant adapter's job.
_MIN_SCOPE_HITS = 2

_OVERVIEW_MARKERS = (
    "details zu",
    "informationen zu",
    "überblick zu",
    "ueberblick zu",
    "was ist",
    "eigenschaften von",
)

# P2-D (owner Leitbild-Audit 2026-07-02, Quellenhierarchie/Konfliktlogik §4.3): a claim-epistemics-
# based tie-break — used ONLY when two cards tie on scope-hit score (previously an arbitrary
# alphabetical card.id tie-break, see git history). A card carrying safety-relevant claims must not
# lose a coin-flip-by-name against a card that only states a generic family tendency, right at the
# top-k cutoff where a tie decides whether a card is retrieved AT ALL. Never overrides the PRIMARY
# relevance ranking (scope-hit count) — a more specifically matching card always wins regardless of
# severity; this only decides between EQUALLY relevant cards. Mirrors the kind taxonomy's own
# severity ordering (fachkarten.py's docstring): hard safety exclusions first, generic tendencies last.
_KIND_SEVERITY = {
    "safety_nogo": 4,
    "safety_caution": 3,
    "qualification_required": 3,
    "regulatory_status": 2,
    "system_dependent": 1,
    "definition": 1,
    "example_value": 1,
    "family_tendency": 0,
}


def _card_severity(card: Fachkarte) -> int:
    """The HIGHEST claim severity on the card — checked across ALL claims (reviewed AND draft), not
    just reviewed_claims(): a draft safety_nogo is still a real signal this card matters, even though
    the draft channel is not yet authoritative for grounding (see the audit's dead-provisional-channel
    finding) — the card-level retrieval decision (does it make the top-k at all) is upstream of that."""
    return max((_KIND_SEVERITY.get(c.kind, 0) for c in card.claims), default=0)


def _quelle(card: Fachkarte, *, reviewed: bool) -> str:
    # Branch on the CLAIM's review state (a card mixes reviewed + draft claims): a draft claim must
    # never be cited as "(reviewed; …)". Mirrors knowledge/versagensmodi.py::quelle().
    tag = "reviewed" if reviewed else "draft — vorläufig, gegen Hersteller verifizieren"
    return f"Fachkarte {card.id} ({tag}; {', '.join(card.provenance)})"


def _score(card: Fachkarte, query_lower: str) -> int:
    return sum(1 for tok in card.scope_tokens() if tok in query_lower)


def _is_material_overview(card: Fachkarte, query_lower: str) -> bool:
    """Allow one explicit material hit for a broad knowledge question.

    Compatibility and design queries still require two scope dimensions. A request such as
    "Details zu PTFE" necessarily names only the subject, though; requiring a medium or application
    there makes the deterministic eval/fallback retriever falsely ungrounded while production Qdrant
    retrieves the same reviewed material card semantically.
    """
    tokens = query_tokens(query_lower)
    materials = tuple(
        str(material).strip()
        for material in card.scope.get("material", ())
        if str(material).strip()
    )
    matched = any(tag_matches(material, tokens, query_lower) for material in materials)
    if not matched:
        return False
    if any(marker in query_lower for marker in _OVERVIEW_MARKERS):
        return True
    # A bare material name is itself an unambiguous overview request in chat.
    return len(tokens) == 1 and any(
        material.lower() in tokens for material in materials
    )


class InProcessRetriever:
    """Implements the ``Retriever`` Protocol over an in-memory ``FachkartenCatalog``."""

    def __init__(self, catalog: FachkartenCatalog | None = None) -> None:
        self._catalog = catalog or load_fachkarten()

    @property
    def catalog(self) -> FachkartenCatalog:
        """The backing catalog — exposed for its ``.version`` (P3 Wissensstand-Referenz), mirroring
        the accessor already on ``InProcessCompatibilityMatrix``/``InProcessVersagensmodiStore``."""
        return self._catalog

    async def retrieve(
        self, query: str, *, tenant_id: str, k: int = 5
    ) -> RetrievalResult:
        if not (tenant_id or "").strip():
            raise ValueError("tenant_id is mandatory (P0 repository-layer scope)")
        q = (query or "").lower()
        scored = [
            (s, c)
            for c in self._catalog.cards
            if (s := _score(c, q)) >= _MIN_SCOPE_HITS
            or (s >= 1 and _is_material_overview(c, q))
        ]
        # strongest scope match first (unchanged); ties broken by claim severity (P2-D), THEN id —
        # still fully deterministic, but a safety-relevant card no longer loses an arbitrary
        # alphabetical tie against a purely generic one right at the top-k cutoff.
        scored.sort(
            key=lambda sc: (
                -sc[0],
                -int(bool(sc[1].reviewed_claims()) and _is_material_overview(sc[1], q)),
                -_card_severity(sc[1]),
                sc[1].id,
            )
        )
        reviewed: list[GroundingFact] = []
        provisional: list[GroundingFact] = []
        for _s, card in scored[: max(0, k)]:
            for claim in card.reviewed_claims():
                reviewed.append(
                    GroundingFact(
                        text=claim.text,
                        quelle=_quelle(card, reviewed=True),
                        card_id=card.id,
                        sources=claim.sources,  # M6c: owner-verified primary sources for the citation
                    )
                )
            for claim in card.draft_claims():
                provisional.append(
                    GroundingFact(
                        text=claim.text,
                        quelle=_quelle(card, reviewed=False),
                        card_id=card.id,
                        sources=claim.sources,
                    )
                )
        return RetrievalResult(
            grounding_facts=tuple(reviewed), provisional=tuple(provisional)
        )
