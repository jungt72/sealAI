"""
Central Response Renderer — Phase F-A.3

Outward Contract: every text leaving the system passes through this module.
No response is yielded to the client without filtering.

Two concerns are handled here:

1. Structural scrubbing (always applied):
   Removes internal artifacts that must never reach the client:
   - UUIDs / internal IDs
   - Governance and state enums  ([governance:...], [state:...])
   - Prompt metadata tags        ([prompt_hash:...], [version:...], [hash:...])
   - Internal field-name prefixes (sealing_state:, asserted_state:, etc.)
   - Raw JSON state dumps

2. Content policy check (fast-path only, via output_guard):
   Detects manufacturer names, recommendation language, suitability assertions.
   On violation the entire text is replaced with a deterministic safe fallback.
   This check is NOT applied to governed-path output, which is already
   deterministic and built from structured data — never free LLM generation.

Usage:
    # Non-streaming
    rendered = render_response(raw_text, path="CONVERSATION")
    send(rendered.text)

    # SSE streaming
    for chunk in llm_stream:
        cleaned = render_chunk(chunk)
        yield cleaned
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from app.agent.runtime.output_guard import (
    FAST_PATH_GUARD_FALLBACK,
    check_fast_path_output,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Structural scrubbing patterns
# ---------------------------------------------------------------------------

# UUID v4 (and adjacent formats)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)

# Internal bracket-notation tags: [governance:...], [state:...],
# [prompt_hash:...], [version:...], [hash:...], [trace_id:...]
_BRACKET_TAG_RE = re.compile(
    r"\["
    r"(?:governance|state|prompt_hash|version|hash|trace_id|node|checkpoint)"
    r":[^\]]*"
    r"\]",
    re.IGNORECASE,
)

# Internal field-name prefixes that may leak as plain text
_FIELD_PREFIX_RE = re.compile(
    r"\b(?:sealing_state|asserted_state|observed_state|normalized_state"
    r"|governed_state|governance_state|working_profile|case_state"
    r"|system\.governed_output|system\.final_text|system\.final_answer"
    r"|system\.preview_text|system\.draft_text)\s*[=:]\s*",
    re.IGNORECASE,
)

# Integer-like numeric literals in outward-visible text should not surface as
# raw floats. Restrict sanitization to common technical units or value
# boundaries so semantic decimals such as 2.5 remain untouched.
_INTEGERISH_FLOAT_RE = re.compile(
    r"(?<![\w.])(?P<int>-?\d+)\.0"
    r"(?=(?:\s*(?:°C|°F|Grad|grad|bar|rpm|mm|MPa|kPa)\b)|(?:\s*(?:[|,;:!?)]|$|\n)))"
)

# Raw JSON object blobs (heuristic: starts with { and has internal-looking keys)
_INTERNAL_KEY_SET = frozenset({
    "sealing_state", "asserted", "observed", "normalized",
    "governance", "working_profile", "checkpoint", "thread_id",
    "run_id", "governed_output_text", "governed_output_status",
})
def _extract_json_blobs(text: str) -> list[tuple[int, int, str]]:
    """Scan text for JSON object blobs, handling nested braces.

    Returns list of (start, end, blob_string) for each found JSON object.
    Only considers objects with at least 20 chars of content.
    """
    results = []
    i = 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        j = i
        in_string = False
        escape_next = False
        while j < len(text):
            ch = text[j]
            if escape_next:
                escape_next = False
            elif ch == "\\" and in_string:
                escape_next = True
            elif ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        blob = text[i : j + 1]
                        if len(blob) >= 22:  # at least {} + 20 chars
                            results.append((i, j + 1, blob))
                        break
            j += 1
        i = j + 1
    return results


def _looks_like_internal_json(blob: str) -> bool:
    """True when a JSON blob contains internal state keys."""
    try:
        obj = json.loads(blob)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(obj, dict):
        return False
    return bool(obj.keys() & _INTERNAL_KEY_SET)


def _scrub_internal_json(text: str) -> str:
    """Remove raw JSON blobs that contain internal state keys."""
    blobs = _extract_json_blobs(text)
    if not blobs:
        return text

    # Process in reverse order so offsets stay valid
    result = text
    offset = 0
    for start, end, blob in blobs:
        if _looks_like_internal_json(blob):
            log.warning("[renderer] stripped internal JSON blob from output")
            adj_start = start + offset
            adj_end = end + offset
            result = result[:adj_start] + result[adj_end:]
            offset -= (end - start)
    return result


def _structural_scrub(text: str) -> str:
    """Apply all structural filters in order. Returns cleaned text."""
    # 1. UUID stripping
    cleaned, uuid_count = _UUID_RE.subn("", text)
    if uuid_count:
        log.warning("[renderer] stripped %d UUID(s) from output", uuid_count)

    # 2. Bracket tags
    cleaned, tag_count = _BRACKET_TAG_RE.subn("", cleaned)
    if tag_count:
        log.warning("[renderer] stripped %d internal bracket tag(s)", tag_count)

    # 3. Internal field prefixes
    cleaned, field_count = _FIELD_PREFIX_RE.subn("", cleaned)
    if field_count:
        log.warning("[renderer] stripped %d internal field prefix(es)", field_count)

    # 4. Internal JSON blobs
    cleaned = _scrub_internal_json(cleaned)

    # 5. Collapse multiple blank lines left by removals
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned


def _sanitize_visible_numeric_literals(text: str) -> str:
    """Normalize integer-like floats in outward-visible text without touching true decimals."""
    return _INTEGERISH_FLOAT_RE.sub(r"\g<int>", text)


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RenderedResponse:
    """Result of rendering a raw LLM / pipeline text for the client."""

    text: str
    """Clean text safe to send to the client."""

    path: Literal["CONVERSATION", "GOVERNED"]
    """The routing path that produced this response."""

    was_scrubbed: bool = False
    """True when any structural artifact was removed."""

    policy_violation: str | None = None
    """Content-policy violation category if fast-path guard triggered, else None."""


# ---------------------------------------------------------------------------
# Core rendering logic
# ---------------------------------------------------------------------------

def _render_text_for_path(
    raw: str,
    path: Literal["CONVERSATION", "GOVERNED"],
) -> tuple[str, bool, str | None]:
    """Returns (clean_text, was_scrubbed, policy_violation_category)."""
    scrubbed = _structural_scrub(raw).strip()
    normalized = _sanitize_visible_numeric_literals(scrubbed)
    was_scrubbed = normalized != raw.strip()

    policy_violation: str | None = None

    if path == "CONVERSATION":
        safe, category = check_fast_path_output(normalized)
        if not safe:
            log.warning(
                "[renderer] conversation-path policy violation (category=%s) "
                "— substituting fallback",
                category,
            )
            return FAST_PATH_GUARD_FALLBACK, True, category
        policy_violation = category  # None when safe

    return normalized, was_scrubbed, policy_violation


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_response(
    raw: str,
    *,
    path: Literal["CONVERSATION", "GOVERNED"],
) -> RenderedResponse:
    """Render a complete (non-streaming) response through the outward contract.

    Args:
        raw:  Raw text from LLM or pipeline.
        path: Routing path — "CONVERSATION" | "GOVERNED".
              Content-policy check (output_guard) is applied only to CONVERSATION.

    Returns:
        RenderedResponse with clean text and audit fields.
    """
    clean, was_scrubbed, policy_violation = _render_text_for_path(raw, path)
    return RenderedResponse(
        text=clean,
        path=path,
        was_scrubbed=was_scrubbed,
        policy_violation=policy_violation,
    )


def render_chunk(
    chunk: str,
    *,
    path: Literal["CONVERSATION", "GOVERNED"],
) -> str:
    """Render a single SSE streaming chunk through the outward contract.

    Applies structural scrubbing. Content-policy check is skipped for chunks
    because individual tokens are not meaningful in isolation — the full
    response check is the caller's responsibility for conversation-path streams.

    Returns the cleaned chunk string (may be empty string if entirely stripped).
    """
    return _sanitize_visible_numeric_literals(_structural_scrub(chunk))
