from __future__ import annotations

import re

from app.agent.domain.risk_claims import unsupported_measured_claim_failures
from app.agent.v91.contracts import FinalAnswerContext, GuardResult


_FORBIDDEN_CLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "final_engineering_release",
        re.compile(
            r"\b(?:freigegeben|zugelassen|approved|technisch\s+validiert|final\s+freigegeben)\b",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        "final_material_suitability",
        re.compile(
            r"\b(?:ist|sind)\s+(?:sicher\s+|final\s+|gut\s+)?geeignet\b",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        "guarantee",
        re.compile(
            r"\b(?:garantiert|sicher\s+passend|garantiert\s+dicht|keine\s+weitere[n]?\s+pruefung|keine\s+weitere[n]?\s+prüfung)\b",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        "manufacturer_approval_claim",
        re.compile(
            r"\b(?:hersteller\s+(?:wird|muss)\s+.*(?:akzeptieren|freigeben)|laut\s+hersteller)\b",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        "compliance_approval",
        re.compile(
            r"\b(?:atex|fda|reach|lebensmittel|pharma).{0,48}\b(?:konform|zertifiziert|zugelassen|freigegeben)\b",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
)


def validate_claim_guard(
    answer_markdown: str,
    context: FinalAnswerContext,
) -> GuardResult:
    """Guard against V9.1-forbidden finality claims in visible answers."""

    findings: list[str] = []
    text = str(answer_markdown or "")
    for finding, pattern in _FORBIDDEN_CLAIM_PATTERNS:
        if pattern.search(text):
            findings.append(f"claim_guard:{finding}")

    for failure in unsupported_measured_claim_failures(context, text):
        findings.append(f"claim_guard:{failure['kind']}")

    forbidden = set(context.freedom_decision.forbidden_actions)
    if "final_material_recommendation" in forbidden and _material_finality(text):
        findings.append("claim_guard:material_finality_language")

    return GuardResult(
        passed=not findings,
        findings=findings,
        fallback_reason="v91_claim_guard" if findings else None,
    )


def _material_finality(text: str) -> bool:
    lowered = text.casefold()
    if not any(
        token in lowered
        for token in ("fkm", "ffkm", "epdm", "nbr", "ptfe", "pom", "peek", "werkstoff", "material")
    ):
        return False
    return any(
        token in lowered
        for token in ("nehmen sie", "nimm ", "verwenden sie", "ist die beste", "beste loesung", "beste lösung")
    )
