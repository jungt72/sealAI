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
    def _result(
        classification: PreGateClassification,
        confidence: float,
        reasoning: str,
        *,
        escalate_to_graph: bool = False,
    ) -> ClassificationResult:
        if classification is PreGateClassification.DOMAIN_INQUIRY:
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
    r"^(danke|vielen\s+dank|dankeschön|merci|thanks|thank\s+you)[\s!.?,]*$",
    r"^(tschüss|auf\s+wiedersehen|bis\s+dann|ciao|bye)[\s!.?,]*$",
    r"^wie\s+geht('?s|\s+es\s+dir)[\s?!.]*$",
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

_KNOWLEDGE_QUERY_PATTERNS = _compile(
    r"^\s*(was\s+ist|was\s+bedeutet|was\s+versteht|erklär\w*|erklaer\w*|definiere)\b",
    r"^\s*(what\s+is|explain|define)\b",
    r"\b(unterschied\s+zwischen|vergleich\s+zwischen|difference\s+between)\b",
    r"^\s*vergleich\b",
    r"\b(wie\s+funktioniert\s+(ein|eine)\b|how\s+does\s+(a|an)\b)",
)
