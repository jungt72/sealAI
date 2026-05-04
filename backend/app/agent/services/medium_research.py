from __future__ import annotations

import logging
import json
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.runtime.output_guard import check_fast_path_output
from app.agent.services.medium_context import MediumContext, resolve_medium_context
from app.llm.factory import get_async_llm
from app.llm.registry import get_registry_default_model_for_role

_log = logging.getLogger(__name__)


SourceType = Literal["deterministic", "rag", "web"]
ValidationStatus = Literal["system_derived", "documented", "web_retrieved", "not_available"]
ResearchStatus = Literal["ok", "no_hits", "disabled", "not_configured", "error", "tenant_missing"]
AnswerMarkdownSource = Literal["deterministic_sections", "medium_composer", "composer_fallback"]

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_MODEL_FALLBACK_ERROR_NAMES = {"BadRequestError", "NotFoundError"}
_MAX_MEDIUM_ANSWER_CHARS = 3800

_INTERNAL_LEAKAGE_FRAGMENTS = (
    "```json",
    "answer_markdown",
    "source_type",
    "validation_status",
    "model_dump",
    "mediumresearch",
    "openai",
    "raw evidence",
)


class MediumResearchAttempt(BaseModel):
    attempted: bool = False
    status: ResearchStatus = "disabled"
    hit_count: int = 0
    tier: str | None = None
    note: str | None = None


class MediumEvidenceItem(BaseModel):
    id: str
    source_type: SourceType
    validation_status: ValidationStatus
    title: str
    source_name: str | None = None
    excerpt: str
    confidence: Literal["low", "medium", "high"] = "medium"
    url: str | None = None


class MediumResearchSection(BaseModel):
    id: str
    title: str
    content: str
    bullets: list[str] = Field(default_factory=list)
    evidence_ref_ids: list[str] = Field(default_factory=list)


class MediumResearchStatus(BaseModel):
    rag: MediumResearchAttempt = Field(default_factory=MediumResearchAttempt)
    web: MediumResearchAttempt = Field(default_factory=MediumResearchAttempt)


class MediumAnswerComposerStatus(BaseModel):
    enabled: bool = False
    attempted: bool = False
    succeeded: bool = False
    source: AnswerMarkdownSource = "deterministic_sections"
    fallback_reason: str | None = None


class MediumResearchResult(BaseModel):
    medium: str
    resolved_medium: str | None = None
    summary: str | None = None
    answer_markdown: str | None = None
    answer_markdown_source: AnswerMarkdownSource = "deterministic_sections"
    sections: list[MediumResearchSection] = Field(default_factory=list)
    evidence: list[MediumEvidenceItem] = Field(default_factory=list)
    research_status: MediumResearchStatus = Field(default_factory=MediumResearchStatus)
    composer: MediumAnswerComposerStatus = Field(default_factory=MediumAnswerComposerStatus)
    limitations: list[str] = Field(default_factory=list)
    not_for_release_decisions: bool = True


class MediumResearchService:
    """Build a source-marked, read-only medium deep dive for the dashboard."""

    def __init__(self, *, rag_k: int = 6) -> None:
        self.rag_k = rag_k

    async def build(
        self,
        medium: str,
        *,
        tenant_id: str | None,
        user_id: str | None = None,
    ) -> MediumResearchResult:
        medium_label = _clean_text(medium, limit=120)
        context = resolve_medium_context(medium_label)
        evidence: list[MediumEvidenceItem] = []

        if context.status == "available":
            evidence.append(_medium_context_evidence(context))

        rag_items, rag_attempt = await _retrieve_rag_evidence(
            medium_label,
            tenant_id=tenant_id,
            user_id=user_id,
            k=self.rag_k,
        )
        evidence.extend(rag_items)

        web_items, web_attempt = await _retrieve_web_evidence(medium_label)
        evidence.extend(web_items)

        sections = _build_sections(
            medium_label=medium_label,
            context=context,
            evidence=evidence,
            rag_hit_count=len(rag_items),
            web_hit_count=len(web_items),
        )
        research_status = MediumResearchStatus(rag=rag_attempt, web=web_attempt)
        limitations = _limitations(web_attempt)
        answer_markdown, answer_source, composer_status = await _compose_medium_answer_markdown(
            medium_label=medium_label,
            context=context,
            sections=sections,
            evidence=evidence,
            research_status=research_status,
            limitations=limitations,
        )

        return MediumResearchResult(
            medium=medium_label,
            resolved_medium=context.medium_label,
            summary=context.summary if context.status == "available" else None,
            answer_markdown=answer_markdown,
            answer_markdown_source=answer_source,
            sections=sections,
            evidence=evidence,
            research_status=research_status,
            composer=composer_status,
            limitations=limitations,
            not_for_release_decisions=True,
        )


async def _compose_medium_answer_markdown(
    *,
    medium_label: str,
    context: MediumContext,
    sections: list[MediumResearchSection],
    evidence: list[MediumEvidenceItem],
    research_status: MediumResearchStatus,
    limitations: list[str],
) -> tuple[str, AnswerMarkdownSource, MediumAnswerComposerStatus]:
    fallback = _deterministic_answer_markdown(
        medium_label=medium_label,
        context=context,
        sections=sections,
        evidence=evidence,
        limitations=limitations,
    )
    if not _medium_answer_composer_enabled():
        return fallback, "deterministic_sections", MediumAnswerComposerStatus(
            enabled=False,
            attempted=False,
            succeeded=False,
            source="deterministic_sections",
        )

    status = MediumAnswerComposerStatus(
        enabled=True,
        attempted=True,
        succeeded=False,
        source="composer_fallback",
    )
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return fallback, "composer_fallback", status.model_copy(
            update={"fallback_reason": "provider_not_configured"}
        )

    try:
        client, model = get_async_llm("medium_answer_composer")
        messages = _medium_answer_messages(
            medium_label=medium_label,
            context=context,
            sections=sections,
            evidence=evidence,
            research_status=research_status,
            limitations=limitations,
        )
        response = await _create_medium_answer_completion(
            client=client,
            model=model,
            messages=messages,
            temperature=0.25,
            max_tokens=1200,
        )
        raw_content = response.choices[0].message.content
        answer = _parse_medium_answer_output(raw_content)
        return answer, "medium_composer", status.model_copy(
            update={"succeeded": True, "source": "medium_composer", "fallback_reason": None}
        )
    except Exception as exc:  # noqa: BLE001
        reason = _safe_reason(exc)
        _log.warning(
            "[medium_research] answer composer failed for medium=%r: %s",
            medium_label[:80],
            reason,
        )
        return fallback, "composer_fallback", status.model_copy(update={"fallback_reason": reason})


def _medium_answer_composer_enabled() -> bool:
    return os.getenv("SEALAI_ENABLE_MEDIUM_ANSWER_COMPOSER", "").strip().lower() in _TRUE_VALUES


async def _create_medium_answer_completion(
    *,
    client: Any,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> Any:
    try:
        return await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=_medium_answer_response_format(),
        )
    except Exception as exc:  # noqa: BLE001
        fallback_model = get_registry_default_model_for_role("medium_answer_composer")
        if model != fallback_model and exc.__class__.__name__ in _MODEL_FALLBACK_ERROR_NAMES:
            return await client.chat.completions.create(
                model=fallback_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=_medium_answer_response_format(),
            )
        raise


def _medium_answer_messages(
    *,
    medium_label: str,
    context: MediumContext,
    sections: list[MediumResearchSection],
    evidence: list[MediumEvidenceItem],
    research_status: MediumResearchStatus,
    limitations: list[str],
) -> list[dict[str, str]]:
    payload = {
        "medium": medium_label,
        "resolved_medium": context.medium_label,
        "curated_summary": context.summary,
        "sections": [section.model_dump(mode="json") for section in sections],
        "evidence": [
            {
                "id": item.id,
                "kind": item.source_type,
                "status": item.validation_status,
                "title": item.title,
                "source_name": item.source_name,
                "excerpt": item.excerpt,
                "confidence": item.confidence,
                "url": item.url,
            }
            for item in evidence[:8]
        ],
        "research_status": research_status.model_dump(mode="json"),
        "limitations": limitations,
    }
    return [
        {"role": "system", "content": _medium_answer_system_prompt()},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=True, default=str)},
    ]


def _medium_answer_system_prompt() -> str:
    return """You are SealAI's Medium Intelligence final answer composer.

Your task is to write a user-facing German markdown deep dive for exactly one sealing medium.
Use only the supplied deterministic sections and evidence excerpts. Do not create engineering truth.

Write like a careful senior sealing-technology engineer:
- direct, useful, detailed, and understandable
- deep enough that a user learns why the medium matters for seals
- structured with headings, bullets, and a compact practical checklist
- no generic filler, no route names, no internal JSON, no model names

Required content:
- identify the medium and why it matters for sealing technology
- explain relevant chemical/physical risk themes from supplied context
- explain what matters for elastomers, PTFE/fluoropolymers, metals, springs, shafts, housings, surfaces, deposits, cleaning, temperature, pressure, and exposure only when supported by supplied sections/evidence
- distinguish curated system context, RAG, and live web evidence by plain wording without exposing internal labels
- state uncertainty and missing data
- include the most useful next data points for a manufacturer-review-ready inquiry
- state clearly that this is orientation, not material release, compliance approval, or manufacturer approval

Forbidden:
- final suitability, final compatibility, final release, compliance/certification, or manufacturer approval claims
- invented norms, legal deadlines, data sheet claims, product names, sources, or values
- manufacturer contact, RFQ export, matching, or dispatch language
- saying a material "is suitable" for the concrete case

Return only JSON:
{"answer_markdown": "...", "confidence_note": null}"""


def _medium_answer_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "sealai_medium_answer_composer_response",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "answer_markdown": {"type": "string"},
                    "confidence_note": {"type": ["string", "null"]},
                },
                "required": ["answer_markdown", "confidence_note"],
            },
        },
    }


def _parse_medium_answer_output(raw_content: Any) -> str:
    try:
        payload = json.loads(str(raw_content or "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_json") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")

    answer = str(payload.get("answer_markdown") or "").strip()
    if not answer:
        raise ValueError("empty_answer_markdown")
    if len(answer) > _MAX_MEDIUM_ANSWER_CHARS:
        raise ValueError("answer_markdown_too_long")
    lowered = answer.casefold()
    if any(fragment in lowered for fragment in _INTERNAL_LEAKAGE_FRAGMENTS):
        raise ValueError("internal_leakage")
    safe, category = check_fast_path_output(answer)
    if not safe:
        raise ValueError(f"unsafe_answer:{category}")
    return answer


def _safe_reason(exc: BaseException) -> str:
    raw = str(exc) if isinstance(exc, ValueError) else exc.__class__.__name__
    safe = re.sub(r"[^a-zA-Z0-9_:\.-]", "_", raw)[:96]
    return safe or "composer_failed"


def _deterministic_answer_markdown(
    *,
    medium_label: str,
    context: MediumContext,
    sections: list[MediumResearchSection],
    evidence: list[MediumEvidenceItem],
    limitations: list[str],
) -> str:
    resolved = context.medium_label or medium_label
    lines = [
        f"### Medium-Deep-Dive: {resolved}",
        "",
        context.summary
        or "SeaLAI hat das Medium noch nicht kuratiert hinterlegt. Die folgenden Punkte sind deshalb Anfrage- und Quellenarbeit, keine technische Freigabe.",
    ]
    for section in sections:
        if section.id == "boundary":
            continue
        lines.extend(["", f"#### {section.title}", "", section.content])
        for bullet in section.bullets[:8]:
            lines.append(f"- {bullet}")
    if evidence:
        lines.extend(["", "#### Quellenlage", ""])
        for item in evidence[:5]:
            source = item.source_name or item.title
            lines.append(f"- {source}: {item.excerpt}")
    if limitations:
        lines.extend(["", "#### Grenze der Aussage", ""])
        for limitation in limitations:
            lines.append(f"- {limitation}")
    return _clean_text("\n".join(lines), limit=_MAX_MEDIUM_ANSWER_CHARS)


async def _retrieve_rag_evidence(
    medium: str,
    *,
    tenant_id: str | None,
    user_id: str | None,
    k: int,
) -> tuple[list[MediumEvidenceItem], MediumResearchAttempt]:
    if not tenant_id:
        return [], MediumResearchAttempt(
            attempted=False,
            status="tenant_missing",
            note="RAG wurde nicht gestartet, weil kein Tenant-Kontext vorhanden ist.",
        )

    query = (
        f"Medium {medium} Dichtung Dichtungen Korrosion Werkstoff "
        "Temperatur Druck Kompatibilitaet Risiko Herstellerpruefung"
    )
    try:
        from app.agent.services.real_rag import retrieve_with_tenant

        raw_result = await retrieve_with_tenant(
            query,
            tenant_id,
            k=k,
            user_id=user_id,
            return_metrics=True,
        )
        raw_hits, metrics = raw_result if isinstance(raw_result, tuple) else (raw_result, {})
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "[medium_research] RAG retrieval failed for medium=%r: %s",
            medium[:80],
            exc.__class__.__name__,
        )
        return [], MediumResearchAttempt(
            attempted=True,
            status="error",
            note="RAG konnte nicht ausgewertet werden.",
        )

    hits = [hit for hit in (raw_hits or []) if _clean_text(hit.get("content"), limit=10)]
    evidence = [_rag_hit_to_evidence(hit, index) for index, hit in enumerate(hits[:k], start=1)]
    tier = str((metrics or {}).get("tier") or "").strip() or None
    return evidence, MediumResearchAttempt(
        attempted=True,
        status="ok" if evidence else "no_hits",
        hit_count=len(evidence),
        tier=tier,
        note=None if evidence else "Keine passende interne Wissensquelle gefunden.",
    )


async def _retrieve_web_evidence(medium: str) -> tuple[list[MediumEvidenceItem], MediumResearchAttempt]:
    enabled = os.getenv("SEALAI_ENABLE_MEDIUM_WEB_RESEARCH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not enabled:
        return [], MediumResearchAttempt(
            attempted=False,
            status="disabled",
            note="Live-Websearch ist deaktiviert; SeaLAI zeigt hier keine ungeprüften Webquellen an.",
        )

    if not os.getenv("OPENAI_API_KEY", "").strip():
        return [], MediumResearchAttempt(
            attempted=False,
            status="not_configured",
            note="Live-Websearch ist aktiviert, aber kein Provider ist konfiguriert.",
        )

    try:
        client, model = get_async_llm("medium_web_research")
        response = await client.responses.create(
            model=model,
            tools=[{"type": "web_search"}],
            tool_choice="required",
            include=["web_search_call.action.sources"],
            input=(
                "Recherchiere knapp und quellenorientiert zum Medium "
                f"{medium!r} im Kontext technischer Dichtungen. "
                "Nenne keine endgültige Werkstofffreigabe, keine erfundenen Normen "
                "und keine rechtlichen Fristen ohne Quelle."
            ),
            max_output_tokens=800,
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "[medium_research] web research failed for medium=%r: %s",
            medium[:80],
            exc.__class__.__name__,
        )
        return [], MediumResearchAttempt(
            attempted=True,
            status="error",
            note="Live-Websearch konnte nicht ausgewertet werden.",
        )

    text = _clean_text(_response_text(response), limit=900)
    if not text:
        return [], MediumResearchAttempt(
            attempted=True,
            status="no_hits",
            note="Live-Websearch lieferte keine verwertbare Zusammenfassung.",
        )

    sources = _response_sources(response)
    evidence = [
        MediumEvidenceItem(
            id="web-1",
            source_type="web",
            validation_status="web_retrieved",
            title="Live-Websearch zum Medium",
            source_name=", ".join(sources[:3]) if sources else "OpenAI Web Search",
            excerpt=text,
            confidence="low",
            url=sources[0] if sources and sources[0].startswith("http") else None,
        )
    ]
    return evidence, MediumResearchAttempt(
        attempted=True,
        status="ok",
        hit_count=len(evidence),
        note="Live-Webquelle wurde abgerufen, bleibt aber technische Orientierung.",
    )


def _build_sections(
    *,
    medium_label: str,
    context: MediumContext,
    evidence: list[MediumEvidenceItem],
    rag_hit_count: int,
    web_hit_count: int,
) -> list[MediumResearchSection]:
    context_ref = ["medium-context"] if any(item.id == "medium-context" for item in evidence) else []
    rag_refs = [item.id for item in evidence if item.source_type == "rag"][:3]
    web_refs = [item.id for item in evidence if item.source_type == "web"][:1]
    resolved = context.medium_label or medium_label

    sections: list[MediumResearchSection] = []
    if context.status == "available":
        sections.append(
            MediumResearchSection(
                id="identity",
                title="Einordnung",
                content=context.summary or f"{resolved} ist als Medium erkannt, aber noch nicht vollständig belegt.",
                bullets=context.properties[:6],
                evidence_ref_ids=context_ref,
            )
        )
        sections.append(
            MediumResearchSection(
                id="sealing_relevance",
                title="Warum das fuer Dichtungen wichtig ist",
                content=(
                    "Das Medium beeinflusst Werkstofffenster, Alterung, Reibung, "
                    "Korrosion an angrenzenden Bauteilen und die spaeteren Nachweise. "
                    "SeaLAI macht daraus keine Freigabe, sondern zeigt die Pruefpunkte."
                ),
                bullets=context.challenges[:6],
                evidence_ref_ids=context_ref + rag_refs,
            )
        )
    else:
        sections.append(
            MediumResearchSection(
                id="identity",
                title="Einordnung",
                content=(
                    f"{medium_label} ist noch nicht im kuratierten Medium-Kontext von SeaLAI hinterlegt. "
                    "Ohne belastbare Quelle wird es deshalb nur als Nutzerangabe behandelt."
                ),
                bullets=[
                    "Genaue Stoffbezeichnung oder Handelsname klaeren",
                    "Konzentration, Temperatur und Druck erfragen",
                    "Sicherheitsdatenblatt oder Herstellerdatenblatt als Evidence nutzen",
                ],
                evidence_ref_ids=rag_refs + web_refs,
            )
        )

    if _looks_like_saltwater(resolved):
        sections.append(
            MediumResearchSection(
                id="saltwater_deep_dive",
                title="Salzwasser-spezifische Pruefpunkte",
                content=(
                    "Bei salzhaltigen Medien stehen Chloridbelastung, leitfaehige Feuchte "
                    "und Rueckstaende im Vordergrund. Kritisch sind nicht nur Elastomere, "
                    "sondern auch Welle, Gehaeuse, Feder, Stuetzringe und Gegenlaufflaechen."
                ),
                bullets=[
                    "Chloride koennen Korrosion an metallischen Komponenten beschleunigen.",
                    "Salzreste, Kristallisation und Trocken-/Nasswechsel koennen Dichtlippen und Laufspuren belasten.",
                    "Feder- und Wellenwerkstoffe muessen zur realen Umgebung passen.",
                    "Spuelung, Entwaesserung, Oberflaechenguete und Wartung sind frueh zu klaeren.",
                ],
                evidence_ref_ids=context_ref + rag_refs + web_refs,
            )
        )

    sections.append(
        MediumResearchSection(
            id="questions",
            title="Welche Angaben jetzt wirklich helfen",
            content=(
                "Fuer eine belastbare technische Einordnung zaehlen konkrete Betriebsdaten mehr "
                "als ein allgemeiner Medienname."
            ),
            bullets=_compact([
                *context.followup_points,
                "direkter Druck an der Dichtstelle",
                "Temperatur inklusive Spitzen",
                "statisch, rotierend, linear oder oszillierend",
                "Konzentration, Additive, Partikel und Reinigungszyklen",
            ])[:8],
            evidence_ref_ids=context_ref,
        )
    )

    if rag_hit_count or web_hit_count:
        sections.append(
            MediumResearchSection(
                id="evidence_summary",
                title="Was die Quellenlage aktuell hergibt",
                content=(
                    f"SeaLAI hat {rag_hit_count} interne RAG-Treffer"
                    f" und {web_hit_count} Live-Web-Hinweise fuer diesen Medium-Deep-Dive markiert. "
                    "Die Quellen werden als Orientierung angezeigt und ersetzen keine Herstellerfreigabe."
                ),
                bullets=[item.title for item in evidence if item.source_type in {"rag", "web"}][:6],
                evidence_ref_ids=rag_refs + web_refs,
            )
        )

    sections.append(
        MediumResearchSection(
            id="boundary",
            title="Grenze der Aussage",
            content=(
                "Diese Ansicht ist technische Orientierung. Eine konkrete Werkstoffauswahl, "
                "Konformitaetsbewertung oder Dichtungsfreigabe darf daraus nicht abgeleitet werden."
            ),
            bullets=[
                "Keine finale Werkstofffreigabe",
                "Keine Aussage zur Herstellerzulassung",
                "Keine automatische Compliance-Bewertung",
            ],
            evidence_ref_ids=[],
        )
    )
    return sections


def _medium_context_evidence(context: MediumContext) -> MediumEvidenceItem:
    parts = _compact([context.summary, *context.properties, *context.challenges])
    return MediumEvidenceItem(
        id="medium-context",
        source_type="deterministic",
        validation_status="system_derived",
        title=f"SeaLAI Medium-Kontext: {context.medium_label}",
        source_name="SeaLAI kuratierter Medium-Kontext",
        excerpt=_clean_text(" ".join(parts), limit=420),
        confidence=context.confidence or "medium",
    )


def _rag_hit_to_evidence(hit: dict[str, Any], index: int) -> MediumEvidenceItem:
    topic = _clean_text(hit.get("topic"), limit=90) or f"Interne Wissensquelle {index}"
    source_ref = _clean_text(hit.get("source_ref"), limit=120)
    content = _clean_text(hit.get("content"), limit=420)
    return MediumEvidenceItem(
        id=f"rag-{index}",
        source_type="rag",
        validation_status="documented",
        title=topic,
        source_name=_source_name(source_ref),
        excerpt=content,
        confidence="medium" if content else "low",
    )


def _limitations(web_attempt: MediumResearchAttempt) -> list[str]:
    items = [
        "Technische Orientierung fuer die Anfragevorbereitung, keine Auslegungsfreigabe.",
        "Werkstoff-, Norm- und Compliance-Aussagen muessen spaeter durch Hersteller oder qualifizierte Fachstelle bestaetigt werden.",
    ]
    if web_attempt.status in {"disabled", "not_configured", "error", "no_hits"}:
        items.append("Es werden keine Live-Webaussagen angezeigt, solange keine verwertbare Webquelle erfolgreich abgerufen wurde.")
    return items


def _clean_text(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", text)
    text = text.replace(os.getcwd(), "[workspace]")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _source_name(source_ref: str) -> str | None:
    if not source_ref:
        return None
    source_ref = source_ref.replace("\\", "/")
    return source_ref.rsplit("/", 1)[-1] or source_ref


def _compact(items: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _clean_text(item, limit=220)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _looks_like_saltwater(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in ("salzwasser", "meerwasser", "salzhalt"))


def _response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return str(text)
    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return ""
    chunks: list[str] = []
    for item in output:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(str(value))
    return "\n".join(chunks)


def _response_sources(response: Any) -> list[str]:
    sources: list[str] = []
    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return sources
    for item in output:
        action = getattr(item, "action", None)
        for source in getattr(action, "sources", []) or []:
            url = getattr(source, "url", None)
            title = getattr(source, "title", None)
            source_text = _clean_text(url or title, limit=160)
            if source_text:
                sources.append(source_text)
        for content in getattr(item, "content", []) or []:
            for annotation in getattr(content, "annotations", []) or []:
                url = getattr(annotation, "url", None)
                title = getattr(annotation, "title", None)
                source = _clean_text(url or title, limit=160)
                if source:
                    sources.append(source)
    return _compact(sources)
