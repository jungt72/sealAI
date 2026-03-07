from __future__ import annotations

from enum import Enum
from typing import Any, List, Literal, Optional, Set


class IdentityClass(str, Enum):
    """Blueprint v1.2 — Identity Classification.
    Determines whether a parameter is confirmed for deterministic lookup or
    requires further validation.
    """
    CONFIRMED = "identity_confirmed"
    PROBABLE = "identity_probable"
    FAMILY_ONLY = "identity_family_only"
    UNRESOLVED = "identity_unresolved"

    @classmethod
    def normalize(cls, value: Any) -> "IdentityClass":
        v = str(value or "").strip().lower()
        if v in {"confirmed", "identity_confirmed"}:
            return cls.CONFIRMED
        if v in {"probable", "identity_probable"}:
            return cls.PROBABLE
        if v in {"family_only", "identity_family_only"}:
            return cls.FAMILY_ONLY
        return cls.UNRESOLVED


class SpecificityLevel(str, Enum):
    """Blueprint v1.2 — Candidate Specificity.
    Governs how candidates are clustered and presented in the Result Contract.
    """
    COMPOUND_REQUIRED = "compound_required"
    PRODUCT_FAMILY_REQUIRED = "product_family_required"
    SUBFAMILY = "subfamily"
    FAMILY_ONLY = "family_only"
    
    # Internal drift values kept for mapping
    COMPOUND_SPECIFIC = "compound_specific"
    FAMILY_LEVEL = "family_level"
    MATERIAL_CLASS = "material_class"
    DOCUMENT_HIT = "document_hit"
    UNRESOLVED = "unresolved"

    @classmethod
    def normalize(cls, value: Any) -> "SpecificityLevel":
        v = str(value or "").strip().lower()
        if v in {"compound_required", "compound_specific"}:
            return cls.COMPOUND_REQUIRED
        if v in {"product_family_required", "material_class"}:
            return cls.PRODUCT_FAMILY_REQUIRED
        if v in {"subfamily"}:
            return cls.SUBFAMILY
        if v in {"family_only", "family_level", "document_hit"}:
            return cls.FAMILY_ONLY
        return cls.FAMILY_ONLY


class ConflictType(str, Enum):
    """Blueprint v1.2 — 9 standard conflict types."""
    FALSE_CONFLICT = "FALSE_CONFLICT"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    SCOPE_CONFLICT = "SCOPE_CONFLICT"
    CONDITION_CONFLICT = "CONDITION_CONFLICT"
    COMPOUND_SPECIFICITY_CONFLICT = "COMPOUND_SPECIFICITY_CONFLICT"
    ASSUMPTION_CONFLICT = "ASSUMPTION_CONFLICT"
    TEMPORAL_VALIDITY_CONFLICT = "TEMPORAL_VALIDITY_CONFLICT"
    PARAMETER_CONFLICT = "PARAMETER_CONFLICT"
    UNKNOWN = "UNKNOWN"


class ConflictSeverity(str, Enum):
    """Blueprint v1.2 — 7 conflict severity classes."""
    SOFT = "SOFT"
    INFO = "INFO"
    WARNING = "WARNING"  # Drift value, mapping to HARD or SOFT depending on context
    HARD = "HARD"
    CRITICAL = "CRITICAL"
    FALSE_CONFLICT = "FALSE_CONFLICT"
    BLOCKING_UNKNOWN = "BLOCKING_UNKNOWN"
    RESOLUTION_REQUIRES_MANUFACTURER_SCOPE = "RESOLUTION_REQUIRES_MANUFACTURER_SCOPE"

    @classmethod
    def normalize(cls, value: Any) -> "ConflictSeverity":
        v = str(value or "").strip().upper()
        if v in {"SOFT", "INFO"}:
            return cls.SOFT if v == "SOFT" else cls.INFO
        if v == "WARNING":
            return cls.HARD  # Legacy WARNING is treated as HARD in v1.2 context
        if v == "HARD":
            return cls.HARD
        if v == "CRITICAL":
            return cls.CRITICAL
        if v == "FALSE_CONFLICT":
            return cls.FALSE_CONFLICT
        if v == "BLOCKING_UNKNOWN":
            return cls.BLOCKING_UNKNOWN
        if v == "RESOLUTION_REQUIRES_MANUFACTURER_SCOPE":
            return cls.RESOLUTION_REQUIRES_MANUFACTURER_SCOPE
        return cls.HARD


class ReleaseStatus(str, Enum):
    """Blueprint v1.2 — RFQ/Contract Release Status."""
    INADMISSIBLE = "inadmissible"
    PRECHECK_ONLY = "precheck_only"
    MANUFACTURER_VALIDATION_REQUIRED = "manufacturer_validation_required"
    RFQ_READY = "rfq_ready"


class CompletenessCategory(str, Enum):
    """Blueprint v1.2 — Risk-driven Completeness Taxonomy."""
    RELEASE_BLOCKING_TECHNICAL_UNKNOWN = "release_blocking_technical_unknown"
    MANUFACTURER_VALIDATION_UNKNOWN = "manufacturer_validation_unknown"
    QUALIFICATION_GAP = "qualification_gap"
    CLARIFICATION_GAP = "clarification_gap"
    OPTIONAL_OPTIMIZATION_GAP = "optional_optimization_gap"


class CompletenessDepth(str, Enum):
    """Blueprint v1.2 — Analysis Depth Levels."""
    PRECHECK = "precheck"
    PREQUALIFICATION = "prequalification"
    CRITICAL_REVIEW = "critical_review"


class ClaimType(str, Enum):
    """Blueprint v1.2 — Claim Governance Taxonomy."""
    DETERMINISTIC_FACT = "deterministic_fact"
    EVIDENCE_BASED_ASSERTION = "evidence_based_assertion"
    HEURISTIC_HINT = "heuristic_hint"
    EXPERT_PATTERN = "expert_pattern"
    MANUFACTURER_LIMIT = "manufacturer_limit"
    DERIVED_ASSUMPTION = "derived_assumption"


# Type aliases for Literal use in Pydantic models (for IDE support)
IdentityClassLiteral = Literal[
    "identity_confirmed",
    "identity_probable",
    "identity_family_only",
    "identity_unresolved"
]

SpecificityLevelLiteral = Literal[
    "compound_required",
    "product_family_required",
    "subfamily",
    "family_only"
]

ConflictTypeLiteral = Literal[
    "FALSE_CONFLICT",
    "SOURCE_CONFLICT",
    "SCOPE_CONFLICT",
    "CONDITION_CONFLICT",
    "COMPOUND_SPECIFICITY_CONFLICT",
    "ASSUMPTION_CONFLICT",
    "TEMPORAL_VALIDITY_CONFLICT",
    "PARAMETER_CONFLICT",
    "UNKNOWN"
]

ConflictSeverityLiteral = Literal[
    "SOFT",
    "INFO",
    "HARD",
    "CRITICAL",
    "FALSE_CONFLICT",
    "BLOCKING_UNKNOWN",
    "RESOLUTION_REQUIRES_MANUFACTURER_SCOPE"
]

ReleaseStatusLiteral = Literal[
    "inadmissible",
    "precheck_only",
    "manufacturer_validation_required",
    "rfq_ready"
]

CompletenessCategoryLiteral = Literal[
    "release_blocking_technical_unknown",
    "manufacturer_validation_unknown",
    "qualification_gap",
    "clarification_gap",
    "optional_optimization_gap"
]

CompletenessDepthLiteral = Literal[
    "precheck",
    "prequalification",
    "critical_review"
]

ClaimTypeLiteral = Literal[
    "deterministic_fact",
    "evidence_based_assertion",
    "heuristic_hint",
    "expert_pattern",
    "manufacturer_limit",
    "derived_assumption"
]
