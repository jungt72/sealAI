from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from app.agent.runtime.output_guard import (
    FAST_PATH_GUARD_FALLBACK,
    check_fast_path_output,
)
from app.domain.source_validation import SourceType, ValidationStatus
from app.domain.pre_gate_classification import PreGateClassification
from app.services.knowledge import FactCardStore
from app.services.knowledge.material_comparison import (
    build_material_comparison_answer,
    build_material_risk_comparison_answer,
    humanize_german_technical_text,
)


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
    ) -> list[dict[str, Any]]: ...


KnowledgeEvidenceSourceType = Literal[
    "fact_card",
    "rag",
    "deterministic",
    "fallback",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class KnowledgeEvidence:
    source_type: KnowledgeEvidenceSourceType
    content: str
    title: str | None = None
    source_name: str | None = None
    confidence: float | None = None
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "title": self.title,
            "content": self.content,
            "source_name": self.source_name,
            "confidence": self.confidence,
            "note": self.note,
        }


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
    knowledge_evidence: tuple[KnowledgeEvidence, ...] = field(default_factory=tuple)

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
            "knowledge_evidence": [
                evidence.as_dict() for evidence in self.knowledge_evidence
            ],
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
    answer_markdown: str | None = None
    knowledge_debug: dict[str, Any] | None = None
    answer_trace: dict[str, Any] | None = None

    @property
    def knowledge_answer_view(self) -> KnowledgeAnswerResult:
        if self.answer_result is not None:
            return self.answer_result
        return _miss_result(self.content)

    @property
    def knowledge_evidence(self) -> tuple[KnowledgeEvidence, ...]:
        return self.knowledge_answer_view.knowledge_evidence


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

        cards = (
            self._store.match_query_to_cards((user_input or "").lower())[:max_cards]
            if _should_query_ptfe_factcards(user_input)
            else []
        )
        if not cards and self._rag_retriever is not None:
            rag_hits = self._rag_retriever(
                query=user_input,
                tenant_id=tenant_id,
                user_id=user_id,
                max_results=max_cards,
            )
            rag_hits = _filter_rag_hits_for_query(user_input, rag_hits)
            if rag_hits:
                return self._response_from_rag_hits(
                    rag_hits,
                    user_input=user_input,
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

        lines = [
            "Ich habe dazu kuratierte SeaLAI-Hinweise gefunden. Kurz eingeordnet:",
        ]
        sources: list[KnowledgeSource] = []
        evidence: list[KnowledgeEvidence] = []
        seen_sources: set[str] = set()
        for card in cards:
            topic = str(card.get("topic") or "Wissenseintrag")
            prop = str(card.get("property") or "").strip()
            value = str(card.get("value") or "").strip()
            units = str(card.get("units") or "").strip()
            source_id = str(card.get("source") or "").strip()
            label = _human_fact_label(topic, prop)
            rendered_value = f"{value} {units}".strip()
            if rendered_value:
                lines.append(f"- {label}: {rendered_value}.")
                evidence.append(
                    _knowledge_evidence(
                        source_type="fact_card",
                        title=label,
                        content=f"{label}: {rendered_value}.",
                        source_name=_source_title(self._store, source_id),
                        note="curated_fact_card",
                    )
                )
            if source_id and source_id not in seen_sources:
                source = self._source_for(source_id)
                if source is not None:
                    sources.append(source)
                    seen_sources.add(source_id)

        if sources:
            lines.append(
                "Quelle: "
                + "; ".join(f"{source.source_id}: {source.title}" for source in sources)
            )
        lines.append(
            "Das ist allgemeine Orientierung, keine konkrete Auswahl und keine "
            "Herstellerfreigabe. Fuer deinen konkreten Fall brauchen wir Medium, "
            "Temperatur, Druck, Bewegung und Einbausituation."
        )
        answer = "\n".join(lines)
        result = _hit_result(answer, tuple(sources), knowledge_evidence=tuple(evidence))
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
        user_input: str,
        source_classification: PreGateClassification,
    ) -> KnowledgeResponse:
        sources: list[KnowledgeSource] = []
        evidence: list[KnowledgeEvidence] = []
        snippets: list[str] = []
        for index, hit in enumerate(hits, start=1):
            text = _clean_excerpt(hit.get("text") or hit.get("content") or "")
            if text:
                snippets.append(text)
            metadata = (
                hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
            )
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
            if text:
                evidence.append(
                    _knowledge_evidence(
                        source_type="rag",
                        title=title,
                        content=text,
                        source_name=title,
                        confidence=confidence,
                        note="documented_rag_snippet",
                    )
                )
            sources.append(
                KnowledgeSource(
                    source_id=source_id,
                    title=title,
                    url=metadata.get("source_url") or metadata.get("url"),
                    source_type=SourceType.rag_verified,
                    validation_status=ValidationStatus.documented,
                    evidence_ref=str(metadata.get("chunk_id") or "") or None,
                    excerpt=text or None,
                    confidence=confidence,
                    rank=index,
                )
            )
        answer = _compose_user_facing_rag_answer(
            user_input=user_input,
            snippets=snippets,
            sources=tuple(sources),
        )
        result = _hit_result(answer, tuple(sources), knowledge_evidence=tuple(evidence))
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
        term_orientation = _unknown_term_orientation_result(user_input)
        if term_orientation is not None:
            return term_orientation
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


def _hit_result(
    answer: str,
    sources: tuple[KnowledgeSource, ...],
    *,
    knowledge_evidence: tuple[KnowledgeEvidence, ...] = (),
) -> KnowledgeAnswerResult:
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
        knowledge_evidence=knowledge_evidence,
        event_names=(
            "KnowledgeQuestionReceived",
            "KnowledgeRAGLookupRequested",
            "KnowledgeRAGAnswerFound",
            "SourceValidationStatusAssigned",
            "KnowledgeAnswerGenerated",
        ),
    )


def _compose_user_facing_rag_answer(
    *,
    user_input: str,
    snippets: list[str],
    sources: tuple[KnowledgeSource, ...],
) -> str:
    material = _detect_material_focus(user_input, snippets)
    if material == "NBR":
        answer = "\n".join(
            [
                "NBR steht für Acrylnitril-Butadien-Kautschuk, häufig auch "
                "Nitrilkautschuk genannt. In der Dichtungstechnik ist NBR ein "
                "verbreiteter Elastomerwerkstoff für O-Ringe, Formteile, "
                "Radialwellendichtringe und klassische Maschinenbau-Dichtstellen.",
                "",
                "Typische Orientierung:",
                "- NBR wird oft im Umfeld von mineralölbasierten Medien, "
                "Fetten und vielen Hydraulikflüssigkeiten betrachtet.",
                "- Kritisch können je nach Mischung Ozon, UV, Witterung, viele "
                "polare Lösemittel, Aromaten, Ketone, Heißwasser, Dampf und "
                "starke Oxidationsmittel sein.",
                "",
                "Für eine konkrete Eignung brauche ich Medium, Temperatur und "
                "Betriebsart. Das ist technische Orientierung, keine technische "
                "Freigabe.",
            ]
        )
        return humanize_german_technical_text(answer)

    if material == "FKM":
        answer = "\n".join(
            [
                "FKM ist eine Fluorelastomer-Werkstofffamilie. In Dichtungen "
                "wird FKM häufig dort betrachtet, wo Temperatur, Alterung, "
                "Ozon/Witterung oder öl- und kraftstoffnahe Medien eine Rolle "
                "spielen.",
                "",
                "Wichtig ist: FKM ist keine einzelne Universalrezeptur. "
                "Tieftemperatur, Dampf, Heißwasser, polare Medien, Amine, "
                "Bremsflüssigkeiten und konkrete Additive müssen compound- und "
                "herstellerbezogen geprüft werden.",
                "",
                "Für eine konkrete Einschätzung brauche ich Medium, "
                "Temperaturfenster, Druck, Bewegung und geforderte Nachweise. "
                "Bis dahin ist das technische Orientierung aus der "
                "dokumentierten Wissensbasis, keine Freigabe und keine "
                "Kompatibilitätszusage.",
            ]
        )
        return humanize_german_technical_text(answer)

    if material == "PTFE":
        answer = "\n".join(
            [
                "PTFE ist ein Fluorpolymer und wird in Dichtungsanwendungen "
                "oft wegen niedriger Reibung, breiter chemischer Orientierung "
                "und hoher Temperaturstabilität betrachtet.",
                "",
                "Gleichzeitig verhält sich PTFE nicht wie ein elastischer "
                "Gummiwerkstoff: Rückstellung, Kaltfluss, Vorspannung, "
                "Füllstoffe, Gegenlauffläche und Einbauraum sind für die "
                "Dichtfunktion entscheidend.",
                "",
                "Für eine konkrete Einschätzung brauche ich Medium, "
                "Temperaturfenster, Druck, Bewegung, Geometrie und ob ein "
                "gefülltes PTFE oder ein Verbundaufbau vorgesehen ist. Bis "
                "dahin ist das technische Orientierung aus der dokumentierten "
                "Wissensbasis, keine Freigabe und keine "
                "Kompatibilitätszusage.",
            ]
        )
        return humanize_german_technical_text(answer)

    points = _user_facing_snippet_points(snippets)
    if points:
        lines = ["Kurz gesagt:"]
        lines.extend(f"- {point}" for point in points[:4])
        lines.extend(
            [
                "",
                "Das ist technische Orientierung aus der dokumentierten "
                "Wissensbasis, keine konkrete Eignungs-, Kompatibilitäts- "
                "oder Herstellerfreigabe.",
            ]
        )
        return humanize_german_technical_text("\n".join(lines))

    source_note = (
        f"{len(sources)} dokumentierten Treffern"
        if len(sources) != 1
        else "einem dokumentierten Treffer"
    )
    answer = (
        "Ich habe dazu Material in der kuratierten Wissensbasis gefunden, "
        f"aber keinen ausreichend sauberen Antwortauszug aus {source_note}. "
        "Ich gebe deshalb keine technische Aussage aus Rohzitaten aus. Für "
        "eine konkrete Bewertung sollten wir Medium, Temperatur, Druck, "
        "Bewegung und Dichtstelle strukturiert aufnehmen."
    )
    return humanize_german_technical_text(answer)


def _detect_material_focus(user_input: str, snippets: list[str]) -> str | None:
    haystack = f"{user_input} {' '.join(snippets[:3])}".casefold()
    if (
        re.search(r"\bnbr\b", haystack)
        or "nitril" in haystack
        or "acrylnitril" in haystack
    ):
        return "NBR"
    if (
        re.search(r"\bfkm\b|\bfpm\b", haystack)
        or "fluorkautschuk" in haystack
        or "fluorelastomer" in haystack
    ):
        return "FKM"
    if re.search(r"\bptfe\b", haystack) or "polytetrafluor" in haystack:
        return "PTFE"
    return None


def _user_facing_snippet_points(snippets: list[str]) -> list[str]:
    points: list[str] = []
    seen: set[str] = set()
    for snippet in snippets:
        for sentence in re.split(r"(?<=[.!?])\s+", snippet):
            candidate = sentence.strip(" -•\t")
            if not candidate or _contains_raw_rag_artifact(candidate):
                continue
            if len(candidate) < 32 or len(candidate) > 240:
                continue
            key = candidate.casefold()
            if key in seen:
                continue
            seen.add(key)
            points.append(candidate)
            if len(points) >= 4:
                return points
    return points


def _contains_raw_rag_artifact(text: str) -> bool:
    lowered = str(text or "").casefold()
    return any(
        marker in lowered
        for marker in (
            "[document:",
            "[dokument:",
            "assumptions_and_scope",
            "rfq-feld-mapping",
            "rfq feld mapping",
            "aus dem kuratierten/rag",
            "source_type",
            "validation_status",
        )
    ) or bool(re.search(r"\[q\d+\]", lowered))


def _deterministic_domain_answer(user_input: str) -> KnowledgeAnswerResult | None:
    """Return safe built-in orientation for high-frequency glossary questions.

    The PTFE fact-card store is intentionally narrow. For basic sealing terms,
    forcing a weak fact-card match can produce irrelevant answers. These
    glossary answers are general orientation only: they do not create case
    truth, compatibility claims, or manufacturer approval.
    """
    text = str(user_input or "").casefold()
    asks_pfas = "pfas" in text or (
        any(token in text for token in ("reach", "echa", "fluor", "fluoriert"))
        and any(token in text for token in ("dichtung", "dichtungen", "werkstoff"))
    )
    if asks_pfas:
        answer = "\n".join(
            [
                "PFAS ist bei Dichtungen vor allem relevant, weil viele fluorierte Dichtungswerkstoffe in diese Diskussion fallen koennen.",
                "",
                "Dazu gehoeren je nach genauer Definition und Regulierung zum Beispiel FKM, FFKM, PTFE, Fluorelastomere und Fluorpolymere. Technisch koennen diese Werkstoffe fuer Chemie-, Temperatur- oder Reibungsthemen wichtig sein. Gleichzeitig koennen PFAS-Regulierung, Lieferantenbewertungen und Dokumentationspflichten die Werkstoffauswahl, Verfuegbarkeit und Freigabedokumente beeinflussen.",
                "",
                "Wichtig: Das ist eine technische Orientierung, keine verbindliche rechtliche Bewertung. Ohne Live-Quelle nenne ich keine konkreten Fristen oder Rechtsstaende. Fuer verbindliche Entscheidungen sollten aktuelle ECHA-/REACH-Informationen, Lieferantenerklaerungen und projektspezifische Compliance-Anforderungen geprueft werden.",
                "",
                "Fuer einen konkreten Dichtungsfall sollten Medium, Temperatur, Druck, Bewegung, Lebensmittel-/Pharma-/ATEX-Bezug und geforderte Nachweise sauber erfasst werden.",
            ]
        )
        answer = humanize_german_technical_text(answer)
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
            missing_reason="domain_pfas_orientation_without_live_regulatory_source",
            next_step=(
                "Fuer bindende Entscheidungen aktuelle ECHA-/REACH-Quellen, "
                "Lieferantenerklaerungen und projektspezifische Anforderungen pruefen."
            ),
            knowledge_evidence=(
                _knowledge_evidence(
                    source_type="deterministic",
                    title="PFAS in Dichtungswerkstoffen",
                    content=answer,
                    note="system_derived_domain_answer_currentness_limited",
                ),
            ),
            event_names=(
                "KnowledgeQuestionReceived",
                "KnowledgeRAGLookupRequested",
                "KnowledgeRAGAnswerMissing",
                "SourceValidationStatusAssigned",
                "KnowledgeAnswerGenerated",
            ),
        )

    asks_epdm_hydraulic_oil = "epdm" in text and any(
        token in text
        for token in (
            "hydrauliköl",
            "hydraulikoel",
            "hlp46",
            "hlp 46",
            "mineralöl",
            "mineraloel",
        )
    )
    if asks_epdm_hydraulic_oil:
        answer = "\n".join(
            [
                "Kurz gesagt: Bei EPDM und mineralölbasiertem Hydrauliköl wie HLP46 wäre ich sehr vorsichtig.",
                "",
                "EPDM wird typischerweise eher bei Wasser, Heißwasser, Dampf, Glykolen und einigen polaren Medien betrachtet. Mineralölbasierte Hydrauliköle können bei EPDM zu Quellung, Erweichung oder Eigenschaftsverlust führen. Aus 80 °C und 10 bar allein würde ich deshalb keine Eignung ableiten.",
                "",
                "Wichtig ist die Medienfamilie: Ist es wirklich ein HLP/HVLP auf Mineralölbasis oder ein wasser- beziehungsweise esterbasierter Hydraulikflüssigkeitstyp? Danach zählen Datenblatt, Dichtungsart, Bewegung, Temperaturprofil, Druck direkt an der Dichtstelle und Herstellerdaten.",
                "",
                "Das ist eine Einordnung für die Anfragebasis, keine Freigabe und keine finale Werkstoffauswahl.",
            ]
        )
        answer = humanize_german_technical_text(answer)
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
            user_visible_label="SeaLAI-Werkstoffwissen - allgemeine Orientierung",
            missing_reason="domain_epdm_hydraulic_oil_orientation_without_rag_hit",
            next_step=(
                "Mediumdatenblatt, Dichtungstyp, Temperaturprofil, Bewegung und "
                "Druck direkt an der Dichtstelle als governed Case aufnehmen."
            ),
            knowledge_evidence=(
                _knowledge_evidence(
                    source_type="deterministic",
                    title="EPDM und mineralölbasierte Hydrauliköle",
                    content=answer,
                    note="system_derived_epdm_hydraulic_oil_orientation",
                ),
            ),
            event_names=(
                "KnowledgeQuestionReceived",
                "KnowledgeRAGLookupRequested",
                "KnowledgeRAGAnswerMissing",
                "SourceValidationStatusAssigned",
                "KnowledgeAnswerGenerated",
            ),
        )

    asks_saltwater = any(
        token in text
        for token in (
            "salzwasser",
            "meerwasser",
            "seewasser",
            "salt water",
            "saltwater",
            "seawater",
            "chlorid",
            "chloride",
            "sole",
        )
    )
    if asks_saltwater:
        answer = "\n".join(
            [
                "Bei Salzwasser sind an Dichtstellen vor allem Chlorid-Korrosion, Ablagerungen und wechselnde Benetzung kritisch.",
                "",
                "Metallische Bauteile wie Welle, Gehaeuse, Feder, Stuetzringe oder Huelsen koennen durch Chloride und galvanische Effekte belastet werden. Salzrueckstaende, Kristallisation und Partikel koennen Dichtlippen und Gleitflaechen zusaetzlich verschleissen, besonders bei Nass-/Trocken-Wechseln.",
                "",
                "Die Elastomer- oder Werkstoffvertraeglichkeit haengt nicht nur vom Wort Salzwasser ab, sondern von Konzentration, Temperatur, Zusatzstoffen, Betriebsdauer, Bewegung, Druck und Oberflaeche. Auch Federwerkstoff, rostfreie Werkstoffe, Spuelung, Entwaesserung, Oberflaechenguete und Wartung koennen entscheidend sein.",
                "",
                "Fuer eine konkrete Richtung brauche ich mindestens Dichtstelle, Bewegung, Temperatur, Druck, Drehzahl oder statische Einordnung, Werkstoffe und ob die Dichtstelle dauerhaft benetzt oder zeitweise trocken ist.",
            ]
        )
        answer = humanize_german_technical_text(answer)
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
            missing_reason="domain_saltwater_orientation_without_rag_hit",
            next_step=(
                "Dichtstelle, Bewegung, Temperatur, Druck, Werkstoffe und "
                "Benetzungsprofil als governed Case aufnehmen."
            ),
            knowledge_evidence=(
                _knowledge_evidence(
                    source_type="deterministic",
                    title="Salzwasser in Dichtungsanwendungen",
                    content=answer,
                    note="system_derived_domain_answer",
                ),
            ),
            event_names=(
                "KnowledgeQuestionReceived",
                "KnowledgeRAGLookupRequested",
                "KnowledgeRAGAnswerMissing",
                "SourceValidationStatusAssigned",
                "KnowledgeAnswerGenerated",
            ),
        )

    material_comparison = build_material_risk_comparison_answer(user_input)
    if material_comparison is None:
        material_comparison = build_material_comparison_answer(user_input)
    if material_comparison is not None:
        answer = material_comparison.answer
        left, right = material_comparison.material_ids
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
            user_visible_label="SeaLAI-Werkstoffvergleich - allgemeine Orientierung",
            missing_reason="domain_material_comparison_without_rag_hit",
            next_step=(
                "Bei konkreter Anwendung Medium, Temperatur, Druck, Bewegung "
                "und Dichtstelle als governed Case aufnehmen."
            ),
            knowledge_evidence=(
                _knowledge_evidence(
                    source_type="deterministic",
                    title=material_comparison.title,
                    content=humanize_german_technical_text(
                        f"{material_comparison.title}: Kurz gesagt: {left} und {right} "
                        "werden allgemein gegenübergestellt; keine konkrete Auswahl, "
                        "keine Materialfreigabe und keine Herstellerfreigabe. "
                        "Die ausführliche Antwort nennt Werkstofffamilie, Temperatur, "
                        "Medienorientierung, Dynamik, typische Grenzen und Prüfpunkte."
                    ),
                    note=f"system_derived_material_comparison:{left}:{right}",
                ),
            ),
            event_names=(
                "KnowledgeQuestionReceived",
                "KnowledgeRAGLookupRequested",
                "KnowledgeRAGAnswerMissing",
                "SourceValidationStatusAssigned",
                "KnowledgeAnswerGenerated",
            ),
        )
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
        answer = humanize_german_technical_text(answer)
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
            knowledge_evidence=(
                _knowledge_evidence(
                    source_type="deterministic",
                    title="SeaLAI-Grundwissen",
                    content=answer,
                    note="system_derived_domain_answer",
                ),
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


def _extract_unknown_term_question(user_input: str) -> str | None:
    text = " ".join(str(user_input or "").strip().split())
    if not text:
        return None
    patterns = (
        r"^\s*was\s+(?:genau\s+|eigentlich\s+)?(?:ist|sind)\s+(?P<term>[^?!.;,]{2,80})",
        r"^\s*was\s+bedeutet\s+(?P<term>[^?!.;,]{2,80})",
        r"^\s*was\s+(?:heisst|heißt)\s+(?P<term>[^?!.;,]{2,80})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.UNICODE)
        if not match:
            continue
        term = str(match.group("term") or "").strip(" '\"`´“”„")
        term = re.sub(r"\s+", " ", term).strip()
        lowered = term.casefold()
        if not term or lowered.startswith(
            (
                "bei ",
                "besser",
                "schlechter",
                "der unterschied",
                "die unterschied",
                "das unterschied",
            )
        ):
            return None
        return term[:80]
    return None


def _unknown_term_orientation_result(user_input: str) -> KnowledgeAnswerResult | None:
    term = _extract_unknown_term_question(user_input)
    if term is None:
        return None

    lowered = term.casefold()
    extra_note = ""
    if any(marker in lowered for marker in ("chlor", "oxid", "hypo")):
        extra_note = (
            "\n\nWeil der Begriff nach Chlor- oder Oxidationschemie klingt, sollte "
            "die genaue chemische Form besonders sauber geklaert werden. Je nach "
            "Stoff kann das fuer Elastomere, Metalle, Federn, Beschichtungen und "
            "Sicherheitsanforderungen sehr unterschiedlich sein."
        )

    answer = "\n".join(
        [
            f'Den Begriff "{term}" kann ich in der kuratierten SeaLAI-Wissensbasis nicht eindeutig als belastbaren Dichtungsbegriff oder eindeutig beschriebenes Medium zuordnen.',
            "",
            "Fuer eine Dichtung reicht so ein Kurzname allein nicht. Entscheidend sind die genaue chemische Bezeichnung, Sicherheitsdatenblatt, Konzentration, Temperatur, Aggregatzustand, Verunreinigungen und ob das Medium dauerhaft oder nur zeitweise an der Dichtstelle anliegt.",
            extra_note.strip(),
            "",
            "Wenn du den Stoff in deinem Fall verwenden willst, gib mir bitte die genaue Bezeichnung aus dem Sicherheitsdatenblatt oder die Zusammensetzung. Daraus kann SeaLAI den Fall weiter strukturieren. Eine Werkstofffreigabe oder Kompatibilitaetsaussage entsteht daraus aber erst nach Hersteller- oder Fachpruefung.",
        ]
    )
    answer = "\n".join(
        line for line in answer.splitlines() if line.strip() or line == ""
    )
    answer = humanize_german_technical_text(answer)
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
        user_visible_label="SeaLAI-Begriffsklaerung - allgemeine Orientierung",
        missing_reason="unknown_term_orientation_without_rag_hit",
        next_step=(
            "Genaue chemische Bezeichnung, Sicherheitsdatenblatt, Konzentration "
            "und Betriebsdaten erfassen."
        ),
        knowledge_evidence=(
            _knowledge_evidence(
                source_type="deterministic",
                title=f"Begriffsklaerung: {term}",
                content=answer,
                note="system_derived_unknown_term_orientation",
            ),
        ),
        event_names=(
            "KnowledgeQuestionReceived",
            "KnowledgeRAGLookupRequested",
            "KnowledgeRAGAnswerMissing",
            "SourceValidationStatusAssigned",
            "KnowledgeAnswerGenerated",
        ),
    )


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
        knowledge_evidence=(
            _knowledge_evidence(
                source_type="deterministic",
                title="Deterministic KnowledgeService answer",
                content=answer,
                note="safe_rag_miss_answer",
            ),
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
        knowledge_evidence=(
            _knowledge_evidence(
                source_type="fallback",
                title=KNOWLEDGE_LLM_FALLBACK_LABEL,
                content=answer,
                note="llm_research_fallback_unvalidated",
            ),
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


def _knowledge_evidence(
    *,
    source_type: KnowledgeEvidenceSourceType,
    content: Any,
    title: Any = None,
    source_name: Any = None,
    confidence: float | None = None,
    note: Any = None,
) -> KnowledgeEvidence:
    return KnowledgeEvidence(
        source_type=source_type,
        title=_clean_optional_text(title, limit=180),
        content=_clean_excerpt(content, limit=900),
        source_name=_clean_optional_text(source_name, limit=180),
        confidence=confidence,
        note=_clean_optional_text(note, limit=180),
    )


def _source_title(store: Any, source_id: str) -> str | None:
    if not source_id:
        return None
    source_map: dict[str, Any] = getattr(store, "_sources", {})
    source = source_map.get(source_id)
    if not isinstance(source, dict):
        return None
    return _clean_optional_text(source.get("title") or source_id, limit=180)


def _human_fact_label(topic: str, prop: str) -> str:
    topic_text = str(topic or "").replace("_", " ").strip() or "Wissenseintrag"
    prop_text = str(prop or "").replace("_", " ").strip()
    prop_map = {
        "chemical resistance": "chemische Beständigkeit",
        "temperature window": "Temperaturbereich",
        "thermal": "Temperaturverhalten",
        "chemical": "chemisches Verhalten",
        "pressure": "Druckbezug",
        "friction": "Reibung",
        "wear": "Verschleiß",
    }
    readable_prop = prop_map.get(prop_text.casefold(), prop_text)
    if readable_prop:
        return f"{topic_text}: {readable_prop}"
    return topic_text


def _settings_fallback_enabled() -> bool:
    try:
        from app.core.config import settings  # noqa: PLC0415

        return bool(getattr(settings, "knowledge_llm_research_fallback_enabled", False))
    except Exception:
        return False


_PTFE_QUERY_PATTERN = re.compile(
    r"\b(?:ptfe|tfm|fluoropolymer|fluorpolymer|polytetrafluorethylen|polytetrafluoroethylene)\b",
    re.IGNORECASE | re.UNICODE,
)
_NON_PTFE_MATERIAL_QUERY_PATTERN = re.compile(
    r"\b(?:fkm|ffkm|fpm|epdm|nbr|hnbr|pom|peek|pa6?|pa12|pu|tpu|vmq|silikon|silicone|viton)\b",
    re.IGNORECASE | re.UNICODE,
)


def _should_query_ptfe_factcards(user_input: str) -> bool:
    """Avoid PTFE factcards overpowering RAG for other named materials."""

    text = str(user_input or "")
    if _NON_PTFE_MATERIAL_QUERY_PATTERN.search(text) and not _PTFE_QUERY_PATTERN.search(text):
        return False
    return True


_MATERIAL_EVIDENCE_TOKENS = {
    "ptfe",
    "fkm",
    "ffkm",
    "fpm",
    "epdm",
    "nbr",
    "hnbr",
    "pom",
    "peek",
    "pa",
    "pa6",
    "pa12",
    "pu",
    "tpu",
    "vmq",
    "silikon",
    "silicone",
    "viton",
}
_PRODUCT_EVIDENCE_TOKENS = {
    "klüber",
    "klueber",
    "klübersynth",
    "kluebersynth",
    "uh1",
}


def _filter_rag_hits_for_query(
    user_input: str,
    hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop RAG snippets that do not cover named materials or products."""

    required_tokens = _named_evidence_tokens(user_input)
    if not required_tokens:
        return hits
    filtered: list[dict[str, Any]] = []
    for hit in hits:
        haystack = _rag_hit_text_for_filtering(hit)
        if any(token in haystack for token in required_tokens):
            filtered.append(hit)
    return filtered


def _named_evidence_tokens(user_input: str) -> set[str]:
    text = str(user_input or "").casefold()
    product_tokens = {token for token in _PRODUCT_EVIDENCE_TOKENS if token in text}
    if product_tokens:
        return product_tokens
    material_tokens = {token for token in _MATERIAL_EVIDENCE_TOKENS if re.search(rf"\b{re.escape(token)}\b", text)}
    if "ptfe" in material_tokens and len(material_tokens) > 1:
        material_tokens.remove("ptfe")
    return material_tokens


def _rag_hit_text_for_filtering(hit: dict[str, Any]) -> str:
    metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
    parts = [
        hit.get("text"),
        hit.get("content"),
        hit.get("title"),
        hit.get("source"),
        metadata.get("title"),
        metadata.get("filename"),
        metadata.get("source_id"),
        metadata.get("document_id"),
        metadata.get("material_code"),
        metadata.get("entity"),
    ]
    return " ".join(str(part or "").casefold() for part in parts)


def _clean_excerpt(value: Any, *, limit: int = 420) -> str:
    text = str(value or "")
    text = re.sub(r"\[(?:Document|Dokument):[^\]]+\]\s*", " ", text, flags=re.I)
    text = re.sub(r"(?:\[(?:Q|F)\d+\])+", " ", text, flags=re.I)
    text = re.sub(r"#{1,6}\s*", " ", text)
    text = re.sub(
        r"\b(?:ASSUMPTIONS_AND_SCOPE|RFQ[-\s]Feld[-\s]Mapping)\b[:\-]?",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b", " ", text)
    text = " ".join(text.split())
    text = re.sub(r"\b[A-Z]{2,8}-[A-Z]-\d{2,4}\b", "", text).strip()
    text = re.sub(
        r"\b(?:chemical_resistance|weather_ozone_uv|temperature_window)/", "", text
    )
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _clean_optional_text(value: Any, *, limit: int) -> str | None:
    text = _clean_excerpt(value, limit=limit)
    return text or None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
