from __future__ import annotations

import re

from app.agent.v91.contracts import FinalAnswerContext, GuardResult


def validate_communication_guard(
    answer_markdown: str,
    context: FinalAnswerContext,
) -> GuardResult:
    """Validate the V9.1 communication contract for visible answer text."""

    findings: list[str] = []
    text = str(answer_markdown or "").strip()
    question_count = _question_count(text)
    max_questions = int(context.response_policy.max_primary_questions or 0)
    if question_count > max_questions:
        findings.append("communication_guard:too_many_questions")

    question_plan = context.question_plan
    if getattr(question_plan, "ask_now", False) and question_count == 0:
        findings.append("communication_guard:planned_question_missing")

    if _contains_internal_artifact(text):
        findings.append("communication_guard:internal_artifact_leak")

    return GuardResult(
        passed=not findings,
        findings=findings,
        fallback_reason="v91_communication_guard" if findings else None,
    )


def _question_count(text: str) -> int:
    return text.count("?")


def _contains_internal_artifact(text: str) -> bool:
    lowered = text.casefold()
    return any(
        fragment in lowered
        for fragment in (
            "semanticboundarydecision",
            "finalanswercontext",
            "llmfreedomdecision",
            "runtimeaction",
            "model_dump",
            "```json",
        )
    )
