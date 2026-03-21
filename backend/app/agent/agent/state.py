from typing import Annotated, Any, Dict, List, Optional, TypedDict, Literal, NotRequired
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages

from app.agent.case_state import CaseState

ReleaseStatus = Literal[
    "inadmissible",
    "precheck_only",
    "manufacturer_validation_required",
    "rfq_ready",
    "not_applicable",
]
RFQAdmissibility = Literal["inadmissible", "provisional", "ready", "not_applicable"]
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
    certainty: str
    confirmed: bool
    source_fact_ids: List[str]


class IdentityRecord(TypedDict, total=False):
    """Blueprint v1.2 Section 02: normalized field metadata with identity class."""

    raw_value: Any
    normalized_value: Any
    identity_class: IdentityClass
    normalization_certainty: str
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


ReviewState = Literal["none", "pending", "approved", "rejected"]


class ReviewLayer(TypedDict, total=False):
    """
    HITL Review Layer — Phase A3.
    Deterministic trigger writes this; frontend/operator resolves it.
    Never populated by the LLM.
    """
    review_required: bool           # True when a human review is mandatory
    review_state: ReviewState       # lifecycle: none → pending → approved | rejected
    review_reason: str              # why the review was triggered (deterministic rule name)
    reviewed_by: Optional[str]      # set by operator after review
    review_decision: Optional[str]  # operator decision text
    review_note: Optional[str]      # optional annotation by reviewer

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
    candidate_clusters: NotRequired[List[Dict[str, Any]]]
    release_status: ReleaseStatus
    rfq_admissibility: RFQAdmissibility
    specificity_level: SpecificityLevel
    output_blocked: bool

class HandoverLayer(TypedDict, total=False):
    """
    Commercial / Handover Layer — Phase A6.
    Populated deterministically at the end of a qualified structured-path case.
    Contains only clean, ERP-ready order-profile data — no internal governance
    state, no reasoning artefacts, no demo-data flags.
    """
    is_handover_ready: bool            # True only when rfq_ready + no pending HITL review
    target_system: Optional[str]       # e.g. "rfq_portal" | "shop" | None
    handover_payload: Optional[Dict[str, Any]]  # sanitised order-profile for the target system


class OutcomeLayer(TypedDict, total=False):
    """
    Outcome-Feedback Layer — Phase A7.
    Populated asynchronously by external feedback loops after the case is closed.
    NEVER written by the agent graph or LLM during a run.
    All fields are optional — the layer starts empty and is filled post-deployment.
    """
    implemented: bool       # Recommendation was implemented as-is
    failed: bool            # Implementation failed in the field
    replaced: bool          # Material was replaced after initial deployment
    review_override: bool   # A human reviewer overrode the governed recommendation
    outcome_note: str       # Free-text field for the operator/engineer feedback note


class SealingAIState(TypedDict):
    """
    Blueprint Section 02 / Phase A1:
    bindender State läuft über Observed -> Normalized -> Asserted -> Governance -> Cycle.
    `selection` bleibt ausschließlich als nicht-bindende Projektion für den Live-Pfad bestehen.
    `review`    trägt den HITL-Status (Phase A3) — niemals LLM-generiert.
    `handover`  trägt den Commercial-Payload (Phase A6) — kein ERP-Call, nur Grenzstruktur.
    `outcome`   trägt das Echtzeit-Feedback nach Deployment (Phase A7) — nur extern befüllt.
    """
    observed: ObservedLayer
    normalized: NormalizedLayer
    asserted: AssertedLayer
    governance: GovernanceLayer
    cycle: CycleLayer
    selection: SelectionLayer
    result_contract: NotRequired[Dict[str, Any]]
    review: NotRequired[ReviewLayer]      # HITL review state (Phase A3)
    handover: NotRequired[HandoverLayer]  # Commercial handover payload (Phase A6)
    outcome: NotRequired[OutcomeLayer]    # Post-deployment outcome feedback (Phase A7)

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
    owner_id: NotRequired[Optional[str]]
    loaded_state_revision: NotRequired[int]
    case_state: NotRequired[CaseState]
    result_form: NotRequired[Optional[str]]   # ResultForm value, e.g. "direct_answer"
    policy_path: NotRequired[Optional[str]]   # "fast" | "structured" — set by router (Phase 0A.3)
    run_meta: NotRequired[Optional[Dict[str, Any]]]  # model_id, prompt_version, policy_version (Phase 0A.5)
    # V3 spec fields (Phase 0A QW-2/3/4)
    turn_count: int                           # current turn in this session (hard limit guard)
    max_turns: int                            # hard ceiling — default 12 (CLAUDE.md)
    user_persona: NotRequired[str]            # "erfahrener" | "einsteiger" | "entscheider" | "unknown"
    knowledge_coverage: NotRequired[str]      # "full" | "partial" | "limited"
    inquiry_id: NotRequired[str]              # session_id mirrored for state traceability
