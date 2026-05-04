from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.agent.graph.slot_answer_binding import resolve_slot_answer_binding
from app.agent.state.models import GovernedSessionState, PendingQuestion, SlotAnswerBinding
from app.agent.communication.v7_contracts import TurnDecision


@dataclass(frozen=True, slots=True)
class ActiveCaseResumeDecision:
    resume_strategy: str
    resume_target_field: str | None = None
    resume_target_question: str | None = None
    resume_reason: str = ""
    pending_question_restored: bool = False
    next_runtime_action: str = "answer_only"
    latest_user_question_answered: bool = True
    slot_answer_detected: bool = False
    case_delta_allowed: bool = False
    governed_graph_allowed: bool = False
    detected_slot_field: str | None = None
    detected_slot_value: Any = None

    def as_trace(self) -> dict[str, Any]:
        return asdict(self)


def reevaluate_active_case_resume(
    *,
    latest_user_message: str,
    governed_state: GovernedSessionState | None,
    turn_decision: TurnDecision | None = None,
) -> ActiveCaseResumeDecision:
    """Decide how communication should resume after an active-case process answer.

    This seam is intentionally communication-only. It may detect that a value
    exists in the latest user turn, but it never confirms or writes engineering
    state.
    """

    pending = getattr(governed_state, "pending_question", None) if governed_state is not None else None
    message = str(latest_user_message or "").strip()
    slot_binding = _detect_pending_slot_answer(
        pending_question=pending,
        message=message,
        governed_state=governed_state,
    )
    if slot_binding is not None:
        return ActiveCaseResumeDecision(
            resume_strategy="accept_or_route_pending_slot_answer",
            resume_target_field=slot_binding.target_field,
            resume_target_question=_pending_question_text(pending),
            resume_reason="latest_user_turn_contains_pending_slot_value",
            pending_question_restored=False,
            next_runtime_action="route_pending_slot_answer",
            slot_answer_detected=True,
            case_delta_allowed=False,
            governed_graph_allowed=True,
            detected_slot_field=slot_binding.target_field,
            detected_slot_value=slot_binding.normalized_value
            if slot_binding.normalized_value is not None
            else slot_binding.raw_value,
        )

    if pending is None:
        return ActiveCaseResumeDecision(
            resume_strategy="answer_only_no_resume",
            resume_reason="no_pending_question_available",
            pending_question_restored=False,
            next_runtime_action="wait_for_user",
        )

    pending_field = str(getattr(pending, "target_field", "") or "").strip()
    pending_status = str(getattr(pending, "status", "") or "").strip()
    if pending_status and pending_status != "open":
        return _reprioritize_or_pause(
            governed_state=governed_state,
            pending_field=pending_field,
            reason=f"pending_question_status_{pending_status}",
        )

    if pending_field and _field_has_asserted_value(governed_state, pending_field):
        return _reprioritize_or_pause(
            governed_state=governed_state,
            pending_field=pending_field,
            reason="pending_field_already_asserted",
        )

    target_question = _pending_question_text(pending)
    return ActiveCaseResumeDecision(
        resume_strategy="answer_then_continue_pending_question",
        resume_target_field=pending_field or None,
        resume_target_question=target_question or None,
        resume_reason="pending_question_still_open_and_no_slot_answer_detected",
        pending_question_restored=bool(target_question),
        next_runtime_action="continue_pending_question",
    )


def _reprioritize_or_pause(
    *,
    governed_state: GovernedSessionState | None,
    pending_field: str,
    reason: str,
) -> ActiveCaseResumeDecision:
    target_field = _next_missing_field(governed_state, exclude={pending_field})
    if target_field:
        return ActiveCaseResumeDecision(
            resume_strategy="answer_then_reprioritize_next_question",
            resume_target_field=target_field,
            resume_target_question=_question_for_field(target_field),
            resume_reason=reason,
            pending_question_restored=False,
            next_runtime_action="ask_reprioritized_question",
        )
    return ActiveCaseResumeDecision(
        resume_strategy="answer_only_no_resume",
        resume_reason=reason,
        pending_question_restored=False,
        next_runtime_action="wait_for_user",
    )


def _detect_pending_slot_answer(
    *,
    pending_question: PendingQuestion | None,
    message: str,
    governed_state: GovernedSessionState | None,
) -> SlotAnswerBinding | None:
    if pending_question is None:
        return None
    turn_index = int(getattr(governed_state, "user_turn_index", 0) or 0) + 1
    binding = resolve_slot_answer_binding(
        pending_question=pending_question,
        message=message,
        turn_index=turn_index,
    )
    if binding is not None:
        return binding
    return _detect_explicit_medium_answer(
        pending_question=pending_question,
        message=message,
        turn_index=turn_index,
    )


def _detect_explicit_medium_answer(
    *,
    pending_question: PendingQuestion,
    message: str,
    turn_index: int,
) -> SlotAnswerBinding | None:
    if str(getattr(pending_question, "target_field", "") or "") != "medium":
        return None
    if str(getattr(pending_question, "expected_answer_type", "") or "") != "medium_value":
        return None
    normalized = " ".join(str(message or "").strip().split())
    if not normalized:
        return None
    match = re.search(
        r"\b(?:das\s+)?medium\s+(?:ist|waere|wäre|is|=|:)\s+([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß0-9 /+\-.]{1,48})",
        normalized,
        re.IGNORECASE,
    )
    if not match:
        return None
    raw = match.group(1).strip(" .,!;:")
    if not raw:
        return None
    return SlotAnswerBinding(
        target_field="medium",
        raw_value=raw,
        normalized_value=raw[:1].upper() + raw[1:],
        source="pending_question",
        confidence=0.86,
        ambiguity=False,
        needs_clarification=False,
        turn_index=turn_index,
    )


def _field_has_asserted_value(governed_state: GovernedSessionState | None, field_name: str) -> bool:
    assertions = getattr(getattr(governed_state, "asserted", None), "assertions", {}) or {}
    claim = assertions.get(field_name)
    value = getattr(claim, "asserted_value", None)
    return value is not None and str(value).strip() != ""


def _next_missing_field(governed_state: GovernedSessionState | None, *, exclude: set[str]) -> str | None:
    asserted = getattr(governed_state, "asserted", None)
    assertions = getattr(asserted, "assertions", {}) or {}
    for field in list(getattr(asserted, "blocking_unknowns", []) or []):
        field_name = str(field or "").strip()
        if not field_name or field_name in exclude:
            continue
        claim = assertions.get(field_name)
        value = getattr(claim, "asserted_value", None)
        if value is None or str(value).strip() == "":
            return field_name
    return None


def _pending_question_text(pending: PendingQuestion | None) -> str:
    if pending is None:
        return ""
    explicit = str(getattr(pending, "question_text", "") or "").strip()
    if explicit:
        return explicit
    return _question_for_field(str(getattr(pending, "target_field", "") or ""))


def _question_for_field(field: str) -> str:
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
