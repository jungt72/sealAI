from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.pre_gate_classification import PreGateClassification
from app.services.knowledge import FactCardStore


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    source_id: str
    title: str
    url: str | None = None
    source_type: str | None = None
    rank: int | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeResponse:
    content: str
    source_classification: PreGateClassification = PreGateClassification.KNOWLEDGE_QUERY
    output_class: str = "conversational_answer"
    citations: tuple[KnowledgeSource, ...] = field(default_factory=tuple)
    no_case_created: bool = True


class KnowledgeService:
    """Dedicated non-case knowledge path backed by the curated FactCard store."""

    def __init__(self, *, factcard_store: FactCardStore | None = None) -> None:
        self._store = factcard_store or FactCardStore.get_instance()

    def answer(self, user_input: str, *, max_cards: int = 3) -> KnowledgeResponse:
        cards = self._store.match_query_to_cards((user_input or "").lower())[:max_cards]
        if not cards:
            return KnowledgeResponse(
                content=(
                    "Dazu habe ich in der kuratierten SeaLAI-Wissensbasis noch keinen "
                    "belastbaren Eintrag gefunden. Ich kann daraus keinen technischen Fall "
                    "oder eine Empfehlung ableiten."
                ),
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
            "und keine Herstellerfreigabe."
        )
        return KnowledgeResponse(content="\n".join(lines), citations=tuple(sources))

    def _source_for(self, source_id: str) -> KnowledgeSource | None:
        source_map: dict[str, Any] = getattr(self._store, "_sources", {})
        source = source_map.get(source_id)
        if not isinstance(source, dict):
            return None
        return KnowledgeSource(
            source_id=source_id,
            title=str(source.get("title") or source_id),
            url=source.get("url"),
            source_type=source.get("type"),
            rank=source.get("rank"),
        )
