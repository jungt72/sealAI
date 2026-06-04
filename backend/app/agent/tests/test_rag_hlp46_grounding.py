from __future__ import annotations

from app.domain.source_validation import SourceType
from app.services.knowledge_service import KnowledgeService


class _FactcardStore:
    _sources: dict[str, dict[str, object]] = {}

    def match_query_to_cards(self, query_lower: str) -> list[dict[str, object]]:
        return []


def test_hlp46_rag_answer_keeps_medium_grounding_and_avoids_nbr_drift() -> None:
    def rag_retriever(**kwargs):
        return [
            {
                "text": "NBR ist eine Acrylnitril-Butadien-Kautschuk-Familie.",
                "metadata": {"source_id": "doc-nbr", "title": "NBR"},
                "fused_score": 0.91,
            },
            {
                "text": "HLP 46 ist ein Hydraulikoel mit ISO-Viskositaetsklasse 46.",
                "metadata": {"source_id": "doc-hlp46", "title": "HLP 46"},
                "fused_score": 0.77,
            },
        ]

    response = KnowledgeService(
        factcard_store=_FactcardStore(),
        rag_retriever=rag_retriever,
        llm_research_fallback_enabled=False,
    ).answer("Was genau bedeutet HLP 46?", tenant_id="sealai", user_id="user-1")

    view = response.knowledge_answer_view

    assert view.rag_answer_found is True
    assert view.rag_miss is False
    assert len(view.sources) == 1
    assert view.sources[0].source_id == "doc-hlp46"
    assert "HLP 46" in response.content
    assert "NBR steht" not in response.content
    assert "nicht automatisch biologisch abbaubar" in response.content


def test_hlp46_rag_miss_uses_limited_system_orientation() -> None:
    response = KnowledgeService(
        factcard_store=_FactcardStore(),
        rag_retriever=lambda **kwargs: [],
        llm_research_fallback_enabled=False,
    ).answer("Was genau bedeutet HLP 46?", tenant_id="sealai", user_id="user-1")

    view = response.knowledge_answer_view

    assert view.rag_answer_found is False
    assert view.rag_miss is True
    assert view.source_type is SourceType.system_derived
    assert view.missing_reason == "domain_hlp46_orientation_without_rag_hit"
    assert "HLP 46" in response.content
    assert "nicht automatisch biologisch abbaubar" in response.content
