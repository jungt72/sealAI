"""Typed internal answer contract and deterministic semantic validation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TechnicalClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1200)
    evidence_ids: list[str] = Field(max_length=12)
    criticality: Literal["context", "supporting", "decision_relevant"]


class TechnicalRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(max_length=1200)
    status: Literal["none", "provisional", "conditional", "not_recommended"]
    conditions: list[str] = Field(max_length=6)


class TechnicalAnswer(BaseModel):
    """Provider output. This object is never rendered directly to the user."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    intent: str = Field(min_length=1, max_length=120)
    case_revision: int = Field(ge=0)
    conclusion: str = Field(min_length=1, max_length=1800)
    assumptions: list[str] = Field(max_length=6)
    missing_information: list[str] = Field(max_length=6)
    claims: list[TechnicalClaim] = Field(max_length=8)
    recommendation: TechnicalRecommendation
    needs_human_review: bool


class TechnicalAnswerValidationError(ValueError):
    pass


_DOMAIN_IDENTIFIERS = frozenset(
    {
        "ACM",
        "AEM",
        "API",
        "ATEX",
        "AU",
        "CIP",
        "CR",
        "DIN",
        "EG",
        "EN",
        "EPDM",
        "EU",
        "FDA",
        "FFKM",
        "FKM",
        "FVMQ",
        "GLRD",
        "HNBR",
        "IIR",
        "ISO",
        "KTW-BWGL",
        "NBR",
        "NORSOK",
        "NSF",
        "PA",
        "PEEK",
        "POM",
        "PTFE",
        "RWDR",
        "SIP",
        "UN",
        "USP",
        "VMQ",
        "W270",
        "WRAS",
    }
)
_MATERIAL_IDENTIFIERS = frozenset(
    {
        "ACM",
        "AEM",
        "AU",
        "CR",
        "EPDM",
        "EU",
        "FFKM",
        "FKM",
        "FVMQ",
        "HNBR",
        "IIR",
        "NBR",
        "PA",
        "PEEK",
        "POM",
        "PTFE",
        "VMQ",
    }
)
_IDENTIFIER_RE = re.compile(
    r"(?<![A-Za-z0-9-])(?:"
    + "|".join(
        sorted((re.escape(item) for item in _DOMAIN_IDENTIFIERS), key=len, reverse=True)
    )
    + r")(?![A-Za-z0-9-])"
)
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:[.,]\d+)?")


def _identifiers(text: str) -> frozenset[str]:
    return frozenset(
        match.group(0).upper() for match in _IDENTIFIER_RE.finditer(text or "")
    )


def _numbers(text: str) -> tuple[float, ...]:
    values: list[float] = []
    for match in _NUMBER_RE.finditer(text or ""):
        try:
            values.append(float(match.group(0).replace(",", ".")))
        except ValueError:
            continue
    return tuple(values)


def _unsupported_numbers(text: str, evidence_text: str) -> bool:
    allowed = _numbers(evidence_text)
    for value in _numbers(text):
        if not any(
            abs(value - candidate) <= max(0.005, abs(candidate) * 0.02)
            for candidate in allowed
        ):
            return True
    return False


def calibrate_technical_answer(answer: TechnicalAnswer) -> TechnicalAnswer:
    """Deterministically weaken unsupported decisions and require human review.

    This never adds evidence or strengthens a model claim. An unsupported decision claim forces
    human review regardless of the model's flag, remains visible only as provisional supporting
    context, and weakens an unsupported conditional/negative recommendation to orientation.
    """
    unsupported_decision = any(
        claim.criticality == "decision_relevant" and not claim.evidence_ids
        for claim in answer.claims
    )
    if not unsupported_decision:
        return answer
    claims = [
        claim.model_copy(update={"criticality": "supporting"})
        if claim.criticality == "decision_relevant" and not claim.evidence_ids
        else claim
        for claim in answer.claims
    ]
    has_evidenced_decision = any(
        claim.criticality == "decision_relevant" and claim.evidence_ids
        for claim in claims
    )
    recommendation = answer.recommendation
    if (
        recommendation.status in {"conditional", "not_recommended"}
        and not has_evidenced_decision
    ):
        recommendation = recommendation.model_copy(update={"status": "provisional"})
    prefix = "Vorläufige Einordnung ohne belastbaren Beleg: "
    conclusion = answer.conclusion
    if not conclusion.startswith(prefix):
        conclusion = prefix + conclusion
    return answer.model_copy(
        update={
            "claims": claims,
            "recommendation": recommendation,
            "conclusion": conclusion,
            "needs_human_review": True,
        }
    )


def validate_technical_answer(
    answer: TechnicalAnswer,
    *,
    case_revision: int,
    allowed_evidence_ids: frozenset[str],
    require_evidence_for_all_claims: bool = False,
    evidence_text_by_id: Mapping[str, str] | None = None,
    calculation_context_text: str = "",
    user_context_text: str = "",
    forbid_material_recommendation: bool = False,
) -> None:
    errors: list[str] = []
    if answer.case_revision != case_revision:
        errors.append("case_revision_mismatch")
    for claim in answer.claims:
        unknown = set(claim.evidence_ids) - allowed_evidence_ids
        if unknown:
            errors.append("unknown_evidence_id")
        if require_evidence_for_all_claims and not claim.evidence_ids:
            errors.append("knowledge_claim_without_evidence")
        if claim.criticality == "decision_relevant" and not claim.evidence_ids:
            errors.append("decision_claim_without_evidence")
        if evidence_text_by_id is not None and claim.evidence_ids:
            cited_text = " ".join(
                evidence_text_by_id.get(evidence_id, "")
                for evidence_id in claim.evidence_ids
            )
            allowed_text = f"{cited_text} {calculation_context_text}"
            if _identifiers(claim.text) - _identifiers(allowed_text):
                errors.append("named_assertion_absent_from_cited_evidence")
            if _unsupported_numbers(claim.text, allowed_text):
                errors.append("number_absent_from_cited_evidence")
    if answer.recommendation.status in {"conditional", "not_recommended"}:
        decision_claims = [
            claim for claim in answer.claims if claim.criticality == "decision_relevant"
        ]
        if not decision_claims or not any(
            claim.evidence_ids for claim in decision_claims
        ):
            errors.append("recommendation_without_decision_evidence")
    if evidence_text_by_id is not None:
        evidenced_claim_text = " ".join(
            claim.text for claim in answer.claims if claim.evidence_ids
        )
        recommendation_text = " ".join(
            [answer.recommendation.summary, *answer.recommendation.conditions]
        )
        # The separate rule above already requires a cited decision claim for a conditional or
        # negative recommendation.  Names and values may additionally restate the user's own case
        # inputs; those are context, not evidence, and never authorise a new claim.
        recommendation_basis = (
            f"{evidenced_claim_text} {calculation_context_text} {user_context_text}"
        )
        if _identifiers(recommendation_text) - _identifiers(recommendation_basis):
            errors.append("named_recommendation_without_decision_evidence")
        if _unsupported_numbers(recommendation_text, recommendation_basis):
            errors.append("recommendation_number_without_decision_evidence")
        if forbid_material_recommendation and (
            _identifiers(recommendation_text) & _MATERIAL_IDENTIFIERS
        ):
            errors.append("material_recommendation_with_unresolved_medium")
        conclusion_basis = (
            f"{evidenced_claim_text} {calculation_context_text} {user_context_text}"
        )
        if _identifiers(answer.conclusion) - _identifiers(conclusion_basis):
            errors.append("named_conclusion_without_evidence")
        if _unsupported_numbers(answer.conclusion, conclusion_basis):
            errors.append("conclusion_number_without_evidence")
    if errors:
        raise TechnicalAnswerValidationError(",".join(sorted(set(errors))))
