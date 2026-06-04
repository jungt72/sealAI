from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ExplorationQueryIntent = Literal[
    "material_suitability",
    "material_comparison",
    "material_detail",
    "norm_explanation",
    "general_orientation",
]


@dataclass(frozen=True)
class ExplorationQuery:
    """Structured retrieval contract for exploration-oriented lookups."""

    topic: str
    detected_parameters: list[str] = field(default_factory=list)
    query_intent: ExplorationQueryIntent = "general_orientation"
    comparison_candidates: list[str] = field(default_factory=list)
    language: str = "de"
    max_results: int = 3
