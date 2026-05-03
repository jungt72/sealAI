from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern

from app.domain.pre_gate_classification import PreGateClassification


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    classification: PreGateClassification
    confidence: float
    reasoning: str
    escalate_to_graph: bool


class PreGateClassifier:
    """Deterministic-first classifier for the pre-gate boundary."""

    def classify(
        self,
        user_input: str,
        *,
        language_hint: str | None = None,
    ) -> ClassificationResult:
        text = (user_input or "").strip()
        if not text:
            return self._result(
                PreGateClassification.DOMAIN_INQUIRY,
                0.5,
                "empty_or_blank_input_fail_safe",
                escalate_to_graph=True,
            )

        if self._matches(_GREETING_PATTERNS, text):
            return self._result(
                PreGateClassification.GREETING,
                0.98,
                "deterministic_greeting",
            )

        if self._is_social_conversation_without_task(text):
            return self._result(
                PreGateClassification.GREETING,
                0.93,
                "deterministic_social_conversation",
            )

        if self._matches(_META_QUESTION_PATTERNS, text):
            return self._result(
                PreGateClassification.META_QUESTION,
                0.9,
                "deterministic_meta_question",
            )

        if self._matches(_BLOCKED_PATTERNS, text):
            return self._result(
                PreGateClassification.BLOCKED,
                0.9,
                "deterministic_policy_block",
            )

        if self._matches(_RECOVERY_PATTERNS, text):
            return self._result(
                PreGateClassification.RECOVERY,
                0.82,
                "deterministic_recovery",
                escalate_to_graph=True,
            )

        if self._matches(_DEEP_DIVE_PATTERNS, text):
            return self._result(
                PreGateClassification.DEEP_DIVE,
                0.8,
                "deterministic_deep_dive",
            )

        if self._is_generic_material_comparison(text):
            return self._result(
                PreGateClassification.KNOWLEDGE_QUERY,
                0.82,
                "deterministic_material_comparison_knowledge",
            )

        if self._matches(_KNOWLEDGE_QUERY_PATTERNS, text):
            return self._result(
                PreGateClassification.KNOWLEDGE_QUERY,
                0.78,
                "deterministic_knowledge_query",
            )

        if self._matches(_DOMAIN_INQUIRY_PATTERNS, text):
            return self._result(
                PreGateClassification.DOMAIN_INQUIRY,
                0.88,
                "deterministic_domain_inquiry",
                escalate_to_graph=True,
            )

        return self._result(
            PreGateClassification.DOMAIN_INQUIRY,
            0.55,
            "ambiguous_fail_safe_domain_inquiry",
            escalate_to_graph=True,
        )

    def classification(
        self,
        user_input: str,
        *,
        language_hint: str | None = None,
    ) -> PreGateClassification:
        return self.classify(user_input, language_hint=language_hint).classification

    @staticmethod
    def _matches(patterns: tuple[Pattern[str], ...], text: str) -> bool:
        return any(pattern.search(text) for pattern in patterns)

    @staticmethod
    def _is_social_conversation_without_task(text: str) -> bool:
        """Detect human social frontdoor turns before technical intake.

        The classifier must not depend on a small list of exact greetings. Users
        often type greetings with typos, time qualifiers, or wellbeing questions.
        This branch only wins when the message contains social intent and no
        explicit technical, knowledge, or case task markers.
        """

        if not PreGateClassifier._matches(_SOCIAL_CONVERSATION_PATTERNS, text):
            return False
        if PreGateClassifier._matches(_TASK_OR_TECHNICAL_INTENT_PATTERNS, text):
            return False
        return True

    @staticmethod
    def _is_generic_material_comparison(text: str) -> bool:
        if not PreGateClassifier._matches(_MATERIAL_COMPARISON_KNOWLEDGE_PATTERNS, text):
            return False
        if PreGateClassifier._matches(_MATERIAL_COMPARISON_CONCRETE_CASE_PATTERNS, text):
            return False
        return PreGateClassifier._mentions_multiple_materials(text)

    @staticmethod
    def _mentions_multiple_materials(text: str) -> bool:
        materials = {match.group(0).casefold() for match in _MATERIAL_TOKEN_PATTERN.finditer(text)}
        return len(materials) >= 2

    @staticmethod
    def _result(
        classification: PreGateClassification,
        confidence: float,
        reasoning: str,
        *,
        escalate_to_graph: bool = False,
    ) -> ClassificationResult:
        if classification in {
            PreGateClassification.DOMAIN_INQUIRY,
            PreGateClassification.RECOVERY,
        }:
            escalate_to_graph = True
        return ClassificationResult(
            classification=classification,
            confidence=confidence,
            reasoning=reasoning,
            escalate_to_graph=escalate_to_graph,
        )


def _compile(*patterns: str) -> tuple[Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE | re.UNICODE) for pattern in patterns)


_GREETING_PATTERNS = _compile(
    r"^(hallo|hi|hey|moin|servus|grüß\s*(gott|dich)|guten\s*(morgen|tag|abend))[\s!.?,]*$",
    r"^(hallo|hi|hey|moin|servus|guten\s*(morgen|tag|abend))[\s,!.?]+(wie\s+geht('?s|\s+es\s+dir)(?:\s+heute)?)[\s?!.]*$",
    r"^(danke|vielen\s+dank|dankeschön|merci|thanks|thank\s+you)[\s!.?,]*$",
    r"^(tschüss|auf\s+wiedersehen|bis\s+dann|ciao|bye)[\s!.?,]*$",
    r"^wie\s+geht('?s|\s+es\s+dir)[\s?!.]*$",
)

_SOCIAL_CONVERSATION_PATTERNS = _compile(
    r"\bwie\s+geht(?:'s|\s+es)?\s+dir\b",
    r"\bwie\s+geht(?:'s|\s+es)?\s+(ihnen|euch)\b",
    r"\bhow\s+are\s+you\b",
    r"\bhow\s+is\s+it\s+going\b",
    r"\b(alles\s+gut|na\s+du|schoen\s+dich\s+zu\s+sehen|schön\s+dich\s+zu\s+sehen)\b",
    r"\b(guten\s+\w+|gute[nr]?\s+\w+|hallo|hi|hey|moin|servus)\b.*\b(wie\s+geht|alles\s+gut)\b",
)

_TASK_OR_TECHNICAL_INTENT_PATTERNS = _compile(
    r"\b(dichtung|dichtring|dichtstelle|seal|rwdr|radialwellendichtring|gleitringdichtung|o[- ]?ring)\b",
    r"\b(medium|druck|temperatur|drehzahl|welle|pumpe|getriebe|r[üu]hrwerk|flansch|hydraulik|leckage|undicht)\b",
    r"\b(ptfe|fkm|ffkm|fpm|epdm|nbr|hnbr|pu|tpu|vmq|silikon|viton|pfas|reach|echa)\b",
    r"\b(ich\s+brauche|wir\s+brauchen|ben[oö]tige|suche|auslegen|berechne|pr[üu]fe|validieren)\b",
    r"\b(was\s+ist|was\s+bedeutet|wie\s+funktioniert|erkl[aä]r\w*|erklaer\w*|vergleiche|vergleich|unterschied)\b",
    r"\b\d+(?:[.,]\d+)?\s*(?:mm|bar|psi|°?\s*[cCfF]|grad|rpm|u\.?/?min)\b",
)

_META_QUESTION_PATTERNS = _compile(
    r"\b(was\s+kann(?:st)?\s+(sealai|dieses\s+system|das\s+tool|du)\b)",
    r"\b(wer\s+bist\s+du|was\s+bist\s+du)\b",
    r"\b(wie\s+funktioniert\s+(sealai|dieses\s+system|dieses\s+tool|das\s+tool)\b)",
    r"\b(wofür\s+ist\s+(sealai|dieses\s+system|das\s+tool)\b)",
    r"\b(was\s+fehlt\s+(noch|mir|dir)?|welche\s+(angaben|parameter|daten)\s+fehlen)\b",
    r"\b(wie\s+ist\s+der\s+(aktuelle\s+)?(stand|fortschritt))\b",
    r"\b(was\s+(hast\s+du|haben\s+sie)\s+(schon\s+)?(verstanden|erfasst|gespeichert))\b",
    r"\b(welche\s+(angaben|parameter)\s+(brauche|benötige)\s+ich\s+noch)\b",
    r"\bzeig\s+(mir\s+)?(den\s+)?(fortschritt|stand|übersicht|status)\b",
    r"\b(what\s+can\s+(sealai|this\s+tool|you)\s+do\b)",
    r"\b(how\s+does\s+(sealai|this\s+tool)\s+work\b)",
)

# Narrow reuse of existing policy semantics without importing across layers.
_BLOCKED_PATTERNS = _compile(
    r"\bwelch\w*\s+hersteller\b",
    r"\bhersteller[- ]?empfehlung\b",
    r"\b(empfiehl|empfehle)\s+mir\b",
    r"\bwas\s+empfiehlst\s+du\b",
    r"\bwelche[rs]?\s+(werkstoff|material|dichtring)\s+soll\b",
    r"\bwelche\s+dichtung\s+soll\b",
    r"\b(kill\s+yourself|kys)\b",
    r"\b(du\s+bist|you\s+are)\s+(dumm|idiot|stupid|idiot)\b",
)

_DOMAIN_INQUIRY_PATTERNS = _compile(
    r"\b(ich\s+brauche|wir\s+brauchen|benötige|suche)\b.*\b(dichtung|dichtring|seal|rwdr|radialwellendichtring)\b",
    r"\b(auslegung|auslegen|berechne|berechnen|prüfe|prüfen|validieren|validation)\b",
    r"\b(leckage|undicht|ausgefallen|verschleiß|failure|leaking|replacement|ersatzteil)\b",
    r"\b\d+(?:[.,]\d+)?\s*(?:mm|bar|psi|°?\s*[cCfF]|rpm|u\.?/?min)\b",
    r"\b(pumpe|getriebe|welle|gehäuse|shaft|pump|gearbox)\b.*\b(dichtung|seal|rwdr|ptfe)\b",
)

_DEEP_DIVE_PATTERNS = _compile(
    r"\b(warum|weshalb|wieso)\b.*\b(mein(?:em|er|en)?\s+fall|dies(?:em|er|en)\s+fall|dabei|dafür|dafuer|diese\s+anwendung)\b",
    r"\b(erklär\w*|erklaer\w*|erläutere|erlaeutere)\b.*\b(mein(?:em|er|en)?\s+fall|dies(?:em|er|en)\s+fall|dabei|dafür|dafuer|diese\s+anwendung)\b",
    r"\b(was\s+bedeutet|welche\s+rolle\s+spielt)\b.*\b(mein(?:em|er|en)?\s+fall|dies(?:em|er|en)\s+fall|dabei|dafür|dafuer|diese\s+anwendung)\b",
    r"\b(warum|weshalb|wieso)\b.*\b(ptfe|fkm|nbr|epdm|rwdr|gleitringdichtung|radialwellendichtring|werkstoff|medium|druck|temperatur)\b",
    r"\b(deep\s*dive|vertief\w*|tiefer\s+erklären|tiefer\s+erklaeren)\b",
)

_MATERIAL_TOKEN_PATTERN = re.compile(
    r"\b(?:ptfe|fkm|ffkm|fpm|epdm|nbr|hnbr|pu|tpu|vmq|silikon|silicone|viton)\b",
    re.IGNORECASE | re.UNICODE,
)

_MATERIAL_COMPARISON_KNOWLEDGE_PATTERNS = _compile(
    r"\b(vergleiche|vergleich(?:e|en)?|materialvergleich|werkstoffvergleich)\b",
    r"\b(unterschied(?:e)?|difference)\b",
    r"\b(vs\.?|versus|oder|statt|gegen[üu]ber)\b",
    r"\b(wann\s+nimmt\s+man|vorteile?|nachteile?|besser|schlechter)\b",
    r"\b(alternative\s+zu|durch\s+\w+\s+ersetzen)\b",
)

_MATERIAL_COMPARISON_CONCRETE_CASE_PATTERNS = _compile(
    r"\b(meine[rmn]?\s+anwendung|bei\s+meiner\s+anlage|in\s+unserer\s+anwendung|"
    r"ich\s+habe|wir\s+haben|bei\s+uns|unsere[rmn]?)\b",
    r"\b(ich\s+brauche|wir\s+brauchen|brauche\s+eine\s+dichtung|ben[oö]tige|suche)\b",
    r"\b(auslegen|auslegung|lege\s+.*\baus|pr[üu]fe|prüfen|"
    r"ersetzen\s+in\s+(meiner|unserer)\s+anwendung|f[aä]llt\s+aus|leckt|leckage|"
    r"undicht|ausgefallen|verschlei[ßs])\b",
    r"\b\d+(?:[.,]\d+)?\s*(?:mm|bar|psi|°?\s*[cCfF]|grad|rpm|u\.?/?min)\b",
    r"\bmedium\s+(?:ist|=)\b",
    r"\b(?:r[üu]hrwerk|pumpe|getriebe|welle|kolben|flansch|hydraulik)\b.*"
    r"\b(?:dichtung|dichtstelle|seal|medium|[oö]l|bar|grad|rpm|mm)\b",
)

_KNOWLEDGE_QUERY_PATTERNS = _compile(
    r"^\s*(was\s+ist|was\s+bedeutet|was\s+versteht|erklär\w*|erklaer\w*|definiere)\b",
    r"^\s*(what\s+is|explain|define)\b",
    r"\b(unterschied\s+zwischen|vergleich\s+zwischen|difference\s+between)\b",
    r"^\s*vergleich\b",
    r"\b(wie\s+funktioniert\s+(ein|eine)\b|how\s+does\s+(a|an)\b)",
)

_RECOVERY_PATTERNS = _compile(
    r"\b(korrigier\w*|korrektur|berichtige|ändere|aendere)\b",
    r"\b(das\s+stimmt\s+nicht|das\s+war\s+falsch|falsch\b|nicht\s+korrekt)\b",
    r"\b(nicht\s+sondern|nicht\b.+\bsondern|sondern\s+eigentlich|stattdessen|gemeint\s+war|ich\s+meinte)\b",
    r"\b(vergiss\s+das|nimm\s+das\s+zurück|nimm\s+das\s+zurueck)\b",
)
