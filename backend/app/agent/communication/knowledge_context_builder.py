from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal


KnowledgeEvidenceSourceType = Literal["fact_card", "rag", "deterministic", "unknown"]

_DEFAULT_HISTORY_LIMIT = 6
_DEFAULT_EVIDENCE_LIMIT = 6
_MAX_HISTORY_CHARS = 900
_MAX_EVIDENCE_CHARS = 900
_MAX_DETERMINISTIC_EVIDENCE_CHARS = 1200

_GENERAL_LIMITATION = (
    "General technical orientation only; no final engineering release, no final "
    "compatibility proof, no manufacturer approval."
)
_RAG_MISS_LIMITATION = (
    "No sufficient curated/RAG source was available in the deterministic knowledge "
    "result; preserve that uncertainty."
)
_REGULATORY_CURRENTNESS_LIMITATION = (
    "No live regulatory source was retrieved in this path; answer must be framed "
    "as technical orientation, not current legal advice."
)
_REGULATORY_RE = re.compile(
    r"\b(pfas|reach|echa|eu\s+regulation|eu-regulation|eu\s+verordnung|"
    r"verordnung|verbot|regulierung|gesetzlich|legal|compliance|"
    r"regulation|regulatory)\b",
    re.IGNORECASE | re.UNICODE,
)


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    role: Literal["user", "assistant"]
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True, slots=True)
class KnowledgeEvidenceItem:
    content: str
    source_type: KnowledgeEvidenceSourceType = "unknown"
    title: str | None = None
    source_note: str | None = None
    confidence: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source_type": self.source_type,
            "content": self.content,
            "source_note": self.source_note,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerContext:
    user_message: str
    deterministic_answer: str
    recent_history: tuple[ConversationTurn, ...] = field(default_factory=tuple)
    evidence_items: tuple[KnowledgeEvidenceItem, ...] = field(default_factory=tuple)
    route_label: str | None = None
    knowledge_mode: str | None = None
    intent: str | None = None
    no_case: bool = True
    limitations: tuple[str, ...] = field(default_factory=tuple)
    language_hint: str = "de"
    regulatory_currentness_required: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_message": self.user_message,
            "deterministic_answer": self.deterministic_answer,
            "recent_history": [turn.as_dict() for turn in self.recent_history],
            "evidence_items": [item.as_dict() for item in self.evidence_items],
            "route_label": self.route_label,
            "knowledge_mode": self.knowledge_mode,
            "intent": self.intent,
            "no_case": self.no_case,
            "limitations": list(self.limitations),
            "language_hint": self.language_hint,
            "regulatory_currentness_required": self.regulatory_currentness_required,
        }


class KnowledgeContextBuilder:
    """Builds a read-only context for no-case knowledge answer composition."""

    def __init__(
        self,
        *,
        history_limit: int = _DEFAULT_HISTORY_LIMIT,
        evidence_limit: int = _DEFAULT_EVIDENCE_LIMIT,
    ) -> None:
        self.history_limit = max(0, int(history_limit))
        self.evidence_limit = max(1, int(evidence_limit))

    def build(
        self,
        *,
        user_message: str,
        deterministic_answer: str,
        knowledge_response: Any | None = None,
        answer_view: Any | None = None,
        recent_history: Iterable[Any] | None = None,
        route_label: str | None = None,
        knowledge_mode: str | None = None,
        intent: str | None = None,
        language_hint: str = "de",
    ) -> KnowledgeAnswerContext:
        answer_view = answer_view or getattr(
            knowledge_response,
            "knowledge_answer_view",
            None,
        )
        deterministic_text = _safe_text(
            deterministic_answer or getattr(knowledge_response, "content", "")
        )
        evidence_items = self._evidence_items(
            answer_view=answer_view,
            deterministic_answer=deterministic_text,
        )
        regulatory_currentness_required = _requires_regulatory_currentness(user_message)
        limitations = self._limitations(
            answer_view=answer_view,
            regulatory_currentness_required=regulatory_currentness_required,
        )
        return KnowledgeAnswerContext(
            user_message=_safe_text(user_message, limit=_MAX_HISTORY_CHARS),
            deterministic_answer=deterministic_text,
            recent_history=self._recent_history(recent_history),
            evidence_items=evidence_items,
            route_label=_optional_text(route_label),
            knowledge_mode=_optional_text(knowledge_mode),
            intent=_optional_text(intent),
            no_case=True,
            limitations=limitations,
            language_hint=_optional_text(language_hint) or "de",
            regulatory_currentness_required=regulatory_currentness_required,
        )

    def _recent_history(
        self,
        recent_history: Iterable[Any] | None,
    ) -> tuple[ConversationTurn, ...]:
        visible_turns: list[ConversationTurn] = []
        for raw_turn in recent_history or ():
            role = _turn_value(raw_turn, "role")
            if role not in {"user", "assistant"}:
                continue
            content = _safe_text(
                _turn_value(raw_turn, "content"),
                limit=_MAX_HISTORY_CHARS,
            )
            if not content:
                continue
            visible_turns.append(
                ConversationTurn(role=role, content=content)  # type: ignore[arg-type]
            )
        if not visible_turns:
            return ()
        if self.history_limit == 0:
            return ()
        return tuple(visible_turns[-self.history_limit :])

    def _evidence_items(
        self,
        *,
        answer_view: Any | None,
        deterministic_answer: str,
    ) -> tuple[KnowledgeEvidenceItem, ...]:
        items: list[KnowledgeEvidenceItem] = []
        for source in tuple(getattr(answer_view, "sources", ()) or ()):
            item = _evidence_from_source(source)
            if item is not None:
                items.append(item)
            if len(items) >= self.evidence_limit:
                break

        deterministic_item = _deterministic_evidence_item(answer_view, deterministic_answer)
        if deterministic_item is not None and len(items) < self.evidence_limit:
            items.append(deterministic_item)

        if not items and deterministic_item is not None:
            items.append(deterministic_item)
        return tuple(items[: self.evidence_limit])

    @staticmethod
    def _limitations(
        *,
        answer_view: Any | None,
        regulatory_currentness_required: bool,
    ) -> tuple[str, ...]:
        limitations: list[str] = [_GENERAL_LIMITATION]
        if answer_view is not None and bool(getattr(answer_view, "rag_miss", False)):
            limitations.append(_RAG_MISS_LIMITATION)
        if regulatory_currentness_required:
            limitations.append(_REGULATORY_CURRENTNESS_LIMITATION)
        return tuple(dict.fromkeys(limitations))


def build_knowledge_answer_context(**kwargs: Any) -> KnowledgeAnswerContext:
    return KnowledgeContextBuilder().build(**kwargs)


def _evidence_from_source(source: Any) -> KnowledgeEvidenceItem | None:
    excerpt = _safe_text(getattr(source, "excerpt", None), limit=_MAX_EVIDENCE_CHARS)
    title = _optional_text(getattr(source, "title", None))
    content = excerpt or title or ""
    if not content:
        return None

    source_type = _evidence_source_type(source, has_excerpt=bool(excerpt))
    validation_status = _enum_value(getattr(source, "validation_status", None))
    confidence = _float_or_none(getattr(source, "confidence", None))
    note_parts = []
    if validation_status:
        note_parts.append(f"validation_status={validation_status}")
    if confidence is not None:
        note_parts.append(f"confidence={confidence:.3g}")
    return KnowledgeEvidenceItem(
        title=title,
        source_type=source_type,
        content=content,
        source_note="; ".join(note_parts) or None,
        confidence=confidence,
    )


def _deterministic_evidence_item(
    answer_view: Any | None,
    deterministic_answer: str,
) -> KnowledgeEvidenceItem | None:
    content = _safe_text(
        deterministic_answer,
        limit=_MAX_DETERMINISTIC_EVIDENCE_CHARS,
    )
    if not content:
        return None
    validation_status = _enum_value(getattr(answer_view, "validation_status", None))
    label = _optional_text(getattr(answer_view, "user_visible_label", None))
    note_parts = []
    if validation_status:
        note_parts.append(f"validation_status={validation_status}")
    if label:
        note_parts.append(f"label={label}")
    return KnowledgeEvidenceItem(
        title="Deterministic KnowledgeService answer",
        source_type="deterministic",
        content=content,
        source_note="; ".join(note_parts) or None,
    )


def _evidence_source_type(
    source: Any,
    *,
    has_excerpt: bool,
) -> KnowledgeEvidenceSourceType:
    raw_source_type = _enum_value(getattr(source, "source_type", None))
    if raw_source_type == "rag_verified":
        return "rag" if has_excerpt else "fact_card"
    if raw_source_type in {"system_derived", "deterministic_calculation"}:
        return "deterministic"
    if has_excerpt:
        return "rag"
    return "unknown"


def _requires_regulatory_currentness(user_message: str) -> bool:
    return bool(_REGULATORY_RE.search(str(user_message or "")))


def _turn_value(turn: Any, key: str) -> str:
    if isinstance(turn, dict):
        value = turn.get(key)
    else:
        value = getattr(turn, key, None)
    return str(value or "").strip()


def _safe_text(value: Any, *, limit: int | None = None) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    if limit is not None and len(text) > limit:
        return text[: max(0, limit - 3)].rstrip() + "..."
    return text


def _optional_text(value: Any) -> str | None:
    text = _safe_text(value)
    return text or None


def _enum_value(value: Any) -> str | None:
    raw = getattr(value, "value", value)
    return _optional_text(raw)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
