from typing import Annotated, Any, Dict, List, Optional, TypedDict, Literal, NotRequired
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages

from app.agent.domain.rwdr import (
    RWDRConfidenceField,
    RWDRSelectorConfig,
    RWDRSelectorDerivedDTO,
    RWDRSelectorInputDTO,
    RWDRSelectorInputPatchDTO,
    RWDRSelectorOutputDTO,
)

ReleaseStatus = Literal[
    "inadmissible",
    "precheck_only",
    "manufacturer_validation_required",
    "rfq_ready",
]
RFQAdmissibility = Literal["inadmissible", "provisional", "ready"]
SpecificityLevel = Literal["family_only", "subfamily", "compound_required", "product_family_required"]
IdentityClass = Literal[
    "identity_confirmed",
    "identity_probable",
    "identity_family_only",
    "identity_unresolved",
]


class ObservedInputRecord(TypedDict, total=False):
    """Blueprint v1.2 Section 02: immutable raw intake before normalization."""

    source: str
    raw_text: str
    claim_type: str
    confidence: float
    source_fact_ids: List[str]


class IdentityRecord(TypedDict, total=False):
    """Blueprint v1.2 Section 02: normalized field metadata with identity class."""

    raw_value: Any
    normalized_value: Any
    identity_class: IdentityClass
    normalization_confidence: float
    mapping_reason: str
    source_fact_ids: List[str]
    deterministic_source: str
    evidence_quality: str
    authority_quality: str
    temporal_quality: str

class ObservedLayer(TypedDict):
    """
    Observed Layer (Rohwerte, Units, Originalformulierungen).
    Blueprint Section 02: technisch wirksame Daten starten hier und bleiben roh.
    """
    observed_inputs: List[ObservedInputRecord]
    raw_parameters: Dict[str, Any]

class NormalizedLayer(TypedDict):
    """
    Normalized Layer (Identity Gating).
    Blueprint Section 02 + Section 03: nur deterministisch validierte Normalisierung.
    """
    identity_records: Dict[str, IdentityRecord]
    normalized_parameters: Dict[str, Any]

class AssertedLayer(TypedDict):
    """
    Asserted Layer (Typed Profiles).
    Blueprint Section 02: bindender technischer State nur aus Normalized-Reducer.
    """
    medium_profile: Dict[str, Any]
    machine_profile: Dict[str, Any]
    installation_profile: Dict[str, Any]
    operating_conditions: Dict[str, Any]  # temperature, pressure
    sealing_requirement_spec: Dict[str, Any]

class GovernanceLayer(TypedDict):
    """
    Governance Layer (Compliance & Readiness).
    Blueprint Sections 02, 06, 08: normative Governance-Enumerationen und Gates.
    """
    release_status: ReleaseStatus
    rfq_admissibility: RFQAdmissibility
    specificity_level: SpecificityLevel
    scope_of_validity: List[str]
    assumptions_active: List[str]
    gate_failures: List[str]
    unknowns_release_blocking: List[str]
    unknowns_manufacturer_validation: List[str]
    conflicts: List[Dict[str, Any]]

class CycleLayer(TypedDict):
    """
    Cycle Control (Determinismus & Revision).
    Blueprint Section 02 + Section 12: revisionsgebunden und obsoleszenzfähig.
    """
    analysis_cycle_id: str
    snapshot_parent_revision: int
    superseded_by_cycle: Optional[str]
    contract_obsolete: bool
    contract_obsolete_reason: Optional[str]
    state_revision: int

class SelectionCandidate(TypedDict):
    candidate_id: str
    candidate_kind: str
    material_family: str
    filler_hint: Optional[str]
    grade_name: Optional[str]
    manufacturer_name: Optional[str]
    viability_status: str
    block_reason: Optional[str]
    evidence_refs: List[str]

class RecommendationArtifact(TypedDict):
    """
    Non-binding projection artifact.
    Blueprint Section 08: never the source of technical truth or release truth.
    """

    selection_status: str
    winner_candidate_id: Optional[str]
    candidate_ids: List[str]
    viable_candidate_ids: List[str]
    blocked_candidates: List[Dict[str, str]]
    evidence_basis: List[str]
    release_status: ReleaseStatus
    rfq_admissibility: RFQAdmissibility
    specificity_level: SpecificityLevel
    output_blocked: bool
    trace_provenance_refs: List[str]

class SelectionLayer(TypedDict):
    """
    Non-binding UI projection only.
    Kept for minimal-diff compatibility with /api/agent responses.
    """

    selection_status: str
    candidates: List[SelectionCandidate]
    viable_candidate_ids: List[str]
    blocked_candidates: List[Dict[str, str]]
    winner_candidate_id: Optional[str]
    recommendation_artifact: Optional[RecommendationArtifact]
    release_status: ReleaseStatus
    rfq_admissibility: RFQAdmissibility
    specificity_level: SpecificityLevel
    output_blocked: bool


RWDRStage = Literal["stage_1", "stage_2", "stage_3"]


class RWDRFlowState(TypedDict, total=False):
    active: bool
    stage: RWDRStage
    collected_fields: Dict[str, Any]
    missing_fields: List[RWDRConfidenceField]
    required_stage1_fields: List[RWDRConfidenceField]
    required_stage2_fields: List[RWDRConfidenceField]
    next_field: Optional[RWDRConfidenceField]
    ready_for_decision: bool
    decision_executed: bool


class RWDRSelectorState(TypedDict, total=False):
    flow: RWDRFlowState
    draft: RWDRSelectorInputPatchDTO
    input: RWDRSelectorInputDTO
    derived: RWDRSelectorDerivedDTO
    output: RWDRSelectorOutputDTO
    config: RWDRSelectorConfig
    config_version: str

class SealingAIState(TypedDict):
    """
    Blueprint Section 02 / Phase A1:
    bindender State läuft über Observed -> Normalized -> Asserted -> Governance -> Cycle.
    `selection` bleibt ausschließlich als nicht-bindende Projektion für den Live-Pfad bestehen.
    """
    observed: ObservedLayer
    normalized: NormalizedLayer
    asserted: AssertedLayer
    governance: GovernanceLayer
    cycle: CycleLayer
    selection: SelectionLayer
    rwdr: NotRequired[RWDRSelectorState]

class AgentState(TypedDict):
    """
    LangGraph Orchestration Layer State.
    Integriert LLM-Kontext (messages) und fachlichen State (sealing_state).
    """
    messages: Annotated[List[AnyMessage], add_messages]
    sealing_state: SealingAIState
    relevant_fact_cards: List[Dict[str, Any]]  # Speichert FactCards für Tool-Nodes (Phase H6)
    working_profile: Dict[str, Any]  # Extrahiertes Live-Profil (Druck, Temperatur, etc.)
    tenant_id: Optional[str]
