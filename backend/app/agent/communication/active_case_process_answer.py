from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from app.agent.communication.active_case_resume import (
    ActiveCaseResumeDecision,
    reevaluate_active_case_resume,
)
from app.agent.communication.templates import render_communication_template
from app.agent.communication.v7_contracts import TurnDecision
from app.agent.runtime.output_guard import check_fast_path_output
from app.agent.state.models import GovernedSessionState, PendingQuestion
from app.llm.factory import get_async_llm

log = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "y", "on", "enabled"}
_MAX_ANSWER_CHARS = 1800


@dataclass(frozen=True, slots=True)
class ActiveCaseProcessAnswerResult:
    answer_markdown: str
    deterministic_fallback: str
    builder_attempted: bool
    builder_succeeded: bool
    fallback_reason: str | None
    pending_question_restored: bool
    resume_decision: ActiveCaseResumeDecision


def is_active_case_process_answer_composer_enabled() -> bool:
    return os.getenv("SEALAI_ENABLE_ACTIVE_CASE_PROCESS_ANSWER_COMPOSER", "true").strip().lower() in _TRUE_VALUES


async def build_active_case_process_answer(
    *,
    latest_user_message: str,
    governed_state: GovernedSessionState | None,
    turn_decision: TurnDecision | None,
) -> ActiveCaseProcessAnswerResult:
    """Build a no-mutation process/help answer for an active governed case."""

    resume_decision = reevaluate_active_case_resume(
        latest_user_message=latest_user_message,
        governed_state=governed_state,
        turn_decision=turn_decision,
    )
    context = _build_process_context(
        latest_user_message=latest_user_message,
        governed_state=governed_state,
        turn_decision=turn_decision,
        resume_decision=resume_decision,
    )
    fallback = _deterministic_process_answer(context)
    attempted = False
    fallback_reason: str | None = None

    if not is_active_case_process_answer_composer_enabled():
        return ActiveCaseProcessAnswerResult(
            answer_markdown=fallback,
            deterministic_fallback=fallback,
            builder_attempted=False,
            builder_succeeded=False,
            fallback_reason="composer_disabled",
            pending_question_restored=resume_decision.pending_question_restored,
            resume_decision=resume_decision,
        )

    attempted = True
    try:
        answer = await asyncio.wait_for(
            _compose_process_answer_with_llm(context=context, deterministic_fallback=fallback),
            timeout=float(os.getenv("SEALAI_ACTIVE_CASE_PROCESS_ANSWER_TIMEOUT_S", "8.0")),
        )
        return ActiveCaseProcessAnswerResult(
            answer_markdown=answer,
            deterministic_fallback=fallback,
            builder_attempted=True,
            builder_succeeded=True,
            fallback_reason=None,
            pending_question_restored=resume_decision.pending_question_restored,
            resume_decision=resume_decision,
        )
    except Exception as exc:  # noqa: BLE001
        fallback_reason = _safe_reason(exc)
        log.warning("[active_case_process_answer] fallback reason=%s", fallback_reason)

    return ActiveCaseProcessAnswerResult(
        answer_markdown=fallback,
        deterministic_fallback=fallback,
        builder_attempted=attempted,
        builder_succeeded=False,
        fallback_reason=fallback_reason,
        pending_question_restored=resume_decision.pending_question_restored,
        resume_decision=resume_decision,
    )


def _build_process_context(
    *,
    latest_user_message: str,
    governed_state: GovernedSessionState | None,
    turn_decision: TurnDecision | None,
    resume_decision: ActiveCaseResumeDecision,
) -> dict[str, Any]:
    pending = getattr(governed_state, "pending_question", None) if governed_state is not None else None
    recent_messages = list(getattr(governed_state, "conversation_messages", []) or [])[-8:] if governed_state is not None else []
    assertions = getattr(getattr(governed_state, "asserted", None), "assertions", {}) or {}
    missing_fields = list(getattr(getattr(governed_state, "asserted", None), "blocking_unknowns", []) or [])
    known_facts = []
    for field_name, claim in list(assertions.items())[:4]:
        value = getattr(claim, "asserted_value", None)
        if value is None or str(value).strip() == "":
            continue
        known_facts.append(
            {
                "field": str(field_name),
                "label": _field_label(str(field_name)),
                "value": str(value),
            }
        )
    pending_text = (
        resume_decision.resume_target_question
        if resume_decision.pending_question_restored
        else ""
    )
    pending_field = (
        str(resume_decision.resume_target_field or "")
        or (str(getattr(pending, "target_field", "") or "") if pending is not None else "")
    )
    return {
        "latest_user_message": str(latest_user_message or "").strip(),
        "recent_messages": [
            {"role": str(getattr(message, "role", "") or ""), "content": str(getattr(message, "content", "") or "")}
            for message in recent_messages
            if str(getattr(message, "content", "") or "").strip()
        ],
        "known_facts": known_facts,
        "missing_fields": [_field_label(str(field)) for field in missing_fields[:6]],
        "pending_question_text": pending_text,
        "pending_field": pending_field,
        "pending_field_label": _field_label(pending_field) if pending_field else "",
        "pending_reason": _pending_reason(pending_field),
        "answer_obligations": list(getattr(turn_decision, "answer_obligations", []) or []),
        "mutation_policy": str(getattr(turn_decision, "mutation_policy", "forbidden") or "forbidden"),
        "resume_strategy": resume_decision.resume_strategy,
        "resume_reason": resume_decision.resume_reason,
        "resume_target_question": resume_decision.resume_target_question or "",
        "slot_answer_detected": resume_decision.slot_answer_detected,
        "detected_slot_field": resume_decision.detected_slot_field or "",
        "detected_slot_value": resume_decision.detected_slot_value,
    }


def _deterministic_process_answer(context: dict[str, Any]) -> str:
    message = str(context.get("latest_user_message") or "").casefold()
    pending_question = str(context.get("pending_question_text") or "").strip()
    resume_target_question = str(context.get("resume_target_question") or "").strip()
    resume_strategy = str(context.get("resume_strategy") or "").strip()
    slot_answer_detected = bool(context.get("slot_answer_detected"))
    pending_reason = str(context.get("pending_reason") or "").strip()
    known_facts = context.get("known_facts") if isinstance(context.get("known_facts"), list) else []
    context_recall = _asks_context_recall(message)

    if context_recall:
        intro = _context_recall_intro(context)
    elif _asks_why_current_field(message) and pending_reason:
        intro = pending_reason
    elif "analyse" in message or "analysis" in message:
        intro = (
            "Die Analyse laeuft Schritt fuer Schritt: Ich halte zunaechst den aktuellen "
            "Fallstand fest, klaere die wichtigsten offenen Betriebsdaten und trenne "
            "gesicherte Angaben von offenen Punkten."
        )
    elif "was machst" in message:
        intro = (
            "Ich ordne gerade deine Dichtungssituation so, dass daraus eine technisch "
            "belastbare Anfragebasis fuer eine Herstellerpruefung werden kann."
        )
    else:
        intro = (
            "Ich helfe dir, aus deiner Dichtungssituation eine technisch belastbare "
            "Anfragebasis zu machen. Dafuer strukturiere ich den Fall Schritt fuer "
            "Schritt: Dichtungsart, Medium, Temperatur, Druck, Bewegung, Einbauraum "
            "sowie Werkstoff- und Risikofaktoren."
        )

    if known_facts:
        facts = ", ".join(
            f"{item.get('label')}: {item.get('value')}" for item in known_facts if item.get("value")
        )
        state_line = f"Aktuell halte ich als Arbeitsstand fest: {facts}."
    else:
        state_line = "Aktuell ist dein Fall noch nicht vollstaendig eingeordnet."

    bridge = ""
    if context_recall:
        bridge = (
            "Ich halte den aktuellen Fallkontext weiter zusammen und trenne dabei "
            "gesicherte Angaben von offenen Punkten."
        )
    elif slot_answer_detected:
        field_label = _field_label(str(context.get("detected_slot_field") or ""))
        value = str(context.get("detected_slot_value") or "").strip()
        bridge = (
            f"Ich habe {value} als moegliche Antwort auf {field_label} erkannt. "
            "Ich bestaetige diesen technischen Wert hier nicht direkt, sondern "
            "fuehre ihn im naechsten technischen Schritt als Kandidat weiter."
        )
    elif pending_question and pending_reason and intro != pending_reason:
        bridge = pending_reason
    elif resume_strategy == "answer_then_reprioritize_next_question" and resume_target_question:
        bridge = (
            "Die vorherige offene Frage ist nach aktuellem Arbeitsstand nicht mehr "
            "der beste naechste Schritt. Ich priorisiere deshalb die naechste offene Angabe."
        )

    follow_up = ""
    if not slot_answer_detected and not context_recall:
        follow_up = pending_question or (
            resume_target_question
            if resume_strategy == "answer_then_reprioritize_next_question"
            else ""
        )

    fallback = "\n\n".join(part for part in (intro, state_line, bridge, follow_up) if str(part).strip())
    return render_communication_template(
        "active_case_process_answer",
        {
            "intro": intro,
            "state_line": state_line,
            "bridge": bridge,
            "follow_up": follow_up,
        },
        fallback=fallback,
    )


def _asks_context_recall(message: str) -> bool:
    return any(
        phrase in message
        for phrase in (
            "was wollte ich von dir",
            "was wollte ich gerade",
            "was war meine frage",
            "was war meine anfrage",
            "worum ging es gerade",
            "wo waren wir",
        )
    )


def _context_recall_intro(context: dict[str, Any]) -> str:
    latest = str(context.get("latest_user_message") or "").strip().casefold()
    recent = context.get("recent_messages") if isinstance(context.get("recent_messages"), list) else []
    for item in reversed(recent):
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "") != "user":
            continue
        content = str(item.get("content") or "").strip()
        if not content or content.casefold() == latest or _looks_like_social_ack(content):
            continue
        return (
            f"Du hattest mich zuletzt hierzu abgeholt: \"{_truncate(content, 180)}\". "
            "Ich habe das im laufenden Dichtungsfall als fachliche Frage im Kontext "
            "deiner Auslegung behandelt."
        )
    return (
        "Wir waren dabei, deine Dichtungssituation fachlich einzuordnen und die "
        "offenen Angaben fuer eine belastbare Anfragebasis sauber zu klaeren."
    )


def _looks_like_social_ack(message: str) -> bool:
    normalized = " ".join(message.casefold().split())
    return normalized.startswith(("danke", "vielen dank", "dankeschoen", "dankeschön"))


def _truncate(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


async def _compose_process_answer_with_llm(
    *,
    context: dict[str, Any],
    deterministic_fallback: str,
) -> str:
    client, model = get_async_llm("governed_answer_composer")
    messages = [
        {
            "role": "system",
            "content": render_communication_template(
                "active_case_process_system",
                fallback=(
                    "You write concise German process/help answers for an active SealAI "
                    "sealing case. Use only the provided context. Answer the latest user "
                    "question first, mention the active case state briefly, then follow the "
                    "provided resume_strategy. Do not ask the old pending question when "
                    "slot_answer_detected is true. Ask at most one question. Do not "
                    "fall back into generic slot intake. If the user asks what they wanted, "
                    "use recent_messages and active case context to answer that directly. "
                    "claim final suitability, RFQ readiness, compliance approval, or "
                    "manufacturer release. Return JSON with key answer_markdown only."
                ),
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "context": context,
                    "deterministic_fallback": deterministic_fallback,
                    "max_answer_chars": _MAX_ANSWER_CHARS,
                },
                ensure_ascii=True,
                default=str,
            ),
        },
    ]
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=500,
        response_format={"type": "json_object"},
    )
    raw_content = response.choices[0].message.content
    payload = json.loads(str(raw_content or "{}"))
    answer = str(payload.get("answer_markdown") or "").strip()
    if not answer:
        raise ValueError("empty_answer_markdown")
    if len(answer) > _MAX_ANSWER_CHARS:
        raise ValueError("answer_too_long")
    if "```" in answer or "answer_markdown" in answer.casefold():
        raise ValueError("internal_format_leakage")
    safe, category = check_fast_path_output(answer)
    if not safe:
        raise ValueError(f"unsafe_answer_markdown:{category}")
    if context.get("slot_answer_detected"):
        repeated_question = str(context.get("resume_target_question") or "").strip()
        if repeated_question and repeated_question in answer:
            raise ValueError("slot_answer_detected_but_pending_question_repeated")
    return answer


def _pending_question_text(pending: PendingQuestion | None) -> str:
    if pending is None:
        return ""
    explicit = str(getattr(pending, "question_text", "") or "").strip()
    if explicit:
        return explicit
    target = str(getattr(pending, "target_field", "") or "").strip()
    return render_communication_template(
        "active_case_pending_question",
        {"field": target},
        fallback=_fallback_question_for_field(target),
    )


def _pending_reason(field: str) -> str:
    if field == "medium":
        return render_communication_template(
            "active_case_pending_reason",
            {"field": field, "label": _field_label(field)},
            fallback=(
                "Der naechste sinnvolle Hebel ist das Medium, weil es Werkstoffauswahl, "
                "Bestaendigkeit und Risikobewertung stark beeinflusst."
            ),
        )
    if field == "temperature_c":
        return render_communication_template(
            "active_case_pending_reason",
            {"field": field, "label": _field_label(field)},
            fallback=(
                "Die Temperatur ist wichtig, weil sie Werkstoffverhalten, Alterung und "
                "Einsatzgrenzen der Dichtung stark beeinflusst."
            ),
        )
    if field == "pressure_bar":
        return render_communication_template(
            "active_case_pending_reason",
            {"field": field, "label": _field_label(field)},
            fallback=(
                "Der Druck ist wichtig, weil er Belastung, Verformung, Extrusionsrisiko "
                "und die passende Dichtungsbauart beeinflusst."
            ),
        )
    if field:
        return render_communication_template(
            "active_case_pending_reason",
            {"field": field, "label": _field_label(field)},
            fallback=(
                f"{_field_label(field)} ist jetzt wichtig, weil diese Angabe den Fall "
                "technisch weiter eingrenzt."
            ),
        )
    return ""


def _field_label(field: str) -> str:
    labels = {
        "medium": "Medium",
        "temperature_c": "Temperatur",
        "pressure_bar": "Druck",
        "sealing_type": "Dichtungstyp",
        "shaft_diameter_mm": "Wellendurchmesser",
        "speed_rpm": "Drehzahl",
        "motion_type": "Bewegung",
        "installation": "Einbausituation",
    }
    return labels.get(field, field.replace("_", " ").strip() or "offene Angabe")


def _fallback_question_for_field(field: str) -> str:
    if field == "medium":
        return "Welches Medium soll abgedichtet werden?"
    if field == "temperature_c":
        return "Welche Betriebstemperatur liegt an?"
    if field == "pressure_bar":
        return "Wie hoch ist der Betriebsdruck?"
    if field == "sealing_type":
        return "Um welchen Dichtungstyp geht es?"
    if field == "motion_type":
        return "Welche Bewegung liegt an?"
    return "Welche Angabe klaeren wir als Naechstes?"


def _asks_why_current_field(message: str) -> bool:
    return any(token in message for token in ("warum", "wozu", "weshalb", "wieso", "wichtig"))


def _safe_reason(exc: Exception) -> str:
    text = exc.__class__.__name__
    detail = str(exc or "").strip().split(":", 1)[0][:48]
    return f"{text}:{detail}" if detail else text
