"""Central V9.2 final output guard."""

from __future__ import annotations

import re
from typing import Any

from app.agent.domain.risk_claims import unsupported_measured_claim_failures
from app.agent.runtime.output_guard import comparative_ranking_patterns
from app.agent.v92.contracts import (
    AdversarialReviewVerdict,
    FinalAnswerContext,
    FinalGuardResult,
    NonTechnicalAnswerContext,
)


_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "final_release",
        re.compile(
            r"\b(?:final\s+freigegeben|technisch\s+validiert|freigegeben|zugelassen|garantiert|"
            r"validiert|validated|approved)\b",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        "suitability_without_scope",
        re.compile(
            r"\b(?:ist|sind)\s+(?:sicher\s+|final\s+|gut\s+|hervorragend\s+)?geeignet\b",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        "absolute_material_medium_compatibility",
        re.compile(
            r"\b(?:material|werkstoff|compound|fkm|ffkm|epdm|nbr|hnbr|ptfe|vmq|silikon)\b"
            r".{0,100}\b(?:ist|sind|is|are)\s+"
            r"(?:chemisch\s+|fully\s+|absolutely\s+|sicher\s+)?"
            r"(?:best[aä]ndig|bestaendig|resistant|compatible|suitable|safe\s+for|chemisch\s+sicher)\b|"
            r"\b(?:material|werkstoff|compound|fkm|ffkm|epdm|nbr|hnbr|ptfe|vmq|silikon)\b"
            r".{0,100}\b(?:geeignet\s+f(?:ü|u|ue)r|trinkwassergeeignet)\b|"
            r"\b(?:material|werkstoff|compound|fkm|ffkm|epdm|nbr|hnbr|ptfe|vmq|silikon)\b"
            r".{0,100}\b(?:freigegeben|zugelassen|approved|validated)\b",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        "compliance_or_certification",
        re.compile(
            r"\b(?:(?:fda|atex|ehedg|trinkwasser|pharma|lebensmittel|reach|norm|standard).{0,80}"
            r"\b(?:konform|zertifiziert|zugelassen|freigegeben|bestaetigt|bestätigt)"
            r"|norm(?:en)?[-\s]?konform)\b",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        "definitive_root_cause",
        re.compile(
            r"\b(?:die\s+ursache\s+ist|eindeutige\s+ursache|finale\s+schadensursache)\b",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        "internal_prompt_leak",
        re.compile(
            r"\b(?:system\s+prompt|developer\s+message|hidden\s+instruction|policy\s+above|langgraph\s+state)\b",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        "placeholder_or_template_artifact",
        re.compile(
            r"(?:\b(?:bewertung|rating|score)\s*:\s*x\b|\b(?:tbd|todo|platzhalter)\b|"
            r"\{\{|\}\}|\[\[|\]\]|(?:nächste|naechste)\s+frage\s*:\s*$)",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
)


# Knowledge-turn backstop subset: only suitability / comparative-ranking /
# compliance. Excludes ``absolute_material_medium_compatibility`` — its
# "<material> … geeignet für" branch false-positives on cautious limit phrasing
# (e.g. "FKM … nicht automatisch geeignet für Heißwasser") present in the
# deterministic comparison render. Comparative-ranking patterns are imported from
# output_guard so the fast-path and final guards share one source of truth (T2.5).
_KNOWLEDGE_ROUTES: frozenset[str] = frozenset(
    {"knowledge_general", "knowledge_case_side_question"}
)
_KNOWLEDGE_SUBSET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    *(
        (name, pattern)
        for name, pattern in _FORBIDDEN_PATTERNS
        if name in {"suitability_without_scope", "compliance_or_certification"}
    ),
    *(("comparative_ranking", pattern) for pattern in comparative_ranking_patterns()),
)


def _empty_guard(allowed_claim_level: str) -> FinalGuardResult:
    return FinalGuardResult(
        decision="pass",
        severity="none",
        allowed_claim_level=allowed_claim_level,
        final_stream_allowed=True,
    )


def _scan_knowledge_subset(text: str, allowed_claim_level: str) -> FinalGuardResult:
    """Knowledge-turn final backstop over the suitability / comparative-ranking /
    compliance subset. Reads only ``text`` — never FinalAnswerContext-only fields —
    so it is safe on a NonTechnicalAnswerContext.
    """
    detected: list[str] = []
    for name, pattern in _KNOWLEDGE_SUBSET_PATTERNS:
        if pattern.search(text) and name not in detected:
            detected.append(name)
    if not detected:
        return _empty_guard(allowed_claim_level)
    return FinalGuardResult(
        decision="block",
        severity="blocking",
        blocked_reasons=["forbidden_user_visible_claims"],
        required_revisions=[f"remove_or_downgrade:{name}" for name in detected],
        allowed_claim_level=allowed_claim_level,
        detected_forbidden_claims=detected,
        final_stream_allowed=False,
    )


def validate_final_output(
    answer_markdown: str,
    *,
    context: FinalAnswerContext | NonTechnicalAnswerContext,
    adversarial_review: AdversarialReviewVerdict | None = None,
) -> FinalGuardResult:
    text = str(answer_markdown or "")
    allowed_claim_level = str(
        getattr(context, "allowed_claim_level", "L2_screening") or "L2_screening"
    )
    if not text.strip():
        return FinalGuardResult(
            decision="block",
            severity="blocking",
            blocked_reasons=["empty_final_answer"],
            allowed_claim_level=allowed_claim_level,
            final_stream_allowed=False,
        )

    if isinstance(context, NonTechnicalAnswerContext):
        if str(getattr(context, "route", "") or "") in _KNOWLEDGE_ROUTES:
            return _scan_knowledge_subset(text, allowed_claim_level)
        return _empty_guard(allowed_claim_level)

    blocked_reasons: list[str] = []
    required_revisions: list[str] = []
    detected_forbidden: list[str] = []
    evidence_failures: list[dict[str, Any]] = []
    calculation_failures: list[dict[str, Any]] = []
    standards_failures: list[dict[str, Any]] = []
    stale_failures: list[dict[str, Any]] = []
    limitations: list[str] = []

    for name, pattern in _FORBIDDEN_PATTERNS:
        if not pattern.search(text):
            continue
        if (
            name == "suitability_without_scope"
            and allowed_claim_level == "L6_expert_approved"
        ):
            continue
        detected_forbidden.append(name)
        required_revisions.append(f"remove_or_downgrade:{name}")

    for failure in unsupported_measured_claim_failures(context, text):
        detected_forbidden.append(str(failure["kind"]))
        evidence_failures.append(
            {
                "kind": failure["kind"],
                "reason": failure["reason"],
            }
        )
        required_revisions.append(f"replace_with_safe_wording:{failure['kind']}")
        limitations.append(str(failure["safe_wording"]))

    has_compound_release_language = bool(
        re.search(
            r"\b(?:compound|mischung|produkt|artikel)\b.{0,80}\b(?:geeignet|freigegeben|zugelassen|passt)\b",
            text,
            re.IGNORECASE | re.UNICODE,
        )
    )
    if has_compound_release_language and not (
        context.compound_candidates or context.product_candidates
    ):
        detected_forbidden.append("compound_or_product_claim_without_evidence_layer")
        evidence_failures.append(
            {
                "kind": "compound_product_layer",
                "reason": "missing compound/product evidence",
            }
        )

    if context.stale_items:
        stale_failures.extend(context.stale_items)
        limitations.append(
            "Mindestens ein abhaengiges Berechnungs- oder Screening-Ergebnis ist stale."
        )
        if re.search(
            r"\b(?:aktuell|berechnet|ergibt|empfehlung|geeignet)\b", text, re.IGNORECASE
        ):
            required_revisions.append("do_not_use_stale_calculation_as_current_basis")

    for result in context.calculation_results:
        status = str(result.get("status") or result.get("validity_status") or "")
        validity_status = str(result.get("validity_status") or "")
        guardrail_violations = list(result.get("guardrail_violations") or [])
        if (
            status in {"stale", "input_missing", "insufficient_data", "blocked"}
            or validity_status
            in {
                "requires_expert_review",
                "stale",
                "input_missing",
            }
            or guardrail_violations
        ):
            calculation_failures.append(
                {
                    "calculation_id": result.get("calculation_id")
                    or result.get("calculator"),
                    "status": status,
                    "validity_status": validity_status,
                    "guardrail_violations": guardrail_violations,
                }
            )

    if context.standards_summary.get("blocking_gaps") and re.search(
        r"\b(?:norm(?:en)?[-\s]?konform|konform|zertifiziert|zugelassen|freigegeben)\b",
        text,
        re.IGNORECASE | re.UNICODE,
    ):
        standards_failures.append(
            {
                "kind": "standards_boundary",
                "reason": "standards gaps present; conformity claims are not allowed",
            }
        )

    if adversarial_review is not None and adversarial_review.decision in {
        "block",
        "human_review",
    }:
        blocked_reasons.append(f"adversarial_review:{adversarial_review.decision}")
    if adversarial_review is not None and adversarial_review.decision == "revise":
        required_revisions.extend(adversarial_review.required_revision_instructions)

    if detected_forbidden:
        blocked_reasons.append("forbidden_user_visible_claims")
    if evidence_failures:
        blocked_reasons.append("evidence_gate_failed")
    if standards_failures:
        blocked_reasons.append("standards_guard_failed")
    if context.review_required:
        limitations.append(
            "Expert Review ist erforderlich, bevor Freigabe- oder Eignungsclaims zulaessig sind."
        )

    decision = "pass"
    severity = "none"
    final_stream_allowed = True
    human_review_required = bool(context.review_required)
    if blocked_reasons:
        decision = "block"
        severity = "blocking"
        final_stream_allowed = False
    elif required_revisions or calculation_failures or stale_failures:
        decision = "revise"
        severity = "medium"

    return FinalGuardResult(
        decision=decision,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        blocked_reasons=blocked_reasons,
        required_revisions=required_revisions,
        allowed_claim_level=allowed_claim_level,
        detected_forbidden_claims=detected_forbidden,
        evidence_failures=evidence_failures,
        calculation_failures=calculation_failures,
        standards_failures=standards_failures,
        stale_failures=stale_failures,
        human_review_required=human_review_required,
        user_visible_limitations=limitations,
        final_stream_allowed=final_stream_allowed,
    )


def guarded_fallback_answer(
    *,
    context: FinalAnswerContext,
    guard_result: FinalGuardResult,
) -> str:
    lines = [
        "Ich kann daraus noch keine technische Empfehlung oder Freigabe ableiten.",
        "Auf Basis des aktuellen Falls ist nur eine begrenzte Screening-Einordnung zulaessig.",
    ]
    for limitation in guard_result.user_visible_limitations[:4]:
        lines.append(f"- {limitation}")
    for warning in context.required_warnings[:4]:
        if warning not in lines:
            lines.append(f"- {warning}")
    if context.human_review_reasons:
        lines.append("Review-Grund: " + "; ".join(context.human_review_reasons[:3]))
    if context.completeness and context.completeness.get("next_best_blocker"):
        lines.append(
            "Naechster Blocker: " + str(context.completeness["next_best_blocker"])
        )
    elif context.required_warnings:
        lines.append("Naechster Schritt: fehlende Pflichtdaten und Evidenz klaeren.")
    return "\n".join(lines).strip()
