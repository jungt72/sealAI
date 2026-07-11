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
from sealai_v2.core.knowledge_answer import build_knowledge_answer_plan
from sealai_v2.core.text_match import query_tokens, tag_matches
from sealai_v2.knowledge.fachkarten import Fachkarte, FachkartenCatalog, load_fachkarten

# A card is retrieved when at least this many of its scope tags appear in the query. Two keeps it
# precise (one material + its medium/application), avoiding a single shared material (e.g. "FKM")
# pulling every card. Deliberately simple; semantic recall is the deferred Qdrant adapter's job.
_MIN_SCOPE_HITS = 2

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
    """Highest visible claim severity; quarantined content cannot affect ranking."""
    return max(
        (_KIND_SEVERITY.get(c.kind, 0) for c in card.claims if not c.quarantined),
        default=0,
    )


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
    # Broadness is structural, not a list of guessed question phrases: one material subject with no
    # medium/property/application tag is an overview. Focused questions retain the stricter 2-scope
    # rule. Comparison language is handled by the full engineering route, not this overview path.
    if any(
        tag_matches(str(tag), tokens, query_lower)
        for dim in ("medium", "property", "application")
        for tag in card.scope.get(dim, ())
    ):
        return False
    return not any(
        marker in query_lower
        for marker in (" vs ", " versus ", "vergleich", "unterschied")
    )


def _is_knowledge_overview(card: Fachkarte, query: str) -> bool:
    """Single-subject overview recall for material, medium and seal-type cards.

    The old exception covered only a bare material ("Details zu PTFE"). A seal-type explanation
    names the subject in ``scope.application`` instead, so the same one-subject/two-scope rule left
    RWDR, O-Ring and mechanical-seal profiles unreachable in the deterministic fallback retriever.
    """
    plan = build_knowledge_answer_plan(
        query,
        material_terms=tuple(card.scope.get("material", ())),
    )
    if plan is None:
        return False
    if plan.subject_type == "material":
        if plan.comparison:
            tokens = query_tokens(query)
            query_lower = query.lower()
            return any(
                tag_matches(str(tag), tokens, query_lower)
                for tag in card.scope.get("material", ())
            )
        return _is_material_overview(card, query.lower())

    # Seal/medium overviews use dedicated reviewed profile cards. This prevents a material card that
    # merely mentions "Gleitring" or "O-Ring" as one application from masquerading as the complete
    # engineering profile for that seal type.
    if (
        plan.subject_type in {"seal_type", "medium"}
        and card.subject_type != plan.subject_type
    ):
        return False
    tokens = query_tokens(query)
    query_lower = query.lower()
    dimension = "medium" if plan.subject_type == "medium" else "application"
    return any(
        tag_matches(str(tag), tokens, query_lower)
        for tag in card.scope.get(dimension, ())
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
        knowledge_turn = build_knowledge_answer_plan(
            query,
            material_terms=tuple(
                dict.fromkeys(
                    term
                    for card in self._catalog.cards
                    for term in card.scope.get("material", ())
                )
            ),
        )
        scored = [
            (s, c)
            for c in self._catalog.cards
            if (s := _score(c, q)) >= _MIN_SCOPE_HITS
            or _is_knowledge_overview(c, query)
        ]
        if (
            knowledge_turn is not None
            and knowledge_turn.subject_type == "material"
            and knowledge_turn.subjects
        ):
            # Prefer cards whose identity names the requested material. Multi-material compatibility
            # cards often list NBR/PTFE only as alternatives while their actual claim concerns EPDM
            # or VMQ; card-level scope alone cannot prove which subject a claim predicates on.
            subject_specific = [
                item
                for item in scored
                if item[1].reviewed_claims()
                and any(
                    subject.lower() in item[1].id.lower()
                    for subject in knowledge_turn.subjects
                )
            ]
            covered_subjects = {
                subject
                for subject in knowledge_turn.subjects
                if any(
                    subject.lower() in card.id.lower()
                    for _score_value, card in subject_specific
                )
            }
            if covered_subjects == set(knowledge_turn.subjects):
                scored = subject_specific
        # On an explicit knowledge turn, reviewed subject profiles lead draft multi-subject cards;
        # otherwise strongest scope match remains first. Ties are broken by claim severity, then id.
        scored.sort(
            key=lambda sc: (
                -int(
                    knowledge_turn is not None
                    and bool(sc[1].reviewed_claims())
                    and _is_knowledge_overview(sc[1], query)
                ),
                -sc[0],
                -_card_severity(sc[1]),
                sc[1].id,
            )
        )
        reviewed: list[GroundingFact] = []
        provisional: list[GroundingFact] = []
        for _s, card in scored[: max(0, k)]:
            for claim_index, claim in enumerate(card.claims):
                if claim.quarantined:
                    continue
                fact = GroundingFact(
                    text=claim.text,
                    quelle=_quelle(card, reviewed=claim.reviewed),
                    card_id=card.id,
                    sources=claim.sources,  # M6c: owner-verified primary sources for the citation
                    claim_kind=claim.kind,
                    answer_facets=claim.answer_facets,
                    subject_type=card.subject_type,
                    claim_id=f"{card.id}:{claim_index}",
                )
                (reviewed if claim.reviewed else provisional).append(fact)
        return RetrievalResult(
            grounding_facts=tuple(reviewed), provisional=tuple(provisional)
        )
