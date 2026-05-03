from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from app.agent.communication.governed_answer_context import GovernedAnswerContext
from app.agent.communication.context import human_label
from app.agent.prompts import prompts
from app.agent.runtime.output_guard import check_fast_path_output
from app.llm.factory import get_async_llm
from app.llm.registry import get_registry_default_model_for_role

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

_MODEL_FALLBACK_ERROR_NAMES = {"BadRequestError", "NotFoundError"}


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
        messages = build_governed_answer_composer_messages(request)
        response = await _create_completion_with_registry_fallback(
            client=client,
            model=model,
            role="governed_answer_composer",
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        raw_content = response.choices[0].message.content
        return parse_governed_answer_composer_output(raw_content)


async def _create_completion_with_registry_fallback(
    *,
    client: Any,
    model: str,
    role: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> Any:
    try:
        return await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=_response_format(),
        )
    except Exception as exc:  # noqa: BLE001
        fallback_model = get_registry_default_model_for_role(role)
        if model != fallback_model and exc.__class__.__name__ in _MODEL_FALLBACK_ERROR_NAMES:
            log.warning(
                "[governed_answer_composer] configured model rejected; retrying registry default"
            )
            return await client.chat.completions.create(
                model=fallback_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=_response_format(),
            )
        raise


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


def render_governed_contextual_fallback(
    context: GovernedAnswerContext,
    deterministic_reply: str,
) -> str:
    """Render a safe V7 fallback from governed context when the LLM is unavailable.

    This is not a second truth source. It only verbalizes already-governed
    context so provider/model failures do not expose the old bureaucratic
    fallback as the visible answer.
    """

    fallback = str(deterministic_reply or "").strip()
    answer = _contextual_fallback_text(context).strip()
    if not answer:
        return fallback
    try:
        if len(answer) > MAX_ANSWER_MARKDOWN_CHARS:
            raise GovernedAnswerComposerError("contextual_fallback_too_long")
        _validate_answer_markdown(answer)
        return answer
    except GovernedAnswerComposerError:
        return fallback


def _contextual_fallback_text(context: GovernedAnswerContext) -> str:
    if context.ambiguous_values:
        item = context.ambiguous_values[0]
        value = _display_value(item.normalized_value or item.raw_value)
        label = _display_label(item.field_key, item.label)
        question = _clean_question(item.clarification_question or context.next_best_question)
        if value and question:
            return (
                f"Danke, ich habe {value} als {label} verstanden. "
                f"Fuer die technische Einordnung muss ich das noch genauer fassen: {question}"
            )
        if question:
            return question

    if context.accepted_updates:
        update = context.accepted_updates[0]
        value = _display_value(update.value)
        label = _display_label(update.field_key, update.label)
        question = _clean_question(context.next_best_question or _question_for_missing_fields(context.missing_fields))
        if value and question:
            return (
                f"Danke, {value} ist als {label} angekommen. "
                f"Als Naechstes ist wichtig: {question}"
            )
        if value:
            return (
                f"Danke, {value} ist als {label} angekommen. "
                "Ich halte es als aktuellen Arbeitsstand fest und pruefe den naechsten sinnvollen Schritt."
            )

    question = _clean_question(context.next_best_question or _question_for_missing_fields(context.missing_fields))
    if question:
        return f"Gern, wir gehen das Schritt fuer Schritt durch. {question}"
    return ""


def _display_value(value: Any) -> str:
    return str(value or "").strip()


def _display_label(field_key: str, label: str | None) -> str:
    text = str(label or "").strip()
    if text:
        return text
    return human_label(str(field_key or "").strip())


def _clean_question(question: str | None) -> str:
    text = str(question or "").strip()
    if not text:
        return ""
    return text


def _question_for_missing_fields(missing_fields: list[str]) -> str:
    normalized = [str(item or "").strip() for item in missing_fields if str(item or "").strip()]
    for key in normalized:
        lowered = key.casefold()
        if "pressure" in lowered or "druck" in lowered:
            return "Welcher Druck liegt direkt an der Dichtstelle an?"
        if "temperature" in lowered or "temperatur" in lowered:
            return "In welchem Temperaturbereich arbeitet die Dichtstelle?"
        if "sealing_type" in lowered or "dichtungstyp" in lowered or "dichtprinzip" in lowered:
            return (
                "Um welches Dichtprinzip geht es, zum Beispiel O-Ring, Wellendichtring, "
                "Flachdichtung, Hydraulikdichtung oder Gleitringdichtung?"
            )
        if "asset" in lowered or "anlage" in lowered or "pump" in lowered or "aggregate" in lowered:
            return (
                "Wo sitzt die Dichtung genau, zum Beispiel an Pumpe, Welle, Flansch, "
                "Zylinder oder Behaelter?"
            )
    return ""


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
