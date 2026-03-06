"""Authority-aware context assembly for final answer generation."""

from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import structlog

try:
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    tiktoken = None

logger = structlog.get_logger("langgraph_v2.context_manager")

SYSTEM_POLICY_BUDGET_TOKENS = 500
CONTRACT_BUDGET_TOKENS = 500
DEFAULT_MAX_TOKENS = 3000
DEFAULT_SIMILARITY_THRESHOLD = 0.92
CHARS_PER_TOKEN_FALLBACK = 4

AUTHORITY_NORM_STANDARD = 1.0
AUTHORITY_MANUFACTURER_SPEC = 0.9
AUTHORITY_INTERNAL_WIKI = 0.7
AUTHORITY_FORUM_UNKNOWN = 0.3

_STANDARD_PATTERNS = (
    r"\bnorm\b",
    r"\bnorms\b",
    r"\bnormen\b",
    r"\bstandard\b",
    r"\bstandards\b",
    r"\bdin\b",
    r"\ben\s?\d",
    r"\biso\b",
    r"\bastm\b",
    r"\bvdi\b",
    r"\bapi\b",
)
_MANUFACTURER_PATTERNS = (
    r"\bmanufacturer\b",
    r"\bhersteller\b",
    r"\bdatasheet\b",
    r"\bdatenblatt\b",
    r"\bspec\b",
    r"\bspecification\b",
    r"\bproduct\b",
    r"\bprodukt\b",
)
_INTERNAL_PATTERNS = (
    r"\binternal\b",
    r"\bintern\b",
    r"\bwiki\b",
    r"\bknowledge\s*base\b",
    r"\bkb\b",
    r"\bconfluence\b",
    r"\bnotion\b",
)
_FORUM_PATTERNS = (
    r"\bforum\b",
    r"\bcommunity\b",
    r"\breddit\b",
    r"\bstack\s*overflow\b",
    r"\bunverified\b",
    r"\bunknown\b",
)


class _TokenCounter:
    def __init__(self) -> None:
        self._encoder = None
        if tiktoken is None:
            logger.info("context_manager.tiktoken_unavailable", fallback="char_estimate")
            return
        try:
            self._encoder = tiktoken.get_encoding("cl100k_base")
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "context_manager.tiktoken_init_failed",
                error=str(exc),
                fallback="char_estimate",
            )

    def count(self, text: str) -> int:
        payload = text or ""
        if self._encoder is not None:
            return len(self._encoder.encode(payload))
        return max(1, (len(payload) + CHARS_PER_TOKEN_FALLBACK - 1) // CHARS_PER_TOKEN_FALLBACK)

    def truncate(self, text: str, max_tokens: int) -> str:
        payload = (text or "").strip()
        if max_tokens <= 0 or not payload:
            return ""
        if self._encoder is not None:
            token_ids = self._encoder.encode(payload)
            if len(token_ids) <= max_tokens:
                return payload
            return self._encoder.decode(token_ids[:max_tokens]).strip()
        max_chars = max_tokens * CHARS_PER_TOKEN_FALLBACK
        return payload[:max_chars].strip()


_TOKEN_COUNTER = _TokenCounter()


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dict(dumped)
    return {}


def _state_get(state: Any, key: str, default: Any = None) -> Any:
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _compact(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _first_str(data: Mapping[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and not isinstance(value, (dict, list, tuple, set)):
            casted = str(value).strip()
            if casted:
                return casted
    return None


def _numeric(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pattern_match(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def evidence_authority_score(metadata: Optional[Mapping[str, Any]], source_hint: Optional[str] = None) -> float:
    """Score evidence authority: norms > manufacturer > internal > forum/unknown."""
    md = dict(metadata or {})
    haystack = " ".join(
        filter(
            None,
            [
                _first_str(md, "domain", "category", "source_type", "source", "title", "section"),
                _first_str(md, "document_type", "doc_type", "knowledge_type"),
                source_hint or "",
            ],
        )
    )
    haystack = _compact(haystack).lower()
    if _pattern_match(haystack, _STANDARD_PATTERNS):
        inferred = AUTHORITY_NORM_STANDARD
    elif _pattern_match(haystack, _MANUFACTURER_PATTERNS):
        inferred = AUTHORITY_MANUFACTURER_SPEC
    elif _pattern_match(haystack, _INTERNAL_PATTERNS):
        inferred = AUTHORITY_INTERNAL_WIKI
    elif _pattern_match(haystack, _FORUM_PATTERNS):
        inferred = AUTHORITY_FORUM_UNKNOWN
    else:
        inferred = AUTHORITY_FORUM_UNKNOWN

    # Optional metadata confidence guard: a source that "sounds official" but
    # is explicitly marked low-trust must not outrank trusted evidence.
    source_class = md.get("source_class")
    if source_class is not None:
        try:
            source_class_f = max(0.0, min(1.0, float(source_class)))
            inferred = min(inferred, source_class_f)
        except (TypeError, ValueError):
            pass
    return inferred


def _chunk_text(chunk: Mapping[str, Any]) -> str:
    for key in ("text", "snippet", "content", "chunk_text"):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip():
            return _sanitize_context_text(value)
    return ""


def _sanitize_context_text(value: Any) -> str:
    lines: List[str] = []
    for raw_line in str(value or "").splitlines():
        line = _compact(raw_line)
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("[system/policy]") or lower.startswith("[contract/calc]") or lower.startswith("[rag facts]"):
            continue
        if lower.startswith("**gefundene informationen aus der wissensdatenbank:**"):
            continue
        if lower.startswith("- dokument:"):
            continue
        if lower.startswith("quelle:"):
            continue
        if lower.startswith("[authority="):
            continue
        if "| abschnitt:" in lower or "| section:" in lower or "| score:" in lower:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _chunk_score(chunk: Mapping[str, Any], metadata: Mapping[str, Any]) -> float:
    return _numeric(
        chunk.get("fused_score")
        or chunk.get("vector_score")
        or chunk.get("score")
        or metadata.get("score")
        or metadata.get("rank_score"),
        default=0.0,
    )


def _chunk_identity(
    chunk: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    fallback_text: str,
    index: int,
) -> str:
    document_id = _first_str(chunk, "document_id", "doc_id") or _first_str(metadata, "document_id", "doc_id")
    chunk_id = _first_str(chunk, "chunk_id", "point_id", "id") or _first_str(metadata, "chunk_id", "point_id", "id")
    chunk_index = _first_str(chunk, "chunk_index") or _first_str(metadata, "chunk_index")
    if document_id and chunk_id:
        return f"{document_id}:{chunk_id}"
    if chunk_id:
        return f"chunk:{chunk_id}"
    if document_id and chunk_index:
        return f"{document_id}#{chunk_index}"
    if document_id:
        return f"doc:{document_id}"
    digest = hashlib.sha256((fallback_text or f"idx:{index}").encode("utf-8")).hexdigest()[:16]
    return f"text:{digest}"


def _normalize_chunk(raw_chunk: Mapping[str, Any], index: int) -> Optional[Dict[str, Any]]:
    metadata = _as_dict(raw_chunk.get("metadata"))
    text = _chunk_text(raw_chunk)
    if not text:
        logger.warning("context_manager.skip_chunk_without_text", index=index)
        return None
    source = (
        _first_str(raw_chunk, "source", "filename", "source_uri")
        or _first_str(metadata, "source", "filename", "source_uri")
        or "unknown"
    )
    authority = evidence_authority_score(metadata, source_hint=source)
    score = _chunk_score(raw_chunk, metadata)
    identity = _chunk_identity(raw_chunk, metadata, fallback_text=text, index=index)
    return {
        "identity": identity,
        "document_id": _first_str(raw_chunk, "document_id", "doc_id") or _first_str(metadata, "document_id", "doc_id"),
        "chunk_id": _first_str(raw_chunk, "chunk_id") or _first_str(metadata, "chunk_id"),
        "source": source,
        "text": text,
        "metadata": metadata,
        "authority_score": authority,
        "retrieval_score": score,
    }


def _rank_key(chunk: Mapping[str, Any]) -> Tuple[float, float, int]:
    return (
        _numeric(chunk.get("authority_score"), 0.0),
        _numeric(chunk.get("retrieval_score"), 0.0),
        len(str(chunk.get("text") or "")),
    )


def _normalized_text_for_similarity(text: str) -> str:
    lowered = _compact(text).lower()
    lowered = re.sub(r"[^a-z0-9\s]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _similarity(a: str, b: str) -> float:
    aa = _normalized_text_for_similarity(a)
    bb = _normalized_text_for_similarity(b)
    if not aa or not bb:
        return 0.0
    return SequenceMatcher(None, aa, bb).ratio()


def dedupe_retrieval_chunks(
    chunks: List[Dict[str, Any]],
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> List[Dict[str, Any]]:
    """Deduplicate retrieval chunks by identity and high text similarity."""
    if not isinstance(chunks, list):
        logger.error(
            "context_manager.invalid_chunks_type",
            expected="list",
            got=type(chunks).__name__,
        )
        raise TypeError("chunks must be a list of dictionaries")

    normalized: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            logger.warning(
                "context_manager.skip_non_dict_chunk",
                index=idx,
                got=type(chunk).__name__,
            )
            continue
        item = _normalize_chunk(chunk, idx)
        if item is not None:
            normalized.append(item)

    if not normalized:
        return []

    best_by_identity: Dict[str, Dict[str, Any]] = {}
    for item in normalized:
        key = str(item["identity"])
        current = best_by_identity.get(key)
        if current is None or _rank_key(item) > _rank_key(current):
            best_by_identity[key] = item

    ranked = sorted(best_by_identity.values(), key=_rank_key, reverse=True)
    kept: List[Dict[str, Any]] = []
    for candidate in ranked:
        replacement_index: Optional[int] = None
        for idx, existing in enumerate(kept):
            ratio = _similarity(str(candidate["text"]), str(existing["text"]))
            if ratio < similarity_threshold:
                continue
            if _rank_key(candidate) > _rank_key(existing):
                replacement_index = idx
            else:
                replacement_index = -1
            break
        if replacement_index is None:
            kept.append(candidate)
        elif replacement_index >= 0:
            kept[replacement_index] = candidate

    return sorted(kept, key=_rank_key, reverse=True)


def _extract_system_policy_text(state: Any) -> str:
    parts: List[str] = []
    final_prompt = _state_get(state, "final_prompt", "")
    if isinstance(final_prompt, str) and final_prompt.strip():
        parts.append(final_prompt.strip())

    final_prompt_metadata = _as_dict(_state_get(state, "final_prompt_metadata", {}))
    for key in ("system_prompt", "policy", "policy_text", "constraints"):
        value = final_prompt_metadata.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    user_context = _as_dict(_state_get(state, "user_context", {}))
    for key in ("policy", "policy_context", "system_context"):
        value = user_context.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    unique: List[str] = []
    seen: set[str] = set()
    for part in parts:
        compact = _compact(part)
        if compact and compact not in seen:
            seen.add(compact)
            unique.append(part.strip())
    return "\n\n".join(unique).strip()


def _extract_contract_text(state: Any) -> str:
    payload: Dict[str, Any] = {}

    answer_contract = _as_dict(_state_get(state, "answer_contract", {}))
    if answer_contract:
        payload["answer_contract"] = answer_contract

    calc_results = _state_get(state, "calc_results", None)
    calc_payload = _as_dict(calc_results)
    if calc_payload:
        payload["calc_results"] = calc_payload

    if not payload:
        return ""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _extract_retrieval_chunks(state: Any) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []

    working_memory = _as_dict(_state_get(state, "working_memory", {}))
    panel_material = _as_dict(working_memory.get("panel_material"))
    technical_docs = panel_material.get("technical_docs")
    if isinstance(technical_docs, list):
        for item in technical_docs:
            if isinstance(item, dict):
                chunks.append(dict(item))
            else:
                logger.warning(
                    "context_manager.skip_panel_material_non_dict",
                    got=type(item).__name__,
                )

    retrieval_meta = _as_dict(_state_get(state, "retrieval_meta", {}))
    for key in ("hits", "documents", "chunks"):
        maybe_hits = retrieval_meta.get(key)
        if not isinstance(maybe_hits, list):
            continue
        for item in maybe_hits:
            if isinstance(item, dict):
                chunks.append(dict(item))
            else:
                logger.warning(
                    "context_manager.skip_retrieval_meta_non_dict",
                    key=key,
                    got=type(item).__name__,
                )

    sources = _state_get(state, "sources", [])
    if isinstance(sources, list):
        for item in sources:
            source_dict = _as_dict(item)
            if not source_dict:
                logger.warning(
                    "context_manager.skip_source_without_mapping",
                    got=type(item).__name__,
                )
                continue
            chunks.append(
                {
                    "text": source_dict.get("snippet") or source_dict.get("text") or "",
                    "source": source_dict.get("source"),
                    "metadata": _as_dict(source_dict.get("metadata")),
                    "score": _as_dict(source_dict.get("metadata")).get("score"),
                }
            )

    context_text = _sanitize_context_text(_state_get(state, "context", ""))
    if context_text:
        chunks.append(
            {
                "text": context_text,
                "source": "state.context",
                "metadata": {"source_type": "internal_context"},
                "score": 0.0,
            }
        )

    return chunks


def _fit_block_to_budget(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    return _TOKEN_COUNTER.truncate(text, max_tokens)


def _render_rag_context_block(ranked_chunks: List[Dict[str, Any]], rag_budget_tokens: int) -> str:
    if rag_budget_tokens <= 0 or not ranked_chunks:
        return ""
    remaining = rag_budget_tokens
    lines: List[str] = []
    for chunk in ranked_chunks:
        if remaining <= 0:
            break
        text = _compact(chunk.get("text"))
        if not text:
            continue
        line = f"- {text}"
        tokens = _TOKEN_COUNTER.count(line)
        if tokens <= remaining:
            lines.append(line)
            remaining -= tokens
            continue
        truncated = _TOKEN_COUNTER.truncate(line, remaining)
        if truncated:
            lines.append(truncated)
            remaining = 0
            break
    return "\n".join(lines).strip()


def build_final_context(state: Any, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """Build final context with strict token budgets for policy, contract, and RAG facts."""
    if max_tokens <= 0:
        logger.error("context_manager.invalid_max_tokens", max_tokens=max_tokens)
        raise ValueError("max_tokens must be > 0")

    system_budget = min(SYSTEM_POLICY_BUDGET_TOKENS, max_tokens)
    contract_budget = min(CONTRACT_BUDGET_TOKENS, max(0, max_tokens - system_budget))
    rag_budget = max(0, max_tokens - system_budget - contract_budget)

    if max_tokens < (SYSTEM_POLICY_BUDGET_TOKENS + CONTRACT_BUDGET_TOKENS):
        logger.warning(
            "context_manager.low_total_budget",
            max_tokens=max_tokens,
            system_budget=system_budget,
            contract_budget=contract_budget,
            rag_budget=rag_budget,
        )

    system_policy_text = _fit_block_to_budget(_extract_system_policy_text(state), system_budget)
    contract_text = _fit_block_to_budget(_extract_contract_text(state), contract_budget)

    raw_chunks = _extract_retrieval_chunks(state)
    deduped_chunks = dedupe_retrieval_chunks(raw_chunks)
    rag_text = _render_rag_context_block(deduped_chunks, rag_budget)

    sections: List[str] = []
    if system_policy_text:
        sections.append(f"[System/Policy]\n{system_policy_text}")
    if contract_text:
        sections.append(f"[Contract/Calc]\n{contract_text}")
    if rag_text:
        sections.append(f"[RAG Facts]\n{rag_text}")

    final_context = "\n\n".join(sections).strip()
    logger.info(
        "context_manager.final_context_built",
        max_tokens=max_tokens,
        system_budget=system_budget,
        contract_budget=contract_budget,
        rag_budget=rag_budget,
        system_tokens=_TOKEN_COUNTER.count(system_policy_text) if system_policy_text else 0,
        contract_tokens=_TOKEN_COUNTER.count(contract_text) if contract_text else 0,
        rag_tokens=_TOKEN_COUNTER.count(rag_text) if rag_text else 0,
        raw_chunk_count=len(raw_chunks),
        deduped_chunk_count=len(deduped_chunks),
    )
    return final_context


__all__ = [
    "AUTHORITY_NORM_STANDARD",
    "AUTHORITY_MANUFACTURER_SPEC",
    "AUTHORITY_INTERNAL_WIKI",
    "AUTHORITY_FORUM_UNKNOWN",
    "evidence_authority_score",
    "dedupe_retrieval_chunks",
    "build_final_context",
]
