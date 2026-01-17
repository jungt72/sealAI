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
    max_chars = max_chars if max_chars is not None else _DEFAULT_MAX_CONTEXT_CHARS
    max_sources = max_sources if max_sources is not None else _DEFAULT_MAX_SOURCES

    raw = (context or "").strip()
    original_chars = len(raw)

    removed_lines = 0
    redacted = 0

    lines = raw.splitlines()
    kept: List[str] = []
    for line in lines:
        if re.search(r"system:", line, re.IGNORECASE) or re.search(
            r"ignore previous instructions", line, re.IGNORECASE
        ):
            removed_lines += 1
            continue
        kept.append(line)

    cleaned = "\n".join(kept).strip()

    redaction_patterns = [
        r"sk-[A-Za-z0-9]{8,}",
        r"\bBearer\s+[A-Za-z0-9\-_\.]+\b",
        r"\bAuthorization:\s*\S+",
        r"\bpassword\s*=\s*\S+",
        r"\bapi_key\s*=\s*\S+",
        r"\bsecret\s*=\s*\S+",
    ]
    for pattern in redaction_patterns:
        cleaned, count = re.subn(pattern, "[REDACTED]", cleaned, flags=re.IGNORECASE)
        redacted += count

    truncated = False
    if max_chars is not None and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars]
        cleaned = cleaned.rstrip()
        cleaned = f"{cleaned}\n[Context truncated to {max_chars} chars for safety]"
        truncated = True

    sources_list = list(sources) if sources else []
    normalized_sources: List[Dict[str, Any]] = []
    seen_sources: set[str] = set()
    deduped = 0
    if sources_list:
        for item in sources_list:
            source_val = (item or {}).get("source")
            if not isinstance(source_val, str):
                continue
            source_val = source_val.strip()
            if not source_val:
                continue
            if source_val in seen_sources:
                deduped += 1
                continue
            seen_sources.add(source_val)
            normalized_sources.append({"source": source_val})
            if len(normalized_sources) >= max_sources:
                break

    if normalized_sources:
        source_lines = [f"Quelle: {item['source']}" for item in normalized_sources if item.get("source")]
        if source_lines:
            cleaned = f"{cleaned}\n" + "\n".join(source_lines)

    evidence = extract_structured_evidence(cleaned)
    safety: Dict[str, Any] = {
        "original_chars": original_chars,
        "removed_lines": removed_lines,
        "redacted": redacted,
        "truncated": truncated,
        "sources": {
            "input": len(sources_list),
            "deduped": deduped,
            "returned": len(normalized_sources),
        },
        "structured_evidence": evidence,
        "evidence_count": len(evidence),
    }

    return cleaned, normalized_sources or None, safety
