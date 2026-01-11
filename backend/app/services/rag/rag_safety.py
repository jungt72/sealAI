from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

_DEFAULT_MAX_CONTEXT_CHARS = 12000
_DEFAULT_MAX_SOURCES = 12

_INJECTION_PATTERNS = [
    re.compile(r"ignore previous instructions", re.IGNORECASE),
    re.compile(r"^system\s*:", re.IGNORECASE),
    re.compile(r"^developer\s*:", re.IGNORECASE),
    re.compile(r"^assistant\s*:", re.IGNORECASE),
    re.compile(r"you are chatgpt", re.IGNORECASE),
    re.compile(r"begin system prompt", re.IGNORECASE),
    re.compile(r"end system prompt", re.IGNORECASE),
    re.compile(r"override.*instructions", re.IGNORECASE),
]

_REDACTION_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9]{10,}\b"), "[REDACTED]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._\\-]+\b", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"\bAuthorization\s*:\s*.+$", re.IGNORECASE), "Authorization: [REDACTED]"),
    (re.compile(r"\bpassword\s*=\s*\S+", re.IGNORECASE), "password=[REDACTED]"),
    (re.compile(r"\bapi_key\s*=\s*\S+", re.IGNORECASE), "api_key=[REDACTED]"),
    (re.compile(r"\bsecret\s*=\s*\S+", re.IGNORECASE), "secret=[REDACTED]"),
]


def _get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _should_drop_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(stripped):
            return True
    return False


def _is_bare_source_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.lower().startswith("quelle:"):
        return False
    return bool(re.match(r"^(https?://|www\.)", stripped, flags=re.IGNORECASE))


def _normalize_source_line(line: str) -> str:
    stripped = line.strip()
    if _is_bare_source_line(stripped):
        return f"Quelle: {stripped}"
    if stripped.lower().startswith("quelle:"):
        value = stripped.split(":", 1)[1].strip()
        return f"Quelle: {value}" if value else "Quelle:"
    return stripped


def _redact_text(text: str) -> Tuple[str, int]:
    redacted = text
    total = 0
    for pattern, replacement in _REDACTION_PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        total += count
    return redacted, total


def _normalize_sources(sources: Optional[Iterable[Dict[str, Any]]], max_sources: int) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    normalized: List[Dict[str, Any]] = []
    seen = set()
    total = 0
    for item in sources or []:
        if not isinstance(item, dict):
            continue
        total += 1
        source = item.get("source")
        if isinstance(source, str):
            source_value = source.strip()
        else:
            source_value = ""
        key = source_value.lower()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        cleaned = dict(item)
        if source_value:
            cleaned["source"] = source_value
        normalized.append(cleaned)
    deduped = len(normalized)
    if max_sources > 0 and len(normalized) > max_sources:
        normalized = normalized[:max_sources]
    return normalized, {"total": total, "deduped": deduped, "kept": len(normalized)}


def sanitize_rag_context(
    context: str,
    sources: Optional[Iterable[Dict[str, Any]]] = None,
    *,
    max_chars: Optional[int] = None,
    max_sources: Optional[int] = None,
) -> Tuple[str, Optional[List[Dict[str, Any]]], Dict[str, Any]]:
    max_chars = max_chars if max_chars is not None else _get_int_env("RAG_MAX_CONTEXT_CHARS", _DEFAULT_MAX_CONTEXT_CHARS)
    max_sources = max_sources if max_sources is not None else _get_int_env("RAG_MAX_SOURCES", _DEFAULT_MAX_SOURCES)

    raw = (context or "").strip()
    removed_lines = 0
    kept_lines: List[str] = []
    for line in raw.splitlines():
        if _should_drop_line(line):
            removed_lines += 1
            continue
        kept_lines.append(_normalize_source_line(line))
    cleaned = "\n".join(kept_lines).strip()

    cleaned, redacted_count = _redact_text(cleaned)

    truncated = False
    original_chars = len(cleaned)
    if max_chars > 0 and len(cleaned) > max_chars:
        truncated = True
        cleaned = cleaned[:max_chars].rstrip()
        cleaned = f"{cleaned}\n[Context truncated to {max_chars} chars for safety]"

    normalized_sources, source_stats = _normalize_sources(sources, max_sources)

    safety: Dict[str, Any] = {
        "removed_lines": removed_lines,
        "redacted": redacted_count,
        "truncated": truncated,
        "max_chars": max_chars,
        "original_chars": original_chars,
        "max_sources": max_sources,
        "sources": source_stats,
    }
    return cleaned, normalized_sources if sources is not None else None, safety


__all__ = ["sanitize_rag_context"]
