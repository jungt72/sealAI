from __future__ import annotations

from typing import Any

from app.agent.v91.contracts import QuestionNeed, QuestionPlan


def build_question_plan_from_strategy(
    *,
    strategy: Any | None,
    state: Any | None = None,
    override_question: str | None = None,
    override_target_field: str | None = None,
    override_reason: str | None = None,
) -> QuestionPlan | None:
    """Project the existing governed strategy into the V9.1 QuestionPlan.

    The current stack already enforces one primary question in
    ConversationStrategyContract. This adapter makes that decision explicit for
    later V9.1 composers, guards and workspace projections.
    """

    question = _clean_text(override_question) or _clean_text(
        getattr(strategy, "primary_question", None)
    )
    if not question:
        return QuestionPlan(
            ask_now=False,
            reason="no_primary_question_required_for_this_turn",
        )

    target_field = _clean_text(override_target_field) or _clean_text(
        getattr(strategy, "focus_key", None)
    )
    reason = (
        _clean_text(override_reason)
        or _clean_text(getattr(strategy, "primary_question_reason", None))
        or _clean_text(getattr(strategy, "supporting_reason", None))
        or _challenge_question_reason(state)
        or "Diese Rueckfrage ist der aktuell naechste begrenzende Punkt."
    )
    need = QuestionNeed(
        need_id=_need_id(target_field, question),
        target_field=target_field,
        blocker_addressed=target_field or "current_turn_clarification",
        why_it_matters=reason,
        priority=_priority_from_strategy(strategy),
        expected_answer_type=_expected_answer_type(state, target_field),
    )
    return QuestionPlan(
        primary_question=question,
        question_need=need,
        ask_now=True,
        reason=reason,
    )


def _challenge_question_reason(state: Any | None) -> str | None:
    challenge = getattr(state, "challenge", None)
    next_question = getattr(challenge, "next_best_question", None)
    return _clean_text(getattr(next_question, "reason", None))


def _expected_answer_type(state: Any | None, target_field: str | None) -> str:
    if target_field:
        challenge = getattr(state, "challenge", None)
        next_question = getattr(challenge, "next_best_question", None)
        if _clean_text(getattr(next_question, "focus_key", None)) == target_field:
            expected = _clean_text(getattr(next_question, "expected_answer_type", None))
            if expected:
                return expected
    if target_field in {
        "temperature_c",
        "pressure_bar",
        "speed_rpm",
        "shaft_diameter_mm",
    }:
        return "number"
    if target_field == "motion_type":
        return "choice"
    return "text"


def _priority_from_strategy(strategy: Any | None) -> int:
    focus_key = _clean_text(getattr(strategy, "focus_key", None))
    if focus_key in {
        "medium",
        "temperature_c",
        "pressure_bar",
        "sealing_type",
        "motion_type",
    }:
        return 1
    if focus_key:
        return 2
    return 3


def _need_id(target_field: str | None, question: str) -> str:
    basis = target_field or question[:42]
    safe = "".join(ch if ch.isalnum() else "_" for ch in basis.casefold()).strip("_")
    return f"question_need.{safe or 'general'}"


def _clean_text(value: Any) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None
