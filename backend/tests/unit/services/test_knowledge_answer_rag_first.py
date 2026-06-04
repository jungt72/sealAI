from __future__ import annotations

from app.domain.conversation_intent import (
    ConversationIntent,
    ResponseMode,
    classify_conversation_route,
)
from app.domain.pre_gate_classification import PreGateClassification
from app.domain.source_validation import SourceType, ValidationStatus
from app.agent.communication.knowledge_context_builder import KnowledgeContextBuilder
from app.services.knowledge_service import KnowledgeService
from app.services.pre_gate_classifier import PreGateClassifier


class _FactcardStore:
    _sources = {"src-1": {"title": "Curated source"}}

    def __init__(self, cards: list[dict[str, object]]) -> None:
        self._cards = cards

    def match_query_to_cards(self, query_lower: str) -> list[dict[str, object]]:
        return list(self._cards)


def test_curated_factcards_are_used_before_injected_rag_retriever() -> None:
    calls: list[str] = []

    def rag_retriever(**kwargs):
        calls.append(str(kwargs["query"]))
        return [
            {
                "text": "This should not be used when curated cards exist.",
                "metadata": {"source_id": "rag-1", "title": "RAG doc"},
            }
        ]

    service = KnowledgeService(
        factcard_store=_FactcardStore(
            [
                {
                    "id": "PTFE-F-001",
                    "topic": "PTFE",
                    "property": "thermal",
                    "value": "documented orientation",
                    "source": "src-1",
                }
            ]
        ),
        rag_retriever=rag_retriever,
    )

    response = service.answer("Was ist PTFE?")

    assert response.knowledge_answer_view.answer_available is True
    assert "PTFE-F-001" not in response.content
    assert "Temperaturverhalten" in response.content
    assert calls == []


def test_injected_rag_retriever_is_used_after_curated_miss() -> None:
    calls: list[dict[str, object]] = []

    def rag_retriever(**kwargs):
        calls.append(dict(kwargs))
        return [
            {
                "text": "Das Spezialprofil XQ-77 ist fuer eine dokumentierte Sonderdichtungsgeometrie beschrieben.",
                "metadata": {
                    "source_id": "doc-xq77",
                    "title": "XQ-77 Grundlagen",
                    "chunk_id": "chunk-1",
                    "vector_id": "internal-vector-123",
                    "embedding": [0.12, 0.34],
                    "db_primary_key": "db-row-99",
                },
                "fused_score": 0.82,
            }
        ]

    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        rag_retriever=rag_retriever,
    ).answer(
        "Bitte ordne diese Dichtungsfrage aus dem Dokumentenkontext ein.",
        tenant_id="tenant-1",
        user_id="user-1",
    )

    view = response.knowledge_answer_view

    assert calls == [
        {
            "query": "Bitte ordne diese Dichtungsfrage aus dem Dokumentenkontext ein.",
            "tenant_id": "tenant-1",
            "user_id": "user-1",
            "max_results": 3,
        }
    ]
    assert view.answer_available is True
    assert view.rag_answer_found is True
    assert view.rag_miss is False
    assert view.source_type is SourceType.rag_verified
    assert view.validation_status is ValidationStatus.documented
    assert view.sources[0].source_id == "doc-xq77"
    assert view.sources[0].evidence_ref == "chunk-1"
    assert view.sources[0].confidence == 0.82
    assert view.knowledge_evidence[0].source_type == "rag"
    assert view.knowledge_evidence[0].title == "XQ-77 Grundlagen"
    assert "Spezialprofil XQ-77" in view.knowledge_evidence[0].content
    evidence_payload = str(view.knowledge_evidence[0].as_dict())
    assert "internal-vector-123" not in evidence_payload
    assert "embedding" not in evidence_payload
    assert "db-row-99" not in evidence_payload
    assert view.fallback_used is False


def test_named_material_query_ignores_unrelated_ptfe_factcards_and_uses_domain_definition() -> (
    None
):
    calls: list[dict[str, object]] = []

    def rag_retriever(**kwargs):
        calls.append(dict(kwargs))
        return [
            {
                "text": "NBR ist eine Acrylnitril-Butadien-Kautschuk-Familie.",
                "metadata": {"source_id": "doc-nbr", "title": "NBR Deep Research"},
                "fused_score": 0.72,
            }
        ]

    response = KnowledgeService(rag_retriever=rag_retriever).answer(
        "Was kannst du mir zu NBR sagen?",
        tenant_id="sealai",
        user_id="user-1",
    )

    view = response.knowledge_answer_view

    assert calls == []
    assert view.rag_answer_found is False
    assert view.rag_miss is True
    assert view.source_type is SourceType.system_derived
    assert "NBR steht für Acrylnitril" in response.content


def test_rag_answer_sanitizes_document_artifacts_for_user_chat() -> None:
    def rag_retriever(**kwargs):
        return [
            {
                "text": (
                    "[Document: original.md] ### RFQ-Feld-Mapping [Q4][Q8] "
                    "### ASSUMPTIONS_AND_SCOPE NBR als Werkstofffamilie: "
                    "NBR ist eine Acrylnitril-Butadien-Kautschuk-Familie."
                ),
                "metadata": {
                    "source_id": "doc-nbr",
                    "title": "NBR Deep Research",
                    "chunk_id": "nbr-1",
                },
                "fused_score": 0.9,
            }
        ]

    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        rag_retriever=rag_retriever,
    ).answer(
        "Bitte fasse den Dokumententreffer zur Sonderdichtung XQ-77 zusammen.",
        tenant_id="sealai",
        user_id="user-1",
    )

    assert response.knowledge_answer_view.rag_answer_found is True
    assert "NBR steht für Acrylnitril" in response.content
    assert "Aus dem kuratierten/RAG-Wissenskontext" not in response.content
    assert "[Document:" not in response.content
    assert "[Q4]" not in response.content
    assert "ASSUMPTIONS_AND_SCOPE" not in response.content
    assert "RFQ-Feld-Mapping" not in response.content

    evidence_text = response.knowledge_answer_view.knowledge_evidence[0].content
    assert "[Document:" not in evidence_text
    assert "[Q4]" not in evidence_text
    assert "ASSUMPTIONS_AND_SCOPE" not in evidence_text


def test_named_product_query_drops_rag_hits_without_that_product() -> None:
    def rag_retriever(**kwargs):
        return [
            {
                "text": "NBR kann je nach ACN-Gehalt fuer Oele relevant sein.",
                "metadata": {"source_id": "doc-nbr", "title": "NBR Deep Research"},
                "fused_score": 0.81,
            }
        ]

    response = KnowledgeService(rag_retriever=rag_retriever).answer(
        "Bitte untersuche ob POM mit Klübersynth UH1 6-220 verträglich ist.",
        tenant_id="sealai",
        user_id="user-1",
    )

    view = response.knowledge_answer_view

    assert view.rag_answer_found is False
    assert view.rag_miss is True
    assert "NBR kann je nach" not in response.content


def test_rag_miss_does_not_call_llm_fallback() -> None:
    fallback_calls: list[str] = []

    def rag_retriever(**kwargs):
        return []

    def llm_fallback_runner(*args, **kwargs):
        fallback_calls.append("called")
        raise AssertionError("LLM fallback must not run in PR 9")

    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        rag_retriever=rag_retriever,
        llm_fallback_runner=llm_fallback_runner,
    ).answer("Was ist ein unbekannter Spezialwerkstoff?")

    view = response.knowledge_answer_view

    assert fallback_calls == []
    assert view.answer_available is True
    assert view.rag_miss is True
    assert view.source_type is SourceType.system_derived
    assert view.fallback_allowed is False
    assert view.fallback_used is False


def test_was_ist_fkm_stays_general_knowledge_not_governed_case_intake() -> None:
    pre_gate = PreGateClassifier().classify("Was ist FKM?")
    route = classify_conversation_route(
        "Was ist FKM?",
        pre_gate_classification=pre_gate.classification,
    )

    assert pre_gate.classification is PreGateClassification.KNOWLEDGE_QUERY
    assert route.intent is ConversationIntent.general_sealing_question
    assert route.response_mode is ResponseMode.knowledge_answer
    assert route.no_durable_engineering_case_state is True
    assert route.selects_governed_case_intake is False


def test_existing_knowledge_response_fields_remain_compatible() -> None:
    response = KnowledgeService(
        factcard_store=_FactcardStore(
            [
                {
                    "id": "PTFE-F-002",
                    "topic": "PTFE",
                    "property": "chemical",
                    "value": "documented",
                    "source": "src-1",
                }
            ]
        )
    ).answer("PTFE Chemie")

    assert response.content
    assert response.output_class == "conversational_answer"
    assert response.no_case_created is True
    assert response.citations
    assert response.source_classification is PreGateClassification.KNOWLEDGE_QUERY


def test_ptfe_fkm_comparison_is_human_general_orientation() -> None:
    response = KnowledgeService(factcard_store=_FactcardStore([])).answer(
        "Was ist der Unterschied zwischen PTFE und FKM?"
    )

    assert response.no_case_created is True
    assert "Kurz gesagt" in response.content
    assert "PTFE" in response.content
    assert "FKM" in response.content
    assert "keine Auswahl" in response.content
    assert "freigegeben" not in response.content.lower()


def test_deterministic_domain_answer_exposes_bounded_evidence_for_context() -> None:
    response = KnowledgeService(factcard_store=_FactcardStore([])).answer(
        "Was ist der Unterschied zwischen PTFE und FKM?"
    )
    view = response.knowledge_answer_view

    assert response.content == view.answer
    assert view.knowledge_evidence
    assert view.knowledge_evidence[0].source_type == "deterministic"
    assert "PTFE und FKM" in view.knowledge_evidence[0].content
    assert len(view.knowledge_evidence[0].content) <= 900

    context = KnowledgeContextBuilder().build(
        user_message="Was ist der Unterschied zwischen PTFE und FKM?",
        deterministic_answer=response.content,
        knowledge_response=response,
    )

    assert context.evidence_items[0].source_type == "deterministic"
    assert "PTFE und FKM" in context.evidence_items[0].content
