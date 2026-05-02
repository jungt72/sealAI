from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from app.agent.communication.governed_answer_context import GovernedAnswerContext
from app.agent.prompts import prompts
from app.agent.runtime.output_guard import check_fast_path_output
from app.llm.factory import get_async_llm

log = logging.getLogger(__name__)

GOVERNED_ANSWER_COMPOSER_PROMPT_VERSION = "sealai_governed_answer_composer_v1"
MAX_ANSWER_MARKDOWN_CHARS = 2200

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}

_INTERNAL_LEAKAGE_FRAGMENTS = (
    "```json",
    "answer_markdown",
    "allowed_claims",
    "forbidden_claims",
    "pending_question",
    "slot_answer_bindings",
    "governed_answer_context",
    "graphstate",
    "output_reply",
    "response_class",
    "model_dump",
    "source=",
)

_FORBIDDEN_APPROVAL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE | re.UNICODE)
    for pattern in (
        r"\b(?:die\s+)?(?:loesung|lösung|dichtung|auslegung)\s+ist\s+(?:freigegeben|zugelassen|approved|sicher|garantiert)",
        r"\b(?:freigegeben|approved|final\s+geeignet|final\s+freigegeben|technisch\s+validiert)\b",
        r"\b(?:garantiert\s+dicht|garantiert\s+passend|sicher\s+passend)\b",
        r"\brfq[-\s]?ready\b",
        r"\bherstellerreif(?:e|er|es|en)?\b",
        r"\b(?:material|werkstoff|fkm|ffkm|epdm|nbr|ptfe)\s+ist\s+(?:gut\s+)?geeignet\b",
        r"\b(?:keine\s+weitere[n]?\s+pruefung|keine\s+weitere[n]?\s+prüfung|keine\s+herstellerpruefung|keine\s+herstellerprüfung)\b",
        r"\bder\s+hersteller\s+(?:wird|muss)\s+das\s+(?:akzeptieren|freigeben)\b",
        r"\b(?:zertifiziert|compliant|konform)\b",
    )
)


@dataclass(frozen=True, slots=True)
class GovernedAnswerComposerInput:
    context: GovernedAnswerContext
    deterministic_reply: str


@dataclass(frozen=True, slots=True)
class GovernedAnswerComposerOutput:
    answer_markdown: str
    confidence_note: str | None = None


class GovernedAnswerComposerError(ValueError):
    pass


def is_governed_answer_composer_enabled() -> bool:
    return os.getenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "").strip().lower() in _TRUE_VALUES


class GovernedAnswerComposer:
    """Read-only final answer composer for governed answers."""

    def __init__(self, *, temperature: float = 0.3, max_tokens: int = 700) -> None:
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def compose(self, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        client, model = get_async_llm("governed_answer_composer")
        response = await client.chat.completions.create(
            model=model,
            messages=build_governed_answer_composer_messages(request),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format=_response_format(),
        )
        raw_content = response.choices[0].message.content
        return parse_governed_answer_composer_output(raw_content)


def build_governed_answer_composer_messages(
    request: GovernedAnswerComposerInput,
) -> list[dict[str, str]]:
    payload = {
        "prompt_version": GOVERNED_ANSWER_COMPOSER_PROMPT_VERSION,
        "deterministic_reply": request.deterministic_reply,
        "governed_answer_context": request.context.model_dump(mode="json"),
    }
    system_prompt = prompts.render(
        "governed/answer_composer.j2",
        {
            "prompt_version": GOVERNED_ANSWER_COMPOSER_PROMPT_VERSION,
            "max_answer_chars": MAX_ANSWER_MARKDOWN_CHARS,
        },
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=True, default=str)},
    ]


def parse_governed_answer_composer_output(raw_content: Any) -> GovernedAnswerComposerOutput:
    try:
        payload = json.loads(str(raw_content or "{}"))
    except json.JSONDecodeError as exc:
        raise GovernedAnswerComposerError("invalid_json") from exc
    if not isinstance(payload, dict):
        raise GovernedAnswerComposerError("invalid_payload")

    answer_markdown = str(payload.get("answer_markdown") or "").strip()
    if not answer_markdown:
        raise GovernedAnswerComposerError("empty_answer_markdown")
    if len(answer_markdown) > MAX_ANSWER_MARKDOWN_CHARS:
        raise GovernedAnswerComposerError("answer_markdown_too_long")
    _validate_answer_markdown(answer_markdown)

    confidence_note = payload.get("confidence_note")
    return GovernedAnswerComposerOutput(
        answer_markdown=answer_markdown,
        confidence_note=str(confidence_note).strip() if confidence_note else None,
    )


def safe_governed_answer_composer_error_reason(exc: BaseException) -> str:
    if isinstance(exc, GovernedAnswerComposerError):
        raw = str(exc) or exc.__class__.__name__
    else:
        raw = exc.__class__.__name__
    safe = re.sub(r"[^a-zA-Z0-9_:\.-]", "_", raw)[:96]
    return safe or "composer_failed"


def _validate_answer_markdown(answer_markdown: str) -> None:
    lowered = answer_markdown.casefold()
    for fragment in _INTERNAL_LEAKAGE_FRAGMENTS:
        if fragment in lowered:
            raise GovernedAnswerComposerError("internal_context_leakage")
    for pattern in _FORBIDDEN_APPROVAL_PATTERNS:
        if pattern.search(answer_markdown):
            raise GovernedAnswerComposerError("forbidden_engineering_claim")
    safe, category = check_fast_path_output(answer_markdown)
    if not safe:
        raise GovernedAnswerComposerError(f"unsafe_answer_markdown:{category}")


def _response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "sealai_governed_answer_composer_response",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "answer_markdown": {"type": "string"},
                    "confidence_note": {"type": ["string", "null"]},
                },
                "required": ["answer_markdown", "confidence_note"],
            },
        },
    }
