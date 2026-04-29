from __future__ import annotations

from app.domain.source_validation import (
    SourceType,
    ValidationStatus,
    is_unvalidated_source,
    source_validation_metadata,
)
from app.services.knowledge_service import KnowledgeService


class _FactcardStore:
    _sources = {"src-1": {"title": "Curated source"}}

    def __init__(self, cards: list[dict[str, object]]) -> None:
        self._cards = cards

    def match_query_to_cards(self, query_lower: str) -> list[dict[str, object]]:
        return list(self._cards)


def _curated_card() -> dict[str, object]:
    return {
        "id": "PTFE-F-001",
        "topic": "PTFE",
        "property": "orientation",
        "value": "documented",
        "source": "src-1",
    }


def test_fallback_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.knowledge_service._settings_fallback_enabled",
        lambda: False,
    )
    fallback_calls: list[str] = []

    def fallback_runner(**kwargs):
        fallback_calls.append(str(kwargs["query"]))
        return "Fallback should not run."

    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        llm_fallback_runner=fallback_runner,
    ).answer("Was ist ein unbekannter Dichtungswerkstoff?")

    view = response.knowledge_answer_view

    assert fallback_calls == []
    assert view.rag_miss is True
    assert view.fallback_allowed is False
    assert view.fallback_used is False
    assert view.answer_available is False


def test_curated_hit_does_not_call_enabled_fallback() -> None:
    fallback_calls: list[str] = []

    def fallback_runner(**kwargs):
        fallback_calls.append(str(kwargs["query"]))
        return "Fallback should not run."

    response = KnowledgeService(
        factcard_store=_FactcardStore([_curated_card()]),
        llm_fallback_runner=fallback_runner,
        llm_research_fallback_enabled=True,
    ).answer("Was ist PTFE?")

    view = response.knowledge_answer_view

    assert fallback_calls == []
    assert view.answer_available is True
    assert view.rag_miss is False
    assert view.source_type is SourceType.rag_verified
    assert view.validation_status is ValidationStatus.documented
    assert view.fallback_used is False


def test_rag_hit_does_not_call_enabled_fallback_after_curated_miss() -> None:
    fallback_calls: list[str] = []

    def rag_retriever(**kwargs):
        return [
            {
                "text": "FKM ist eine Fluorelastomer-Werkstofffamilie.",
                "metadata": {"source_id": "rag-fkm", "title": "FKM Grundlagen"},
            }
        ]

    def fallback_runner(**kwargs):
        fallback_calls.append(str(kwargs["query"]))
        return "Fallback should not run."

    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        rag_retriever=rag_retriever,
        llm_fallback_runner=fallback_runner,
        llm_research_fallback_enabled=True,
    ).answer("Was ist FKM?")

    view = response.knowledge_answer_view

    assert fallback_calls == []
    assert view.answer_available is True
    assert view.rag_miss is False
    assert view.source_type is SourceType.rag_verified
    assert view.validation_status is ValidationStatus.documented
    assert view.fallback_used is False


def test_rag_miss_with_fallback_disabled_returns_safe_miss() -> None:
    fallback_calls: list[str] = []

    def rag_retriever(**kwargs):
        return []

    def fallback_runner(**kwargs):
        fallback_calls.append(str(kwargs["query"]))
        return "Fallback should not run."

    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        rag_retriever=rag_retriever,
        llm_fallback_runner=fallback_runner,
        llm_research_fallback_enabled=False,
    ).answer("Was ist ein Spezialwerkstoff ohne Wissensbasis?")

    view = response.knowledge_answer_view

    assert fallback_calls == []
    assert view.rag_miss is True
    assert view.fallback_used is False
    assert view.answer_available is False
    assert view.source_type is SourceType.unknown
    assert view.validation_status is ValidationStatus.unknown


def test_enabled_fallback_without_provider_returns_safe_miss() -> None:
    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        llm_research_fallback_enabled=True,
    ).answer("Was ist ein Spezialwerkstoff ohne Wissensbasis?")

    view = response.knowledge_answer_view

    assert view.rag_miss is True
    assert view.fallback_allowed is True
    assert view.fallback_used is False
    assert view.answer_available is False
    assert view.missing_reason == "llm_research_fallback_provider_unavailable"


def test_enabled_fallback_returns_unvalidated_general_orientation_contract() -> None:
    calls: list[dict[str, object]] = []

    def fallback_runner(**kwargs):
        calls.append(dict(kwargs))
        return "Allgemeine Orientierung zu einer seltenen Dichtungsfrage."

    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        llm_fallback_runner=fallback_runner,
        llm_research_fallback_enabled=True,
    ).answer("Was ist eine seltene Dichtung?", tenant_id="tenant-1", user_id="user-1")

    view = response.knowledge_answer_view
    payload = view.as_dict()

    assert calls == [
        {
            "query": "Was ist eine seltene Dichtung?",
            "tenant_id": "tenant-1",
            "user_id": "user-1",
            "use_scope": "general_orientation_only",
        }
    ]
    assert view.answer_available is True
    assert view.rag_miss is True
    assert view.fallback_allowed is True
    assert view.fallback_used is True
    assert view.source_type is SourceType.llm_research_fallback
    assert view.validation_status is ValidationStatus.unvalidated
    assert view.user_visible_label == "LLM-Recherche - nicht validiert"
    assert "nicht validiert" in view.user_visible_label
    assert view.not_final_release is True
    assert view.use_scope == "general_orientation_only"
    assert payload["source_validation_badges"][0]["source_type"] == "llm_research_fallback"
    assert payload["source_validation_badges"][0]["validation_status"] == "unvalidated"
    assert payload["source_validation_badges"][0]["not_final_release"] is True
    assert "LLMResearchFallbackUsed" in view.event_names
    assert "KnowledgeRAGAnswerMissing" in view.event_names
    assert "KnowledgeAnswerGenerated" in view.event_names


def test_fallback_result_is_not_authoritative_by_source_validation_helpers() -> None:
    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        llm_fallback_runner=lambda **kwargs: "General orientation only.",
        llm_research_fallback_enabled=True,
    ).answer("Was ist eine seltene Dichtung?")

    view = response.knowledge_answer_view
    metadata = source_validation_metadata(
        source_type=view.source_type,
        validation_status=view.validation_status,
    )

    assert metadata.authoritative is False
    assert metadata.not_for_release_decisions is True
    assert is_unvalidated_source(view.source_type, view.validation_status)


def test_fallback_provider_exception_returns_safe_miss_without_leaking_details() -> None:
    def fallback_runner(**kwargs):
        raise RuntimeError("secret stack trace detail")

    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        llm_fallback_runner=fallback_runner,
        llm_research_fallback_enabled=True,
    ).answer("Was ist eine seltene Dichtung?")

    view = response.knowledge_answer_view
    payload = view.as_dict()

    assert view.rag_miss is True
    assert view.fallback_allowed is True
    assert view.fallback_used is False
    assert view.answer_available is False
    assert view.missing_reason == "llm_research_fallback_error"
    assert view.fallback_error == "fallback_provider_error"
    assert "secret stack trace detail" not in view.answer
    assert "secret stack trace detail" not in str(payload)


def test_unsafe_fallback_text_is_replaced_before_user_visible_answer() -> None:
    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        llm_fallback_runner=lambda **kwargs: (
            "Dieses Material ist geeignet und final freigegeben."
        ),
        llm_research_fallback_enabled=True,
    ).answer("Ist dieser Werkstoff geeignet?")

    view = response.knowledge_answer_view
    lowered = view.answer.lower()

    assert view.fallback_used is True
    assert "dieses material ist geeignet" not in lowered
    assert "final freigegeben" not in lowered
    assert view.source_type is SourceType.llm_research_fallback
    assert view.validation_status is ValidationStatus.unvalidated


def test_fallback_does_not_create_case_rfq_or_compliance_evidence_contract() -> None:
    response = KnowledgeService(
        factcard_store=_FactcardStore([]),
        llm_fallback_runner=lambda **kwargs: "General orientation only.",
        llm_research_fallback_enabled=True,
    ).answer("Was ist eine seltene Dichtung?")

    view = response.knowledge_answer_view
    payload = view.as_dict()

    forbidden_events = {
        "CaseCreated",
        "CaseFieldConfirmed",
        "RFQPreviewGenerated",
        "RFQConsentGranted",
        "ComplianceEvidenceCreated",
        "ManufacturerApprovalRecorded",
    }
    assert forbidden_events.isdisjoint(set(view.event_names))
    assert response.no_case_created is True
    assert "case_id" not in payload
    assert "case_revision" not in payload
    assert "artifact_type" not in payload
    assert "compliance_evidence" not in payload
