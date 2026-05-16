from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal

from app.agent.communication.governed_answer_context import GovernedAnswerContext
from app.agent.communication.context import human_label
from app.agent.prompts import prompts
from app.agent.runtime.output_guard import check_fast_path_output
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
    "slot_question_before_orientation",
    "routine_confirmation_or_restatement",
    "restates_recently_supplied_value",
    "communication_guard:planned_question_missing",
    "communication_guard:too_many_questions",
}


@dataclass(frozen=True, slots=True)
class GovernedAnswerComposerInput:
    context: GovernedAnswerContext
    deterministic_reply: str


@dataclass(frozen=True, slots=True)
class GovernedAnswerComposerOutput:
    answer_markdown: str
    confidence_note: str | None = None


@dataclass(frozen=True, slots=True)
class GovernedAnswerComposerStreamEvent:
    event_type: Literal["chunk", "reset", "final"]
    text: str = ""
    output: GovernedAnswerComposerOutput | None = None


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
        try:
            return await self._compose_once(
                client=client,
                model=model,
                request=request,
                messages=messages,
            )
        except GovernedAnswerComposerError as exc:
            if not _is_recoverable_repair_reason(exc):
                raise
            repair_messages = build_governed_answer_composer_messages(
                request,
                repair_reason=safe_governed_answer_composer_error_reason(exc),
            )
            return await self._compose_once(
                client=client,
                model=model,
                request=request,
                messages=repair_messages,
            )

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
        return output

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
        "governed_answer_context": request.context.model_dump(mode="json"),
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
        if terms:
            repair_instruction += (
                f"The user explicitly named these material families: {terms}. "
                "Mention them in a short bounded orientation before the governed next question. "
            )
        repair_instruction += "Return only the requested output format."
        messages.append({"role": "user", "content": repair_instruction})
    return messages


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
    if _technical_orientation_for_user_task(context.latest_user_message):
        return True
    if _needs_human_intake_fallback(context, deterministic_reply):
        return True
    return has_v9_challenge_context(context)


def _contextual_fallback_text(context: GovernedAnswerContext) -> str:
    orientation = _technical_orientation_for_user_task(context.latest_user_message)
    if context.ambiguous_values:
        item = context.ambiguous_values[0]
        value = _display_value(item.normalized_value or item.raw_value)
        label = _display_label(item.field_key, item.label)
        question = _clean_question(item.clarification_question or context.next_best_question)
        if value and question:
            clarification = (
                f"{value} ist als {label} im Arbeitsstand. "
                f"Für die technische Einordnung muss ich das genauer fassen: {question}"
            )
            return _join_orientation_and_question(orientation, clarification)
        if question:
            return _join_orientation_and_question(orientation, question)

    if context.accepted_updates:
        question = _clean_question(context.next_best_question or _question_for_missing_fields(context.missing_fields))
        if question:
            return _join_orientation_and_question(orientation, question)
        return _join_orientation_and_question(
            orientation,
            "Ich halte die Angabe als Arbeitsstand fest und prüfe den nächsten sinnvollen Schritt.",
        )

    question = _clean_question(context.next_best_question or _question_for_missing_fields(context.missing_fields))
    if question:
        intake_orientation = _human_intake_orientation(context.latest_user_message)
        if intake_orientation:
            return _join_intake_orientation_and_question(
                intake_orientation,
                _humanize_intake_question(question),
            )
        return _join_orientation_and_question(orientation, question)
    return ""


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
        return (
            "Verstanden, eine Leckage würde ich zuerst als Fallbild sauber eingrenzen, "
            "damit wir Ursache, Betriebsbedingungen und Dichtprinzip nicht vermischen."
        )
    if any(marker in text for marker in goal_markers):
        return (
            "Verstanden, wir grenzen die Anwendung Schritt für Schritt ein und halten nur "
            "belastbare Angaben als Arbeitsstand fest."
        )
    return ""


def _humanize_intake_question(question: str) -> str:
    text = str(question or "").strip()
    lowered = text.casefold()
    if "medium" in lowered and "welches medium" in lowered:
        return (
            "Was kommt an der Dichtstelle genau an, inklusive Konzentration, "
            "Additiven oder Reinigungsmedien?"
        )
    if "dichtungstyp" in lowered or "dichtprinzip" in lowered:
        return (
            "Wo sitzt die Leckage genau und welches Dichtprinzip ist dort verbaut, "
            "zum Beispiel RWDR, Gleitringdichtung, O-Ring oder Flachdichtung?"
        )
    if "druck" in lowered:
        return "Welcher Druck liegt direkt an der Dichtstelle an?"
    if "temperatur" in lowered:
        return "In welchem Temperaturbereich arbeitet die Dichtstelle?"
    return text


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
        return (
            "Bei früher Leckage an einem RWDR würde ich nicht zuerst den Werkstoff allein "
            "bewerten, sondern das Schadbild systematisch trennen. Typische Ursachencluster "
            "sind Gegenlauffläche, Laufspur, Rundlauf, Montage, Dichtlippe, Schmierung, "
            "Druck direkt an der Dichtstelle, Temperatur, Mediumverträglichkeit und "
            "Verschmutzung. Das ist eine technische Orientierung, keine Freigabe."
        )
    if {"ptfe", "fkm", "epdm", "nbr", "hnbr"}.intersection(set(re.findall(r"\b[a-z0-9]+\b", text))):
        if ("hydraulik" in text or "hlp" in text or "öl" in text or "oel" in text) and "epdm" in text:
            return (
                "Bei mineralöl- oder hydraulikölnahen Medien ist EPDM eher ein Warnpunkt, "
                "während NBR, HNBR oder FKM je nach Temperatur, Bauform und Compound eher "
                "als Prüfhypothesen betrachtet werden. Das ist eine Vororientierung, keine "
                "Werkstofffreigabe."
            )
        return (
            "Bei diesem Werkstoffvergleich sind Medium, Temperatur, Dichtungstyp, Vorspannung, "
            "Geometrie und Kontaktzeit die Haupttreiber. Das ist eine Vororientierung, keine "
            "Werkstofffreigabe."
        )
    if "rwdr" in text or "wellendichtring" in text or "radialwellendichtring" in text:
        return (
            "Technisch kritisch sind bei einem RWDR vor allem Druck direkt an der Dichtlippe, "
            "Umfangsgeschwindigkeit, Reibwärme, Schmierung, Gegenlauffläche, Rundlauf und "
            "Medium-/Temperaturbelastung. Das ist eine technische Orientierung, keine Freigabe."
        )
    return (
        "Technisch relevant sind zuerst Medium, Temperaturprofil, Druck direkt an der Dichtstelle, "
        "Bewegung, Geometrie und Nachweise. Das ist eine Vororientierung, keine Freigabe."
    )


def _join_orientation_and_question(orientation: str, question: str) -> str:
    clean_orientation = str(orientation or "").strip()
    clean_question = str(question or "").strip()
    if clean_orientation and clean_question:
        return f"{clean_orientation}\n\nDie wichtigste Rückfrage ist: {clean_question}"
    return clean_question or clean_orientation


def _join_intake_orientation_and_question(orientation: str, question: str) -> str:
    clean_orientation = str(orientation or "").strip()
    clean_question = str(question or "").strip()
    if clean_orientation and clean_question:
        return f"{clean_orientation}\n\nDafür muss ich zuerst wissen: {clean_question}"
    return clean_question or clean_orientation


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
                "Zylinder oder Behälter?"
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
