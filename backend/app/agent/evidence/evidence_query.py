from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


EvidenceQueryIntent = Literal[
    "material_suitability",
    "failure_mode",
    "norm_reference",
    "calculation_basis",
]


@dataclass(frozen=True)
class EvidenceQuery:
    """Structured retrieval contract for governed evidence lookups."""

    topic: str
    detected_sts_codes: list[str] = field(default_factory=list)
    query_intent: EvidenceQueryIntent = "material_suitability"
    language: str = "de"
    max_results: int = 5
