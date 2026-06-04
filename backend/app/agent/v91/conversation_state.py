from __future__ import annotations

from typing import Any

from app.agent.v91.contracts import (
    AnswerDepth,
    ConversationTaskState,
    DialogueDebt,
)


def build_conversation_task_state(
    *,
    state: Any,
    governed_context: Any,
    response_class: str | None,
) -> ConversationTaskState:
    """Build the V9.1 non-authoritative conversation task slice."""

    question = _clean(getattr(governed_context, "next_best_question", None))
    final_context = getattr(governed_context, "v91_final_answer_context", None)
    response_policy = getattr(final_context, "response_policy", None)
    answer_depth = getattr(response_policy, "answer_depth", AnswerDepth.NORMAL)
    return ConversationTaskState(
        active_intent=_intent_from_response_class(response_class),
        last_asked_question=question,
        open_side_topics=_strings(getattr(governed_context, "open_points", []), limit=6),
        answer_depth=answer_depth,
        pause_resume_status="waiting_for_user" if question else "active",
        user_preference_notes=_strings(
            getattr(getattr(state, "exploration_progress", None), "tentative_domain_signals", []),
            limit=4,
        ),
    )


def build_dialogue_debt(
    *,
    state: Any,
    governed_context: Any,
    conversation_task: ConversationTaskState,
) -> DialogueDebt:
    """Track unresolved conversational obligations without creating truth."""

    question = _clean(conversation_task.last_asked_question)
    previous = getattr(state, "v91_dialogue_debt", None)
    previous_question_id = _clean(getattr(previous, "last_asked_question_id", None))
    question_id = _question_id(question)
    repeated_count = (
        int(getattr(previous, "repeated_question_count", 0) or 0) + 1
        if question_id and question_id == previous_question_id
        else (1 if question_id else 0)
    )
    conflicts = _strings(
        getattr(getattr(state, "asserted", None), "conflict_flags", []),
        limit=6,
    )
    tab_updates: list[str] = []
    if getattr(governed_context, "accepted_updates", None):
        tab_updates.append("parameter_update_available")
    if conflicts:
        tab_updates.append("conflict_requires_attention")
    return DialogueDebt(
        pending_questions=[question] if question else [],
        pending_explanations=[],
        pending_conflicts=conflicts,
        pending_tab_updates=tab_updates,
        last_asked_question_id=question_id,
        repeated_question_count=repeated_count,
    )


def _intent_from_response_class(response_class: str | None) -> str | None:
    value = _clean(response_class)
    if not value:
        return None
    if value in {"structured_clarification", "governed_state_update"}:
        return "case_intake"
    if value in {"technical_preselection", "candidate_shortlist"}:
        return "concrete_suitability_screening"
    if value in {"inquiry_ready", "rfq_preview", "rfq_readiness"}:
        return "rfq_or_export_boundary"
    return value


def _question_id(question: str | None) -> str | None:
    text = _clean(question)
    if not text:
        return None
    return "q:" + text.casefold()[:96]


def _strings(value: Any, *, limit: int) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, (list, tuple, set)):
        candidates = [str(item) for item in value]
    else:
        candidates = [str(value)]
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = _clean(candidate)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _clean(value: Any) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None
