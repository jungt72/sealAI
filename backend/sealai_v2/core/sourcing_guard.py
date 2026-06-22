"""sourcing_guard -- deterministischer Guard gegen Hersteller-/RFQ-Text in L1-Ausgaben.

Reine Funktion: kein I/O, kein LLM, keine Kernel-Importe.
Konservativ: im Zweifel NICHT strippen (false-negative besser als technischen Inhalt verlieren).
"""

from __future__ import annotations

import re

# Satztrenner: nach Satzende-Zeichen (.!?) gefolgt von Leerzeichen.
_SENTENCE_SEP = re.compile(r"(?<=[.!?])\s+")

# Muster fuer eindeutige Beschaffungs-/RFQ-Saetze (INC-2 Definition a/b/c).
# Jedes Muster muss fuer sich allein eine klare Beschaffungs-Handlung signalisieren.
_SOURCING_PATTERNS: tuple[re.Pattern, ...] = (  # type: ignore[type-arg]
    # (c) "Fordern Sie ... an" -- Angebots-/Beschaffungs-Imperativ
    re.compile(r"\bFordern\s+Sie\b.+\ban\b", re.IGNORECASE),
    # (c) "Angebot anfordern / einholen / anfragen"
    re.compile(r"\bAngebot\s+(anfordern|einholen|anfragen)\b", re.IGNORECASE),
    # (c) "bestellen Sie bei"
    re.compile(r"\bbestellen\s+Sie\s+bei\b", re.IGNORECASE),
    # (c) "Bezugsquelle:"
    re.compile(r"\bBezugsquelle\s*:", re.IGNORECASE),
    # (a)+(b) "wenden/kontaktieren Sie ... Angebot"
    re.compile(r"\b(wenden|kontaktieren)\s+Sie\b.+\bAngebot\b", re.IGNORECASE),
)


def _is_sourcing_sentence(sentence: str) -> bool:
    """True wenn der Satz eindeutig eine Beschaffungs-Handlung anweist."""
    return any(p.search(sentence) for p in _SOURCING_PATTERNS)


def strip_sourcing(text: str) -> str:
    """Entfernt RFQ-/Beschaffungssaetze aus *text*; gibt den bereinigten String zurueck.

    Satzweise: nur eindeutige Beschaffungs-Imperative werden entfernt.
    Im Zweifel bleibt der Satz erhalten (konservativ, kein false-positive).
    Keine LLM-Aufrufe, kein Netz, keine I/O-Abhaengigkeiten.
    """
    sentences = _SENTENCE_SEP.split(text)
    kept = [s for s in sentences if not _is_sourcing_sentence(s)]
    if len(kept) == len(sentences):
        return text
    return " ".join(s.strip() for s in kept if s.strip())
