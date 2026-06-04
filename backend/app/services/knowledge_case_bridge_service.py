from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from app.agent.domain.normalization import extract_parameters
from app.agent.state.models import ConversationMessage, ObservedExtraction


class TransitionSignalKind(str, Enum):
    NONE = "none"
    CONCRETE_CASE = "concrete_case"


@dataclass(frozen=True, slots=True)
class TransitionSignal:
    kind: TransitionSignalKind
    confidence: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeConversationTurn:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ParameterSeed:
    field_name: str
    raw_value: object
    raw_unit: str | None = None
    confidence: float = 0.75
    source_turn_index: int = 0


@dataclass(frozen=True, slots=True)
class KnowledgeSessionContext:
    session_id: str
    mentioned_parameters: Mapping[str, ParameterSeed] = field(default_factory=dict)
    explored_concepts: tuple[str, ...] = ()
    detected_intent: str | None = None
    transition_offered: bool = False
    conversation_turns: tuple[KnowledgeConversationTurn, ...] = ()
    user_turn_index: int = 0


@dataclass(frozen=True, slots=True)
class KnowledgeCaseSeed:
    conversation_messages: tuple[ConversationMessage, ...]
    observed_extractions: tuple[ObservedExtraction, ...]
    observed_topic: str | None = None
    tentative_domain_signals: tuple[str, ...] = ()
    user_turn_index: int = 0


class KnowledgeCaseBridgeService:
    def update_context(
        self,
        turn_text: str,
        *,
        context: KnowledgeSessionContext | None = None,
        session_id: str | None = None,
        role: str = "user",
    ) -> KnowledgeSessionContext:
        base = context or KnowledgeSessionContext(
            session_id=str(session_id or "default")
        )
        clean_text = " ".join(str(turn_text or "").split()).strip()
        if not clean_text:
            return base

        turns = base.conversation_turns + (
            KnowledgeConversationTurn(role=role, content=clean_text),
        )
        update_data: dict[str, object] = {"conversation_turns": turns}

        if role != "user":
            return self._replace_context(base, **update_data)

        turn_index = base.user_turn_index + 1
        extracted = extract_parameters(clean_text)
        merged_parameters = dict(base.mentioned_parameters)
        merged_parameters.update(
            self._parameter_seeds_from_extract(extracted, turn_index=turn_index)
        )
        explored_concepts = self._merge_concepts(
            base.explored_concepts,
            self._extract_concepts(clean_text, extracted),
        )
        signal = self.detect_transition_signal(clean_text, context=base)
        update_data.update(
            {
                "mentioned_parameters": merged_parameters,
                "explored_concepts": explored_concepts,
                "detected_intent": (
                    "bridge_candidate"
                    if signal.kind is TransitionSignalKind.CONCRETE_CASE
                    else "knowledge_query"
                ),
                "user_turn_index": turn_index,
            }
        )
        return self._replace_context(base, **update_data)

    def detect_transition_signal(
        self,
        turn_text: str,
        context: KnowledgeSessionContext | None = None,
    ) -> TransitionSignal:
        reasons: list[str] = []
        text = str(turn_text or "").casefold()
        if re.search(r"\b(meine|mein|unsere|unser|my|our)\b", text):
            reasons.append("possessive_reference")
        if re.search(r"\d+(?:[.,]\d+)?\s*(mm|bar|rpm|u\.?/?min|c|grad)", text):
            reasons.append("concrete_parameter")
        if re.search(
            r"\b(ich\s+brauche|wir\s+brauchen|suche|benoetige|brauche)\b", text
        ):
            reasons.append("explicit_need")
        if re.search(
            r"(welche|was soll|empfiehl|where do i buy|who makes|hersteller)", text
        ):
            reasons.append("outcome_or_match_seeking")
        if context and context.mentioned_parameters:
            reasons.append("session_has_parameters")
        if not reasons:
            return TransitionSignal(TransitionSignalKind.NONE, 0.0, ())
        return TransitionSignal(
            TransitionSignalKind.CONCRETE_CASE,
            min(0.95, 0.35 + 0.12 * len(reasons)),
            tuple(reasons),
        )

    def build_bridge_invitation(
        self,
        turn_text: str,
        *,
        context: KnowledgeSessionContext | None = None,
    ) -> str | None:
        if _is_simple_definition_question(turn_text):
            return None
        signal = self.detect_transition_signal(turn_text, context=context)
        if signal.kind is not TransitionSignalKind.CONCRETE_CASE:
            return None
        if context and context.transition_offered:
            return None
        if context and context.mentioned_parameters:
            return (
                "Wenn das Ihr konkreter Anwendungsfall ist, kann ich die bisher genannten "
                "Angaben direkt in einen technischen Fall überführen und die offenen Punkte "
                "strukturiert weiterklären."
            )
        return (
            "Wenn das in Richtung einer konkreten Anwendung geht, kann ich daraus direkt "
            "einen technischen Fall aufbauen und die fehlenden Betriebsdaten geordnet nachziehen."
        )

    def build_governed_seed(
        self, context: KnowledgeSessionContext
    ) -> KnowledgeCaseSeed:
        observed_extractions = tuple(
            ObservedExtraction(
                field_name=seed.field_name,
                raw_value=seed.raw_value,
                raw_unit=seed.raw_unit,
                source="user",
                confidence=seed.confidence,
                turn_index=seed.source_turn_index,
            )
            for _, seed in sorted(
                context.mentioned_parameters.items(),
                key=lambda item: (item[1].source_turn_index, item[0]),
            )
        )
        conversation_messages = tuple(
            ConversationMessage(role=turn.role, content=turn.content)
            for turn in context.conversation_turns
        )
        observed_topic = self._observed_topic(context)
        tentative_domain_signals = tuple(
            f"knowledge_seed:{field_name}"
            for field_name in sorted(context.mentioned_parameters)
        )
        return KnowledgeCaseSeed(
            conversation_messages=conversation_messages,
            observed_extractions=observed_extractions,
            observed_topic=observed_topic,
            tentative_domain_signals=tentative_domain_signals,
            user_turn_index=context.user_turn_index,
        )

    @staticmethod
    def mark_transition_offered(
        context: KnowledgeSessionContext,
    ) -> KnowledgeSessionContext:
        return KnowledgeSessionContext(
            session_id=context.session_id,
            mentioned_parameters=dict(context.mentioned_parameters),
            explored_concepts=tuple(context.explored_concepts),
            detected_intent=context.detected_intent,
            transition_offered=True,
            conversation_turns=tuple(context.conversation_turns),
            user_turn_index=context.user_turn_index,
        )

    @staticmethod
    def _replace_context(
        context: KnowledgeSessionContext,
        **updates: object,
    ) -> KnowledgeSessionContext:
        payload = {
            "session_id": context.session_id,
            "mentioned_parameters": dict(context.mentioned_parameters),
            "explored_concepts": tuple(context.explored_concepts),
            "detected_intent": context.detected_intent,
            "transition_offered": context.transition_offered,
            "conversation_turns": tuple(context.conversation_turns),
            "user_turn_index": context.user_turn_index,
        }
        payload.update(updates)
        return KnowledgeSessionContext(**payload)

    @staticmethod
    def _merge_concepts(
        existing: tuple[str, ...], new_items: list[str]
    ) -> tuple[str, ...]:
        merged: list[str] = []
        seen: set[str] = set()
        for item in list(existing) + new_items:
            clean = str(item or "").strip()
            if not clean:
                continue
            lowered = clean.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            merged.append(clean)
        return tuple(merged)

    @staticmethod
    def _extract_concepts(turn_text: str, extracted: dict[str, object]) -> list[str]:
        concepts: list[str] = []
        for key in (
            "material_normalized",
            "material_confirmation_required",
            "medium_normalized",
            "medium_confirmation_required",
        ):
            value = extracted.get(key)
            if value:
                concepts.append(str(value))
        for pattern in (
            r"(?:was\s+ist|erklaer\w*|erkl[aä]r\w*|define)\s+([\w\-\/]+)",
            r"(?:unterschied\s+zwischen|difference\s+between)\s+([\w\-\/]+)\s+(?:und|and)\s+([\w\-\/]+)",
        ):
            match = re.search(pattern, turn_text, re.IGNORECASE)
            if not match:
                continue
            concepts.extend(group for group in match.groups() if group)
        return concepts

    @staticmethod
    def _parameter_seeds_from_extract(
        extracted: dict[str, object],
        *,
        turn_index: int,
    ) -> dict[str, ParameterSeed]:
        seeds: dict[str, ParameterSeed] = {}

        def _add(
            field_name: str,
            value: object,
            *,
            unit: str | None = None,
            confidence: float = 0.75,
        ) -> None:
            if value is None:
                return
            seeds[field_name] = ParameterSeed(
                field_name=field_name,
                raw_value=value,
                raw_unit=unit,
                confidence=confidence,
                source_turn_index=turn_index,
            )

        _add(
            "temperature_c", extracted.get("temperature_c"), unit="°C", confidence=0.92
        )
        _add("pressure_bar", extracted.get("pressure_bar"), unit="bar", confidence=0.92)
        _add(
            "shaft_diameter_mm",
            extracted.get("diameter_mm"),
            unit="mm",
            confidence=0.92,
        )
        _add("speed_rpm", extracted.get("speed_rpm"), unit="rpm", confidence=0.92)
        _add("medium", extracted.get("medium_normalized"), confidence=0.85)
        if "medium" not in seeds:
            _add(
                "medium", extracted.get("medium_confirmation_required"), confidence=0.60
            )
        _add("material", extracted.get("material_normalized"), confidence=0.85)
        if "material" not in seeds:
            _add(
                "material",
                extracted.get("material_confirmation_required"),
                confidence=0.60,
            )
        _add("motion_type", extracted.get("motion_type"), confidence=0.88)
        return seeds

    @staticmethod
    def _observed_topic(context: KnowledgeSessionContext) -> str | None:
        last_user_turn = next(
            (
                turn.content
                for turn in reversed(context.conversation_turns)
                if turn.role == "user"
            ),
            "",
        ).strip()
        if last_user_turn:
            return last_user_turn[:160]
        if context.explored_concepts:
            return ", ".join(context.explored_concepts[:3])
        return None


def _is_simple_definition_question(text: str) -> bool:
    normalized = str(text or "").casefold()
    if not normalized.strip():
        return False
    if re.search(r"\d+(?:[.,]\d+)?\s*(mm|bar|rpm|u\.?/?min|c|grad)", normalized):
        return False
    if re.search(
        r"\b(meine|mein|unsere|unser|ich\s+brauche|wir\s+brauchen|suche|benoetige|brauche)\b",
        normalized,
    ):
        return False
    return bool(
        re.search(r"\bwas\s+ist\b", normalized)
        or re.search(r"\bwas\s+bedeutet\b", normalized)
        or re.search(r"\bwas\s+kannst\s+du\s+mir\s+zu\b", normalized)
    )
