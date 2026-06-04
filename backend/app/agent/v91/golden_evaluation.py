from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from app.agent.v91.contracts import FinalAnswerContext
from app.agent.v91.final_answer_guard import validate_v91_final_answer


@dataclass(frozen=True)
class VisibleGoldenExpectation:
    """Expected V10-visible communication qualities for one golden answer."""

    answer_first: bool = True
    one_question: bool = True
    question_reason: bool = False
    no_overclaim: bool = True
    no_external_utility_answer: bool = True
    no_tab_spam: bool = True
    evidence_visible: bool | None = None
    rfq_boundary: bool = False
    recovery: bool = False


@dataclass(frozen=True)
class VisibleGoldenResult:
    passed: bool
    metrics: Mapping[str, bool]
    findings: tuple[str, ...] = field(default_factory=tuple)


def evaluate_visible_golden_answer(
    answer_markdown: str,
    context: FinalAnswerContext,
    expectation: VisibleGoldenExpectation,
) -> VisibleGoldenResult:
    """Evaluate a visible answer against the V10 golden-conversation metrics."""

    guard_result = validate_v91_final_answer(answer_markdown, context)
    findings = list(guard_result.findings)
    text = str(answer_markdown or "")
    metrics = {
        "answer_first": not _has_finding(findings, "communication_guard:answer_first_missing"),
        "one_question": not _has_finding(findings, "communication_guard:too_many_questions"),
        "question_reason": not _has_finding(findings, "communication_guard:missing_question_reason"),
        "no_overclaim": not any(finding.startswith("claim_guard:") for finding in findings),
        "no_external_utility_answer": not _has_finding(findings, "communication_guard:external_utility_answer"),
        "no_tab_spam": not _has_finding(findings, "communication_guard:tab_spam"),
        "evidence_visible": _evidence_visible(text, context),
        "rfq_boundary": _rfq_boundary_kept(text),
        "recovery": _recovery_visible(text),
    }
    required = _required_metrics(expectation)
    missing = [name for name in required if not metrics.get(name, False)]
    findings.extend(f"golden_metric:{name}" for name in missing)
    return VisibleGoldenResult(
        passed=guard_result.passed and not missing,
        metrics=metrics,
        findings=tuple(findings),
    )


def _required_metrics(expectation: VisibleGoldenExpectation) -> tuple[str, ...]:
    required: list[str] = []
    if expectation.answer_first:
        required.append("answer_first")
    if expectation.one_question:
        required.append("one_question")
    if expectation.question_reason:
        required.append("question_reason")
    if expectation.no_overclaim:
        required.append("no_overclaim")
    if expectation.no_external_utility_answer:
        required.append("no_external_utility_answer")
    if expectation.no_tab_spam:
        required.append("no_tab_spam")
    if expectation.evidence_visible is True:
        required.append("evidence_visible")
    if expectation.rfq_boundary:
        required.append("rfq_boundary")
    if expectation.recovery:
        required.append("recovery")
    return tuple(required)


def _has_finding(findings: list[str], code: str) -> bool:
    return any(finding == code for finding in findings)


def _evidence_visible(text: str, context: FinalAnswerContext) -> bool:
    refs = [str(ref).strip() for ref in context.evidence_ref_ids if str(ref or "").strip()]
    if not refs:
        return False
    lowered = text.casefold()
    return any(ref.casefold() in lowered for ref in refs)


def _rfq_boundary_kept(text: str) -> bool:
    lowered = text.casefold()
    dispatch_claims = (
        "ich habe gesendet",
        "ich habe versendet",
        "wurde gesendet",
        "wurde versendet",
        "automatisch gesendet",
        "an den hersteller gesendet",
        "dispatch complete",
    )
    if any(fragment in lowered for fragment in dispatch_claims):
        return False
    boundary_terms = ("zustimmung", "consent", "review", "pruef", "prüf", "nicht automatisch", "preview")
    return any(term in lowered for term in boundary_terms)


def _recovery_visible(text: str) -> bool:
    lowered = text.casefold()
    recovery_terms = ("korrig", "verstanden", "neu ein", "ich uebernehme", "ich übernehme")
    return any(term in lowered for term in recovery_terms)
