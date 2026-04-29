from __future__ import annotations

from app.domain.conversation_intent import (
    ConversationIntent,
    ResponseMode,
    classify_conversation_route,
)
from app.domain.pre_gate_classification import PreGateClassification
from app.domain.source_validation import SourceType, ValidationStatus
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
    assert "PTFE-F-001" in response.content
    assert calls == []


def test_injected_rag_retriever_is_used_after_curated_miss() -> None:
    calls: list[dict[str, object]] = []

    def rag_retriever(**kwargs):
        calls.append(dict(kwargs))
        return [
            {
                "text": "FKM ist eine Fluorelastomer-Werkstofffamilie.",
                "metadata": {
                    "source_id": "doc-fkm",
                    "title": "FKM Grundlagen",
                    "chunk_id": "chunk-1",
                },
                "fused_score": 0.82,
            }
        ]

    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        rag_retriever=rag_retriever,
    ).answer("Was ist FKM?", tenant_id="tenant-1", user_id="user-1")

    view = response.knowledge_answer_view

    assert calls == [
        {
            "query": "Was ist FKM?",
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
    assert view.sources[0].source_id == "doc-fkm"
    assert view.sources[0].evidence_ref == "chunk-1"
    assert view.sources[0].confidence == 0.82
    assert view.fallback_used is False


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
    assert view.answer_available is False
    assert view.rag_miss is True
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
