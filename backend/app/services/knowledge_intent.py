from __future__ import annotations

import re
from typing import Pattern


def _compile(*patterns: str) -> tuple[Pattern[str], ...]:
    return tuple(
        re.compile(pattern, re.IGNORECASE | re.UNICODE) for pattern in patterns
    )


TECHNICAL_SUBJECT_PATTERNS = _compile(
    r"\b(ptfe|fkm|ffkm|fpm|epdm|nbr|hnbr|pu|tpu|pom|peek|pa6?|pa12|vmq|silikon|silicone|viton|pfas|reach|echa)\b",
    r"\b(kl[üu]ber|klueber|klübersynth|kluebersynth|uh1|hydraulik[oö]l|hydraulikoel|fett|schmierstoff)\b",
    r"\b(radialwellendichtring|rwdr|gleitringdichtung|werkstoff|elastomer|thermoplast|medium|best[aä]ndigkeit|bestaendigkeit)\b",
)

KNOWLEDGE_INFORMATION_REQUEST_PATTERNS = _compile(
    r"\b(?:infos?|informationen|details|einordnung|einsch[aä]tzung|überblick|ueberblick|hintergrund|wissen)"
    r"\s+(?:zu|ueber|über)\b",
    r"\b(?:bitte\s+)?(?:gib|geb|gebe|geben|nenn|nenne|liefer|liefere|zeig|zeige|beschreib|beschreibe)\w*"
    r"\s+(?:mir|uns)?\s*(?:bitte\s+)?(?:detaillierte\s+|mehr\s+|kurze\s+|eine\s+)?"
    r"(?:informationen|infos|details|einordnung|einsch[aä]tzung|überblick|ueberblick|hintergrund|wissen)"
    r"\s+(?:zu|ueber|über)\b",
    r"\b(?:ich|wir)\s+(?:h[aä]tte|haette|h[aä]tten|haetten|habe|haben)\s+gern"
    r"\s+(?:detaillierte\s+|mehr\s+|eine\s+)?"
    r"(?:informationen|infos|details|einordnung|einsch[aä]tzung|überblick|ueberblick|hintergrund)"
    r"\s+(?:zu|ueber|über)\b",
    r"\b(?:kannst|könntest|koenntest)\s+du\s+(?:mir|uns)?\s*(?:bitte\s+)?"
    r"(?:detaillierte\s+|mehr\s+|eine\s+)?"
    r"(?:informationen|infos|details|einordnung|einsch[aä]tzung|überblick|ueberblick|hintergrund)"
    r"\s+(?:zu|ueber|über)\b",
)

CONCRETE_CASE_MARKER_PATTERNS = _compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mm|bar|barg|bara|psi|°?\s*[cCfF]|grad|rpm|u\.?/?min)\b",
    r"\b(salzwasser|wasser|öl|oel|ethanol|dampf|medium)\b.*\b(\d|bar|grad|welle|pumpe|ruehrwerk|rührwerk)\b",
    r"\b(rotierende?\s+welle|welle|pumpe|ruehrwerk|rührwerk|getriebe)\b.*\b(salzwasser|wasser|öl|oel|ethanol|medium|ptfe|fkm|nbr|epdm)\b",
)


def _matches(patterns: tuple[Pattern[str], ...], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def has_technical_knowledge_subject(message: str) -> bool:
    text = str(message or "").strip()
    return bool(text) and _matches(TECHNICAL_SUBJECT_PATTERNS, text)


def is_information_request_about_technical_subject(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    return _matches(KNOWLEDGE_INFORMATION_REQUEST_PATTERNS, text) and has_technical_knowledge_subject(text)


def is_standalone_technical_subject(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    words = re.findall(r"[\wäöüÄÖÜß+-]+", text, flags=re.UNICODE)
    return 1 <= len(words) <= 4 and has_technical_knowledge_subject(text)


def contains_concrete_case_marker(message: str) -> bool:
    text = str(message or "").strip()
    return bool(text) and _matches(CONCRETE_CASE_MARKER_PATTERNS, text)
