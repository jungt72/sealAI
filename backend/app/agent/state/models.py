"""
Governed State Models — Phase F-B.1

Four-layer state architecture for the governed execution path.
All layers are Pydantic BaseModels (not TypedDicts) — immutable after construction,
serialisable, and explicitly typed.

Write-access rules (enforced by reducers.py — never bypass):

  Layer            | Who may write           | How
  ─────────────────┼─────────────────────────┼────────────────────────────────
  ObservedState    | LLM, User, Tile-Override | Directly (append-only)
  NormalizedState  | Reducer only            | reduce_observed_to_normalized()
  AssertedState    | Reducer only            | reduce_normalized_to_asserted()
  GovernanceState  | Reducer only            | reduce_asserted_to_governance()

Architecture invariant (Umbauplan F-B):
  LLM writes ONLY to ObservedState.
  Everything downstream is deterministic.
  No shortcut from raw text → Asserted/Governance.

Relation to existing state.py:
  The TypedDict-based layers (ObservedLayer, NormalizedLayer, …) in agent/state.py
  remain active for the LangGraph orchestration graph during Phase F.
  These Pydantic models are the TARGET state for the new governed execution path
  (graph/nodes/*) introduced in Phase F-C.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.agent.services.medium_context import MediumContext

try:
    import ulid
except ModuleNotFoundError:  # pragma: no cover - compatibility fallback for local test envs
    class _UlidCompat:
        @staticmethod
        def new() -> str:
            return uuid.uuid4().hex

    ulid = _UlidCompat()


def _new_idempotency_key() -> str:
    if hasattr(ulid, "new"):
        return str(ulid.new())  # type: ignore[call-arg]
    if hasattr(ulid, "ULID"):
        return str(ulid.ULID())  # type: ignore[call-arg]
    return uuid.uuid4().hex

# ---------------------------------------------------------------------------
# Shared sub-types
# ---------------------------------------------------------------------------

class MappingConfidence(str):
    """Confidence grade for a normalized parameter value.

    Mirrors domain/normalization.MappingConfidence — redefined here to keep
    state/models.py self-contained without a circular import.
    """
    CONFIRMED = "confirmed"
    ESTIMATED = "estimated"
    INFERRED = "inferred"
    REQUIRES_CONFIRMATION = "requires_confirmation"


# Literal alias for Pydantic fields
ConfidenceLevel = Literal[
    "confirmed",
    "estimated",
    "inferred",
    "requires_confirmation",
]

FieldLifecycleStatus = Literal[
    "observed",
    "assumed",
    "derived",
    "stale",
    "contradicted",
]

MediumClassificationStatus = Literal[
    "recognized",
    "family_only",
    "mentioned_unclassified",
    "unavailable",
]

MediumClassificationConfidence = Literal["high", "medium", "low"]

MediumFamily = Literal[
    "waessrig",
    "waessrig_salzhaltig",
    "oelhaltig",
    "gasfoermig",
    "dampffoermig",
    "loesemittelhaltig",
    "chemisch_aggressiv",
    "lebensmittelnah",
    "partikelhaltig",
    "unknown",
]


# ---------------------------------------------------------------------------
# ObservedState — Phase F-B.1
# ---------------------------------------------------------------------------

class ObservedExtraction(BaseModel):
    """A single value extracted by the LLM from a user message.

    LLM may produce multiple extractions per turn and per field.
    Conflicts between extractions are resolved by the NormalizedState reducer.
    """

    field_name: str
    """Canonical parameter name (e.g. 'pressure_bar', 'temperature_c', 'medium')."""

    raw_value: Any
    """Verbatim extracted value before any unit normalization."""

    raw_unit: Optional[str] = None
    """Unit string as extracted (e.g. '°C', 'bar', 'mm')."""

    source: Literal["llm", "user"] = "llm"
    """Origin of the extraction."""

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    """LLM-reported or heuristic extraction confidence (0.0 – 1.0)."""

    turn_index: int = Field(default=0, ge=0)
    """Turn number within the session when this extraction was made."""


class UserOverride(BaseModel):
    """A deliberate user correction submitted via the tile UI.

    User overrides always win over LLM extractions for the same field.
    They are the ONLY mechanism by which a user may change a normalized value.
    Never written by the LLM or any reducer.
    """

    field_name: str
    """Canonical parameter name being overridden."""

    override_value: Any
    """New value supplied by the user."""

    override_unit: Optional[str] = None
    """Unit supplied with the override (may differ from previous unit)."""

    turn_index: int = Field(default=0, ge=0)
    """Turn number when the override was submitted."""


class ObservedState(BaseModel):
    """Raw intake layer — the only layer LLM and users may write to.

    append-only during a governed session. Never mutated after a turn completes.
    All downstream state (Normalized → Asserted → Governance) is derived
    deterministically from this layer.
    """

    raw_extractions: list[ObservedExtraction] = Field(default_factory=list)
    """All LLM and user extractions across all turns, in order."""

    user_overrides: list[UserOverride] = Field(default_factory=list)
    """User-submitted tile overrides. Always win over raw_extractions."""

    source_turns: list[int] = Field(default_factory=list)
    """Ordered list of turn indices that contributed to this observed state."""

    def with_extraction(self, extraction: ObservedExtraction) -> "ObservedState":
        """Return a new ObservedState with the extraction appended."""
        return self.model_copy(
            update={
                "raw_extractions": self.raw_extractions + [extraction],
                "source_turns": sorted(set(self.source_turns + [extraction.turn_index])),
            }
        )

    def with_override(self, override: UserOverride) -> "ObservedState":
        """Return a new ObservedState with the user override appended."""
        return self.model_copy(
            update={
                "user_overrides": self.user_overrides + [override],
                "source_turns": sorted(set(self.source_turns + [override.turn_index])),
            }
        )


# ---------------------------------------------------------------------------
# NormalizedState — Phase F-B.1
# ---------------------------------------------------------------------------

class NormalizedParameter(BaseModel):
    """A single parameter after normalization and unit harmonization.

    Produced exclusively by reduce_observed_to_normalized().
    """

    field_name: str
    value: Any
    """Normalized value in the canonical unit for this field."""

    unit: Optional[str] = None
    """Canonical unit (SI where applicable)."""

    confidence: ConfidenceLevel = "confirmed"
    """Confidence grade of the normalization."""

    source: Literal["llm", "user_override", "default"] = "llm"
    """Which input produced this parameter."""

    source_turn: Optional[int] = None
    """Turn index of the source extraction or override."""


class ConflictRef(BaseModel):
    """Reference to a detected parameter conflict."""

    field_name: str
    description: str
    severity: Literal["warning", "blocking"] = "warning"


class AssumptionRef(BaseModel):
    """Reference to an implicit assumption introduced during normalization."""

    field_name: str
    description: str


class NormalizedState(BaseModel):
    """Deterministically derived from ObservedState.

    Only reduce_observed_to_normalized() may produce this.
    No LLM writes. No direct field assignments from call-site code.
    """

    parameters: dict[str, NormalizedParameter] = Field(default_factory=dict)
    """Canonical parameter map. Key = field_name."""

    unit_system: str = "SI"
    """Active unit system for this normalization pass."""

    conflicts: list[ConflictRef] = Field(default_factory=list)
    """Detected conflicts between extractions of the same field."""

    assumptions: list[AssumptionRef] = Field(default_factory=list)
    """Implicit assumptions introduced during normalization."""

    parameter_status: dict[str, FieldLifecycleStatus] = Field(default_factory=dict)
    """Per-field canonical status for downstream consumers."""


# ---------------------------------------------------------------------------
# AssertedState — Phase F-B.1
# ---------------------------------------------------------------------------

class AssertedClaim(BaseModel):
    """A single asserted (confirmed) technical value.

    Produced exclusively by reduce_normalized_to_asserted().
    """

    field_name: str
    asserted_value: Any
    evidence_refs: list[str] = Field(default_factory=list)
    """References to evidence claims that support this assertion."""

    confidence: ConfidenceLevel = "confirmed"


class AssertedState(BaseModel):
    """Deterministically derived from NormalizedState + Evidence.

    Only reduce_normalized_to_asserted() may produce this.
    """

    assertions: dict[str, AssertedClaim] = Field(default_factory=dict)
    """Confirmed technical claims. Key = field_name."""

    blocking_unknowns: list[str] = Field(default_factory=list)
    """Field names that must be resolved before governance can proceed."""

    conflict_flags: list[str] = Field(default_factory=list)
    """Field names with unresolved conflicts that block assertions."""


# ---------------------------------------------------------------------------
# DerivedState / EvidenceState — W2.1 additive six-layer mapping
# ---------------------------------------------------------------------------

class DerivedState(AssertedState):
    """Six-layer deterministic state based on AssertedState.

    Additive mapping only: legacy AssertedState remains authoritative for
    existing code paths, while DerivedState provides the target six-layer slot.
    """

    rwdr_result: dict[str, Any] = Field(default_factory=dict)
    pv_value: float | None = None
    velocity: float | None = None
    suitability: dict[str, Any] = Field(default_factory=dict)
    material_suitability: dict[str, Any] = Field(default_factory=dict)
    applicable_norms: list[str] = Field(default_factory=list)
    requirement_class: Optional["RequirementClass"] = None
    field_status: dict[str, FieldLifecycleStatus] = Field(default_factory=dict)


class EvidenceState(BaseModel):
    """Dedicated evidence layer separated from derived and decision state."""

    evidence_results: list[Any] = Field(default_factory=list)
    source_versions: dict[str, str] = Field(default_factory=dict)
    retrieval_query: str | None = None


# ---------------------------------------------------------------------------
# GovernanceState — Phase F-B.1
# ---------------------------------------------------------------------------

# Governance class thresholds (Umbauplan F-B, F-C.2):
#   A — all core fields asserted, no blocking unknowns, no conflicts
#   B — partial — enough to proceed, some unknowns remain
#   C — cycle limit reached or unresolvable unknowns (auto-fallback)
#   D — fundamentally out of scope (domain rules)

GovClass = Literal["A", "B", "C", "D"]


class RequirementClass(BaseModel):
    """A neutral platform requirement class.

    Identifies the technical solution space without naming a manufacturer.
    Example: 'RD30-2-1', 'PTFE10'.
    """

    class_id: str
    """Short identifier, e.g. 'RD30-2-1'."""

    description: str = ""
    """Human-readable description of what this class covers."""

    seal_type: Optional[str] = None
    """Broad seal family (e.g. 'RWDR', 'O-Ring', 'Flachdichtung')."""


class GovernanceState(BaseModel):
    """Deterministically derived from AssertedState.

    Only reduce_asserted_to_governance() may produce this.
    """

    requirement_class: Optional[RequirementClass] = None
    """Resolved requirement class, or None if not yet determinable."""

    gov_class: Optional[GovClass] = None
    """Governance readiness class A/B/C/D."""

    rfq_admissible: bool = False
    """True only for Class A with complete assertions and no open conflicts."""

    validity_limits: list[str] = Field(default_factory=list)
    """Explicit scope-of-validity statements for the outward contract."""

    open_validation_points: list[str] = Field(default_factory=list)
    """Items that require manufacturer validation before final release."""


class DecisionState(GovernanceState):
    """Six-layer deterministic decision layer based on GovernanceState."""

    outward_class: str | None = None
    preselection: dict[str, Any] | None = None
    decision_basis_hash: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    field_status: dict[str, FieldLifecycleStatus] = Field(default_factory=dict)


class MediumCaptureState(BaseModel):
    raw_mentions: list[str] = Field(default_factory=list)
    primary_raw_text: str | None = None
    source_turn_ref: str | None = None
    source_turn_index: int | None = None


class MediumClassificationState(BaseModel):
    canonical_label: str | None = None
    family: MediumFamily = "unknown"
    confidence: MediumClassificationConfidence = "low"
    status: MediumClassificationStatus = "unavailable"
    normalization_source: str | None = None
    mapping_confidence: ConfidenceLevel | None = None
    matched_alias: str | None = None
    source_registry_key: str | None = None
    followup_question: str | None = None


class ContextHintState(BaseModel):
    label: str | None = None
    confidence: MediumClassificationConfidence = "low"
    source_turn_ref: str | None = None
    source_turn_index: int | None = None
    source_type: str | None = None


# ---------------------------------------------------------------------------
# MatchingState — Phase G Block 1
# ---------------------------------------------------------------------------

class ManufacturerRef(BaseModel):
    """Minimal deterministic manufacturer reference for outward-safe matching."""

    manufacturer_name: str
    candidate_ids: list[str] = Field(default_factory=list)
    material_families: list[str] = Field(default_factory=list)
    grade_names: list[str] = Field(default_factory=list)
    capability_hints: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    qualified_for_rfq: bool = False


class ManufacturerCapability(BaseModel):
    """Minimal deterministic manufacturer capability summary."""

    manufacturer_name: str
    requirement_class_ids: list[str] = Field(default_factory=list)
    material_families: list[str] = Field(default_factory=list)
    grade_names: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    capability_hints: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    qualified_for_rfq: bool = False


class MatchingState(BaseModel):
    """Deterministic matching result slice for the governed path."""

    matchability_status: str = "not_ready"
    status: str = "pending"
    selected_manufacturer_ref: Optional[ManufacturerRef] = None
    manufacturer_refs: list[ManufacturerRef] = Field(default_factory=list)
    manufacturer_capabilities: list[ManufacturerCapability] = Field(default_factory=list)
    matching_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# RFQState — Phase G Block 2
# ---------------------------------------------------------------------------

class RecipientRef(BaseModel):
    """Minimal recipient reference for RFQ handover."""

    manufacturer_name: str
    partner_id: Optional[str] = None
    qualified_for_rfq: bool = False


class RfqState(BaseModel):
    """Deterministic RFQ handover slice for the governed path."""

    status: str = "pending"
    rfq_ready: bool = False
    rfq_admissible: bool = False
    critical_review_status: str = "not_run"
    critical_review_passed: bool = False
    blocking_findings: list[str] = Field(default_factory=list)
    soft_findings: list[str] = Field(default_factory=list)
    required_corrections: list[str] = Field(default_factory=list)
    handover_status: Optional[str] = None
    rfq_object: dict[str, Any] = Field(default_factory=dict)
    rfq_send_payload: dict[str, Any] = Field(default_factory=dict)
    selected_manufacturer_ref: Optional[ManufacturerRef] = None
    recipient_refs: list[RecipientRef] = Field(default_factory=list)
    qualified_material_ids: list[str] = Field(default_factory=list)
    qualified_materials: list[dict[str, Any]] = Field(default_factory=list)
    confirmed_parameters: dict[str, Any] = Field(default_factory=dict)
    dimensions: dict[str, Any] = Field(default_factory=dict)
    requirement_class: Optional[RequirementClass] = None
    handover_summary: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# DispatchState — Phase G Block 3
# ---------------------------------------------------------------------------

class DispatchState(BaseModel):
    """Deterministic dispatch/transport preparation slice for the governed path."""

    dispatch_ready: bool = False
    dispatch_status: str = "pending"
    selected_manufacturer_ref: Optional[ManufacturerRef] = None
    recipient_refs: list[RecipientRef] = Field(default_factory=list)
    requirement_class: Optional[RequirementClass] = None
    transport_channel: Optional[str] = None
    handover_summary: Optional[str] = None
    dispatch_notes: list[str] = Field(default_factory=list)


class ActionReadinessState(BaseModel):
    """Six-layer readiness layer derived from RFQ and dispatch-adjacent slices."""

    pdf_ready: bool = False
    pdf_url: str | None = None
    inquiry_sent: bool = False
    idempotency_key: str = Field(default_factory=_new_idempotency_key)
    missing_for_inquiry: list[str] = Field(default_factory=list)
    dispatch_ready: bool = False
    dispatch_status: str | None = None
    handover_status: str | None = None


# ---------------------------------------------------------------------------
# SealAINormState — Phase H.1
# ---------------------------------------------------------------------------

class SealaiNormIdentity(BaseModel):
    """Stable identity slice for the neutral SealAI norm object."""

    sealai_request_id: Optional[str] = None
    norm_version: str = "sealai_norm_v1"
    requirement_class_id: Optional[str] = None
    seal_family: Optional[str] = None


class SealaiNormOperatingConditions(BaseModel):
    """Stable operating-condition slice for the neutral norm object."""

    medium: Optional[str] = None
    temperature_c: Optional[float] = None
    pressure_bar: Optional[float] = None
    dynamic_type: Optional[str] = None


class SealaiNormMaterial(BaseModel):
    """Stable material slice for the neutral norm object."""

    material_family: Optional[str] = None
    qualified_materials: list[str] = Field(default_factory=list)


class SealaiNormState(BaseModel):
    """Versioned, manufacturer-neutral SealAI norm request object."""

    status: str = "pending"
    identity: SealaiNormIdentity = Field(default_factory=SealaiNormIdentity)
    application_summary: Optional[str] = None
    operating_conditions: SealaiNormOperatingConditions = Field(default_factory=SealaiNormOperatingConditions)
    geometry: dict[str, Any] = Field(default_factory=dict)
    material: SealaiNormMaterial = Field(default_factory=SealaiNormMaterial)
    assumptions: list[str] = Field(default_factory=list)
    validity_limits: list[str] = Field(default_factory=list)
    open_validation_points: list[str] = Field(default_factory=list)
    manufacturer_validation_required: bool = False


# ---------------------------------------------------------------------------
# ExportProfileState — Phase H.2
# ---------------------------------------------------------------------------

class ExportProfileState(BaseModel):
    """Versioned export-profile view derived from norm + commercial readiness."""

    status: str = "pending"
    export_profile_version: str = "sealai_export_profile_v1"
    sealai_request_id: Optional[str] = None
    selected_manufacturer: Optional[str] = None
    recipient_refs: list[str] = Field(default_factory=list)
    requirement_class_id: Optional[str] = None
    application_summary: Optional[str] = None
    dimensions_summary: list[str] = Field(default_factory=list)
    material_summary: Optional[str] = None
    rfq_ready: bool = False
    dispatch_ready: bool = False
    unresolved_points: list[str] = Field(default_factory=list)
    export_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ManufacturerMappingState — Phase H.3
# ---------------------------------------------------------------------------

class ManufacturerMappingState(BaseModel):
    """Bounded manufacturer-mapping layer derived from export_profile + catalog."""

    status: str = "pending"
    mapping_version: str = "manufacturer_mapping_v1"
    selected_manufacturer: Optional[str] = None
    mapped_product_family: Optional[str] = None
    mapped_material_family: Optional[str] = None
    geometry_export_hint: Optional[str] = None
    unresolved_mapping_points: list[str] = Field(default_factory=list)
    mapping_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# DispatchContractState — Phase I.1
# ---------------------------------------------------------------------------

class DispatchContractState(BaseModel):
    """Systemneutraler connector-ready handover contract for later adapters."""

    status: str = "pending"
    contract_version: str = "dispatch_contract_v1"
    sealai_request_id: Optional[str] = None
    selected_manufacturer: Optional[str] = None
    recipient_refs: list[str] = Field(default_factory=list)
    requirement_class_id: Optional[str] = None
    application_summary: Optional[str] = None
    material_summary: Optional[str] = None
    dimensions_summary: list[str] = Field(default_factory=list)
    rfq_ready: bool = False
    dispatch_ready: bool = False
    unresolved_points: list[str] = Field(default_factory=list)
    mapping_summary: Optional[str] = None
    handover_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Conversation strategy contract (preparatory, non-authoritative)
# ---------------------------------------------------------------------------

ConversationPhase = Literal[
    "rapport",
    "exploration",
    "narrowing",
    "clarification",
    "recommendation",
    "matching",
    "rfq_handover",
    "review",
    "escalation",
]

ResponseMode = Literal[
    "open_invitation",
    "single_question",
    "guided_explanation",
    "result_summary",
    "handover_summary",
]


class ConversationStrategyContract(BaseModel):
    """Optional per-turn communication contract.

    This model is explicitly non-authoritative for governed state.
    It exists to carry a small, typed communication plan between the
    deterministic system state and later human-facing rendering layers.
    """

    conversation_phase: ConversationPhase = "exploration"
    turn_goal: str = "continue_conversation"
    user_signal_mirror: str = ""
    """Legacy compatibility field.

    v1.2 communication hardening no longer injects or requires a fixed
    mirrored opening sentence in outward replies.
    """
    primary_question: Optional[str] = None
    primary_question_reason: str = ""
    """Die eine technische Begründung, warum genau diese Frage jetzt wichtig ist."""
    supporting_reason: Optional[str] = None
    response_mode: ResponseMode = "guided_explanation"

    @field_validator("user_signal_mirror")
    @classmethod
    def _validate_user_signal_mirror(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("primary_question")
    @classmethod
    def _validate_primary_question(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value or "").strip()
        if not text:
            return None
        if text.count("?") != 1 or not text.endswith("?"):
            raise ValueError("primary_question must be exactly one question sentence")
        if any(marker in text[:-1] for marker in ".!?"):
            raise ValueError("primary_question must not contain multiple sentences")
        return text

    @field_validator("primary_question_reason")
    @classmethod
    def _validate_primary_question_reason(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if "?" in text:
            raise ValueError("primary_question_reason must not contain a question")
        sentence_count = len([part for part in re.split(r"[.!]", text) if part.strip()])
        if sentence_count > 1:
            raise ValueError("primary_question_reason must be at most one sentence")
        return text

    @model_validator(mode="after")
    def _sync_reason_fields(self) -> "ConversationStrategyContract":
        if not self.primary_question_reason and self.supporting_reason:
            self.primary_question_reason = str(self.supporting_reason).strip()
        if not self.supporting_reason and self.primary_question_reason:
            self.supporting_reason = self.primary_question_reason
        return self


class TurnContextContract(ConversationStrategyContract):
    """Small shared communication context for one visible turn.

    Additive only: this is a compact communication-layer view and never a
    source of technical or governance authority.
    """

    confirmed_facts_summary: list[str] = Field(default_factory=list)
    open_points_summary: list[str] = Field(default_factory=list)


class ConversationMessage(BaseModel):
    """Visible chat transcript entry bound to the governed live session canon."""

    role: Literal["user", "assistant"]
    content: str
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Combined governed session state (convenience wrapper)
# ---------------------------------------------------------------------------

class GovernedSessionState(BaseModel):
    """Full governed session state with legacy and six-layer slices.

    Used as the input/output type for the governed graph nodes (Phase F-C).
    Kept separate from AgentState (LangGraph orchestration layer) to prevent
    cross-layer writes.
    """

    observed: ObservedState = Field(default_factory=ObservedState)
    normalized: NormalizedState = Field(default_factory=NormalizedState)
    asserted: AssertedState = Field(default_factory=AssertedState)
    derived: DerivedState = Field(default_factory=DerivedState)
    evidence: EvidenceState = Field(default_factory=EvidenceState)
    governance: GovernanceState = Field(default_factory=GovernanceState)
    decision: DecisionState = Field(default_factory=DecisionState)
    medium_capture: MediumCaptureState = Field(default_factory=MediumCaptureState)
    medium_classification: MediumClassificationState = Field(default_factory=MediumClassificationState)
    application_hint: ContextHintState = Field(default_factory=ContextHintState)
    motion_hint: ContextHintState = Field(default_factory=ContextHintState)
    matching: MatchingState = Field(default_factory=MatchingState)
    rfq: RfqState = Field(default_factory=RfqState)
    dispatch: DispatchState = Field(default_factory=DispatchState)
    action_readiness: ActionReadinessState = Field(default_factory=ActionReadinessState)
    sealai_norm: SealaiNormState = Field(default_factory=SealaiNormState)
    export_profile: ExportProfileState = Field(default_factory=ExportProfileState)
    manufacturer_mapping: ManufacturerMappingState = Field(default_factory=ManufacturerMappingState)
    dispatch_contract: DispatchContractState = Field(default_factory=DispatchContractState)
    medium_context: MediumContext = Field(default_factory=MediumContext)
    conversation_messages: list[ConversationMessage] = Field(default_factory=list)

    analysis_cycle: int = Field(default=0, ge=0)
    """Number of completed analysis cycles in this session."""

    max_cycles: int = Field(default=3, ge=1)
    """Configured cycle limit. When exceeded → auto Class C."""

    @model_validator(mode="before")
    @classmethod
    def _hydrate_six_layers_from_legacy_inputs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)

        def _dump_model(value: Any) -> Any:
            return value.model_dump() if isinstance(value, BaseModel) else value

        if "derived" not in payload and "asserted" in payload:
            payload["derived"] = _dump_model(payload["asserted"])
        if "asserted" not in payload and "derived" in payload:
            payload["asserted"] = _dump_model(payload["derived"])

        if "decision" not in payload and "governance" in payload:
            payload["decision"] = _dump_model(payload["governance"])
        if "governance" not in payload and "decision" in payload:
            payload["governance"] = _dump_model(payload["decision"])

        if "evidence" not in payload:
            payload["evidence"] = {}

        if "action_readiness" not in payload:
            rfq_payload = payload.get("rfq")
            dispatch_payload = payload.get("dispatch")
            action_payload: dict[str, Any] = {}

            if isinstance(rfq_payload, (dict, RfqState)):
                rfq_state = rfq_payload if isinstance(rfq_payload, RfqState) else RfqState.model_validate(rfq_payload)
                action_payload["inquiry_sent"] = bool(rfq_state.rfq_send_payload)
                action_payload["missing_for_inquiry"] = list(rfq_state.required_corrections)
                action_payload["handover_status"] = rfq_state.handover_status

            if isinstance(dispatch_payload, (dict, DispatchState)):
                dispatch_state = (
                    dispatch_payload
                    if isinstance(dispatch_payload, DispatchState)
                    else DispatchState.model_validate(dispatch_payload)
                )
                action_payload["dispatch_ready"] = dispatch_state.dispatch_ready
                action_payload["dispatch_status"] = dispatch_state.dispatch_status

            payload["action_readiness"] = action_payload

        return payload
