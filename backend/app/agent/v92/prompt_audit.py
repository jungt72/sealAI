"""Prompt audit helpers for V9.2 LLM calls.

Only metadata and hashes leave this module. Rendered prompts and customer text
are intentionally not logged or surfaced in the public contracts.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

from app.agent.v92.contracts import PromptTrace


def rendered_prompt_hash(rendered_prompt: str) -> str:
    return hashlib.sha256(str(rendered_prompt or "").encode("utf-8")).hexdigest()[:16]


def messages_prompt_hash(messages: Iterable[Mapping[str, Any]]) -> str:
    sanitized = [
        {
            "role": str(message.get("role") or ""),
            "content_hash": rendered_prompt_hash(str(message.get("content") or "")),
        }
        for message in messages
    ]
    return rendered_prompt_hash(
        json.dumps(sanitized, sort_keys=True, ensure_ascii=True)
    )


def build_prompt_trace(
    *,
    prompt_template_id: str,
    prompt_template_version: str,
    rendered_prompt: str | None = None,
    messages: Iterable[Mapping[str, Any]] | None = None,
    input_schema_version: str,
    output_schema_version: str,
    model_role: str,
    case_revision: int | None = None,
    trace_id: str,
) -> PromptTrace:
    prompt_hash = (
        messages_prompt_hash(messages)
        if messages is not None
        else rendered_prompt_hash(rendered_prompt or "")
    )
    return PromptTrace(
        prompt_template_id=prompt_template_id,
        prompt_template_version=prompt_template_version,
        rendered_prompt_hash=prompt_hash,
        input_schema_version=input_schema_version,
        output_schema_version=output_schema_version,
        model_role=model_role,
        case_revision=case_revision,
        trace_id=trace_id,
    )


__all__ = ["build_prompt_trace", "messages_prompt_hash", "rendered_prompt_hash"]
