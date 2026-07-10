"""Typed internal answer contract and deterministic semantic validation."""

from __future__ import annotations

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
) -> None:
    errors: list[str] = []
    if answer.case_revision != case_revision:
        errors.append("case_revision_mismatch")
    for claim in answer.claims:
        unknown = set(claim.evidence_ids) - allowed_evidence_ids
        if unknown:
            errors.append("unknown_evidence_id")
        if claim.criticality == "decision_relevant" and not claim.evidence_ids:
            errors.append("decision_claim_without_evidence")
    if answer.recommendation.status in {"conditional", "not_recommended"}:
        decision_claims = [
            claim for claim in answer.claims if claim.criticality == "decision_relevant"
        ]
        if not decision_claims or not any(
            claim.evidence_ids for claim in decision_claims
        ):
            errors.append("recommendation_without_decision_evidence")
    if errors:
        raise TechnicalAnswerValidationError(",".join(sorted(set(errors))))
