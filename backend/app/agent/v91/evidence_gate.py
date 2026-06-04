from __future__ import annotations

import re

from app.agent.v91.contracts import FinalAnswerContext, GuardResult


_EXPLICIT_EVIDENCE_REF_RE = re.compile(
    r"\b(?:evidence|quelle|source|upload|doc|document)[_:/-][A-Za-z0-9_.:-]+\b",
    re.IGNORECASE | re.UNICODE,
)
_DOCUMENT_CLAIM_RE = re.compile(
    r"\b(?:laut|gemaess|gemäß|nach)\s+(?:datenblatt|dokument|quelle|paperless|pdf)\b",
    re.IGNORECASE | re.UNICODE,
)


def validate_evidence_gate(
    answer_markdown: str,
    context: FinalAnswerContext,
) -> GuardResult:
    """Ensure visible evidence/document claims are backed by known refs."""

    text = str(answer_markdown or "")
    known_refs = {str(ref) for ref in context.evidence_ref_ids if str(ref or "").strip()}
    findings: list[str] = []
    for match in _EXPLICIT_EVIDENCE_REF_RE.findall(text):
        if match not in known_refs:
            findings.append(f"evidence_gate:unknown_ref:{match}")
    if _DOCUMENT_CLAIM_RE.search(text) and not known_refs:
        findings.append("evidence_gate:document_claim_without_evidence_ref")
    return GuardResult(
        passed=not findings,
        findings=findings,
        fallback_reason="v91_evidence_gate" if findings else None,
    )
