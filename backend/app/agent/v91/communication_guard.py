from __future__ import annotations

import re

from app.agent.v91.contracts import FinalAnswerContext, GuardResult

_QUESTION_REASON_RE = re.compile(
    r"\b(weil|wichtig|damit|relevant|beeinflusst|entscheidend|brauche|"
    r"benoetige|benotige|bestimmt|grenzt|klaert|klart)\b",
    re.IGNORECASE | re.UNICODE,
)
_TAB_MARKER_RE = re.compile(
    r"\b(tab|tabs|cockpit|dashboard|workspace|kachel|aktualisiert|"
    r"aktualisierung|update)\b",
    re.IGNORECASE | re.UNICODE,
)
_QUESTION_START_RE = re.compile(
    r"^(welche|welcher|welches|wie|was|warum|wann|wo|woran|"
    r"kannst|koennen|konnen|ist|sind)\b",
    re.IGNORECASE | re.UNICODE,
)
_EXTERNAL_UTILITY_DIRECT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:morgen|heute|aktuell)\b.{0,80}\b(?:sonnig|regen|regnet|"
        r"schnee|bewoelkt|bewolkt|grad|temperatur)\b",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(
        r"\bdax\b.{0,80}\b(?:steht|liegt|faellt|fallt|steigt|punkte)\b",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(
        r"\b(?:news|nachrichten|eilmeldung)\b.{0,80}\b(?:ist|sind|meldet|berichtet)\b",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(
        r"\b(?:flug|hotel|reise)\b.{0,80}\b(?:kostet|buchen|verfuegbar|verfugbar)\b",
        re.IGNORECASE | re.UNICODE,
    ),
)


def validate_communication_guard(
    answer_markdown: str,
    context: FinalAnswerContext,
) -> GuardResult:
    """Validate the V9.1 communication contract for visible answer text."""

    findings: list[str] = []
    text = str(answer_markdown or "").strip()
    communication_plan = context.communication_plan
    question_count = _question_count(text)
    max_questions = _max_questions(context)
    if question_count > max_questions:
        findings.append("communication_guard:too_many_questions")

    question_plan = context.question_plan
    ask_user_question = _ask_user_question(context)
    if getattr(question_plan, "ask_now", False) and question_count == 0:
        findings.append("communication_guard:planned_question_missing")
    if question_count > 0 and not ask_user_question:
        findings.append("communication_guard:unplanned_question")
    if (
        question_count > 0
        and _question_justification_required(context)
        and not _contains_question_reason(text, context)
    ):
        findings.append("communication_guard:missing_question_reason")
    if _answer_first_required(context) and _starts_with_question(text):
        findings.append("communication_guard:answer_first_missing")
    if _expects_external_utility_redirect(communication_plan) and _contains_external_utility_answer(text):
        findings.append("communication_guard:external_utility_answer")
    if _violates_tab_visibility(text, communication_plan):
        findings.append("communication_guard:tab_spam")

    if _contains_internal_artifact(text):
        findings.append("communication_guard:internal_artifact_leak")

    return GuardResult(
        passed=not findings,
        findings=findings,
        fallback_reason="v91_communication_guard" if findings else None,
    )


def _question_count(text: str) -> int:
    return text.count("?")


def _max_questions(context: FinalAnswerContext) -> int:
    plan = context.communication_plan
    if plan is not None:
        return max(0, int(getattr(plan, "max_new_questions", 0) or 0))
    return max(0, int(context.response_policy.max_primary_questions or 0))


def _ask_user_question(context: FinalAnswerContext) -> bool:
    plan = context.communication_plan
    if plan is not None:
        return bool(getattr(plan, "ask_user_question", False))
    return bool(getattr(context.question_plan, "ask_now", False))


def _question_justification_required(context: FinalAnswerContext) -> bool:
    plan = context.communication_plan
    if plan is not None:
        return bool(getattr(plan, "question_justification_required", False))
    return bool(getattr(context.question_plan, "ask_now", False))


def _answer_first_required(context: FinalAnswerContext) -> bool:
    plan = context.communication_plan
    if plan is not None:
        return bool(
            getattr(plan, "answer_first", False)
            or getattr(plan, "user_question_must_be_answered", False)
        )
    return bool(getattr(context.response_policy, "answer_first", False))


def _contains_question_reason(text: str, context: FinalAnswerContext) -> bool:
    if _QUESTION_REASON_RE.search(text):
        return True
    reason = str(getattr(context.question_plan, "reason", "") or "").strip()
    if not reason and context.communication_plan is not None:
        reason = str(getattr(context.communication_plan, "primary_question_reason", "") or "").strip()
    if not reason:
        return False
    lowered_text = text.casefold()
    reason_words = [
        word
        for word in re.findall(r"\w+", reason.casefold(), flags=re.UNICODE)
        if len(word) >= 6
    ]
    if not reason_words:
        return False
    matches = sum(1 for word in reason_words[:8] if word in lowered_text)
    return matches >= min(2, len(reason_words))


def _starts_with_question(text: str) -> bool:
    stripped = str(text or "").lstrip()
    if not stripped:
        return False
    first_question = stripped.find("?")
    if first_question >= 0:
        question_prefix = stripped[:first_question].strip()
        if ":" in question_prefix:
            lead_in = question_prefix.split(":", 1)[0].strip()
            if lead_in and not _QUESTION_START_RE.match(lead_in):
                return False
    first_sentence_end = len(stripped)
    first_punctuation = re.search(r"[.?!\n]", stripped)
    if first_punctuation is not None:
        first_sentence_end = first_punctuation.end()
    first_sentence = stripped[:first_sentence_end].strip()
    if first_sentence.endswith("?"):
        return True
    return bool(_QUESTION_START_RE.match(first_sentence))


def _expects_external_utility_redirect(plan: object | None) -> bool:
    if plan is None:
        return False
    moves = {_value(move) for move in list(getattr(plan, "response_moves", []) or [])}
    return str(getattr(plan, "goal", "")) == "redirect" or "redirect" in moves


def _contains_external_utility_answer(text: str) -> bool:
    return any(pattern.search(text) for pattern in _EXTERNAL_UTILITY_DIRECT_PATTERNS)


def _value(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def _violates_tab_visibility(text: str, plan: object | None) -> bool:
    if plan is None:
        return False
    count = len(_TAB_MARKER_RE.findall(text))
    if count == 0:
        return False
    visibility = str(getattr(plan, "tab_update_visibility", "silent") or "silent")
    if visibility == "silent":
        return True
    if visibility == "concise" and count > 2:
        return True
    return False


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
