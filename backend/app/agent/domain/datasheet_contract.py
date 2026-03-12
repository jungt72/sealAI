"""Blueprint-aligned datasheet contract for deterministic material selection governance.

This module introduces the single internal v2.3 contract for product-near
datasheets in the existing /api/agent path. It does not create a second
architecture; it provides a typed contract that later patches can map KB/RAG
evidence into and consume from governance/selection logic.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasheetSpecificityLevel(str, Enum):
    """Deterministic specificity ceiling for datasheet-derived identity."""

    family_only = "family_only"
    subfamily = "subfamily"
    compound_required = "compound_required"


class DocumentClass(str, Enum):
    """Supported datasheet-like document classes for v2.3 governance."""

    manufacturer_grade_sheet = "manufacturer_grade_sheet"
    manufacturer_datasheet = "manufacturer_datasheet"
    distributor_sheet = "distributor_sheet"
    certificate = "certificate"
    standard_specification = "standard_specification"
    standard_test_method = "standard_test_method"
    unknown = "unknown"


class DocumentBindingStrength(str, Enum):
    """Strength of deterministic binding between contract and source document."""

    direct_document = "direct_document"
    source_registry_bound = "source_registry_bound"
    fact_card_bound = "fact_card_bound"
    weak_reference = "weak_reference"


class DataExtractionMethod(str, Enum):
    """Deterministic origin of extracted structured values."""

    manual_structured = "manual_structured"
    deterministic_parser = "deterministic_parser"
    regex_structured = "regex_structured"
    llm_extracted = "llm_extracted"
    mixed = "mixed"


class DataOriginType(str, Enum):
    """Business meaning of the source claim origin."""

    manufacturer_declared = "manufacturer_declared"
    manufacturer_grade_sheet = "manufacturer_grade_sheet"
    distributor_sheet = "distributor_sheet"
    certificate = "certificate"
    standard_document = "standard_document"
    marketing_estimate = "marketing_estimate"
    unknown = "unknown"


class EvidenceStrengthClass(str, Enum):
    """Contract-level evidence strength used for release decisions."""

    strong = "strong"
    qualified = "qualified"
    weak = "weak"
    unknown = "unknown"


class DocumentCollisionStatus(str, Enum):
    """Deterministic collision state across bound documents."""

    none = "none"
    resolved = "resolved"
    unresolved = "unresolved"


class HumanReviewStatus(str, Enum):
    """Human review state for audit-sensitive datasheet contracts."""

    not_required = "not_required"
    required = "required"
    completed = "completed"


class TestSpecimenSource(str, Enum):
    """Source provenance for test specimen context."""

    manufacturer_specimen = "manufacturer_specimen"
    third_party_specimen = "third_party_specimen"
    unknown = "unknown"


class DocumentIdentity(BaseModel):
    """Stable identity for a datasheet-bound evidence artifact."""

    model_config = ConfigDict(extra="forbid")

    source_ref: str
    source_type: str
    source_rank: Optional[int] = None
    document_class: DocumentClass = DocumentClass.unknown
    linked_manufacturer_grade_sheet_ref: Optional[str] = None


class DocumentMetadata(BaseModel):
    """Structured document metadata only from explicit documented sources."""

    model_config = ConfigDict(extra="forbid")

    manufacturer_name: Optional[str] = None
    product_line: Optional[str] = None
    grade_name: Optional[str] = None
    material_family: Optional[str] = None
    revision_date: Optional[str] = None
    published_at: Optional[str] = None
    edition_year: Optional[int | str] = None
    document_revision: Optional[str] = None
    applies_to_color: Optional[str] = None
    certificate_color_dependent: bool = False
    evidence_scope: List[str] = Field(default_factory=list)
    scope_of_validity: List[str] = Field(default_factory=list)


class AuditContract(BaseModel):
    """Hard governance inputs for v2.3 release admissibility."""

    model_config = ConfigDict(extra="forbid")

    document_binding_strength: DocumentBindingStrength
    data_extraction_method: DataExtractionMethod
    data_origin_type: DataOriginType
    evidence_strength_class: EvidenceStrengthClass
    context_completeness_score: int = Field(ge=0, le=100)
    document_collision_status: DocumentCollisionStatus = DocumentCollisionStatus.none
    audit_gate_passed: bool = False
    human_review_status: HumanReviewStatus = HumanReviewStatus.not_required
    normalization_uncertainty: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    test_specimen_source: TestSpecimenSource = TestSpecimenSource.unknown
    critical_test_context_present: bool = True
    non_standard_unit_block: bool = False
    unit_normalized_present: bool = True


class SelectionReadiness(BaseModel):
    """Deterministic release/selection envelope derived from the contract."""

    model_config = ConfigDict(extra="forbid")

    selection_allowed: bool = True
    release_relevant: bool = False
    compound_level_allowed: bool = False
    max_specificity_level: DatasheetSpecificityLevel = DatasheetSpecificityLevel.family_only
    rfq_ready_eligible: bool = False
    blocking_reasons: List[str] = Field(default_factory=list)


class DatasheetContractV23(BaseModel):
    """Single internal datasheet contract for the existing product path.

    Blueprint mapping:
    - Section 02: typed internal state shape
    - Section 03: deterministic gates only
    - Section 06/08: governance and release admissibility
    - Section 12: engineering firewall over free language
    """

    model_config = ConfigDict(extra="forbid")

    document_identity: DocumentIdentity
    document_metadata: DocumentMetadata
    material_identity: Dict[str, Any] = Field(default_factory=dict)
    property_facts: List[Dict[str, Any]] = Field(default_factory=list)
    chemical_resistance_entries: List[Dict[str, Any]] = Field(default_factory=list)
    regulatory_scope: Dict[str, Any] = Field(default_factory=dict)
    processing_dependency: Dict[str, Any] = Field(default_factory=dict)
    audit: AuditContract
    selection_readiness: SelectionReadiness = Field(default_factory=SelectionReadiness)

    @model_validator(mode="after")
    def apply_governance_rules(self) -> "DatasheetContractV23":
        """Apply v2.3 hard rules without LLM or soft heuristics."""

        readiness = self.selection_readiness.model_copy(deep=True)
        reasons: List[str] = []
        metadata = self.document_metadata
        identity = self.document_identity
        audit = self.audit

        if metadata.material_family:
            readiness.max_specificity_level = DatasheetSpecificityLevel.family_only
        if metadata.material_family and (metadata.grade_name or metadata.product_line):
            readiness.max_specificity_level = DatasheetSpecificityLevel.subfamily
        if metadata.material_family and metadata.grade_name and metadata.manufacturer_name:
            readiness.compound_level_allowed = True
            readiness.max_specificity_level = DatasheetSpecificityLevel.compound_required

        if identity.document_class == DocumentClass.distributor_sheet and not identity.linked_manufacturer_grade_sheet_ref:
            readiness.compound_level_allowed = False
            readiness.max_specificity_level = DatasheetSpecificityLevel.subfamily
            reasons.append("distributor_sheet_ceiling_without_manufacturer_grade_sheet")

        if not metadata.grade_name:
            readiness.compound_level_allowed = False

        if audit.document_collision_status == DocumentCollisionStatus.unresolved:
            readiness.selection_allowed = False
            readiness.compound_level_allowed = False
            reasons.append("document_collision_unresolved")

        marketing_block = audit.data_origin_type == DataOriginType.marketing_estimate
        unit_block = audit.non_standard_unit_block or not audit.unit_normalized_present
        color_block = metadata.certificate_color_dependent and not metadata.applies_to_color
        context_block = not audit.critical_test_context_present

        if marketing_block:
            readiness.compound_level_allowed = False
            reasons.append("marketing_estimate_never_release_relevant")
        if unit_block:
            reasons.append("non_standard_unit_block")
        if color_block:
            reasons.append("color_binding_missing")
        if context_block:
            readiness.compound_level_allowed = False
            reasons.append("critical_test_context_missing")

        if audit.context_completeness_score >= 80 and audit.evidence_strength_class in {
            EvidenceStrengthClass.strong,
            EvidenceStrengthClass.qualified,
        }:
            readiness.release_relevant = True

        if (
            marketing_block
            or unit_block
            or color_block
            or context_block
            or not audit.audit_gate_passed
        ):
            readiness.release_relevant = False
            readiness.rfq_ready_eligible = False

        if not audit.audit_gate_passed:
            readiness.rfq_ready_eligible = False
            readiness.release_relevant = False
            reasons.append("audit_gate_not_passed")

        if (
            readiness.compound_level_allowed
            and readiness.max_specificity_level == DatasheetSpecificityLevel.compound_required
            and readiness.release_relevant
            and audit.audit_gate_passed
            and audit.document_collision_status != DocumentCollisionStatus.unresolved
            and audit.data_origin_type != DataOriginType.marketing_estimate
            and audit.unit_normalized_present
            and not audit.non_standard_unit_block
            and audit.critical_test_context_present
        ):
            readiness.rfq_ready_eligible = True

        readiness.blocking_reasons = list(dict.fromkeys(reasons))
        self.selection_readiness = readiness
        return self
