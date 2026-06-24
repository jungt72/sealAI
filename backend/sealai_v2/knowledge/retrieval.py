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
from sealai_v2.knowledge.fachkarten import Fachkarte, FachkartenCatalog, load_fachkarten

# A card is retrieved when at least this many of its scope tags appear in the query. Two keeps it
# precise (one material + its medium/application), avoiding a single shared material (e.g. "FKM")
# pulling every card. Deliberately simple; semantic recall is the deferred Qdrant adapter's job.
_MIN_SCOPE_HITS = 2


def _quelle(card: Fachkarte, *, reviewed: bool) -> str:
    # Branch on the CLAIM's review state (a card mixes reviewed + draft claims): a draft claim must
    # never be cited as "(reviewed; …)". Mirrors knowledge/versagensmodi.py::quelle().
    tag = "reviewed" if reviewed else "draft — vorläufig, gegen Hersteller verifizieren"
    return f"Fachkarte {card.id} ({tag}; {', '.join(card.provenance)})"


def _score(card: Fachkarte, query_lower: str) -> int:
    return sum(1 for tok in card.scope_tokens() if tok in query_lower)


class InProcessRetriever:
    """Implements the ``Retriever`` Protocol over an in-memory ``FachkartenCatalog``."""

    def __init__(self, catalog: FachkartenCatalog | None = None) -> None:
        self._catalog = catalog or load_fachkarten()

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
        ]
        # strongest first; id tie-break keeps the order deterministic for the eval REPLAY
        scored.sort(key=lambda sc: (-sc[0], sc[1].id))
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
