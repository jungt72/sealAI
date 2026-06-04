from __future__ import annotations

import re
from typing import Any, Literal, TypedDict


ANSWER_TRACE_KEY = "answer_trace"

ReplySource = Literal[
    "fast_responder",
    "knowledge_service",
    "light_conversation",
    "exploration_stream",
    "governed_output_contract",
    "hcl",
    "legacy_renderer",
    "api_guard",
    "llm_guard",
    "unknown",
]

AnswerMarkdownSource = Literal[
    "reply_passthrough",
    "fast_responder",
    "knowledge_service",
    "knowledge_composer",
    "governed_composer",
    "hcl",
    "light_conversation",
    "exploration_stream",
    "legacy_renderer",
    "llm_guard",
    "composer_fallback",
    "deterministic_fallback",
    "unknown",
]

FinalVisibleSource = Literal[
    "answer_markdown",
    "reply",
    "unknown",
]


class AnswerTrace(TypedDict):
    reply_source: ReplySource
    answer_markdown_source: AnswerMarkdownSource
    final_visible_source: FinalVisibleSource
    composer_attempted: bool
    composer_succeeded: bool
    hcl_attempted: bool
    hcl_succeeded: bool
    fallback_reason: str | None


_SAFE_REASON_RE = re.compile(r"[^a-zA-Z0-9_.:-]+")


def safe_fallback_reason(reason: Any, *, limit: int = 96) -> str | None:
    """Return a bounded, non-content fallback reason for public run metadata."""

    text = str(reason or "").strip()
    if not text:
        return None
    sanitized = _SAFE_REASON_RE.sub("_", text).strip("_")
    if not sanitized:
        return None
    return sanitized[:limit]


def build_answer_trace(
    *,
    reply_source: ReplySource = "unknown",
    answer_markdown_source: AnswerMarkdownSource = "unknown",
    final_visible_source: FinalVisibleSource = "unknown",
    composer_attempted: bool = False,
    composer_succeeded: bool = False,
    hcl_attempted: bool = False,
    hcl_succeeded: bool = False,
    fallback_reason: Any = None,
) -> AnswerTrace:
    return {
        "reply_source": reply_source,
        "answer_markdown_source": answer_markdown_source,
        "final_visible_source": final_visible_source,
        "composer_attempted": bool(composer_attempted),
        "composer_succeeded": bool(composer_succeeded),
        "hcl_attempted": bool(hcl_attempted),
        "hcl_succeeded": bool(hcl_succeeded),
        "fallback_reason": safe_fallback_reason(fallback_reason),
    }


def with_answer_trace(
    run_meta: dict[str, Any] | None,
    trace: AnswerTrace | None = None,
    **trace_kwargs: Any,
) -> dict[str, Any]:
    meta = dict(run_meta or {})
    meta[ANSWER_TRACE_KEY] = trace or build_answer_trace(**trace_kwargs)
    return meta
