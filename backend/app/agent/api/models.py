from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, Literal
from app.agent.case_state import (
    QUALIFIED_ACTION_AUDIT_EVENT,
    QualifiedActionAuditEventType,
    QualifiedActionId,
    QualifiedActionLifecycleStatus,
)

BindingLevel = Literal[
    "KNOWLEDGE",
    "ORIENTATION",
    "CALCULATION",
    "QUALIFIED_PRESELECTION",
    "RFQ_BASIS",
]

from app.agent.domain.rwdr import (
    RWDRSelectorConfig,
    RWDRSelectorDerivedDTO,
    RWDRSelectorInputDTO,
    RWDRSelectorInputPatchDTO,
    RWDRSelectorOutputDTO,
)

class ChatRequest(BaseModel):
    """
    API Request Modell für Chat-Anfragen (Phase F1).
    Erzwingt einen strikten API-Vertrag (Engineering before Language).
    """
    message: str = Field(..., min_length=1, description="Die Nutzereingabe an den Agenten.")
    session_id: Optional[str] = Field(default="default", description="Eindeutige ID zur Session-Nachverfolgung.")
    rwdr_input: Optional[RWDRSelectorInputDTO] = Field(
        default=None,
        description="Optional strukturierter RWDR-Selector-Input fuer spaetere orchestrierte Flows.",
    )
    rwdr_input_patch: Optional[RWDRSelectorInputPatchDTO] = Field(
        default=None,
        description="Optional partieller RWDR-Selector-Patch fuer mehrturnige Stage-1/2-Ergaenzungen.",
    )

    model_config = ConfigDict(extra="forbid")


class QualifiedActionContract(BaseModel):
    action: QualifiedActionId
    allowed: bool
    rfq_ready: bool
    binding_level: BindingLevel
    summary: str
    block_reasons: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class QualifiedActionGateResponse(BaseModel):
    action: QualifiedActionId
    allowed: bool
    rfq_ready: bool
    binding_level: BindingLevel
    source_type: str
    source_ref: str
    block_reasons: list[str] = Field(default_factory=list)
    summary: str

    model_config = ConfigDict(extra="forbid")


class MaterialDirectionContractResponse(BaseModel):
    authority_layer: str
    direction_layer: str
    source_provenance: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class CandidateClusterContract(BaseModel):
    cluster_key: str
    cluster_status: str
    candidate_ids: list[str] = Field(default_factory=list)
    candidate_count: int
    winner_candidate_id: Optional[str] = None
    candidate_source_origin: Optional[str] = None
    direction_authority: Optional[str] = None
    material_direction_contract: Optional[MaterialDirectionContractResponse] = None
    source_ref: str

    model_config = ConfigDict(extra="forbid")


class QualifiedActionStatusResponse(BaseModel):
    action: QualifiedActionId
    last_status: QualifiedActionLifecycleStatus
    allowed_at_execution_time: bool
    executed: bool
    block_reasons: list[str] = Field(default_factory=list)
    timestamp: str
    binding_level: BindingLevel
    runtime_path: str
    source_ref: str
    action_payload_stub: Optional[str] = None
    current_gate_allows_action: bool
    artifact_provenance: Optional["ArtifactProvenanceResponse"] = None

    model_config = ConfigDict(extra="forbid")


class QualifiedActionAuditDetailsResponse(BaseModel):
    action: QualifiedActionId
    status: QualifiedActionLifecycleStatus
    executed: bool
    block_reasons: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class QualifiedActionAuditEventResponse(BaseModel):
    event_type: QualifiedActionAuditEventType = Field(
        default=QUALIFIED_ACTION_AUDIT_EVENT,
        description="Canonical audit event for qualified actions.",
    )
    timestamp: str
    source_ref: str
    details: QualifiedActionAuditDetailsResponse

    model_config = ConfigDict(extra="forbid")


class ResultContractResponse(BaseModel):
    analysis_cycle_id: Optional[str] = None
    state_revision: int
    binding_level: BindingLevel
    release_status: str
    rfq_admissibility: str
    specificity_level: str
    scope_of_validity: Optional[list[str]] = None
    contract_obsolete: bool
    invalidation_requires_recompute: bool
    invalidation_reasons: list[str] = Field(default_factory=list)
    qualified_action: QualifiedActionContract
    evidence_ref_count: int
    evidence_refs: list[str] = Field(default_factory=list)
    source_ref: str

    model_config = ConfigDict(extra="forbid")


class SelectionSnapshotContract(BaseModel):
    winner_candidate_id: Optional[str] = None
    direction_authority: Optional[str] = None
    viable_candidate_ids: list[str] = Field(default_factory=list)
    qualified_candidate_ids: list[str] = Field(default_factory=list)
    candidate_source_origin: Optional[str] = None
    output_blocked: bool
    material_direction_contract: Optional[MaterialDirectionContractResponse] = None

    model_config = ConfigDict(extra="forbid")


class RenderArtifactResponse(BaseModel):
    artifact_type: str
    artifact_version: str
    mime_type: str
    filename: str
    content: str
    source_ref: str

    model_config = ConfigDict(extra="forbid")


class ArtifactProvenanceResponse(BaseModel):
    artifact_type: str
    artifact_version: str
    filename: str
    mime_type: str
    source_ref: str

    model_config = ConfigDict(extra="forbid")


class SealingRequirementSpecResponse(BaseModel):
    contract_type: str
    contract_version: str
    rendering_status: str
    rendering_message: str
    analysis_cycle_id: Optional[str] = None
    state_revision: int
    binding_level: BindingLevel
    runtime_path: str
    release_status: str
    rfq_admissibility: str
    specificity_level: str
    scope_of_validity: Optional[list[str]] = None
    contract_obsolete: bool
    qualified_action: QualifiedActionContract
    selection_snapshot: Optional[SelectionSnapshotContract] = None
    candidate_clusters: list[CandidateClusterContract] = Field(default_factory=list)
    render_artifact: Optional[RenderArtifactResponse] = None
    source_ref: str

    model_config = ConfigDict(extra="forbid")


class ActionPayloadResponse(BaseModel):
    sealing_requirement_spec: SealingRequirementSpecResponse
    contract_version: str
    rendering_status: str
    message: str
    render_artifact: RenderArtifactResponse

    model_config = ConfigDict(extra="forbid")


class CaseMetaResponse(BaseModel):
    case_id: Optional[str] = None
    session_id: Optional[str] = None
    analysis_cycle_id: Optional[str] = None
    state_revision: int
    status: Optional[str] = None
    origin: Optional[str] = None
    runtime_path: str
    binding_level: BindingLevel
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # 0A.5: additive version provenance — present when a structured request populates it
    version_provenance: Optional[Dict[str, Any]] = Field(
        default=None,
        description="0A.5: Version provenance for reproducibility.",
    )

    model_config = ConfigDict(extra="forbid")


class CaseStateResponse(BaseModel):
    case_meta: Optional[CaseMetaResponse] = None
    active_domain: Optional[str] = None
    raw_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    derived_calculations: dict[str, dict[str, Any]] = Field(default_factory=dict)
    engineering_signals: dict[str, dict[str, Any]] = Field(default_factory=dict)
    qualification_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    result_contract: Optional[ResultContractResponse] = None
    candidate_clusters: list[CandidateClusterContract] = Field(default_factory=list)
    sealing_requirement_spec: Optional[SealingRequirementSpecResponse] = None
    qualified_action_gate: Optional[QualifiedActionGateResponse] = None
    qualified_action_status: Optional[QualifiedActionStatusResponse] = None
    qualified_action_history: list[QualifiedActionStatusResponse] = Field(default_factory=list)
    readiness: Optional[dict[str, Any]] = None
    evidence_trace: Optional[dict[str, Any]] = None
    invalidation_state: Optional[dict[str, Any]] = None
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class SealingStateCycleResponse(BaseModel):
    analysis_cycle_id: Optional[str] = None
    state_revision: int
    contract_obsolete: Optional[bool] = None
    contract_obsolete_reason: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class SealingStateAssertedResponse(BaseModel):
    sealing_requirement_spec: Optional[SealingRequirementSpecResponse] = None

    model_config = ConfigDict(extra="allow")


class SealingStateSelectionResponse(BaseModel):
    candidate_clusters: list[CandidateClusterContract] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class SealingStateResponse(BaseModel):
    cycle: Optional[SealingStateCycleResponse] = None
    asserted: Optional[SealingStateAssertedResponse] = None
    selection: Optional[SealingStateSelectionResponse] = None
    result_contract: Optional[ResultContractResponse] = None

    model_config = ConfigDict(extra="allow")


class VisibleCaseNarrativeItemResponse(BaseModel):
    key: str
    label: str
    value: str
    detail: Optional[str] = None
    severity: Literal["low", "medium", "high"] = "low"

    model_config = ConfigDict(extra="forbid")


class NextStepContractResponse(BaseModel):
    """0B.2a: Machine-readable next-step/missing-input contract from live post-run case state.

    Source: build_conversation_guidance_contract(state) — post-run, live truth.
    Deliberately excludes required_fields (pre-run policy snapshot) to avoid stale-state confusion.
    """

    ask_mode: str = Field(
        ...,
        description="Deterministic mode: critical_inputs | review_inputs | recompute_first | qualification_ready | no_question_needed",
    )
    requested_fields: list[str] = Field(
        default_factory=list,
        description="Prioritized list of fields the system is waiting on (post-run, live state).",
    )
    reason_code: str = Field(
        ...,
        description="Machine-readable reason for current ask mode.",
    )
    impact_hint: Optional[str] = Field(
        default=None,
        description="Short deterministic hint about impact of the current ask mode.",
    )
    rfq_admissibility: str = Field(
        default="inadmissible",
        description="Current rfq_admissibility from governance state.",
    )
    state_revision: int = Field(
        default=0,
        description="State revision at the time this contract was derived.",
    )

    model_config = ConfigDict(extra="forbid")


class VisibleCaseNarrativeResponse(BaseModel):
    governed_summary: str
    technical_direction: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    validity_envelope: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    next_best_inputs: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    suggested_next_questions: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    handover_status: Optional[VisibleCaseNarrativeItemResponse] = None
    delta_status: Optional[VisibleCaseNarrativeItemResponse] = None
    failure_analysis: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    case_summary: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    qualification_status: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    # 0B.2: additive coverage/boundary section — empty list when no policy context available
    coverage_scope: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ChatResponse(BaseModel):
    """
    API Response Modell für Agenten-Antworten (Phase F1).
    Enthält die sprachliche Antwort sowie den technischen System-State.
    """
    reply: str = Field(..., description="Die Antwort des Agenten.")
    session_id: str = Field(..., description="Die Session-ID zur Nachverfolgung.")
    interaction_class: str = Field(..., description="Maschinenlesbare Interaction-Klasse des aktiven Runtime-Pfads.")
    runtime_path: str = Field(..., description="Maschinenlesbarer aktiver Runtime-Pfad.")
    binding_level: BindingLevel = Field(..., description="Maschinenlesbare Verbindlichkeitsstufe der Antwort.")
    has_case_state: bool = Field(..., description="Kennzeichnet, ob im aktuellen Pfad ein strukturierter Case-State aktiv ist.")
    case_id: Optional[str] = Field(default=None, description="Optionale kanonische Case-ID bei strukturierten Pfaden.")
    qualified_action_gate: Optional[QualifiedActionGateResponse] = Field(default=None, description="Deterministischer Qualified-Action-Gate-Contract fuer RFQ-/Download-nahe Aktionen.")
    result_contract: Optional[ResultContractResponse] = Field(default=None, description="Deterministischer outward-facing Result-Contract fuer strukturierte Agent-Pfade.")
    rfq_ready: bool = Field(default=False, description="Legacy-kompatibles RFQ-Ready-Flag, strikt aus qualified_action_gate abgeleitet.")
    case_state: Optional[CaseStateResponse] = Field(default=None, description="Kanonische Case-State-Shell fuer strukturierte Produktivpfade.")
    visible_case_narrative: Optional[VisibleCaseNarrativeResponse] = Field(default=None, description="Read-only Narrative-Projection fuer sichtbare Kommunikation aus deterministischer Semantik.")
    working_profile: Optional[Dict[str, Any]] = Field(default=None, description="Optionales Read-Model fuer UI-kompatible Fast-Path-Payloads.")
    rwdr_output: Optional[RWDRSelectorOutputDTO] = Field(
        default=None,
        description="Optional strukturierter RWDR-Selector-Output fuer spaetere deterministische Entscheidungen.",
    )
    # 0A.2: Interaction Policy V1 — additive, optional, no breaking change
    result_form: Optional[str] = Field(
        default=None,
        description="0A.2: Ergebnisform der Interaction Policy (direct/guided/deterministic/qualified).",
    )
    coverage_status: Optional[str] = Field(
        default=None,
        description="0A.2: Coverage-Status der Policy-Entscheidung (in_scope/partial/out_of_scope/unknown).",
    )
    boundary_flags: Optional[list[str]] = Field(
        default=None,
        description="0A.2: Grenz-Flags der Policy-Entscheidung (z.B. orientation_only, no_manufacturer_release).",
    )
    escalation_reason: Optional[str] = Field(
        default=None,
        description="0A.2: Optionaler Eskalationsgrund bei Policy-Downgrade (z.B. qualification_signal_without_data_basis).",
    )
    # 0A.5: additive version provenance for reproducibility
    version_provenance: Optional[Dict[str, Any]] = Field(
        default=None,
        description="0A.5: Version provenance (model, prompt, policy, projection) for reproducibility.",
    )
    # 0B.2a: machine-readable next-step/missing-input contract — present on structured paths, None on fast paths
    next_step_contract: Optional[NextStepContractResponse] = Field(
        default=None,
        description="0B.2a: Machine-readable next-step/missing-input contract from live post-run case state. None for fast paths.",
    )

    model_config = ConfigDict(extra="forbid")


class CaseActionRequest(BaseModel):
    """Typed action request for server-enforced structured case actions."""

    action: Literal["download_rfq"] = Field(
        default="download_rfq",
        description="Deterministic structured action identifier.",
    )

    model_config = ConfigDict(extra="forbid")


class CaseActionResponse(BaseModel):
    """Deterministic action enforcement result for structured RFQ-style actions."""

    case_id: str
    action: QualifiedActionId
    allowed: bool
    executed: bool
    block_reasons: list[str] = Field(default_factory=list)
    runtime_path: str
    binding_level: BindingLevel
    qualified_action_gate: QualifiedActionGateResponse | None = None
    result_contract: ResultContractResponse | None = None
    case_state: CaseStateResponse | None = None
    visible_case_narrative: VisibleCaseNarrativeResponse | None = None
    action_payload: ActionPayloadResponse | None = None
    audit_event: QualifiedActionAuditEventResponse | None = None

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "ChatRequest",
    "ChatResponse",
    "CaseActionRequest",
    "CaseActionResponse",
    "RWDRSelectorConfig",
    "RWDRSelectorDerivedDTO",
    "RWDRSelectorInputDTO",
    "RWDRSelectorInputPatchDTO",
    "RWDRSelectorOutputDTO",
]
