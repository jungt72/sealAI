from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.agent.runtime.output_guard import (
    FAST_PATH_GUARD_FALLBACK,
    check_fast_path_output,
)
from app.domain.source_validation import SourceType, ValidationStatus
from app.domain.pre_gate_classification import PreGateClassification
from app.services.knowledge import FactCardStore


log = logging.getLogger(__name__)

KNOWLEDGE_GENERAL_ORIENTATION_SCOPE = "general_technical_orientation_only"
KNOWLEDGE_FALLBACK_GENERAL_ORIENTATION_SCOPE = "general_orientation_only"
KNOWLEDGE_RAG_HIT_LABEL = "Kuratiertes/RAG-Wissen - dokumentiert"
KNOWLEDGE_RAG_MISS_LABEL = "Kein kuratierter/RAG-Treffer - keine technische Antwort"
KNOWLEDGE_LLM_FALLBACK_LABEL = "LLM-Recherche - nicht validiert"
KNOWLEDGE_MISS_ANSWER = (
    "Dazu habe ich in der kuratierten SeaLAI-Wissensbasis oder im angebundenen "
    "RAG-Kontext keinen ausreichend belastbaren Eintrag gefunden. Ich gebe deshalb "
    "keine technische Eignungs-, Kompatibilitaets- oder Freigabeaussage aus. "
    "Fuer einen konkreten Fall koennen wir die Betriebsdaten strukturiert aufnehmen "
    "und fuer eine Herstellerpruefung vorbereiten."
)


class KnowledgeRetriever(Protocol):
    def __call__(
        self,
        *,
        query: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
        max_results: int = 3,
    ) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    source_id: str
    title: str
    url: str | None = None
    source_type: SourceType = SourceType.rag_verified
    validation_status: ValidationStatus = ValidationStatus.documented
    rank: int | None = None
    evidence_ref: str | None = None
    excerpt: str | None = None
    confidence: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "source_type": self.source_type.value,
            "validation_status": self.validation_status.value,
            "rank": self.rank,
            "evidence_ref": self.evidence_ref,
            "excerpt": self.excerpt,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class SourceValidationBadgeView:
    source_type: SourceType
    validation_status: ValidationStatus
    user_visible_label: str
    use_scope: str = KNOWLEDGE_GENERAL_ORIENTATION_SCOPE
    not_final_release: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type.value,
            "validation_status": self.validation_status.value,
            "user_visible_label": self.user_visible_label,
            "use_scope": self.use_scope,
            "not_final_release": self.not_final_release,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerResult:
    answer: str
    answer_available: bool
    rag_lookup_attempted: bool
    rag_answer_found: bool
    rag_miss: bool
    sources: tuple[KnowledgeSource, ...] = field(default_factory=tuple)
    source_type: SourceType = SourceType.unknown
    validation_status: ValidationStatus = ValidationStatus.unknown
    use_scope: str = KNOWLEDGE_GENERAL_ORIENTATION_SCOPE
    not_final_release: bool = True
    fallback_allowed: bool = False
    fallback_used: bool = False
    fallback_error: str | None = None
    user_visible_label: str = KNOWLEDGE_RAG_MISS_LABEL
    missing_reason: str | None = None
    next_step: str | None = None
    event_names: tuple[str, ...] = field(default_factory=tuple)

    @property
    def source_validation_badges(self) -> tuple[SourceValidationBadgeView, ...]:
        if self.sources:
            return tuple(
                SourceValidationBadgeView(
                    source_type=source.source_type,
                    validation_status=source.validation_status,
                    user_visible_label=self.user_visible_label,
                    use_scope=self.use_scope,
                    not_final_release=self.not_final_release,
                )
                for source in self.sources
            )
        return (
            SourceValidationBadgeView(
                source_type=self.source_type,
                validation_status=self.validation_status,
                user_visible_label=self.user_visible_label,
                use_scope=self.use_scope,
                not_final_release=self.not_final_release,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "answer_available": self.answer_available,
            "rag_lookup_attempted": self.rag_lookup_attempted,
            "rag_answer_found": self.rag_answer_found,
            "rag_miss": self.rag_miss,
            "sources": [source.as_dict() for source in self.sources],
            "source_type": self.source_type.value,
            "validation_status": self.validation_status.value,
            "use_scope": self.use_scope,
            "not_final_release": self.not_final_release,
            "fallback_allowed": self.fallback_allowed,
            "fallback_used": self.fallback_used,
            "fallback_error": self.fallback_error,
            "user_visible_label": self.user_visible_label,
            "missing_reason": self.missing_reason,
            "next_step": self.next_step,
            "event_names": list(self.event_names),
            "source_validation_badges": [
                badge.as_dict() for badge in self.source_validation_badges
            ],
        }


@dataclass(frozen=True, slots=True)
class KnowledgeResponse:
    content: str
    source_classification: PreGateClassification = PreGateClassification.KNOWLEDGE_QUERY
    output_class: str = "conversational_answer"
    citations: tuple[KnowledgeSource, ...] = field(default_factory=tuple)
    no_case_created: bool = True
    answer_result: KnowledgeAnswerResult | None = None

    @property
    def knowledge_answer_view(self) -> KnowledgeAnswerResult:
        if self.answer_result is not None:
            return self.answer_result
        return _miss_result(self.content)


class KnowledgeService:
    """Dedicated non-case knowledge path backed by the curated FactCard store."""

    def __init__(
        self,
        *,
        factcard_store: FactCardStore | None = None,
        rag_retriever: KnowledgeRetriever | None = None,
        llm_fallback_runner: Callable[..., Any] | None = None,
        llm_research_fallback_enabled: bool | None = None,
    ) -> None:
        self._store = factcard_store or FactCardStore.get_instance()
        self._rag_retriever = rag_retriever
        self._llm_fallback_runner = llm_fallback_runner
        self._llm_research_fallback_enabled = (
            _settings_fallback_enabled()
            if llm_research_fallback_enabled is None
            else bool(llm_research_fallback_enabled)
        )

    def answer(
        self,
        user_input: str,
        *,
        max_cards: int = 3,
        source_classification: PreGateClassification = PreGateClassification.KNOWLEDGE_QUERY,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> KnowledgeResponse:
        deterministic_answer = _deterministic_domain_answer(user_input)
        if deterministic_answer is not None:
            return KnowledgeResponse(
                source_classification=source_classification,
                content=deterministic_answer.answer,
                answer_result=deterministic_answer,
            )

        cards = self._store.match_query_to_cards((user_input or "").lower())[:max_cards]
        if not cards and self._rag_retriever is not None:
            rag_hits = self._rag_retriever(
                query=user_input,
                tenant_id=tenant_id,
                user_id=user_id,
                max_results=max_cards,
            )
            if rag_hits:
                return self._response_from_rag_hits(
                    rag_hits,
                    source_classification=source_classification,
                )

        if not cards:
            result = self._fallback_or_miss(
                user_input,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            return KnowledgeResponse(
                source_classification=source_classification,
                content=result.answer,
                answer_result=result,
            )

        lines = ["Aus der kuratierten SeaLAI-Wissensbasis:"]
        sources: list[KnowledgeSource] = []
        seen_sources: set[str] = set()
        for card in cards:
            card_id = str(card.get("id") or "knowledge-card")
            topic = str(card.get("topic") or "Wissenseintrag")
            prop = str(card.get("property") or "").strip()
            value = str(card.get("value") or "").strip()
            units = str(card.get("units") or "").strip()
            source_id = str(card.get("source") or "").strip()
            source_marker = f" [{source_id}]" if source_id else ""
            label = f"{topic}/{prop}" if prop else topic
            rendered_value = f"{value} {units}".strip()
            lines.append(f"- {label}: {rendered_value} ({card_id}){source_marker}")
            if source_id and source_id not in seen_sources:
                source = self._source_for(source_id)
                if source is not None:
                    sources.append(source)
                    seen_sources.add(source_id)

        if sources:
            lines.append(
                "Quellen: "
                + "; ".join(f"{source.source_id}: {source.title}" for source in sources)
            )
        lines.append(
            "Das ist eine Wissensantwort, kein angelegter technischer Fall "
            "und keine Herstellerfreigabe. Fuer eine konkrete Anwendung ist "
            "Herstellerpruefung erforderlich."
        )
        answer = "\n".join(lines)
        result = _hit_result(answer, tuple(sources))
        return KnowledgeResponse(
            content=answer,
            source_classification=source_classification,
            citations=tuple(sources),
            answer_result=result,
        )

    def _response_from_rag_hits(
        self,
        hits: list[dict[str, Any]],
        *,
        source_classification: PreGateClassification,
    ) -> KnowledgeResponse:
        sources: list[KnowledgeSource] = []
        lines = ["Aus dem kuratierten/RAG-Wissenskontext:"]
        for index, hit in enumerate(hits, start=1):
            text = _clean_excerpt(hit.get("text") or hit.get("content") or "")
            if text:
                lines.append(f"- {text}")
            metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
            source_id = str(
                metadata.get("source_id")
                or metadata.get("document_id")
                or metadata.get("doc_id")
                or hit.get("source")
                or f"rag-hit-{index}"
            )
            title = str(
                metadata.get("title")
                or metadata.get("filename")
                or hit.get("title")
                or source_id
            )
            confidence = _float_or_none(
                hit.get("fused_score") or hit.get("vector_score") or hit.get("score")
            )
            sources.append(
                KnowledgeSource(
                    source_id=source_id,
                    title=title,
                    url=metadata.get("source_url") or metadata.get("url"),
                    source_type=SourceType.rag_verified,
                    validation_status=ValidationStatus.documented,
                    evidence_ref=str(metadata.get("chunk_id") or "")
                    or None,
                    excerpt=text or None,
                    confidence=confidence,
                    rank=index,
                )
            )
        lines.append(
            "Das ist eine allgemeine technische Orientierung aus dokumentierten "
            "Quellen, keine konkrete Eignungs-, Kompatibilitaets- oder "
            "Herstellerfreigabe."
        )
        answer = "\n".join(lines)
        result = _hit_result(answer, tuple(sources))
        return KnowledgeResponse(
            content=answer,
            source_classification=source_classification,
            citations=tuple(sources),
            answer_result=result,
        )

    def _source_for(self, source_id: str) -> KnowledgeSource | None:
        source_map: dict[str, Any] = getattr(self._store, "_sources", {})
        source = source_map.get(source_id)
        if not isinstance(source, dict):
            return None
        return KnowledgeSource(
            source_id=source_id,
            title=str(source.get("title") or source_id),
            url=source.get("url"),
            source_type=SourceType.rag_verified,
            validation_status=ValidationStatus.documented,
            rank=source.get("rank"),
        )

    def _fallback_or_miss(
        self,
        user_input: str,
        *,
        tenant_id: str | None,
        user_id: str | None,
    ) -> KnowledgeAnswerResult:
        if not self._llm_research_fallback_enabled:
            return _miss_result(KNOWLEDGE_MISS_ANSWER)
        if self._llm_fallback_runner is None:
            return _miss_result(
                KNOWLEDGE_MISS_ANSWER,
                fallback_allowed=True,
                missing_reason="llm_research_fallback_provider_unavailable",
            )
        try:
            raw_result = self._llm_fallback_runner(
                query=user_input,
                tenant_id=tenant_id,
                user_id=user_id,
                use_scope=KNOWLEDGE_FALLBACK_GENERAL_ORIENTATION_SCOPE,
            )
        except Exception:
            log.warning(
                "Knowledge LLM research fallback failed; returning safe RAG miss."
            )
            return _miss_result(
                KNOWLEDGE_MISS_ANSWER,
                fallback_allowed=True,
                missing_reason="llm_research_fallback_error",
                fallback_error="fallback_provider_error",
            )

        fallback_text = _fallback_text_from_provider_result(raw_result)
        if not fallback_text:
            return _miss_result(
                KNOWLEDGE_MISS_ANSWER,
                fallback_allowed=True,
                missing_reason="llm_research_fallback_empty",
            )

        safe, _category = check_fast_path_output(fallback_text)
        if not safe:
            fallback_text = FAST_PATH_GUARD_FALLBACK

        return _fallback_result(fallback_text)


def _hit_result(answer: str, sources: tuple[KnowledgeSource, ...]) -> KnowledgeAnswerResult:
    return KnowledgeAnswerResult(
        answer=answer,
        answer_available=True,
        rag_lookup_attempted=True,
        rag_answer_found=True,
        rag_miss=False,
        sources=sources,
        source_type=SourceType.rag_verified,
        validation_status=ValidationStatus.documented,
        user_visible_label=KNOWLEDGE_RAG_HIT_LABEL,
        next_step=(
            "Fuer eine konkrete Anwendung Betriebsdaten bereitstellen und als "
            "governed Case fuer Herstellerpruefung qualifizieren."
        ),
        event_names=(
            "KnowledgeQuestionReceived",
            "KnowledgeRAGLookupRequested",
            "KnowledgeRAGAnswerFound",
            "SourceValidationStatusAssigned",
            "KnowledgeAnswerGenerated",
        ),
    )


def _deterministic_domain_answer(user_input: str) -> KnowledgeAnswerResult | None:
    """Return safe built-in orientation for high-frequency glossary questions.

    The PTFE fact-card store is intentionally narrow. For basic sealing terms,
    forcing a weak fact-card match can produce irrelevant answers. These
    glossary answers are general orientation only: they do not create case
    truth, compatibility claims, or manufacturer approval.
    """
    text = str(user_input or "").casefold()
    asks_explanation = any(
        token in text
        for token in (
            "was ist",
            "was sind",
            "erklär",
            "erklaer",
            "bedeutet",
            "wie funktioniert",
        )
    )
    rwdr_terms = (
        "radialwellendichtring",
        "wellendichtring",
        "rwdr",
        "simmerring",
    )
    if asks_explanation and any(term in text for term in rwdr_terms):
        answer = "\n".join(
            [
                "Ein Radialwellendichtring, kurz RWDR, dichtet typischerweise eine rotierende Welle gegen ein Gehaeuse ab.",
                "",
                "Typisch ist eine flexible Dichtlippe, die auf der Welle oder einer Huelse laeuft. Entscheidend fuer die Praxis sind Medium, Temperatur, Druck, Drehzahl, Wellendurchmesser, Oberflaeche, Schmierung und Einbauraum.",
                "",
                "Als allgemeine Orientierung: RWDR sind oft kompakte Loesungen fuer rotierende Wellen. Bei hoeherem Druck, trockener Laufstelle, abrasiven Medien, anspruchsvoller Chemie oder Pumpenanwendungen muss der konkrete Aufbau genauer geprueft werden.",
                "",
                "Das ist eine allgemeine Wissensantwort, keine konkrete Auslegung und keine Herstellerfreigabe. Wenn du moechtest, koennen wir daraus direkt einen konkreten Dichtungsfall aufbauen.",
            ]
        )
        return KnowledgeAnswerResult(
            answer=answer,
            answer_available=True,
            rag_lookup_attempted=True,
            rag_answer_found=False,
            rag_miss=True,
            source_type=SourceType.system_derived,
            validation_status=ValidationStatus.unvalidated,
            use_scope=KNOWLEDGE_FALLBACK_GENERAL_ORIENTATION_SCOPE,
            not_final_release=True,
            fallback_allowed=False,
            fallback_used=False,
            user_visible_label="SeaLAI-Grundwissen - allgemeine Orientierung",
            missing_reason="domain_glossary_answer_without_rag_hit",
            next_step=(
                "Bei konkreter Anwendung Medium, Temperatur, Druck, Drehzahl "
                "und Wellendurchmesser als governed Case aufnehmen."
            ),
            event_names=(
                "KnowledgeQuestionReceived",
                "KnowledgeRAGLookupRequested",
                "KnowledgeRAGAnswerMissing",
                "SourceValidationStatusAssigned",
                "KnowledgeAnswerGenerated",
            ),
        )
    return None


def _miss_result(
    answer: str,
    *,
    fallback_allowed: bool = False,
    missing_reason: str = "no_curated_or_rag_answer_available",
    fallback_error: str | None = None,
) -> KnowledgeAnswerResult:
    return KnowledgeAnswerResult(
        answer=answer,
        answer_available=False,
        rag_lookup_attempted=True,
        rag_answer_found=False,
        rag_miss=True,
        source_type=SourceType.unknown,
        validation_status=ValidationStatus.unknown,
        fallback_allowed=fallback_allowed,
        fallback_error=fallback_error,
        user_visible_label=KNOWLEDGE_RAG_MISS_LABEL,
        missing_reason=missing_reason,
        next_step=(
            "Keine technische Antwort erfinden; konkrete Anwendungsdaten aufnehmen "
            "oder spaeter nicht validierte LLM-Recherche explizit aktivieren."
        ),
        event_names=(
            "KnowledgeQuestionReceived",
            "KnowledgeRAGLookupRequested",
            "KnowledgeRAGAnswerMissing",
            "SourceValidationStatusAssigned",
            "KnowledgeAnswerGenerated",
        ),
    )


def _fallback_result(provider_answer: str) -> KnowledgeAnswerResult:
    answer = "\n".join(
        [
            f"Information source: {KNOWLEDGE_LLM_FALLBACK_LABEL}.",
            "Validation status: Not validated. Use: general orientation only.",
            str(provider_answer).strip(),
            (
                "Fuer konkrete Betriebsdaten, Kompatibilitaet, Compliance, RFQ "
                "oder Herstellerfreigabe ist eine verifizierte Quelle oder "
                "Herstellerpruefung erforderlich."
            ),
        ]
    )
    return KnowledgeAnswerResult(
        answer=answer,
        answer_available=True,
        rag_lookup_attempted=True,
        rag_answer_found=False,
        rag_miss=True,
        source_type=SourceType.llm_research_fallback,
        validation_status=ValidationStatus.unvalidated,
        use_scope=KNOWLEDGE_FALLBACK_GENERAL_ORIENTATION_SCOPE,
        not_final_release=True,
        fallback_allowed=True,
        fallback_used=True,
        user_visible_label=KNOWLEDGE_LLM_FALLBACK_LABEL,
        missing_reason="curated_or_rag_miss_fallback_used",
        next_step=(
            "Fuer einen konkreten Fall RAG/kuratierten Nachweis, Upload-Evidence "
            "oder Herstellerpruefung heranziehen; diese LLM-Recherche nicht als "
            "Case Truth, RFQ Truth, Compliance-Nachweis oder Freigabe verwenden."
        ),
        event_names=(
            "KnowledgeQuestionReceived",
            "KnowledgeRAGLookupRequested",
            "KnowledgeRAGAnswerMissing",
            "LLMResearchFallbackUsed",
            "SourceValidationStatusAssigned",
            "KnowledgeAnswerGenerated",
        ),
    )


def _fallback_text_from_provider_result(raw_result: Any) -> str:
    if isinstance(raw_result, str):
        return raw_result.strip()
    if isinstance(raw_result, dict):
        for key in ("answer", "content", "text"):
            value = raw_result.get(key)
            if value:
                return str(value).strip()
    value = getattr(raw_result, "answer", None)
    if value:
        return str(value).strip()
    value = getattr(raw_result, "content", None)
    if value:
        return str(value).strip()
    return ""


def _settings_fallback_enabled() -> bool:
    try:
        from app.core.config import settings  # noqa: PLC0415

        return bool(getattr(settings, "knowledge_llm_research_fallback_enabled", False))
    except Exception:
        return False


def _clean_excerpt(value: Any, *, limit: int = 420) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
