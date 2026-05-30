from __future__ import annotations

import json
import hashlib
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal

from app.agent.communication.governed_answer_context import GovernedAnswerContext
from app.agent.communication.context import human_label
from app.agent.communication.templates import render_communication_template
from app.agent.communication.technical_case_challenge import (
    ANSWER_MODE_TECHNICAL_CASE_CHALLENGE,
    render_technical_case_challenge_plan,
)
from app.agent.prompts import prompts
from app.agent.runtime.output_guard import check_fast_path_output
from app.agent.v92.contracts import PromptTrace
from app.agent.v92.prompt_audit import build_prompt_trace
from app.agent.v91.final_answer_guard import validate_v91_final_answer
from app.llm.factory import get_async_llm
from app.llm.registry import get_registry_default_model_for_role

log = logging.getLogger(__name__)

GOVERNED_ANSWER_COMPOSER_PROMPT_VERSION = "sealai_governed_answer_composer_v2"
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
        r"\b(?:material|werkstoff|compound|fkm|ffkm|epdm|nbr|hnbr|ptfe|vmq|silikon)\b.{0,100}\b(?:ist|sind|is|are)\s+(?:chemisch\s+|fully\s+|absolutely\s+|sicher\s+)?(?:best[aä]ndig|bestaendig|resistant|compatible|suitable|safe\s+for|chemisch\s+sicher)\b",
        r"\b(?:material|werkstoff|compound|fkm|ffkm|epdm|nbr|hnbr|ptfe|vmq|silikon)\b.{0,100}\b(?:geeignet\s+f(?:ü|u|ue)r|trinkwassergeeignet)\b",
        r"\b(?:material|werkstoff|compound|fkm|ffkm|epdm|nbr|hnbr|ptfe|vmq|silikon)\b.{0,100}\b(?:freigegeben|zugelassen|approved|validated|validiert)\b",
        r"\b(?:nehmen\s+sie|nimm|verwenden\s+sie|verwende)\b.{0,80}\b(?:material|werkstoff|fkm|ffkm|epdm|nbr|ptfe|pom|peek)\b",
        r"\b(?:material|werkstoff|fkm|ffkm|epdm|nbr|ptfe|pom|peek)\b.{0,80}\b(?:ist\s+die\s+beste|beste\s+l(?:oe|ö)sung)\b",
        r"\b(?:keine\s+weitere[n]?\s+pruefung|keine\s+weitere[n]?\s+prüfung|keine\s+herstellerpruefung|keine\s+herstellerprüfung)\b",
        r"\bder\s+hersteller\s+(?:wird|muss)\s+das\s+(?:akzeptieren|freigeben)\b",
        r"\b(?:zertifiziert|compliant|konform)\b",
    )
)

_MODEL_FALLBACK_ERROR_NAMES = {"BadRequestError", "NotFoundError"}

_RECOVERABLE_REPAIR_REASONS = {
    "bare_medium_intake_question",
    "missing_material_orientation",
    "robotic_intake_opening",
    "slot_question_before_orientation",
    "routine_confirmation_or_restatement",
    "restates_recently_supplied_value",
    "communication_guard:planned_question_missing",
    "communication_guard:too_many_questions",
    "communication_guard:unplanned_question",
    "communication_guard:missing_question_reason",
    "communication_guard:answer_first_missing",
    "communication_guard:external_utility_answer",
    "communication_guard:tab_spam",
}


@dataclass(frozen=True, slots=True)
class GovernedAnswerComposerInput:
    context: GovernedAnswerContext
    deterministic_reply: str


@dataclass(frozen=True, slots=True)
class GovernedAnswerComposerOutput:
    answer_markdown: str
    confidence_note: str | None = None
    prompt_trace: PromptTrace | None = None


@dataclass(frozen=True, slots=True)
class GovernedAnswerComposerStreamEvent:
    event_type: Literal["chunk", "reset", "final"]
    text: str = ""
    output: GovernedAnswerComposerOutput | None = None


class GovernedAnswerComposerError(ValueError):
    pass


def is_governed_answer_composer_enabled() -> bool:
    return os.getenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "true").strip().lower() in _TRUE_VALUES


class GovernedAnswerComposer:
    """Read-only final answer composer for governed answers."""

    def __init__(self, *, temperature: float = 0.3, max_tokens: int = 700) -> None:
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def compose(self, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        client, model = get_async_llm("governed_answer_composer")
        messages = build_governed_answer_composer_messages(request)
        try:
            return await self._compose_once(
                client=client,
                model=model,
                request=request,
                messages=messages,
            )
        except GovernedAnswerComposerError as exc:
            fallback = _recoverable_contextual_output(request, exc)
            if fallback is not None:
                return fallback
            if not _is_recoverable_repair_reason(exc):
                raise
            repair_messages = build_governed_answer_composer_messages(
                request,
                repair_reason=safe_governed_answer_composer_error_reason(exc),
            )
            try:
                return await self._compose_once(
                    client=client,
                    model=model,
                    request=request,
                    messages=repair_messages,
                )
            except GovernedAnswerComposerError as repair_exc:
                fallback = _recoverable_contextual_output(request, repair_exc)
                if fallback is not None:
                    return fallback
                raise

    async def stream(
        self,
        request: GovernedAnswerComposerInput,
    ) -> AsyncGenerator[GovernedAnswerComposerStreamEvent, None]:
        """Stream the visible governed answer while keeping the deterministic basis.

        The graph has already decided the technical basis. This method only
        streams the LLM wording pass and validates the complete answer before
        emitting the final event. If the stream crosses a hard boundary, it
        raises and the caller must replace the final answer with the deterministic
        fallback.
        """

        client, model = get_async_llm("governed_answer_composer")
        messages = build_governed_answer_composer_messages(
            request,
            output_format="markdown_stream",
        )
        first_attempt_text = ""
        try:
            async for event in self._stream_once(
                client=client,
                model=model,
                request=request,
                messages=messages,
            ):
                if event.event_type == "chunk":
                    first_attempt_text += event.text
                yield event
            return
        except GovernedAnswerComposerError as exc:
            if not _is_recoverable_repair_reason(exc):
                raise
            failed_reason = safe_governed_answer_composer_error_reason(exc)

        repair_messages = build_governed_answer_composer_messages(
            request,
            output_format="markdown_stream",
            repair_reason=failed_reason,
            failed_answer=first_attempt_text,
        )
        yield GovernedAnswerComposerStreamEvent(event_type="reset")
        async for event in self._stream_once(
            client=client,
            model=model,
            request=request,
            messages=repair_messages,
        ):
            yield event

    async def _compose_once(
        self,
        *,
        client: Any,
        model: str,
        request: GovernedAnswerComposerInput,
        messages: list[dict[str, str]],
    ) -> GovernedAnswerComposerOutput:
        response = await _create_completion_with_registry_fallback(
            client=client,
            model=model,
            role="governed_answer_composer",
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        raw_content = response.choices[0].message.content
        output = parse_governed_answer_composer_output(raw_content)
        _validate_complete_answer(output.answer_markdown, request.context)
        return GovernedAnswerComposerOutput(
            answer_markdown=output.answer_markdown,
            confidence_note=output.confidence_note,
            prompt_trace=_prompt_trace_for_messages(request=request, messages=messages),
        )

    async def _stream_once(
        self,
        *,
        client: Any,
        model: str,
        request: GovernedAnswerComposerInput,
        messages: list[dict[str, str]],
    ) -> AsyncGenerator[GovernedAnswerComposerStreamEvent, None]:
        response = await _create_stream_with_registry_fallback(
            client=client,
            model=model,
            role="governed_answer_composer",
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        accumulated: list[str] = []
        async for chunk in response:
            delta = chunk.choices[0].delta if getattr(chunk, "choices", None) else None
            text = getattr(delta, "content", None) if delta else None
            if not text:
                continue
            tentative = "".join(accumulated) + str(text)
            _validate_stream_prefix(tentative)
            accumulated.append(str(text))
            yield GovernedAnswerComposerStreamEvent(event_type="chunk", text=str(text))

        answer_markdown = "".join(accumulated).strip()
        if not answer_markdown:
            raise GovernedAnswerComposerError("empty_stream_answer_markdown")
        if len(answer_markdown) > MAX_ANSWER_MARKDOWN_CHARS:
            raise GovernedAnswerComposerError("answer_markdown_too_long")
        _validate_complete_answer(answer_markdown, request.context)
        yield GovernedAnswerComposerStreamEvent(
            event_type="final",
            output=GovernedAnswerComposerOutput(
                answer_markdown=answer_markdown,
                confidence_note=None,
                prompt_trace=_prompt_trace_for_messages(request=request, messages=messages),
            ),
        )


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


async def _create_stream_with_registry_fallback(
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
            stream=True,
        )
    except Exception as exc:  # noqa: BLE001
        fallback_model = get_registry_default_model_for_role(role)
        if model != fallback_model and exc.__class__.__name__ in _MODEL_FALLBACK_ERROR_NAMES:
            log.warning(
                "[governed_answer_composer] configured stream model rejected; retrying registry default"
            )
            return await client.chat.completions.create(
                model=fallback_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
        raise


def build_governed_answer_composer_messages(
    request: GovernedAnswerComposerInput,
    *,
    output_format: Literal["json", "markdown_stream"] = "json",
    repair_reason: str | None = None,
    failed_answer: str | None = None,
) -> list[dict[str, str]]:
    payload = {
        "prompt_version": GOVERNED_ANSWER_COMPOSER_PROMPT_VERSION,
        "deterministic_reply": request.deterministic_reply,
        "governed_answer_context": _governed_answer_context_prompt_payload(request.context),
    }
    if repair_reason:
        must_mention_terms = _user_named_material_terms(request.context.latest_user_message)
        payload["repair"] = {
            "reason": repair_reason,
            "failed_answer": str(failed_answer or "")[:MAX_ANSWER_MARKDOWN_CHARS],
            "must_mention_user_material_terms": must_mention_terms,
            "instruction": (
                "Rewrite the visible answer from the same governed context. "
                "Fix the named issue; do not add unsupported engineering truth."
            ),
        }
    system_prompt = prompts.render(
        "governed/answer_composer.j2",
        {
            "prompt_version": GOVERNED_ANSWER_COMPOSER_PROMPT_VERSION,
            "max_answer_chars": MAX_ANSWER_MARKDOWN_CHARS,
            "output_format": output_format,
        },
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=True, default=str)},
    ]
    if repair_reason:
        terms = ", ".join(payload["repair"]["must_mention_user_material_terms"])
        repair_instruction = (
            f"Repair the previous governed answer. Reason: {repair_reason}. "
            "Use deterministic_reply and governed_answer_context as the only grounding. "
        )
        if repair_reason == "bare_medium_intake_question":
            repair_instruction += (
                "For this first intake, do not write the bare question 'Welches Medium soll abgedichtet werden?'. "
                "Ask naturally what touches or leaks at the sealing point, including concentration, additives, "
                "or cleaning media if relevant. "
            )
        if repair_reason == "robotic_intake_opening":
            repair_instruction += (
                "The user is asking for help with a sealing situation, not supplying a concrete parameter yet. "
                "Open warmly and empathetically. Ask one broad intake question that covers application, medium, "
                "and relevant operating/installation conditions. Do not use phrases like 'technische Richtung', "
                "'belastbarer Hebel', or a bare medium slot question. "
            )
        if terms:
            repair_instruction += (
                f"The user explicitly named these material families: {terms}. "
                "Mention them in a short bounded orientation before the governed next question. "
            )
        repair_instruction += "Return only the requested output format."
        messages.append({"role": "user", "content": repair_instruction})
    return messages


def _governed_answer_context_prompt_payload(context: GovernedAnswerContext) -> dict[str, Any]:
    """Return the compact user-facing composer context."""

    def dump(value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        return _bounded_prompt_payload(value)

    final_context = dump(context.v91_final_answer_context)
    payload: dict[str, Any] = {
        "latest_user_message": context.latest_user_message,
        "answer_mode": context.answer_mode,
        "answer_mode_source": context.answer_mode_source,
        "recent_conversation_messages": list(context.conversation_messages or [])[-8:],
        "pending_question": dump(context.pending_question),
        "slot_answer_bindings": [dump(item) for item in context.slot_answer_bindings[:3]],
        "accepted_updates": [dump(item) for item in context.accepted_updates[:6]],
        "ambiguous_values": [dump(item) for item in context.ambiguous_values[:4]],
        "rejected_updates": [dump(item) for item in context.rejected_updates[:4]],
        "confirmed_facts": [dump(item) for item in context.confirmed_facts[:12]],
        "calculation_results": [dump(item) for item in context.calculation_results[:6]],
        "missing_fields": list(context.missing_fields or [])[:16],
        "open_points": list(context.open_points or [])[:16],
        "challenge_findings": list(context.challenge_findings or [])[:6],
        "challenge_hypotheses": list(context.challenge_hypotheses or [])[:6],
        "technical_case_challenge_plan": dump(context.technical_case_challenge_plan),
        "next_best_question": context.next_best_question,
        "v91_question_plan": dump(context.v91_question_plan),
        "response_class": context.response_class,
        "allowed_claims": list(context.allowed_claims or [])[:24],
        "forbidden_claims": list(context.forbidden_claims or [])[:12],
        "safety_boundaries": list(context.safety_boundaries or [])[:12],
        "answer_goal": context.answer_goal,
    }
    if isinstance(final_context, dict):
        payload["v91_final_answer_context"] = {
            key: final_context.get(key)
            for key in (
                "answer_mode",
                "freedom_level",
                "required_question",
                "allowed_claims",
                "forbidden_claims",
                "must_not_claim",
            )
            if key in final_context
        }
    return _bounded_prompt_payload(payload)


def _bounded_prompt_payload(value: Any, *, string_limit: int = 900) -> Any:
    if isinstance(value, str):
        text = " ".join(value.split())
        if len(text) <= string_limit:
            return text
        return f"{text[:string_limit].rstrip()} ... [gekuerzt: {len(text) - string_limit} Zeichen]"
    if isinstance(value, dict):
        return {str(key): _bounded_prompt_payload(item, string_limit=string_limit) for key, item in value.items()}
    if isinstance(value, list):
        return [_bounded_prompt_payload(item, string_limit=string_limit) for item in value]
    if isinstance(value, tuple):
        return [_bounded_prompt_payload(item, string_limit=string_limit) for item in value]
    return value


def _prompt_trace_for_messages(
    *,
    request: GovernedAnswerComposerInput,
    messages: list[dict[str, str]],
) -> PromptTrace:
    trace_source = json.dumps(
        {
            "latest_user_message": request.context.latest_user_message,
            "response_class": request.context.response_class,
            "deterministic_reply_hash_basis": bool(request.deterministic_reply),
        },
        ensure_ascii=True,
        sort_keys=True,
        default=str,
    )
    trace_id = "prompt_" + re.sub(
        r"[^a-f0-9]",
        "",
        hashlib.sha256(trace_source.encode("utf-8")).hexdigest(),
    )[:24]
    return build_prompt_trace(
        prompt_template_id="governed/answer_composer.j2",
        prompt_template_version=GOVERNED_ANSWER_COMPOSER_PROMPT_VERSION,
        messages=messages,
        input_schema_version="GovernedAnswerComposerInput.v1",
        output_schema_version="GovernedAnswerComposerOutput.v1",
        model_role="governed_answer_composer",
        case_revision=None,
        trace_id=trace_id,
    )


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


def _validate_stream_prefix(text: str) -> None:
    """Fail early before a forbidden fragment reaches the user as a chunk."""

    lowered = str(text or "").casefold()
    if any(fragment in lowered for fragment in _INTERNAL_LEAKAGE_FRAGMENTS):
        raise GovernedAnswerComposerError("stream_internal_leakage")
    for pattern in _FORBIDDEN_APPROVAL_PATTERNS:
        if pattern.search(text):
            raise GovernedAnswerComposerError("stream_forbidden_approval_language")


def _user_named_material_terms(latest_user_message: str | None) -> list[str]:
    latest = str(latest_user_message or "").casefold()
    if not latest:
        return []
    known_terms = ("EPDM", "FKM", "FFKM", "NBR", "HNBR", "PTFE", "PU", "POM", "PEEK")
    return [term for term in known_terms if re.search(rf"\b{re.escape(term.casefold())}\b", latest)]


def _is_recoverable_repair_reason(exc: GovernedAnswerComposerError) -> bool:
    reason = safe_governed_answer_composer_error_reason(exc)
    return reason in _RECOVERABLE_REPAIR_REASONS


def _recoverable_contextual_output(
    request: GovernedAnswerComposerInput,
    exc: GovernedAnswerComposerError,
) -> GovernedAnswerComposerOutput | None:
    if not _is_recoverable_repair_reason(exc):
        return None
    answer = render_governed_contextual_fallback(
        request.context,
        request.deterministic_reply,
    )
    if not str(answer or "").strip():
        return None
    if str(answer).strip() == str(request.deterministic_reply or "").strip():
        return None
    return GovernedAnswerComposerOutput(
        answer_markdown=str(answer).strip(),
        confidence_note=None,
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
        _validate_v91_final_answer(answer, context)
        return answer
    except GovernedAnswerComposerError:
        return fallback


def has_v9_challenge_context(context: GovernedAnswerContext | None) -> bool:
    """Return whether a governed turn carries enough context for V9 fallback wording."""

    if context is None:
        return False
    return bool(
        getattr(context, "challenge_findings", None)
        or getattr(context, "challenge_hypotheses", None)
        or context.ambiguous_values
        or context.rejected_updates
    )


def should_render_governed_contextual_fallback(
    context: GovernedAnswerContext | None,
    deterministic_reply: str,
) -> bool:
    """Return whether deterministic intake wording needs human-facing context."""

    if context is None:
        return False
    if (
        getattr(context, "answer_mode", None) == ANSWER_MODE_TECHNICAL_CASE_CHALLENGE
        and getattr(context, "technical_case_challenge_plan", None) is not None
    ):
        return True
    if _technical_orientation_for_user_task(context.latest_user_message):
        return True
    if _needs_human_intake_fallback(context, deterministic_reply):
        return True
    return has_v9_challenge_context(context)


def _contextual_fallback_text(context: GovernedAnswerContext) -> str:
    if (
        getattr(context, "answer_mode", None) == ANSWER_MODE_TECHNICAL_CASE_CHALLENGE
        and context.technical_case_challenge_plan is not None
    ):
        return render_technical_case_challenge_plan(context.technical_case_challenge_plan)

    orientation = _technical_orientation_for_user_task(context.latest_user_message)
    calculation_orientation = _calculation_orientation(context)
    if calculation_orientation:
        orientation = _join_sentences(orientation, calculation_orientation)
    if context.ambiguous_values:
        item = context.ambiguous_values[0]
        value = _display_value(item.normalized_value or item.raw_value)
        label = _display_label(item.field_key, item.label)
        question = _clean_question(item.clarification_question or context.next_best_question)
        if value and question:
            clarification = (
                f"{value} ist als {label} im Arbeitsstand. "
                "Für die technische Einordnung muss ich das genauer fassen, "
                f"weil die genaue Einordnung die Dichtungsbewertung beeinflusst: {question}"
            )
            return _join_orientation_and_question(orientation, clarification)
        if question:
            return _join_orientation_and_question(orientation, _question_with_reason(question, context))

    if context.accepted_updates:
        question = _clean_question(context.next_best_question or _question_for_missing_fields(context.missing_fields))
        if question:
            return _join_orientation_and_question(orientation, _question_with_reason(question, context))
        return _join_orientation_and_question(
            orientation,
            "Ich halte die Angabe als Arbeitsstand fest und prüfe den nächsten sinnvollen Schritt.",
        )

    question = _clean_question(context.next_best_question or _question_for_missing_fields(context.missing_fields))
    if question:
        open_help_prompt = (
            _open_sealing_help_prompt(context.latest_user_message)
            if not (context.accepted_updates or context.ambiguous_values or context.rejected_updates)
            else ""
        )
        if open_help_prompt:
            return open_help_prompt
        intake_orientation = _human_intake_orientation(context.latest_user_message)
        if intake_orientation and not orientation:
            return _join_intake_orientation_and_question(
                intake_orientation,
                _humanize_intake_question(question),
            )
        return _join_orientation_and_question(orientation, _question_with_reason(question, context))
    return ""


def _question_with_reason(question: str, context: GovernedAnswerContext) -> str:
    clean_question = _clean_question(question)
    if not clean_question:
        return ""
    lowered = clean_question.casefold()
    if any(marker in lowered for marker in ("weil", "wichtig", "damit", "relevant", "beeinflusst")):
        return clean_question
    reason = ""
    question_plan = getattr(context, "v91_question_plan", None)
    if question_plan is not None:
        reason = str(getattr(question_plan, "reason", "") or "").strip()
    final_context = getattr(context, "v91_final_answer_context", None)
    if not reason and final_context is not None:
        final_question_plan = getattr(final_context, "question_plan", None)
        reason = str(getattr(final_question_plan, "primary_question_reason", "") or "").strip()
    if not reason:
        return clean_question
    clean_reason = reason.rstrip(" .")
    return f"{clean_question} Das ist wichtig, weil {clean_reason}."


_CALC_OUTPUT_LABELS = {
    "v_surface_m_s": "Umfangsgeschwindigkeit",
    "pv_value_mpa_m_s": "p-v-Wert",
    "dn_value": "DN-Wert",
    "temperature_headroom_c": "Temperaturreserve",
    "temp_min_c": "Temperatur minimum",
    "temp_max_c": "Temperatur maximum",
    "temp_peak_c": "Temperaturspitze",
}


def _join_sentences(left: str, right: str) -> str:
    clean_left = str(left or "").strip()
    clean_right = str(right or "").strip()
    if not clean_left:
        return clean_right
    if not clean_right:
        return clean_left
    return f"{clean_left} {clean_right}"


def _format_calc_value(value: Any) -> str:
    if isinstance(value, float):
        text = f"{value:.3f}".rstrip("0").rstrip(".")
        return text.replace(".", ",")
    return str(value)


def _calculation_orientation(context: GovernedAnswerContext) -> str:
    facts = list(getattr(context, "calculation_results", []) or [])
    if not facts:
        return ""
    text = str(context.latest_user_message or "").casefold()
    if not any(marker in text for marker in ("berech", "umfang", "geschwindigkeit", "grenzwert", "pv", "dn", "wert")):
        return ""
    parts: list[str] = []
    for fact in facts:
        outputs = dict(getattr(fact, "outputs", {}) or {})
        units = dict(getattr(fact, "units", {}) or {})
        for key, value in outputs.items():
            if key in {"status", "calc_type", "pressure_window"} or value in (None, "", [], {}):
                continue
            label = _CALC_OUTPUT_LABELS.get(str(key), str(key))
            unit = str(units.get(key) or "").strip()
            rendered = f"{label}: {_format_calc_value(value)}"
            if unit and unit != "text":
                rendered += f" {unit}"
            parts.append(rendered)
            if len(parts) >= 3:
                break
        if len(parts) >= 3:
            break
    if not parts:
        return ""
    return (
        "Deterministisch berechnet: "
        + "; ".join(parts)
        + ". Das ist ein Screening-Zwischenwert, keine Freigabe."
    )


def _needs_human_intake_fallback(
    context: GovernedAnswerContext,
    deterministic_reply: str,
) -> bool:
    """Detect bare governed intake questions that would feel form-like in chat."""

    if str(context.response_class or "").strip() != "structured_clarification":
        return False
    question = _clean_question(context.next_best_question or _question_for_missing_fields(context.missing_fields))
    if not question:
        return False
    if context.accepted_updates or context.ambiguous_values or context.rejected_updates:
        return False
    if _human_intake_orientation(context.latest_user_message):
        return True
    reply = str(deterministic_reply or "").strip()
    if not reply:
        return False
    return reply.rstrip() == question.rstrip() or reply.count("?") == 1


def _human_intake_orientation(latest_user_message: str | None) -> str:
    text = str(latest_user_message or "").casefold()
    if not text:
        return ""
    problem_markers = (
        "leck",
        "undicht",
        "ausfall",
        "schaden",
        "verschleiß",
        "verschleiss",
        "problem",
    )
    goal_markers = (
        "auslegen",
        "dichtung",
        "dichtungsfall",
        "dichtstelle",
        "pumpe",
        "welle",
        "getriebe",
        "rührwerk",
        "ruehrwerk",
    )
    if any(marker in text for marker in problem_markers):
        return render_communication_template(
            "governed_human_intake_orientation",
            {"mode": "leakage"},
            fallback=(
                "Verstanden, eine Leckage würde ich zuerst als Fallbild sauber eingrenzen, "
                "damit wir Ursache, Betriebsbedingungen und Dichtprinzip nicht vermischen."
            ),
        )
    if any(marker in text for marker in goal_markers):
        return render_communication_template(
            "governed_human_intake_orientation",
            {"mode": "goal"},
            fallback=(
                "Verstanden, wir grenzen die Anwendung Schritt für Schritt ein und halten nur "
                "belastbare Angaben als Arbeitsstand fest."
            ),
        )
    return ""


_OPEN_SEALING_HELP_RE = re.compile(
    r"\b(?:kannst|könntest|koenntest|hilf|hilfe|unterstütz\w*|unterstuetz\w*)\b"
    r".{0,80}\b(?:dichtung|dichtungs\w*|dichtstelle|seal)\b"
    r"|\b(?:dichtung|dichtungs\w*|dichtstelle|seal)\b"
    r".{0,80}\b(?:helfen|hilfe|unterstütz\w*|unterstuetz\w*)\b",
    re.IGNORECASE | re.UNICODE,
)


def _is_open_sealing_help_request(latest_user_message: str | None) -> bool:
    text = str(latest_user_message or "").strip()
    if not text:
        return False
    return bool(_OPEN_SEALING_HELP_RE.search(text))


def _open_sealing_help_prompt(latest_user_message: str | None) -> str:
    if not _is_open_sealing_help_request(latest_user_message):
        return ""
    return render_communication_template(
        "governed_human_intake_orientation",
        {"mode": "open_help"},
        fallback=(
            "Gerne unterstütze ich dich. Erzähl mir bitte kurz von deiner "
            "Dichtungssituation: Welche Anwendung liegt vor, welches Medium "
            "berührt die Dichtung und welche Rahmenbedingungen sind wichtig, "
            "damit ich den Fall sauber einordnen kann?"
        ),
    )


def _humanize_intake_question(question: str) -> str:
    text = str(question or "").strip()
    lowered = text.casefold()
    if "medium" in lowered and "welches medium" in lowered:
        return render_communication_template(
            "governed_humanize_intake_question",
            {"kind": "medium", "question": text},
            fallback=(
                "Was kommt an der Dichtstelle genau an, inklusive Konzentration, "
                "Additiven oder Reinigungsmedien?"
            ),
        )
    if "dichtungstyp" in lowered or "dichtprinzip" in lowered:
        return render_communication_template(
            "governed_humanize_intake_question",
            {"kind": "sealing_principle", "question": text},
            fallback=(
                "Wo sitzt die Leckage genau und welches Dichtprinzip ist dort verbaut, "
                "zum Beispiel RWDR, Gleitringdichtung, O-Ring oder Flachdichtung?"
            ),
        )
    if "druck" in lowered:
        return render_communication_template(
            "governed_humanize_intake_question",
            {"kind": "pressure", "question": text},
            fallback="Welcher Druck liegt direkt an der Dichtstelle an?",
        )
    if "temperatur" in lowered:
        return render_communication_template(
            "governed_humanize_intake_question",
            {"kind": "temperature", "question": text},
            fallback="In welchem Temperaturbereich arbeitet die Dichtstelle?",
        )
    return render_communication_template(
        "governed_humanize_intake_question",
        {"kind": "default", "question": text},
        fallback=text,
    )


def _technical_orientation_for_user_task(latest_user_message: str | None) -> str:
    text = str(latest_user_message or "").casefold()
    if not text:
        return ""
    asks_risk_orientation = any(
        marker in text
        for marker in (
            "vergleich",
            "vergleiche",
            "unterschied",
            "gegenüber",
            "gegenueber",
            "ordne",
            "einordnen",
            "einschätzen",
            "einschaetzen",
            "bewerte",
            "bewerten",
            "technisch kritisch",
            "technisch ein",
            "was ist kritisch",
            "kritisch?",
            "risiko",
            "risiken",
            "ursachen",
            "systematisch prüfen",
            "systematisch pruefen",
        )
    )
    if not asks_risk_orientation:
        return ""
    if (
        ("rwdr" in text or "wellendichtring" in text or "radialwellendichtring" in text)
        and any(marker in text for marker in ("leckt", "leckage", "ursachen", "systematisch"))
    ):
        return render_communication_template(
            "governed_technical_orientation",
            {"mode": "rwdr_leakage"},
            fallback=(
                "Bei früher Leckage an einem RWDR würde ich nicht zuerst den Werkstoff allein "
                "bewerten, sondern das Schadbild systematisch trennen. Typische Ursachencluster "
                "sind Gegenlauffläche, Laufspur, Rundlauf, Montage, Dichtlippe, Schmierung, "
                "Druck direkt an der Dichtstelle, Temperatur, Mediumverträglichkeit und "
                "Verschmutzung. Das ist eine technische Orientierung, keine Freigabe."
            ),
        )
    if {"ptfe", "fkm", "epdm", "nbr", "hnbr"}.intersection(set(re.findall(r"\b[a-z0-9]+\b", text))):
        if ("hydraulik" in text or "hlp" in text or "öl" in text or "oel" in text) and "epdm" in text:
            return render_communication_template(
                "governed_technical_orientation",
                {"mode": "hydraulic_epdm"},
                fallback=(
                    "Bei mineralöl- oder hydraulikölnahen Medien ist EPDM eher ein Warnpunkt, "
                    "während NBR, HNBR oder FKM je nach Temperatur, Bauform und Compound eher "
                    "als Prüfhypothesen betrachtet werden. Das ist eine Vororientierung, keine "
                    "Werkstofffreigabe."
                ),
            )
        return render_communication_template(
            "governed_technical_orientation",
            {"mode": "material_comparison"},
            fallback=(
                "Bei diesem Werkstoffvergleich sind Medium, Temperatur, Dichtungstyp, Vorspannung, "
                "Geometrie und Kontaktzeit die Haupttreiber. Das ist eine Vororientierung, keine "
                "Werkstofffreigabe."
            ),
        )
    if "rwdr" in text or "wellendichtring" in text or "radialwellendichtring" in text:
        return render_communication_template(
            "governed_technical_orientation",
            {"mode": "rwdr_general"},
            fallback=(
                "Technisch kritisch sind bei einem RWDR vor allem Druck direkt an der Dichtlippe, "
                "Umfangsgeschwindigkeit, Reibwärme, Schmierung, Gegenlauffläche, Rundlauf und "
                "Medium-/Temperaturbelastung. Das ist eine technische Orientierung, keine Freigabe."
            ),
        )
    return render_communication_template(
        "governed_technical_orientation",
        {"mode": "general"},
        fallback=(
            "Technisch relevant sind zuerst Medium, Temperaturprofil, Druck direkt an der Dichtstelle, "
            "Bewegung, Geometrie und Nachweise. Das ist eine Vororientierung, keine Freigabe."
        ),
    )


def _join_orientation_and_question(orientation: str, question: str) -> str:
    clean_orientation = str(orientation or "").strip()
    clean_question = str(question or "").strip()
    fallback = (
        f"{clean_orientation}\n\nDie wichtigste Rückfrage ist: {clean_question}"
        if clean_orientation and clean_question
        else clean_question or clean_orientation
    )
    return render_communication_template(
        "governed_orientation_question_join",
        {"orientation": clean_orientation, "question": clean_question},
        fallback=fallback,
    )


def _join_intake_orientation_and_question(orientation: str, question: str) -> str:
    clean_orientation = str(orientation or "").strip()
    clean_question = str(question or "").strip()
    fallback = (
        f"{clean_orientation}\n\nDafür muss ich zuerst wissen: {clean_question}"
        if clean_orientation and clean_question
        else clean_question or clean_orientation
    )
    return render_communication_template(
        "governed_intake_question_join",
        {"orientation": clean_orientation, "question": clean_question},
        fallback=fallback,
    )


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
            return render_communication_template(
                "governed_missing_field_question",
                {"kind": "pressure"},
                fallback="Welcher Druck liegt direkt an der Dichtstelle an?",
            )
        if "temperature" in lowered or "temperatur" in lowered:
            return render_communication_template(
                "governed_missing_field_question",
                {"kind": "temperature"},
                fallback="In welchem Temperaturbereich arbeitet die Dichtstelle?",
            )
        if "sealing_type" in lowered or "dichtungstyp" in lowered or "dichtprinzip" in lowered:
            return render_communication_template(
                "governed_missing_field_question",
                {"kind": "sealing_principle"},
                fallback=(
                    "Um welches Dichtprinzip geht es, zum Beispiel O-Ring, Wellendichtring, "
                    "Flachdichtung, Hydraulikdichtung oder Gleitringdichtung?"
                ),
            )
        if "asset" in lowered or "anlage" in lowered or "pump" in lowered or "aggregate" in lowered:
            return render_communication_template(
                "governed_missing_field_question",
                {"kind": "asset"},
                fallback=(
                    "Wo sitzt die Dichtung genau, zum Beispiel an Pumpe, Welle, Flansch, "
                    "Zylinder oder Behälter?"
                ),
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


def _validate_complete_answer(answer_markdown: str, context: GovernedAnswerContext) -> None:
    _validate_answer_markdown(answer_markdown)
    _validate_v91_final_answer(answer_markdown, context)
    _validate_contextual_answer_discipline(answer_markdown, context)


def _validate_contextual_answer_discipline(
    answer_markdown: str,
    context: GovernedAnswerContext,
) -> None:
    """Reject LLM wording that reintroduces robotic intake habits.

    The deterministic fallback already knows the next governed question. If the
    model repeats freshly supplied values or asks for routine confirmation, we
    fall back to that governed question instead of showing a bureaucratic answer.
    """

    latest = str(context.latest_user_message or "")
    lowered_answer = answer_markdown.casefold()
    if (
        _human_intake_orientation(latest)
        and not context.accepted_updates
        and not context.ambiguous_values
        and "welches medium soll abgedichtet werden" in lowered_answer
    ):
        raise GovernedAnswerComposerError("bare_medium_intake_question")
    if (
        _is_open_sealing_help_request(latest)
        and not context.accepted_updates
        and not context.ambiguous_values
    ):
        robotic_fragments = (
            "die technische richtung ist schon enger",
            "technische richtung ist schon enger",
            "belastbaren hebel",
            "welches medium soll abgedichtet werden",
        )
        if any(fragment in lowered_answer for fragment in robotic_fragments):
            raise GovernedAnswerComposerError("robotic_intake_opening")
        if not all(fragment in lowered_answer for fragment in ("anwendung", "medium")):
            raise GovernedAnswerComposerError("robotic_intake_opening")

    if _technical_orientation_for_user_task(latest):
        latest_lowered = latest.casefold()
        material_terms = {"epdm", "fkm", "nbr", "hnbr", "ptfe", "ffkm", "pu"}
        material_task = bool(
            material_terms.intersection(set(re.findall(r"\b[a-z0-9]+\b", latest_lowered)))
            and any(
                marker in latest_lowered
                for marker in (
                    "vergleich",
                    "vergleiche",
                    "ordne",
                    "einordnen",
                    "bewerte",
                    "bewerten",
                    "technisch ein",
                    "risiko",
                    "risiken",
                )
            )
        )
        if material_task and not any(term in lowered_answer for term in material_terms):
            raise GovernedAnswerComposerError("missing_material_orientation")
        if (
            "ich habe schon ein paar eckdaten" in lowered_answer
            or "für den nächsten sinnvollen schritt brauche ich noch" in lowered_answer
            or "fuer den naechsten sinnvollen schritt brauche ich noch" in lowered_answer
            or "die technische richtung ist schon enger" in lowered_answer
            or "belastbaren hebel" in lowered_answer
        ) and not any(
            marker in lowered_answer
            for marker in ("technisch kritisch", "typische risiken", "ursachencluster", "vor allem")
        ):
            raise GovernedAnswerComposerError("slot_question_before_orientation")

    if not context.accepted_updates or context.ambiguous_values or not context.next_best_question:
        return

    lowered = answer_markdown.casefold()
    routine_fragments = (
        "danke fuer die information",
        "danke für die information",
        "ich habe verstanden",
        "ich habe die",
        "zur kenntnis genommen",
        "technischen details sind klarer",
        "bitte bestaetigen",
        "bitte bestätigen",
        "koennten sie bitte bestaetigen",
        "könnten sie bitte bestätigen",
    )
    if any(fragment in lowered for fragment in routine_fragments):
        raise GovernedAnswerComposerError("routine_confirmation_or_restatement")

    for update in context.accepted_updates:
        value = str(update.value or "").strip()
        if len(value) < 3:
            continue
        if value.casefold() in lowered:
            raise GovernedAnswerComposerError("restates_recently_supplied_value")


def _validate_v91_final_answer(
    answer_markdown: str,
    context: GovernedAnswerContext,
) -> None:
    result = validate_v91_final_answer(
        answer_markdown,
        getattr(context, "v91_final_answer_context", None),
    )
    if not result.passed:
        reason = result.findings[0] if result.findings else "v91_guard_failed"
        raise GovernedAnswerComposerError(reason)


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
