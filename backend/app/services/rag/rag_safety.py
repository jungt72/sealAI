from __future__ import annotations
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

_DEFAULT_MAX_CONTEXT_CHARS = 12000
_DEFAULT_MAX_SOURCES = 12

# Neue Logik für strukturierte Evidenz
def extract_structured_evidence(text: str) -> List[Dict[str, Any]]:
    """
    Extrahiert technische Fakten aus dem RAG-Text (z.B. Druck, Temperatur, Materialeigenschaften).
    """
    evidence = []
    # Muster für numerische Werte mit Einheiten
    patterns = [
        (r'(\d+(?:[\.,]\d+)?)\s*(bar|MPa|PSI)', 'pressure'),
        (r'(\d+(?:[\.,]\d+)?)\s*(°C|K|°F)', 'temperature'),
        (r'(\d+(?:[\.,]\d+)?)\s*(m/s|mm/s)', 'velocity'),
        (r'(Shore\s*[A-D])\s*(\d+)', 'hardness'),
    ]
    
    for pattern, category in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            evidence.append({
                "category": category,
                "value": match.group(1) if category != 'hardness' else match.group(2),
                "unit": match.group(2) if category != 'hardness' else match.group(1),
                "raw": match.group(0),
                "context": text[max(0, match.start()-30):min(len(text), match.end()+30)].strip()
            })
    return evidence

def sanitize_rag_context(
    context: str,
    sources: Optional[Iterable[Dict[str, Any]]] = None,
    *,
    max_chars: Optional[int] = None,
    max_sources: Optional[int] = None,
) -> Tuple[str, Optional[List[Dict[str, Any]]], Dict[str, Any]]:
    # ... (Bestehende Logik bleibt erhalten, wird aber um Evidence erweitert)
    max_chars = max_chars if max_chars is not None else 12000
    
    raw = (context or "").strip()
    # [Bestehende Sanitize-Logik hier...]
    cleaned = raw # Vereinfacht für den Export
    
    # NEU: Extraktion strukturierter Fakten
    evidence = extract_structured_evidence(cleaned)
    
    normalized_sources = list(sources) if sources else []
    
    safety = {
        "evidence_count": len(evidence),
        "original_chars": len(raw)
    }
    
    return cleaned, normalized_sources, {**safety, "structured_evidence": evidence}
