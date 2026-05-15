from __future__ import annotations

from app.agent.v91.claim_guard import validate_claim_guard
from app.agent.v91.communication_guard import validate_communication_guard
from app.agent.v91.contracts import FinalAnswerContext, GuardResult
from app.agent.v91.evidence_gate import validate_evidence_gate


def validate_v91_final_answer(
    answer_markdown: str,
    context: FinalAnswerContext | None,
) -> GuardResult:
    if context is None:
        return GuardResult(passed=True)

    findings: list[str] = []
    fallback_reason: str | None = None
    for result in (
        validate_claim_guard(answer_markdown, context),
        validate_evidence_gate(answer_markdown, context),
        validate_communication_guard(answer_markdown, context),
    ):
        if result.passed:
            continue
        findings.extend(result.findings)
        fallback_reason = fallback_reason or result.fallback_reason
    return GuardResult(
        passed=not findings,
        findings=findings,
        fallback_reason=fallback_reason,
    )
