from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}


def is_final_answer_layer_enabled() -> bool:
    return os.getenv("SEALAI_ENABLE_FINAL_ANSWER_LAYER", "true").strip().lower() in _TRUE_VALUES


@dataclass(frozen=True, slots=True)
class FinalAnswerEnvelope:
    route: str
    answer_mode: str
    deterministic_fallback_reply: str
    latest_user_message: str | None = None
    existing_answer_markdown: str | None = None
    existing_answer_markdown_source: str | None = None
    existing_reply_source: str | None = None
    composer_tier: str | None = None
    fallback_reason: str | None = None


def answer_mode_for_fast_classification(classification: Any) -> str:
    value = getattr(classification, "value", classification)
    if value == "SMALLTALK":
        return "smalltalk"
    if value == "META":
        return "meta"
    if value == "BLOCKED":
        return "blocked"
    return "fast"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _trace_source(run_meta: dict[str, Any] | None, key: str) -> str | None:
    trace = (run_meta or {}).get("answer_trace")
    if isinstance(trace, dict):
        value = trace.get(key)
        return str(value) if value else None
    return None


def apply_final_answer_layer(payload: dict[str, Any], envelope: FinalAnswerEnvelope) -> dict[str, Any]:
    """Select the final visible answer without changing deterministic truth.

    The layer is intentionally fallback-first. When disabled it returns the
    payload unchanged. When enabled it only chooses between already prepared
    answer text and the deterministic reply, then records safe trace metadata.
    """

    if not is_final_answer_layer_enabled():
        return payload

    updated = dict(payload)
    reply = _clean_text(updated.get("reply") or envelope.deterministic_fallback_reply)
    explicit_answer = _clean_text(envelope.existing_answer_markdown or updated.get("answer_markdown"))
    selected = explicit_answer or reply

    existing_source = envelope.existing_answer_markdown_source or _trace_source(
        updated.get("run_meta"), "answer_markdown_source"
    )
    selected_source = existing_source if explicit_answer else "deterministic_reply"

    updated["reply"] = reply
    updated["answer_markdown"] = selected

    run_meta = dict(updated.get("run_meta") or {})
    answer_trace = dict(run_meta.get("answer_trace") or {})
    answer_trace.setdefault("answer_markdown_source", selected_source)
    answer_trace["answer_mode"] = envelope.answer_mode
    answer_trace["composer_tier"] = envelope.composer_tier or "none"
    answer_trace["final_layer_source"] = selected_source
    run_meta["answer_trace"] = answer_trace
    run_meta["final_answer_layer"] = {
        "enabled": True,
        "route": envelope.route,
        "answer_mode": envelope.answer_mode,
        "selected_source": selected_source,
        "composer_tier": envelope.composer_tier or "none",
        "fallback_used": selected == reply and not explicit_answer,
        "fallback_reason": envelope.fallback_reason,
    }
    updated["run_meta"] = run_meta
    return updated
