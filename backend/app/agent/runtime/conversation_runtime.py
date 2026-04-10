"""
Conversation Runtime — Phase F-A.4

Handles the CONVERSATION routing zone:
- General knowledge questions about sealing technology
- Smalltalk and process questions
- First orientation without technical system effect
- Explanation of governed results to the user

Properties (Umbauplan F-A.4):
- Direct LLM call (OpenAI async streaming)
- SSE streaming — same wire format as governed path
- No RAG, no LangGraph, no graph state
- Stateless — caller provides history slice
- Boundary block appended deterministically after LLM text
- All output passes through response_renderer outward contract

SSE wire format (matches existing sse_runtime.py convention):
    data: {"type": "text_chunk", "text": "..."}\n\n
    data: {"type": "boundary_block", "text": "..."}\n\n
    data: {"type": "stream_end"}\n\n
    data: [DONE]\n\n
"""
from __future__ import annotations

import json
import logging
import os
import inspect
import re
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal

import openai

from app.agent.runtime.boundaries import FAST_PATH_DISCLAIMER
from app.agent.runtime.user_facing_reply import assemble_user_facing_reply
from app.agent.runtime.clarification_priority import select_next_focus_from_known_context
from app.agent.runtime.reply_composition import (
    _build_turn_context_instruction,
    build_conversation_phase_prompt,
    compose_user_facing_mouth_reply,
    build_turn_context_instruction,
)
from app.agent.runtime.response_renderer import render_chunk, render_response
from app.agent.runtime.turn_context import build_turn_context_contract
from app.agent.state.models import ConversationStrategyContract
from prompts.builder import PromptBuilder

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_CONVERSATION_MODEL = os.environ.get("SEALAI_CONVERSATION_MODEL", "gpt-4o-mini")

_prompt_builder = PromptBuilder()

_GREETING_RE = re.compile(r"^\s*(hallo|hi|hey|guten tag|guten morgen|moin)\b[\s!,.?]*$", re.IGNORECASE)
_OPEN_ENTRY_RE = re.compile(
    r"\b(moechte|möchte|will|wir suchen|suche|brauche|erarbeiten|entwickeln|auslegen|hilfe|unterstuetzung|unterstützung)\b",
    re.IGNORECASE,
)
_TECHNICAL_MARKER_RE = re.compile(
    r"\b(bar|°c|rpm|mm|mpa|hydraulik|temperatur|druck|medium|wellendurchmesser|drehzahl|rwdr)\b|\d",
    re.IGNORECASE,
)
_ORIENTATION_QUESTION_RE = re.compile(
    r"^\s*(was\s+ist|was\s+bedeutet|wie\s+funktioniert|erklaer|erklär|wofuer|wofür|wann\s+nimmt\s+man)\b",
    re.IGNORECASE,
)
_LEAKAGE_RE = re.compile(r"\b(leck\w*|leckage\w*|undicht\w*|dichtheit\w*)\b", re.IGNORECASE)
_PROBLEM_RE = re.compile(r"\b(problem\w*|ausfall\w*|stoer\w*|stör\w*|schaden\w*|fehler\w*|undicht\w*|leckage\w*)\b", re.IGNORECASE)
_UNCERTAINTY_RE = re.compile(r"\b(unsicher|unklar|weiss nicht|weiß nicht|nicht sicher|offen)\b", re.IGNORECASE)
_CORRECTION_RE = re.compile(r"\b(korrigier\w*|korrektur|nicht\s+[^.?!]+\s+sondern|stattdessen)\b", re.IGNORECASE)

# Detects medium mentions in user turns — used to suppress repeated "Welches Medium?" questions
# when the user has already mentioned a medium in prior conversation history.
_MEDIUM_MENTION_RE = re.compile(
    r"\b(wasser|oel|öl|dampf|luft|hydraulik|hydrauliköl|hydraulikoel|"
    r"chemie|saeure|säure|lauge|lösungsmittel|loesungsmittel|"
    r"kraftstoff|benzin|diesel|emulsion|kuehlmittel|kühlmittel|"
    r"schmiermittel|medium|fluessigkeit|flüssigkeit|reiniger|tensid|"
    r"ipa|alkohol|glykol|glysantin|wärmeträger|waermetraeger|öle\b|"
    r"mineraloel|mineralöl|synthetiköl|synthetikoel|ethanol|methanol|"
    r"druckluft|stickstoff|wärmetraeger)\b",
    re.IGNORECASE,
)

ConversationLightMode = Literal["CONVERSATION", "EXPLORATION"]

# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse(event_type: str, text: str) -> str:
    return f"data: {json.dumps({'type': event_type, 'text': text})}\n\n"


def _sse_end() -> str:
    return "data: [DONE]\n\n"


def _sse_error(message: str) -> str:
    return f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"


def _conversation_visible_event(event_type: str, text: str, **metadata: Any) -> dict[str, Any]:
    """Single exit seam for visible conversation text events."""
    event: dict[str, Any] = {"type": event_type, "text": text}
    event.update(metadata)
    return event


def _conversation_state_update_event(
    *,
    reply: str,
    strategy: ConversationStrategyContract | None,
    turn_context,
) -> dict[str, Any]:
    payload = assemble_user_facing_reply(
        reply=reply,
        structured_state=None,
        policy_path="fast",
        run_meta=None,
        state_update=False,
        response_class="conversational_answer",
    )
    event: dict[str, Any] = {"type": "state_update", **payload}
    if strategy is not None:
        event["conversation_strategy"] = strategy.model_dump()
    if turn_context is not None:
        event["turn_context"] = turn_context.model_dump()
    return event


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------

def _build_messages(
    message: str,
    history: list[dict[str, str]] | None,
    case_summary: str | None = None,
    mode: ConversationLightMode | None = None,
) -> list[dict[str, str]]:
    """Build the OpenAI messages list from history + current message."""
    turn_context = _build_conversation_turn_context(
        message,
        history=history,
        case_summary=case_summary,
        mode=mode,
    )
    phase_prompt = (
        None
        if mode == "CONVERSATION"
        else build_conversation_phase_prompt(
            turn_context=turn_context,
            latest_user_text=_last_user_turn_text(message, history),
            case_summary=case_summary,
        )
    )
    system_prompt = (
        None
        if mode == "CONVERSATION"
        else phase_prompt or _prompt_builder.conversation(case_summary=case_summary)
    )
    msgs: list[dict[str, str]] = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})
    strategy_instruction = (
        build_turn_context_instruction(turn_context)
        if phase_prompt is None
        else _build_turn_context_instruction(
            turn_context,
            include_phase_guidance=False,
            include_focus=True,
            include_reason=False,
        )
    )
    if strategy_instruction:
        msgs.append({"role": "system", "content": strategy_instruction})
    for turn in (history or []):
        role = turn.get("role", "")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})
    # Belt-and-suspenders: inject explicit "DO NOT ASK AGAIN" block when we have
    # confirmed params. This guards against the LLM ignoring history-based hints.
    if case_summary and case_summary.strip():
        msgs.append({
            "role": "system",
            "content": (
                "BEREITS BEKANNTE PARAMETER — DIESE NICHT ERNEUT ERFRAGEN:\n"
                + case_summary
                + "\n\nFrage KEINEN dieser Parameter erneut ab. Baue stattdessen auf ihnen auf."
            ),
        })
    msgs.append({"role": "user", "content": message})
    return msgs


def _count_user_turns(history: list[dict[str, str]] | None) -> int:
    return sum(1 for turn in (history or []) if turn.get("role") == "user")


def _last_user_turn_text(message: str, history: list[dict[str, str]] | None) -> str:
    current = str(message or "").strip()
    if current:
        return current
    for turn in reversed(history or []):
        if turn.get("role") == "user" and str(turn.get("content") or "").strip():
            return str(turn.get("content") or "").strip()
    return ""


def _build_conversation_turn_context(
    message: str,
    *,
    history: list[dict[str, str]] | None = None,
    case_summary: str | None = None,
    mode: ConversationLightMode | None = None,
):
    strategy = _build_conversation_strategy_contract(
        message,
        history=history,
        case_summary=case_summary,
        mode=mode,
    )
    return build_turn_context_contract(
        strategy=strategy,
        confirmed_facts_summary=_build_light_confirmed_facts_summary(
            history=history,
            case_summary=case_summary,
        ),
        open_points_summary=_build_light_open_points_summary(strategy),
    )


def _build_light_confirmed_facts_summary(
    *,
    history: list[dict[str, str]] | None,
    case_summary: str | None,
) -> list[str]:
    facts: list[str] = []
    for raw_line in str(case_summary or "").splitlines():
        text = str(raw_line or "").strip()
        if text.startswith("-"):
            text = text[1:].strip()
        if ":" not in text or not text:
            continue
        if text not in facts:
            facts.append(text)
        if len(facts) >= 3:
            return facts

    for turn in reversed(history or []):
        if turn.get("role") != "user":
            continue
        content = str(turn.get("content") or "").strip()
        if not content:
            continue
        if content not in facts:
            facts.append(content)
        if len(facts) >= 3:
            break
    return facts[:3]


def _build_light_open_points_summary(
    strategy: ConversationStrategyContract | None,
) -> list[str]:
    if strategy is None or not strategy.primary_question:
        return []
    return [str(strategy.primary_question).rstrip("?").strip()]


def _known_fields_from_case_summary(case_summary: str | None) -> set[str]:
    labels = {
        "medium": "medium",
        "druck": "pressure_bar",
        "betriebsdruck": "pressure_bar",
        "temperatur": "temperature_c",
        "betriebstemperatur": "temperature_c",
        "wellen-ø": "shaft_diameter_mm",
        "wellendurchmesser": "shaft_diameter_mm",
        "drehzahl": "speed_rpm",
        "einbausituation": "installation",
        "geometrie": "geometry_context",
        "bauform": "geometry_context",
        "spalt": "clearance_gap_mm",
        "toleranz": "clearance_gap_mm",
        "oberflaeche": "counterface_surface",
        "oberfläche": "counterface_surface",
        "gegenlaufpartner": "counterface_surface",
        "gegenlaufwerkstoff": "counterface_material",
        "gegenlaufmaterial": "counterface_material",
        "anforderungsklasse": "requirement_class",
    }
    known: set[str] = set()
    raw_segments: list[str] = []
    for raw_line in str(case_summary or "").splitlines():
        raw_segments.extend(segment.strip() for segment in raw_line.split("|"))
    for raw_line in raw_segments:
        text = str(raw_line or "").strip().lstrip("-").strip()
        if ":" not in text:
            continue
        label = text.split(":", 1)[0].strip().lower()
        mapped = labels.get(label)
        if mapped:
            known.add(mapped)
    return known


def _build_conversation_strategy_contract(
    message: str,
    *,
    history: list[dict[str, str]] | None = None,
    case_summary: str | None = None,
    mode: ConversationLightMode | None = None,
) -> ConversationStrategyContract | None:
    """Return a small deterministic strategy hint for conversation turns."""
    text = str(message or "").strip()
    lowered = text.lower()
    turn_index = _count_user_turns(history) + 1
    has_case_context = bool(case_summary and case_summary.strip())
    known_fields = _known_fields_from_case_summary(case_summary)

    # ROOT CAUSE FIX: If medium is not yet in case_summary (e.g. pure fast-path session
    # where the governed graph was never run), scan the conversation history for medium
    # mentions. This prevents the AI from repeatedly asking "Welches Medium soll abgedichtet
    # werden?" after the user has already mentioned a medium substance.
    if "medium" not in known_fields:
        for _turn in reversed((history or [])[-16:]):
            if _turn.get("role") == "user":
                if _MEDIUM_MENTION_RE.search(str(_turn.get("content") or "")):
                    known_fields = known_fields | {"medium"}
                    break

    is_problem = bool(_LEAKAGE_RE.search(lowered) or _PROBLEM_RE.search(lowered))
    is_goal = bool(_OPEN_ENTRY_RE.search(lowered))
    is_uncertain = bool(_UNCERTAINTY_RE.search(lowered))
    is_correction = bool(_CORRECTION_RE.search(lowered))
    has_technical_markers = bool(_TECHNICAL_MARKER_RE.search(lowered))

    if is_correction:
        user_signal_mirror = "Verstanden, ich gehe jetzt von Ihrer Korrektur aus"
    elif is_problem:
        user_signal_mirror = "Verstanden, Sie beschreiben ein konkretes Leckage- oder Ausfallbild"
    elif is_goal:
        user_signal_mirror = "Verstanden, Sie wollen die Anwendung schrittweise eingrenzen"
    elif is_uncertain:
        user_signal_mirror = "Verstanden, die Lage ist noch nicht ganz klar"
    elif has_technical_markers:
        user_signal_mirror = "Verstanden, damit liegen schon technische Randbedingungen vor"
    else:
        user_signal_mirror = ""

    focus_priority = select_next_focus_from_known_context(
        known_fields=known_fields,
        medium_status="recognized" if "medium" in known_fields else "unknown",
        current_text=" ".join(
            filter(
                None,
                [
                    text,
                    *(str(turn.get("content") or "").strip() for turn in (history or [])[-4:] if turn.get("role") == "user"),
                    str(case_summary or "").strip(),
                ],
            )
        ),
        application_anchor_present="installation" in known_fields,
        rotary_context_detected=bool({"speed_rpm", "shaft_diameter_mm"} & known_fields),
    )

    if mode == "CONVERSATION":
        return ConversationStrategyContract(
            conversation_phase="rapport" if turn_index == 1 else "exploration",
            turn_goal="answer_light_request",
            user_signal_mirror=user_signal_mirror,
            primary_question=None,
            primary_question_reason="",
            response_mode="guided_explanation",
        )
    if mode == "EXPLORATION":
        conversation_phase = "exploration"
    else:
        if turn_index == 1 and not has_case_context:
            conversation_phase = "rapport"
        elif focus_priority is not None and has_case_context:
            conversation_phase = "narrowing"
        else:
            conversation_phase = "exploration" if turn_index in (2, 3) and not has_case_context else "recommendation"

    if conversation_phase == "rapport":
        return ConversationStrategyContract(
            conversation_phase="rapport",
            turn_goal="open_conversation",
            user_signal_mirror=user_signal_mirror,
            primary_question="Beschreiben Sie mir bitte zunaechst kurz, worum es in Ihrer Anwendung oder Ihrem Anliegen geht?",
            primary_question_reason="Ein offenes Bild der Ausgangslage setzt den sinnvollsten naechsten Fokus.",
            response_mode="open_invitation",
        )

    if conversation_phase == "exploration":
        if focus_priority is not None and has_case_context:
            return ConversationStrategyContract(
                conversation_phase="exploration",
                turn_goal="set_next_best_focus",
                user_signal_mirror=user_signal_mirror or "Das hilft schon deutlich.",
                primary_question=focus_priority.question,
                primary_question_reason=focus_priority.reason,
                response_mode="open_invitation",
            )
        if is_problem:
            primary_question = "In welcher Situation zeigt sich die Leckage oder das Problem am deutlichsten?"
            primary_question_reason = "Der sichtbarste Auftretensmoment macht die naechste Eingrenzung am belastbarsten."
        elif is_goal:
            primary_question = "Welche Anwendung oder Situation sollen wir uns dafuer als Erstes genauer ansehen?"
            primary_question_reason = "Der erste Anwendungsanker setzt den sinnvollsten weiteren Fokus."
        elif is_uncertain:
            primary_question = "Welche Stelle der Situation ist fuer Sie im Moment noch am unklarsten?"
            primary_question_reason = "Die groesste Unklarheit zeigt, wo wir zuerst Struktur schaffen sollten."
        else:
            primary_question = "Welche Situation sollen wir uns als Naechstes gemeinsam genauer ansehen?"
            primary_question_reason = "So setzen wir den naechsten Schritt auf den relevantesten Aspekt."
        return ConversationStrategyContract(
            conversation_phase="exploration",
            turn_goal="expand_case_understanding",
            user_signal_mirror=user_signal_mirror,
            primary_question=primary_question,
            primary_question_reason=primary_question_reason,
            response_mode="open_invitation",
        )

    if conversation_phase == "recommendation":
        return ConversationStrategyContract(
            conversation_phase="recommendation",
            turn_goal="explain_current_state",
            user_signal_mirror=user_signal_mirror,
            primary_question=None,
            primary_question_reason="",
            response_mode="guided_explanation",
        )

    if _ORIENTATION_QUESTION_RE.search(lowered):
        return ConversationStrategyContract(
            conversation_phase="narrowing",
            turn_goal="answer_orientation_question",
            user_signal_mirror=user_signal_mirror,
            primary_question=None,
            primary_question_reason="",
            response_mode="guided_explanation",
        )

    if focus_priority is not None:
        return ConversationStrategyContract(
            conversation_phase="narrowing",
            turn_goal="clarify_primary_open_point",
            user_signal_mirror=user_signal_mirror or "Dann setze ich jetzt den naechsten technischen Hebel.",
            primary_question=focus_priority.question,
            primary_question_reason=focus_priority.reason,
            response_mode="single_question",
        )

    return ConversationStrategyContract(
        conversation_phase="narrowing",
        turn_goal="clarify_primary_open_point",
        user_signal_mirror=user_signal_mirror,
        primary_question="Welcher Aspekt Ihrer Anwendung ist im Moment am kritischsten?",
        primary_question_reason="So priorisieren wir den naechsten technischen Klaerungsschritt.",
        response_mode="single_question",
    )

async def _create_completion_stream(client: openai.AsyncOpenAI, *, messages: list[dict[str, str]]):
    """Support both awaitable SDK responses and direct test doubles."""
    stream_or_awaitable = client.chat.completions.create(
        model=_CONVERSATION_MODEL,
        messages=messages,
        stream=True,
        temperature=0.3,
        max_tokens=800,
    )
    if inspect.isawaitable(stream_or_awaitable):
        return await stream_or_awaitable
    return stream_or_awaitable


# ---------------------------------------------------------------------------
# Core conversation execution
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConversationResult:
    reply_text: str
    error_message: str | None = None


async def iter_conversation_events(
    message: str,
    *,
    history: list[dict[str, str]] | None = None,
    case_summary: str | None = None,
    mode: ConversationLightMode | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Yield canonical conversation events for both JSON and SSE adapters.

    Args:
        message: Current user message.
        history: Optional list of prior turns as {"role": ..., "content": ...}.
                 Maximum recent turns the caller should include — this runtime
                 is stateless and does not store history itself.
        case_summary: Optional parameter summary built from working_profile,
                      injected into the system prompt so Thomas Reiter knows
                      what parameters have already been captured.

    Properties:
        - No RAG, no LangGraph.
        - No graph state writes or governed persistence.
        - All text chunks pass through render_chunk (outward contract).
        - Full assembled text passes through render_response for policy check.
        - Boundary block (FAST_PATH_DISCLAIMER) is always appended on success.
        - LLM errors yield an error event and stop.
    """
    client = openai.AsyncOpenAI()
    messages = _build_messages(message, history, case_summary=case_summary, mode=mode)
    strategy = _build_conversation_strategy_contract(
        message,
        history=history,
        case_summary=case_summary,
        mode=mode,
    )
    turn_context = _build_conversation_turn_context(
        message,
        history=history,
        case_summary=case_summary,
        mode=mode,
    )

    accumulated: list[str] = []
    try:
        stream = await _create_completion_stream(client, messages=messages)
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            text = getattr(delta, "content", None) if delta else None
            if not text:
                continue
            clean = render_chunk(text, path="CONVERSATION")
            if not clean:
                continue
            accumulated.append(clean)
            yield _conversation_visible_event("text_chunk", clean, preview_only=True)

    except Exception as exc:
        log.error("[conversation_runtime] LLM stream error: %s: %s", type(exc).__name__, exc)
        yield {"type": "error", "message": "Momentan nicht verfügbar — bitte erneut versuchen."}
        return

    full_text = "".join(accumulated)
    rendered = render_response(full_text, path="CONVERSATION")
    final_reply = str(rendered.text or "").strip()
    final_reply = compose_user_facing_mouth_reply(
        final_reply,
        turn_context,
        response_class="conversational_answer",
    )
    if final_reply:
        final_reply = str(render_response(final_reply, path="CONVERSATION").text or final_reply).strip()

    if rendered.policy_violation:
        # Policy guard triggered — emit only an audit replacement marker.
        # The canonical visible reply is carried exclusively via state_update.
        log.warning(
            "[conversation_runtime] policy violation (%s) — emitting correction",
            rendered.policy_violation,
        )
        yield _conversation_visible_event("text_replacement", final_reply)

    yield _conversation_state_update_event(
        reply=final_reply,
        strategy=strategy,
        turn_context=turn_context,
    )

    yield _conversation_visible_event("boundary_block", FAST_PATH_DISCLAIMER)
    yield {"type": "stream_end"}


async def run_conversation(
    message: str,
    *,
    history: list[dict[str, str]] | None = None,
    case_summary: str | None = None,
    mode: ConversationLightMode | None = None,
) -> ConversationResult:
    """Execute the conversation path and return the canonical reply text."""
    reply_text = ""
    replacement_echo: str | None = None

    async for event in iter_conversation_events(message, history=history, case_summary=case_summary, mode=mode):
        event_type = str(event.get("type") or "")
        if event_type == "text_replacement":
            replacement_echo = str(event.get("text") or "")
            continue
        if event_type == "state_update":
            reply_text = str(event.get("reply") or "").strip()
            replacement_echo = None
            continue
        if event_type == "text_chunk":
            text = str(event.get("text") or "")
            if not text:
                continue
            continue
        if event_type == "error":
            message_text = str(event.get("message") or "").strip()
            return ConversationResult(reply_text=message_text, error_message=message_text or None)
    return ConversationResult(reply_text=reply_text.strip())


async def stream_conversation(
    message: str,
    *,
    history: list[dict[str, str]] | None = None,
    case_summary: str | None = None,
    mode: ConversationLightMode | None = None,
) -> AsyncGenerator[str, None]:
    """Stream a conversation-path response as SSE events."""
    async for event in iter_conversation_events(message, history=history, case_summary=case_summary, mode=mode):
        event_type = str(event.get("type") or "")
        if event_type == "error":
            yield _sse_error(str(event.get("message") or ""))
            yield _sse_end()
            return
        if event_type == "stream_end":
            yield 'data: {"type": "stream_end"}\n\n'
            yield _sse_end()
            return
        if event_type == "state_update":
            yield f"data: {json.dumps(event, default=str)}\n\n"
            continue
        if "text" in event:
            yield f"data: {json.dumps(event, default=str)}\n\n"
