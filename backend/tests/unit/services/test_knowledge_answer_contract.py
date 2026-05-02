from __future__ import annotations

from app.domain.source_validation import SourceType, ValidationStatus
from app.services.knowledge_service import (
    KNOWLEDGE_GENERAL_ORIENTATION_SCOPE,
    KnowledgeService,
)


class _FactcardStore:
    _sources = {
        "src-ptfe": {
            "title": "PTFE handbook excerpt",
            "url": "https://example.invalid/ptfe",
            "rank": 1,
        }
    }

    def __init__(self, cards: list[dict[str, object]]) -> None:
        self._cards = cards

    def match_query_to_cards(self, query_lower: str) -> list[dict[str, object]]:
        return list(self._cards)


def _ptfe_card() -> dict[str, object]:
    return {
        "id": "PTFE-F-001",
        "topic": "PTFE",
        "property": "temperature_window",
        "value": "-200 bis 260",
        "units": "C",
        "source": "src-ptfe",
    }


def test_curated_factcard_hit_returns_machine_readable_answer_contract() -> None:
    response = KnowledgeService(factcard_store=_FactcardStore([_ptfe_card()])).answer(
        "Was ist PTFE?"
    )

    view = response.knowledge_answer_view

    assert response.no_case_created is True
    assert response.content == view.answer
    assert view.answer_available is True
    assert view.rag_lookup_attempted is True
    assert view.rag_answer_found is True
    assert view.rag_miss is False
    assert view.source_type is SourceType.rag_verified
    assert view.validation_status is ValidationStatus.documented
    assert view.use_scope == KNOWLEDGE_GENERAL_ORIENTATION_SCOPE
    assert view.not_final_release is True
    assert view.fallback_allowed is False
    assert view.fallback_used is False
    assert view.sources[0].source_type is SourceType.rag_verified
    assert view.sources[0].validation_status is ValidationStatus.documented
    assert view.knowledge_evidence
    assert view.knowledge_evidence[0].source_type == "fact_card"
    assert view.knowledge_evidence[0].title == "PTFE: Temperaturbereich"
    assert "-200 bis 260 C" in view.knowledge_evidence[0].content
    evidence_payload = str(view.knowledge_evidence[0].as_dict())
    assert "PTFE-F-001" not in evidence_payload
    assert "src-ptfe" not in evidence_payload
    assert "KnowledgeQuestionReceived" in view.event_names
    assert "KnowledgeRAGAnswerFound" in view.event_names
    assert "SourceValidationStatusAssigned" in view.event_names


def test_source_validation_badge_view_is_serializable_with_primitives() -> None:
    response = KnowledgeService(factcard_store=_FactcardStore([_ptfe_card()])).answer(
        "PTFE Temperatur"
    )

    payload = response.knowledge_answer_view.as_dict()

    assert payload["source_type"] == SourceType.rag_verified.value
    assert payload["validation_status"] == ValidationStatus.documented.value
    assert payload["source_validation_badges"][0]["source_type"] == "rag_verified"
    assert payload["source_validation_badges"][0]["validation_status"] == "documented"
    assert payload["source_validation_badges"][0]["not_final_release"] is True
    assert payload["knowledge_evidence"][0]["source_type"] == "fact_card"
    assert "PTFE" in payload["knowledge_evidence"][0]["content"]


def test_curated_hit_is_general_orientation_not_case_specific_release() -> None:
    response = KnowledgeService(factcard_store=_FactcardStore([_ptfe_card()])).answer(
        "Ist PTFE fuer meinen konkreten Fall geeignet?"
    )

    view = response.knowledge_answer_view

    assert view.use_scope == "general_technical_orientation_only"
    assert view.not_final_release is True
    assert "allgemeine Orientierung" in response.content
    assert "keine konkrete Auswahl" in response.content
    assert "keine Herstellerfreigabe" in response.content


def test_rag_miss_returns_safe_contract_without_technical_suitability_claim() -> None:
    response = KnowledgeService(factcard_store=_FactcardStore([])).answer(
        "Ist unobtainium fuer Dampf geeignet?"
    )

    view = response.knowledge_answer_view

    assert view.answer_available is False
    assert view.rag_lookup_attempted is True
    assert view.rag_answer_found is False
    assert view.rag_miss is True
    assert view.source_type is SourceType.unknown
    assert view.validation_status is ValidationStatus.unknown
    assert view.fallback_allowed is False
    assert view.fallback_used is False
    assert view.missing_reason == "no_curated_or_rag_answer_available"
    assert "KnowledgeRAGAnswerMissing" in view.event_names
    lowered = view.answer.lower()
    assert " ist geeignet" not in lowered
    assert "kompatibilitaet ist bestaetigt" not in lowered
    assert "freigegeben fuer" not in lowered
