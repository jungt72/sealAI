"""Typed contract for source-bound engineering knowledge answers.

Knowledge answers need a richer contract than case narration: every statement is bound to one
subject and one engineering facet, while numerical content must already exist in reviewed evidence
or in the deterministic material-parameter registry.  The renderer, not the model, owns tables.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EngineeringClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=120)
    facet: str = Field(min_length=1, max_length=80)
    statement: str = Field(min_length=1, max_length=1600)
    evidence_ids: list[str] = Field(min_length=1, max_length=6)
    criticality: Literal["context", "design_relevant", "limit"]


class EngineeringKnowledgeAnswer(BaseModel):
    """Provider output for pure knowledge and comparison routes."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2]
    profile: str = Field(min_length=1, max_length=120)
    case_revision: int = Field(ge=0)
    conclusion: str = Field(min_length=1, max_length=1800)
    claims: list[EngineeringClaim] = Field(max_length=20)
    assumptions: list[str] = Field(max_length=6)
    missing_information: list[str] = Field(max_length=10)


class EngineeringAnswerValidationError(ValueError):
    pass


_NUMBER_RE = re.compile(r"(?<![\w])[-+]?\d+(?:[.,]\d+)?")


def numeric_tokens(text: str) -> frozenset[str]:
    """Normalized numeric tokens used by the no-fake-precision check."""
    out: set[str] = set()
    for match in _NUMBER_RE.finditer(text or ""):
        value = match.group(0).replace(",", ".")
        try:
            number = float(value)
            out.add(str(int(number)) if number.is_integer() else str(number))
        except ValueError:
            continue
    return frozenset(out)


def validate_engineering_answer(
    answer: EngineeringKnowledgeAnswer,
    *,
    profile: str,
    case_revision: int,
    allowed_subjects: tuple[str, ...],
    evidence_facets: dict[str, frozenset[str]],
    evidence_subjects: dict[str, frozenset[str]],
    evidence_texts: dict[str, str],
    required_cells: dict[str, tuple[frozenset[str], ...]] | None = None,
    parameter_text: str = "",
) -> None:
    """Validate identity, subject/facet provenance and every generated number.

    JSON Schema guarantees shape.  These checks enforce domain semantics that a schema cannot:
    evidence for NBR must not support a PTFE cell, a limits claim must cite limits evidence, and a
    model-generated number must be present verbatim in reviewed evidence or kernel parameters.
    """
    errors: list[str] = []
    if answer.case_revision != case_revision:
        errors.append("case_revision_mismatch")
    if answer.profile != profile:
        errors.append("profile_mismatch")

    allowed_subject_map = {subject.casefold(): subject for subject in allowed_subjects}
    allowed_numbers = set(numeric_tokens(parameter_text))
    allowed_numbers.update(
        token for text in evidence_texts.values() for token in numeric_tokens(text)
    )
    generated_numbers = set(numeric_tokens(answer.conclusion))

    for claim in answer.claims:
        subject_key = claim.subject.casefold()
        if allowed_subject_map and subject_key not in allowed_subject_map:
            errors.append("unknown_subject")
        unknown_ids = set(claim.evidence_ids) - set(evidence_texts)
        if unknown_ids:
            errors.append("unknown_evidence_id")
            continue
        if not any(
            claim.facet in evidence_facets.get(evidence_id, frozenset())
            for evidence_id in claim.evidence_ids
        ):
            errors.append("facet_not_supported")
        if allowed_subject_map and not all(
            subject_key
            in {
                subject.casefold()
                for subject in evidence_subjects.get(evidence_id, frozenset())
            }
            for evidence_id in claim.evidence_ids
        ):
            errors.append("subject_evidence_mismatch")
        generated_numbers.update(numeric_tokens(claim.statement))

    for subject, cells in (required_cells or {}).items():
        for facets in cells:
            if not any(
                claim.subject.casefold() == subject.casefold() and claim.facet in facets
                for claim in answer.claims
            ):
                errors.append("required_engineering_cell_missing")

    if generated_numbers - allowed_numbers:
        errors.append("unsupported_numeric_content")
    if errors:
        raise EngineeringAnswerValidationError(",".join(sorted(set(errors))))
