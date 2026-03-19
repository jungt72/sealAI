from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, NotRequired, TypedDict

from app.agent.deterministic_foundation import (
    build_calculation_foundation,
    build_engineering_signal_foundation,
)
from app.agent.material_core import (
    build_material_provider_contract_snapshot,
    evaluate_material_qualification_core,
)


ActiveDomain = Literal[
    "material_static_seal_prequalification",
    "rwdr_preselection",
    "knowledge_only",
    "calculation_only",
    "unknown",
]

QualifiedActionId = Literal["download_rfq"]
QualifiedActionLifecycleStatus = Literal["none", "blocked", "executed"]
QualifiedActionAuditEventType = Literal["qualified_action"]

QUALIFIED_ACTION_DOWNLOAD_RFQ: QualifiedActionId = "download_rfq"
QUALIFIED_ACTION_STATUS_NONE: QualifiedActionLifecycleStatus = "none"
QUALIFIED_ACTION_STATUS_BLOCKED: QualifiedActionLifecycleStatus = "blocked"
QUALIFIED_ACTION_STATUS_EXECUTED: QualifiedActionLifecycleStatus = "executed"
QUALIFIED_ACTION_AUDIT_EVENT: QualifiedActionAuditEventType = "qualified_action"

# 0A.5: Version constants for case-state projection and builder.
PROJECTION_VERSION = "visible_case_narrative_v1"
CASE_STATE_BUILDER_VERSION = "case_state_builder_v1"


class VersionProvenance(TypedDict, total=False):
    """0A.5: Minimal version provenance for reproducibility of structured results.

    All fields are optional (total=False). Fields that are not applicable for a
    given runtime path (e.g. model_id on non-LLM fast paths) are omitted or None.
    """

    model_id: str | None
    prompt_version: str
    prompt_hash: str
    visible_reply_prompt_version: str
    visible_reply_prompt_hash: str
    policy_version: str
    projection_version: str
    case_state_builder_version: str
    rwdr_config_version: str | None
    data_version_note: str


class CaseMeta(TypedDict, total=False):
    case_id: str
    session_id: str
    analysis_cycle_id: str | None
    state_revision: int
    status: str
    origin: str
    runtime_path: str
    binding_level: str
    created_at: str
    updated_at: str
    # 0A.5: additive — present when a structured request populates it
    version_provenance: VersionProvenance


class RawInputEntry(TypedDict, total=False):
    value: Any
    unit: str | None
    source_type: str
    source_ref: str
    confidence: float
    confirmed: bool


class DerivedCalculationEntry(TypedDict, total=False):
    value: Any
    unit: str | None
    status: str
    source_type: str
    source_ref: str
    input_refs: List[str]
    formula_id: str


class EngineeringSignalEntry(TypedDict, total=False):
    value: Any
    signal_class: str
    severity: str
    source_type: str
    source_ref: str
    input_refs: List[str]


class QualificationResultEntry(TypedDict, total=False):
    status: str
    binding_level: str
    source_type: str
    source_ref: str
    details: Dict[str, Any]


class QualifiedActionGate(TypedDict, total=False):
    action: QualifiedActionId
    allowed: bool
    rfq_ready: bool
    binding_level: str
    source_type: str
    source_ref: str
    block_reasons: List[str]
    summary: str


class QualifiedActionStatus(TypedDict, total=False):
    action: QualifiedActionId
    last_status: QualifiedActionLifecycleStatus
    allowed_at_execution_time: bool
    executed: bool
    block_reasons: List[str]
    timestamp: str
    binding_level: str
    runtime_path: str
    source_ref: str
    action_payload_stub: str | None
    current_gate_allows_action: bool
    artifact_provenance: Dict[str, str] | None


QualifiedActionHistoryEntry = QualifiedActionStatus


class ResultContractQualifiedActionView(TypedDict, total=False):
    action: QualifiedActionId
    allowed: bool
    rfq_ready: bool
    binding_level: str
    summary: str
    block_reasons: List[str]


class ResultContract(TypedDict, total=False):
    analysis_cycle_id: str | None
    state_revision: int
    binding_level: str
    release_status: str
    rfq_admissibility: str
    specificity_level: str
    scope_of_validity: List[str] | None
    contract_obsolete: bool
    invalidation_requires_recompute: bool
    invalidation_reasons: List[str]
    qualified_action: ResultContractQualifiedActionView
    evidence_ref_count: int
    evidence_refs: List[str]
    source_ref: str


class MaterialDirectionContract(TypedDict, total=False):
    authority_layer: str
    direction_layer: str
    source_provenance: str | None


class CandidateCluster(TypedDict, total=False):
    cluster_key: str
    cluster_status: str
    candidate_ids: List[str]
    candidate_count: int
    winner_candidate_id: str | None
    candidate_source_origin: str | None
    direction_authority: str | None
    material_direction_contract: MaterialDirectionContract | None
    source_ref: str


class RenderArtifact(TypedDict, total=False):
    artifact_type: str
    artifact_version: str
    mime_type: str
    filename: str
    content: str
    source_ref: str


class SealingRequirementSpec(TypedDict, total=False):
    contract_type: str
    contract_version: str
    rendering_status: str
    rendering_message: str
    analysis_cycle_id: str | None
    state_revision: int
    binding_level: str
    runtime_path: str
    release_status: str
    rfq_admissibility: str
    specificity_level: str
    scope_of_validity: List[str] | None
    contract_obsolete: bool
    qualified_action: ResultContractQualifiedActionView
    selection_snapshot: Dict[str, Any] | None
    candidate_clusters: List[CandidateCluster]
    render_artifact: RenderArtifact
    source_ref: str


class ReadinessState(TypedDict, total=False):
    has_structured_case: bool
    ready_for_guidance: bool
    ready_for_qualification: bool
    missing_critical_inputs: List[str]
    missing_review_inputs: List[str]


class EvidenceTrace(TypedDict, total=False):
    used_evidence_refs: List[str]
    source_fact_ids: List[str]
    evidence_ref_count: int


class InvalidationState(TypedDict, total=False):
    requires_recompute: bool
    stale_sections: List[str]
    recompute_reasons: List[str]
    recompute_completed: bool
    material_input_revision: int
    previous_material_input_fingerprint: str | None
    current_material_input_fingerprint: str | None
    provider_contract_revision: int
    previous_provider_contract_fingerprint: str | None
    current_provider_contract_fingerprint: str | None
    matched_promoted_registry_record_ids: List[str]


class AuditTrailEvent(TypedDict, total=False):
    event_type: str
    timestamp: str
    source_ref: str
    details: Dict[str, Any]


class VisibleNarrativeItem(TypedDict, total=False):
    key: str
    label: str
    value: str
    detail: str | None
    severity: Literal["low", "medium", "high"]


class VisibleCaseNarrative(TypedDict, total=False):
    governed_summary: str
    technical_direction: List[VisibleNarrativeItem]
    validity_envelope: List[VisibleNarrativeItem]
    next_best_inputs: List[VisibleNarrativeItem]
    suggested_next_questions: List[VisibleNarrativeItem]
    handover_status: VisibleNarrativeItem | None
    delta_status: VisibleNarrativeItem | None
    failure_analysis: List[VisibleNarrativeItem]
    case_summary: List[VisibleNarrativeItem]
    qualification_status: List[VisibleNarrativeItem]
    # 0B.2: additive coverage/boundary section — translated from InteractionPolicyDecision signals
    coverage_scope: List[VisibleNarrativeItem]


class QualifiedActionAuditDetails(TypedDict):
    action: QualifiedActionId
    status: QualifiedActionLifecycleStatus
    executed: bool
    block_reasons: List[str]


class QualifiedActionAuditEvent(TypedDict):
    event_type: QualifiedActionAuditEventType
    timestamp: str
    source_ref: str
    details: QualifiedActionAuditDetails


class CaseState(TypedDict):
    case_meta: CaseMeta
    active_domain: ActiveDomain
    raw_inputs: Dict[str, RawInputEntry]
    derived_calculations: Dict[str, DerivedCalculationEntry]
    engineering_signals: Dict[str, EngineeringSignalEntry]
    qualification_results: Dict[str, QualificationResultEntry]
    result_contract: ResultContract
    candidate_clusters: List[CandidateCluster]
    sealing_requirement_spec: SealingRequirementSpec
    qualified_action_gate: QualifiedActionGate
    qualified_action_status: NotRequired[QualifiedActionStatus]
    qualified_action_history: NotRequired[List[QualifiedActionHistoryEntry]]
    readiness: ReadinessState
    evidence_trace: EvidenceTrace
    invalidation_state: InvalidationState
    audit_trail: List[AuditTrailEvent]


def normalize_qualified_action_id(action: Any) -> QualifiedActionId:
    if action in {
        QUALIFIED_ACTION_DOWNLOAD_RFQ,
        "download_technical_rfq",
        "download_rfq_action",
        "download_rfq_artifact",
    }:
        return QUALIFIED_ACTION_DOWNLOAD_RFQ
    return QUALIFIED_ACTION_DOWNLOAD_RFQ


def normalize_qualified_action_lifecycle_status(value: Any) -> QualifiedActionLifecycleStatus:
    if value in {
        QUALIFIED_ACTION_STATUS_NONE,
        QUALIFIED_ACTION_STATUS_BLOCKED,
        QUALIFIED_ACTION_STATUS_EXECUTED,
    }:
        return value
    return QUALIFIED_ACTION_STATUS_NONE


def build_default_candidate_clusters() -> List[CandidateCluster]:
    return []


def build_default_result_contract(
    *,
    analysis_cycle_id: str | None = None,
    state_revision: int = 0,
) -> ResultContract:
    return {
        "analysis_cycle_id": analysis_cycle_id,
        "state_revision": state_revision,
        "binding_level": "ORIENTATION",
        "release_status": "inadmissible",
        "rfq_admissibility": "inadmissible",
        "specificity_level": "family_only",
        "scope_of_validity": None,
        "contract_obsolete": False,
        "invalidation_requires_recompute": False,
        "invalidation_reasons": [],
        "qualified_action": {
            "action": QUALIFIED_ACTION_DOWNLOAD_RFQ,
            "allowed": False,
            "rfq_ready": False,
            "binding_level": "ORIENTATION",
            "summary": "qualified_action_blocked",
            "block_reasons": [],
        },
        "evidence_ref_count": 0,
        "evidence_refs": [],
        "source_ref": "case_state.default_result_contract",
    }


def build_default_sealing_requirement_spec(
    *,
    analysis_cycle_id: str | None = None,
    state_revision: int = 0,
    runtime_path: str | None = None,
    candidate_clusters: List[CandidateCluster] | None = None,
) -> SealingRequirementSpec:
    sealing_requirement_spec: SealingRequirementSpec = {
        "contract_type": "sealing_requirement_spec",
        "contract_version": "sealing_requirement_spec_v1",
        "rendering_status": "rendered",
        "rendering_message": "Deterministic markdown artifact generated from sealing_requirement_spec.",
        "analysis_cycle_id": analysis_cycle_id,
        "state_revision": state_revision,
        "binding_level": "ORIENTATION",
        "runtime_path": runtime_path or "",
        "release_status": "inadmissible",
        "rfq_admissibility": "inadmissible",
        "specificity_level": "family_only",
        "scope_of_validity": None,
        "contract_obsolete": False,
        "qualified_action": {
            "action": QUALIFIED_ACTION_DOWNLOAD_RFQ,
            "allowed": False,
            "rfq_ready": False,
            "binding_level": "ORIENTATION",
            "summary": "qualified_action_blocked",
            "block_reasons": [],
        },
        "selection_snapshot": None,
        "candidate_clusters": list(candidate_clusters or []),
        "source_ref": "case_state.default_sealing_requirement_spec",
    }
    sealing_requirement_spec["render_artifact"] = _build_rendered_sealing_requirement_spec_artifact(
        sealing_requirement_spec=sealing_requirement_spec,
        source_ref="case_state.default_rendered_sealing_requirement_spec",
    )
    return sealing_requirement_spec


def sync_case_state_to_state(
    state: Dict[str, Any],
    *,
    session_id: str,
    runtime_path: str,
    binding_level: str,
    version_provenance: VersionProvenance | None = None,
) -> Dict[str, Any]:
    updated = dict(state)
    case_state = build_case_state(
        updated,
        session_id=session_id,
        runtime_path=runtime_path,
        binding_level=binding_level,
        version_provenance=version_provenance,
    )
    updated["case_state"] = case_state
    return updated


def sync_material_cycle_control(
    state: Dict[str, Any],
    *,
    previous_material_snapshot: Dict[str, Any] | None = None,
    previous_material_fingerprint: str | None = None,
    previous_provider_snapshot: Dict[str, Any] | None = None,
    previous_provider_fingerprint: str | None = None,
) -> Dict[str, Any]:
    """Blueprint Section 02/12: persist deterministic material input revision info."""

    updated = dict(state)
    sealing_state = updated.get("sealing_state") or {}
    cycle = sealing_state.setdefault("cycle", {})
    working_profile = updated.get("working_profile") or {}

    current_snapshot = _build_material_input_snapshot(sealing_state, working_profile)
    current_fingerprint = _material_input_fingerprint(current_snapshot)
    current_provider_snapshot = _build_material_provider_snapshot(updated)
    current_provider_fingerprint = _material_provider_fingerprint(current_provider_snapshot)

    stored_snapshot = cycle.get("material_input_snapshot") or {}
    stored_fingerprint = cycle.get("material_input_fingerprint")
    baseline_snapshot = previous_material_snapshot if previous_material_snapshot is not None else stored_snapshot
    baseline_fingerprint = previous_material_fingerprint if previous_material_fingerprint is not None else stored_fingerprint
    input_changed = bool(
        baseline_fingerprint
        and baseline_fingerprint != current_fingerprint
    )
    stored_provider_snapshot = cycle.get("provider_contract_snapshot") or {}
    stored_provider_fingerprint = cycle.get("provider_contract_fingerprint")
    baseline_provider_snapshot = (
        previous_provider_snapshot
        if previous_provider_snapshot is not None
        else stored_provider_snapshot
    )
    baseline_provider_fingerprint = (
        previous_provider_fingerprint
        if previous_provider_fingerprint is not None
        else stored_provider_fingerprint
    )
    provider_changed = bool(
        baseline_provider_fingerprint
        and baseline_provider_fingerprint != current_provider_fingerprint
    )

    cycle["material_input_snapshot"] = current_snapshot
    cycle["material_input_fingerprint"] = current_fingerprint
    cycle["material_input_revision"] = int(cycle.get("state_revision", 0) or 0)
    cycle["provider_contract_snapshot"] = current_provider_snapshot
    cycle["provider_contract_fingerprint"] = current_provider_fingerprint
    cycle["provider_contract_revision"] = int(cycle.get("state_revision", 0) or 0)
    cycle["matched_promoted_registry_record_ids"] = list(
        current_provider_snapshot.get("matched_promoted_registry_record_ids", [])
    )

    if input_changed:
        cycle["last_material_recompute_previous_fingerprint"] = baseline_fingerprint
        cycle["last_material_recompute_current_fingerprint"] = current_fingerprint
        cycle["last_material_recompute_reasons"] = _diff_material_snapshots(
            baseline_snapshot or {},
            current_snapshot,
        )
        cycle["last_material_recompute_revision"] = int(cycle.get("state_revision", 0) or 0)
    if provider_changed:
        cycle["last_provider_recompute_previous_fingerprint"] = baseline_provider_fingerprint
        cycle["last_provider_recompute_current_fingerprint"] = current_provider_fingerprint
        cycle["last_provider_recompute_reasons"] = _diff_material_provider_snapshots(
            baseline_provider_snapshot or {},
            current_provider_snapshot,
        )
        cycle["last_provider_recompute_revision"] = int(cycle.get("state_revision", 0) or 0)
    if input_changed or provider_changed:
        cycle["contract_obsolete"] = False
        cycle["contract_obsolete_reason"] = None

    updated["sealing_state"] = sealing_state
    return updated


def get_material_input_snapshot_and_fingerprint(state: Dict[str, Any]) -> tuple[Dict[str, Any], str]:
    sealing_state = state.get("sealing_state") or {}
    working_profile = state.get("working_profile") or {}
    snapshot = _build_material_input_snapshot(sealing_state, working_profile)
    return snapshot, _material_input_fingerprint(snapshot)


def get_material_provider_snapshot_and_fingerprint(state: Dict[str, Any]) -> tuple[Dict[str, Any], str]:
    snapshot = _build_material_provider_snapshot(state)
    return snapshot, _material_provider_fingerprint(snapshot)


def build_case_state(
    state: Dict[str, Any],
    *,
    session_id: str,
    runtime_path: str,
    binding_level: str,
    version_provenance: VersionProvenance | None = None,
) -> CaseState:
    sealing_state = state.get("sealing_state") or {}
    working_profile = state.get("working_profile") or {}
    rwdr_state = sealing_state.get("rwdr") or {}
    cycle = sealing_state.get("cycle") or {}
    now = _now_iso()

    raw_inputs = _build_raw_inputs(sealing_state, working_profile, rwdr_state)
    derived_calculations = _build_derived_calculations(sealing_state, working_profile, rwdr_state)
    engineering_signals = _build_engineering_signals(
        sealing_state,
        working_profile,
        rwdr_state,
        derived_calculations,
    )
    invalidation_state = _build_invalidation_state(state, sealing_state, working_profile)
    qualification_results = _build_qualification_results(
        state,
        sealing_state,
        binding_level=binding_level,
        rwdr_state=rwdr_state,
        invalidation_state=invalidation_state,
    )
    qualified_action_gate = _build_qualified_action_gate(
        qualification_results=qualification_results,
        invalidation_state=invalidation_state,
    )
    effective_binding_level = _resolve_effective_binding_level(
        binding_level,
        qualified_action_gate=qualified_action_gate,
    )
    qualified_action_status = _build_qualified_action_status(
        state,
        qualified_action_gate=qualified_action_gate,
    )
    qualified_action_history = _build_qualified_action_history(state)
    evidence_trace = _build_evidence_trace(state, sealing_state)
    result_contract = _build_result_contract(
        sealing_state=sealing_state,
        binding_level=effective_binding_level,
        invalidation_state=invalidation_state,
        qualified_action_gate=qualified_action_gate,
        evidence_trace=evidence_trace,
    )
    candidate_clusters = _build_candidate_clusters(qualification_results)
    sealing_requirement_spec = _build_sealing_requirement_spec(
        runtime_path=runtime_path,
        result_contract=result_contract,
        qualification_results=qualification_results,
        candidate_clusters=candidate_clusters,
    )
    readiness = _build_readiness(sealing_state, raw_inputs, rwdr_state)
    audit_trail = _build_audit_trail(
        cycle=cycle,
        runtime_path=runtime_path,
        readiness=readiness,
        rwdr_state=rwdr_state,
        qualification_results=qualification_results,
        qualified_action_gate=qualified_action_gate,
        qualified_action_status=qualified_action_status,
        qualified_action_history=qualified_action_history,
        timestamp=now,
        version_provenance=version_provenance,
    )

    _case_meta: CaseMeta = {
        "case_id": session_id,
        "session_id": session_id,
        "analysis_cycle_id": cycle.get("analysis_cycle_id"),
        "state_revision": int(cycle.get("state_revision", 0) or 0),
        "status": "active_structured_case",
        "origin": "transitional_structured_projection",
        "runtime_path": runtime_path,
        "binding_level": effective_binding_level,
        "created_at": now,
        "updated_at": now,
    }
    if version_provenance is not None:
        _case_meta["version_provenance"] = version_provenance

    return {
        "case_meta": _case_meta,
        "active_domain": _detect_active_domain(sealing_state, rwdr_state),
        "raw_inputs": raw_inputs,
        "derived_calculations": derived_calculations,
        "engineering_signals": engineering_signals,
        "qualification_results": qualification_results,
        "result_contract": result_contract,
        "candidate_clusters": candidate_clusters,
        "sealing_requirement_spec": sealing_requirement_spec,
        "qualified_action_gate": qualified_action_gate,
        "qualified_action_status": qualified_action_status,
        "qualified_action_history": qualified_action_history,
        "readiness": readiness,
        "evidence_trace": evidence_trace,
        "invalidation_state": invalidation_state,
        "audit_trail": audit_trail,
    }


def _build_raw_inputs(
    sealing_state: Dict[str, Any],
    working_profile: Dict[str, Any],
    rwdr_state: Dict[str, Any],
) -> Dict[str, RawInputEntry]:
    raw_inputs: Dict[str, RawInputEntry] = {}
    observed = sealing_state.get("observed") or {}
    asserted = sealing_state.get("asserted") or {}
    normalized = sealing_state.get("normalized") or {}
    rwdr_input = _model_to_payload(rwdr_state.get("input")) or {}

    observed_raw = observed.get("raw_parameters") or {}
    for key, value in observed_raw.items():
        _put_raw_input(
            raw_inputs,
            key,
            value=value,
            unit=_infer_unit(key),
            source_type="observed.raw_parameters",
            source_ref=f"observed.raw_parameters.{key}",
            confidence=1.0,
            confirmed=True,
        )

    normalized_params = normalized.get("normalized_parameters") or {}
    for key, value in normalized_params.items():
        _put_raw_input(
            raw_inputs,
            key,
            value=value,
            unit=_infer_unit(key),
            source_type="normalized.normalized_parameters",
            source_ref=f"normalized.normalized_parameters.{key}",
            confidence=0.9,
            confirmed=True,
        )

    for key, value in rwdr_input.items():
        _put_raw_input(
            raw_inputs,
            key,
            value=value,
            unit=_infer_unit(key),
            source_type="rwdr.input",
            source_ref=f"rwdr.input.{key}",
            confidence=1.0,
            confirmed=True,
        )

    medium_profile = asserted.get("medium_profile") or {}
    machine_profile = asserted.get("machine_profile") or {}
    operating_conditions = asserted.get("operating_conditions") or {}
    if medium_profile.get("name"):
        _put_raw_input(raw_inputs, "medium", medium_profile.get("name"), None, "asserted.medium_profile", "asserted.medium_profile.name", 0.85, True)
    if machine_profile.get("material"):
        _put_raw_input(raw_inputs, "material", machine_profile.get("material"), None, "asserted.machine_profile", "asserted.machine_profile.material", 0.85, True)
    if operating_conditions.get("pressure") is not None:
        _put_raw_input(raw_inputs, "pressure_bar", operating_conditions.get("pressure"), "bar", "asserted.operating_conditions", "asserted.operating_conditions.pressure", 0.85, True)
    if operating_conditions.get("temperature") is not None:
        _put_raw_input(raw_inputs, "temperature_c", operating_conditions.get("temperature"), "C", "asserted.operating_conditions", "asserted.operating_conditions.temperature", 0.85, True)

    working_profile_mapping = {
        "diameter": ("shaft_diameter_mm", "mm"),
        "speed": ("max_speed_rpm", "rpm"),
        "pressure": ("pressure_bar", "bar"),
        "temperature": ("temperature_c", "C"),
        "medium": ("medium", None),
        "material": ("material", None),
        "seal_material": ("seal_material", None),
        "eccentricity": ("eccentricity", None),
    }
    for source_key, (target_key, unit) in working_profile_mapping.items():
        value = working_profile.get(source_key)
        _put_raw_input(
            raw_inputs,
            target_key,
            value=value,
            unit=unit,
            source_type="working_profile",
            source_ref=f"working_profile.{source_key}",
            confidence=0.7,
            confirmed=False,
        )

    return raw_inputs


def _build_derived_calculations(
    sealing_state: Dict[str, Any],
    working_profile: Dict[str, Any],
    rwdr_state: Dict[str, Any],
) -> Dict[str, DerivedCalculationEntry]:
    return build_calculation_foundation(sealing_state, working_profile, rwdr_state)


def _build_material_direction_contract(
    *,
    direction_authority: Any,
    candidate_source_origin: Any,
) -> MaterialDirectionContract:
    authority_token = str(direction_authority or "none")
    if authority_token == "governed_authority":
        authority_layer = "governed_authority"
        direction_layer = "governed_direction"
    elif authority_token == "evidence_oriented":
        authority_layer = "not_trust_granting"
        direction_layer = "evidence_oriented_direction"
    else:
        authority_layer = "none"
        direction_layer = "none"

    return {
        "authority_layer": authority_layer,
        "direction_layer": direction_layer,
        "source_provenance": str(candidate_source_origin) if candidate_source_origin else None,
    }


def _build_engineering_signals(
    sealing_state: Dict[str, Any],
    working_profile: Dict[str, Any],
    rwdr_state: Dict[str, Any],
    derived_calculations: Dict[str, DerivedCalculationEntry],
) -> Dict[str, EngineeringSignalEntry]:
    return build_engineering_signal_foundation(
        sealing_state,
        working_profile,
        rwdr_state,
        derived_calculations,
    )


def _build_qualification_results(
    state: Dict[str, Any],
    sealing_state: Dict[str, Any],
    *,
    binding_level: str,
    rwdr_state: Dict[str, Any],
    invalidation_state: InvalidationState,
) -> Dict[str, QualificationResultEntry]:
    results: Dict[str, QualificationResultEntry] = {}
    governance = sealing_state.get("governance") or {}
    selection = sealing_state.get("selection") or {}
    rwdr_output = _model_to_payload(rwdr_state.get("output")) or {}

    results["material_governance"] = {
        "status": str(governance.get("release_status", "inadmissible")),
        "binding_level": binding_level,
        "source_type": "sealing_state.governance",
        "source_ref": "sealing_state.governance",
        "details": {
            "rfq_admissibility": governance.get("rfq_admissibility"),
            "specificity_level": governance.get("specificity_level"),
            "assumptions_active": list(governance.get("assumptions_active", [])),
            "gate_failures": list(governance.get("gate_failures", [])),
            "unknowns_release_blocking": list(governance.get("unknowns_release_blocking", [])),
            "unknowns_manufacturer_validation": list(governance.get("unknowns_manufacturer_validation", [])),
        },
    }
    material_core_output = evaluate_material_qualification_core(
        candidates=list(selection.get("candidates", [])),
        relevant_fact_cards=list(state.get("relevant_fact_cards") or []),
        asserted_state=sealing_state.get("asserted") or {},
        governance_state=governance,
    )
    results["material_core"] = {
        "status": material_core_output.qualification_status,
        "binding_level": (
            "QUALIFIED_PRESELECTION"
            if material_core_output.qualification_status == "neutral_rfq_basis_ready"
            else "ORIENTATION"
        ),
        "source_type": "material_core",
        "source_ref": "material_core.evaluate_material_qualification_core",
        "details": material_core_output.model_dump(),
    }
    material_stale = bool(
        invalidation_state.get("requires_recompute")
        and any(
            section in {"qualification_results.material_core", "qualification_results.material_selection_projection"}
            for section in invalidation_state.get("stale_sections", [])
        )
    )
    if material_stale:
        results["material_core"]["status"] = "stale_requires_recompute"
        results["material_core"]["details"]["stale"] = True
        results["material_core"]["details"]["stale_reasons"] = list(invalidation_state.get("recompute_reasons", []))
    if selection:
        direction_authority = (
            selection.get("direction_authority")
            or (
                "governed_authority"
                if list(selection.get("qualified_candidate_ids", []))
                and selection.get("winner_candidate_id") in list(selection.get("qualified_candidate_ids", []))
                else "evidence_oriented"
                if (
                    selection.get("winner_candidate_id")
                    or list(selection.get("viable_candidate_ids", []))
                )
                else "none"
            )
        )
        candidate_source_origin = (
            selection.get("candidate_source_origin")
            or (
                material_core_output.candidate_source_origins[0]
                if len(material_core_output.candidate_source_origins) == 1
                else "mixed_candidate_source_boundary_v1"
            )
        )
        results["material_selection_projection"] = {
            "status": str(selection.get("selection_status", "not_started")),
            "binding_level": "ORIENTATION",
            "source_type": "sealing_state.selection",
            "source_ref": "sealing_state.selection",
            "details": {
                "winner_candidate_id": selection.get("winner_candidate_id"),
                "direction_authority": direction_authority,
                "viable_candidate_ids": list(selection.get("viable_candidate_ids", [])),
                "qualified_candidate_ids": list(selection.get("qualified_candidate_ids", [])),
                "exploratory_candidate_ids": list(selection.get("exploratory_candidate_ids", [])),
                "promoted_candidate_ids": list(
                    selection.get("promoted_candidate_ids", [])
                    or material_core_output.promoted_candidate_ids
                ),
                "transition_candidate_ids": list(
                    selection.get("transition_candidate_ids", [])
                    or material_core_output.transition_candidate_ids
                ),
                "blocked_candidates": list(selection.get("blocked_candidates", [])),
                "blocked_by_candidate_source": list(selection.get("blocked_by_candidate_source", [])),
                "candidate_source_adapter": (
                    selection.get("candidate_source_adapter")
                    or material_core_output.deterministic_gate_summary.get("candidate_source_adapter")
                ),
                "candidate_source_origin": candidate_source_origin,
                "candidate_source_origins": list(
                    selection.get("candidate_source_origins", [])
                    or material_core_output.candidate_source_origins
                ),
                "candidate_source_records": list(
                    selection.get("candidate_source_records", [])
                    or material_core_output.model_dump().get("candidate_source_records", [])
                ),
                "has_promoted_candidate_source": bool(material_core_output.has_promoted_candidate_source),
                "output_blocked": bool(selection.get("output_blocked", True)),
                "material_direction_contract": _build_material_direction_contract(
                    direction_authority=direction_authority,
                    candidate_source_origin=candidate_source_origin,
                ),
            },
        }
        if material_stale:
            results["material_selection_projection"]["status"] = "stale_requires_recompute"
            results["material_selection_projection"]["details"]["stale"] = True
            results["material_selection_projection"]["details"]["stale_reasons"] = list(invalidation_state.get("recompute_reasons", []))
    if rwdr_output:
        results["rwdr_preselection"] = {
            "status": str(rwdr_output.get("type_class") or "engineering_review_required"),
            "binding_level": "QUALIFIED_PRESELECTION",
            "source_type": "rwdr.output",
            "source_ref": "rwdr.output",
            "details": {
                "type_class": rwdr_output.get("type_class"),
                "review_flags": list(rwdr_output.get("review_flags", [])),
                "warnings": list(rwdr_output.get("warnings", [])),
                "modifiers": list(rwdr_output.get("modifiers", [])),
                "hard_stop": rwdr_output.get("hard_stop"),
                "reasoning": list(rwdr_output.get("reasoning", [])),
            },
        }
    return results


def _build_readiness(
    sealing_state: Dict[str, Any],
    raw_inputs: Dict[str, RawInputEntry],
    rwdr_state: Dict[str, Any],
) -> ReadinessState:
    governance = sealing_state.get("governance") or {}
    rwdr_flow = rwdr_state.get("flow") or {}
    missing_critical_inputs = list(governance.get("unknowns_release_blocking", []))
    if not raw_inputs:
        missing_critical_inputs.append("technical_inputs_not_confirmed")

    missing_review_inputs = list(governance.get("unknowns_manufacturer_validation", []))
    missing_review_inputs.extend(str(item) for item in rwdr_flow.get("missing_fields", []) if item)

    return {
        "has_structured_case": True,
        "ready_for_guidance": bool(raw_inputs),
        "ready_for_qualification": (
            governance.get("rfq_admissibility") == "ready"
            or bool(rwdr_flow.get("ready_for_decision"))
            or bool(rwdr_state.get("output"))
        ),
        "missing_critical_inputs": list(dict.fromkeys(missing_critical_inputs)),
        "missing_review_inputs": list(dict.fromkeys(missing_review_inputs)),
    }


def build_conversation_guidance_contract(state: Dict[str, Any]) -> Dict[str, Any]:
    """Return the deterministic conversation-discipline contract for visible chat rendering.

    The visible chat response may be LLM-rendered, but the next required inputs,
    recompute handling, and qualification-readiness stay bound to deterministic state.
    """

    sealing_state = state.get("sealing_state") or {}
    rwdr_state = sealing_state.get("rwdr") or {}
    working_profile = state.get("working_profile") or {}
    cycle = sealing_state.get("cycle") or {}
    governance = sealing_state.get("governance") or {}

    raw_inputs = _build_raw_inputs(sealing_state, working_profile, rwdr_state)
    readiness = _build_readiness(sealing_state, raw_inputs, rwdr_state)
    invalidation_state = _build_invalidation_state(state, sealing_state, working_profile)

    if invalidation_state.get("requires_recompute"):
        return {
            "ask_mode": "recompute_first",
            "requested_fields": [],
            "reason_code": "stale_sections_require_recompute",
            "state_revision": int(cycle.get("state_revision", 0) or 0),
            "rfq_admissibility": str(governance.get("rfq_admissibility") or "inadmissible"),
            "impact_hint": "Recompute stale qualification sections before requesting more data.",
        }

    critical_inputs = [str(item) for item in readiness.get("missing_critical_inputs", []) if item][:3]
    if critical_inputs:
        return {
            "ask_mode": "critical_inputs",
            "requested_fields": critical_inputs,
            "reason_code": "qualification_blocked_by_missing_core_inputs",
            "state_revision": int(cycle.get("state_revision", 0) or 0),
            "rfq_admissibility": str(governance.get("rfq_admissibility") or "inadmissible"),
            "impact_hint": "Qualification remains blocked until the listed core inputs are confirmed.",
        }

    review_inputs = [str(item) for item in readiness.get("missing_review_inputs", []) if item][:3]
    if review_inputs:
        return {
            "ask_mode": "review_inputs",
            "requested_fields": review_inputs,
            "reason_code": "review_gap_remaining",
            "state_revision": int(cycle.get("state_revision", 0) or 0),
            "rfq_admissibility": str(governance.get("rfq_admissibility") or "inadmissible"),
            "impact_hint": "The technical core is present; the listed review inputs tighten the case for downstream validation.",
        }

    if readiness.get("ready_for_qualification"):
        return {
            "ask_mode": "qualification_ready",
            "requested_fields": [],
            "reason_code": "ready_for_qualification",
            "state_revision": int(cycle.get("state_revision", 0) or 0),
            "rfq_admissibility": str(governance.get("rfq_admissibility") or "inadmissible"),
            "impact_hint": "No further missing-input turn is deterministically required before qualification.",
        }

    return {
        "ask_mode": "no_question_needed",
        "requested_fields": [],
        "reason_code": "no_action_needed",
        "state_revision": int(cycle.get("state_revision", 0) or 0),
        "rfq_admissibility": str(governance.get("rfq_admissibility") or "inadmissible"),
        "impact_hint": "No additional input is deterministically required at this step.",
    }


def build_visible_case_narrative(
    *,
    state: Dict[str, Any],
    case_state: Dict[str, Any] | None = None,
    binding_level: str | None = None,
    policy_context: Dict[str, Any] | None = None,
) -> VisibleCaseNarrative:
    active_case_state = case_state or state.get("case_state") or {}
    if not active_case_state:
        sealing_state = state.get("sealing_state") or {}
        working_profile = state.get("working_profile") or {}
        rwdr_state = sealing_state.get("rwdr") or {}
        raw_inputs = _build_raw_inputs(sealing_state, working_profile, rwdr_state)
        readiness = _build_readiness(sealing_state, raw_inputs, rwdr_state)
        invalidation_state = _build_invalidation_state(state, sealing_state, working_profile)
        effective_binding_level = str(binding_level or "QUALIFIED_PRESELECTION")
        qualification_results = _build_qualification_results(
            state,
            sealing_state,
            binding_level=effective_binding_level,
            rwdr_state=rwdr_state,
            invalidation_state=invalidation_state,
        )
        qualified_action_gate = _build_qualified_action_gate(
            qualification_results=qualification_results,
            invalidation_state=invalidation_state,
        )
        result_contract = _build_result_contract(
            sealing_state=sealing_state,
            binding_level=effective_binding_level,
            invalidation_state=invalidation_state,
            qualified_action_gate=qualified_action_gate,
            evidence_trace=_build_evidence_trace(state, sealing_state),
        )
        active_case_state = {
            "qualification_results": qualification_results,
            "result_contract": result_contract,
            "readiness": readiness,
            "invalidation_state": invalidation_state,
            "qualified_action_gate": qualified_action_gate,
            "case_meta": {"binding_level": effective_binding_level},
        }
    qualification_results = active_case_state.get("qualification_results") or {}
    result_contract = active_case_state.get("result_contract") or {}
    readiness = active_case_state.get("readiness") or {}
    invalidation_state = active_case_state.get("invalidation_state") or {}
    guidance_contract = build_conversation_guidance_contract(state)
    visible_binding = (
        binding_level
        or result_contract.get("binding_level")
        or ((active_case_state.get("case_meta") or {}).get("binding_level"))
        or ((active_case_state.get("qualified_action_gate") or {}).get("binding_level"))
        or "ORIENTATION"
    )
    technical_direction = _build_visible_technical_direction(
        qualification_results=qualification_results,
        result_contract=result_contract,
        readiness=readiness,
        binding_level=str(visible_binding),
    )
    validity_envelope = _build_visible_validity_envelope(
        qualification_results=qualification_results,
        result_contract=result_contract,
        readiness=readiness,
        invalidation_state=invalidation_state,
    )
    next_best_inputs = _build_visible_next_best_inputs(
        readiness=readiness,
        result_contract=result_contract,
        invalidation_state=invalidation_state,
    )
    suggested_next_questions = _build_visible_suggested_next_questions(
        guidance_contract=guidance_contract,
    )
    handover_status = _build_visible_handover_status(
        result_contract=result_contract,
        qualified_action_gate=active_case_state.get("qualified_action_gate") or {},
        binding_level=str(visible_binding),
    )
    delta_status = _build_visible_delta_status(
        invalidation_state=invalidation_state,
        result_contract=result_contract,
    )
    failure_analysis = _build_visible_failure_analysis(
        qualification_results=qualification_results,
        readiness=readiness,
    )
    case_summary = _build_visible_case_summary(
        state=state,
        active_case_state=active_case_state,
        binding_level=str(visible_binding),
    )
    qualification_status = _build_visible_qualification_status(
        active_case_state=active_case_state,
        binding_level=str(visible_binding),
        delta_status=delta_status,
    )
    coverage_scope = _build_visible_coverage_scope(policy_context)
    return {
        "governed_summary": _build_visible_governed_summary(
            technical_direction=technical_direction,
            validity_envelope=validity_envelope,
            handover_status=handover_status,
            policy_context=policy_context,
        ),
        "technical_direction": technical_direction,
        "validity_envelope": validity_envelope,
        "next_best_inputs": next_best_inputs,
        "suggested_next_questions": suggested_next_questions,
        "handover_status": handover_status,
        "delta_status": delta_status,
        "failure_analysis": failure_analysis,
        "case_summary": case_summary,
        "qualification_status": qualification_status,
        # 0B.2: additive coverage/boundary section
        "coverage_scope": coverage_scope,
    }


def _build_visible_qualification_status(
    *,
    active_case_state: Dict[str, Any],
    binding_level: str,
    delta_status: VisibleNarrativeItem | None = None,
) -> List[VisibleNarrativeItem]:
    # delta_status must be passed from build_visible_case_narrative to avoid
    # calling _build_visible_delta_status() twice with identical arguments.
    items: List[VisibleNarrativeItem] = []
    qualification_results = active_case_state.get("qualification_results") or {}
    result_contract = active_case_state.get("result_contract") or {}
    readiness = active_case_state.get("readiness") or {}
    invalidation_state = active_case_state.get("invalidation_state") or {}

    # 1. Qualification Level
    qualification_level = _resolve_qualification_level(qualification_results)
    if qualification_level:
        items.append(_narrative_item(
            key="qualification_level",
            label="Qualification Level",
            value=_humanize_token(str(qualification_level.get("status", "pending"))),
            detail=" · ".join(filter(None, [
                _build_qualification_details_summary(qualification_level.get("details") or {}),
                f"Source {qualification_level.get('source_ref')}" if qualification_level.get("source_ref") else None
            ])) or None
        ))

    # 2. RFQ Admissibility
    rfq = result_contract.get("rfq_admissibility")
    if isinstance(rfq, str):
        items.append(_narrative_item(
            key="rfq_admissibility",
            label="RFQ Admissibility",
            value=rfq,
            detail=" · ".join(filter(None, [
                f"Release {result_contract.get('release_status')}" if result_contract.get("release_status") else None,
                f"Binding {result_contract.get('binding_level')}" if result_contract.get("binding_level") else None,
                f"Scope {', '.join(result_contract.get('scope_of_validity', []))}" if result_contract.get("scope_of_validity") else None
            ])) or None,
            severity="low" if rfq == "ready" else "medium" if rfq == "provisional" else "high"
        ))

    # 3. Hard Stops
    hard_stops = _collect_detail_strings(qualification_results, "hard_stop")
    items.append(_narrative_item(
        key="hard_stops",
        label="Hard Stops",
        value=str(len(hard_stops)),
        detail=", ".join(hard_stops) if hard_stops else "None",
        severity="high" if hard_stops else "low"
    ))

    # 4. Review Cases
    review_flags = _collect_detail_strings(qualification_results, "review_flags")
    items.append(_narrative_item(
        key="review_cases",
        label="Review Cases",
        value=str(len(review_flags)),
        detail=", ".join(review_flags) if review_flags else "None",
        severity="medium" if review_flags else "low"
    ))

    # 5. Missing Critical Summary
    missing_critical = [str(i) for i in (readiness.get("missing_critical_inputs") or []) if i]
    items.append(_narrative_item(
        key="missing_critical_summary",
        label="Missing Critical Data",
        value=str(len(missing_critical)),
        detail=", ".join(missing_critical) if missing_critical else "None",
        severity="high" if missing_critical else "low"
    ))

    # 6. Delta Impact — reuse pre-computed delta_status, do not recompute.
    # If not passed (legacy/test call), fall back to recomputing once here.
    effective_delta = delta_status if delta_status is not None else _build_visible_delta_status(
        invalidation_state=invalidation_state,
        result_contract=result_contract,
    )
    if effective_delta:
        items.append(effective_delta)

    return items


def _build_qualification_details_summary(details: Dict[str, Any]) -> str | None:
    parts = []
    if details.get("type_class"):
        parts.append(f"Type {details['type_class']}")
    if details.get("hard_stop"):
        parts.append(f"Hard stop {details['hard_stop']}")
    if details.get("rfq_admissibility"):
        parts.append(f"RFQ {details['rfq_admissibility']}")
    if details.get("specificity_level"):
        parts.append(f"Specificity {details['specificity_level']}")
    return " · ".join(parts) if parts else None


def _narrative_item(
    *,
    key: str,
    label: str,
    value: str,
    detail: str | None = None,
    severity: Literal["low", "medium", "high"] = "low",
) -> VisibleNarrativeItem:
    return {
        "key": key,
        "label": label,
        "value": value,
        "detail": detail,
        "severity": severity,
    }


def _humanize_token(value: str) -> str:
    if not value:
        return "N/A"
    if value.upper() == value and any(ch.isalpha() for ch in value):
        return value
    return " ".join(part.upper() if part.upper() == "RWDR" else part.capitalize() for part in value.replace("_", " ").split())


def _collect_detail_strings(qualification_results: Dict[str, Any], key: str) -> List[str]:
    values: List[str] = []
    for entry in qualification_results.values():
        details = entry.get("details") or {}
        raw = details.get(key)
        if isinstance(raw, str) and raw:
            values.append(raw)
        elif isinstance(raw, list):
            values.extend(str(item) for item in raw if item)
    return list(dict.fromkeys(values))


def _resolve_qualification_level(qualification_results: Dict[str, Any]) -> Dict[str, Any] | None:
    for key in ("material_core", "rwdr_preselection", "material_governance", "material_selection_projection"):
        entry = qualification_results.get(key) or {}
        if isinstance(entry.get("status"), str):
            return entry
    return None


def _build_visible_technical_direction(
    *,
    qualification_results: Dict[str, Any],
    result_contract: Dict[str, Any],
    readiness: Dict[str, Any],
    binding_level: str,
) -> List[VisibleNarrativeItem]:
    rwdr = qualification_results.get("rwdr_preselection") or {}
    selection = qualification_results.get("material_selection_projection") or {}
    selection_details = selection.get("details") or {}
    hard_stops = _collect_detail_strings(qualification_results, "hard_stop")
    review_flags = _collect_detail_strings(qualification_results, "review_flags")
    critical_inputs = [str(item) for item in readiness.get("missing_critical_inputs", []) if item]
    review_inputs = [str(item) for item in readiness.get("missing_review_inputs", []) if item]
    winner_candidate_id = selection_details.get("winner_candidate_id")
    direction_authority = str(selection_details.get("direction_authority") or "none")
    candidate_source_origin = selection_details.get("candidate_source_origin")
    type_class = (rwdr.get("details") or {}).get("type_class")
    qualification_level = _resolve_qualification_level(qualification_results)

    if hard_stops:
        current_value = "Blocked"
        current_detail = f"Deterministic hard stop {', '.join(hard_stops)}"
    elif isinstance(winner_candidate_id, str) and winner_candidate_id:
        current_value = winner_candidate_id
        current_detail = "Leading deterministic material candidate"
    elif isinstance(type_class, str) and type_class:
        current_value = _humanize_token(type_class)
        current_detail = "RWDR type-class direction"
    elif critical_inputs:
        current_value = "Pending core inputs"
        current_detail = f"Missing {', '.join(critical_inputs)}"
    else:
        current_value = "No active technical direction"
        current_detail = None

    basis_tokens = []
    if qualification_level and qualification_level.get("status"):
        basis_tokens.append(f"Qualification {_humanize_token(str(qualification_level['status']))}")
    if isinstance(type_class, str) and type_class:
        basis_tokens.append(f"RWDR {type_class}")
    if isinstance(winner_candidate_id, str) and winner_candidate_id:
        basis_tokens.append(f"Winner {winner_candidate_id}")
    if direction_authority and direction_authority != "none":
        basis_tokens.append(f"Authority {_humanize_token(direction_authority)}")
    if candidate_source_origin:
        basis_tokens.append(f"Source {candidate_source_origin}")

    return [
        _narrative_item(
            key="technical_direction_current",
            label="Current Direction",
            value=current_value,
            detail=current_detail,
            severity="high" if hard_stops or critical_inputs else "medium" if review_flags or review_inputs else "low",
        ),
        _narrative_item(
            key="technical_direction_basis",
            label="Direction Basis",
            value=_humanize_token("blocked" if hard_stops else "rwdr" if type_class else "material" if winner_candidate_id else "none"),
            detail=" · ".join(basis_tokens) or None,
            severity="high" if hard_stops else "low",
        ),
        _narrative_item(
            key="technical_direction_authority",
            label="Direction Authority",
            value=(
                "Governed authority"
                if direction_authority == "governed_authority"
                else "Evidence-oriented direction"
                if direction_authority == "evidence_oriented"
                else "No active direction authority"
            ),
            detail=" · ".join(
                part
                for part in [
                    "Governed domain data is the active trust-granting basis"
                    if direction_authority == "governed_authority"
                    else "Evidence supports orientation and viability but is not trust-granting"
                    if direction_authority == "evidence_oriented"
                    else None,
                    f"Source {candidate_source_origin}" if candidate_source_origin else None,
                ]
                if part
            )
            or None,
            severity="low" if direction_authority == "governed_authority" else "medium" if direction_authority == "evidence_oriented" else "low",
        ),
        _narrative_item(
            key="technical_direction_binding",
            label="Binding Scope",
            value=binding_level,
            detail=" · ".join(
                part
                for part in [
                    f"RFQ {result_contract.get('rfq_admissibility')}" if result_contract.get("rfq_admissibility") else None,
                    f"Release {result_contract.get('release_status')}" if result_contract.get("release_status") else None,
                ]
                if part
            )
            or None,
            severity="high" if result_contract.get("rfq_admissibility") == "inadmissible" else "medium" if result_contract.get("rfq_admissibility") == "provisional" else "low",
        ),
        _narrative_item(
            key="technical_direction_limits",
            label="Limits & Reviews",
            value=f"{len(hard_stops)} hard stop(s)" if hard_stops else f"{len(review_flags) + len(review_inputs) + len(critical_inputs)} open item(s)",
            detail=" · ".join(
                part
                for part in [
                    f"Hard stops {', '.join(hard_stops)}" if hard_stops else None,
                    f"Critical {', '.join(critical_inputs)}" if critical_inputs else None,
                    f"Review flags {', '.join(review_flags)}" if review_flags else None,
                    f"Review inputs {', '.join(review_inputs)}" if review_inputs else None,
                ]
                if part
            )
            or "No active blocker or review item",
            severity="high" if hard_stops or critical_inputs else "medium" if review_flags or review_inputs else "low",
        ),
    ]


def _build_visible_validity_envelope(
    *,
    qualification_results: Dict[str, Any],
    result_contract: Dict[str, Any],
    readiness: Dict[str, Any],
    invalidation_state: Dict[str, Any],
) -> List[VisibleNarrativeItem]:
    governance_details = (qualification_results.get("material_governance") or {}).get("details") or {}
    scope = [str(item) for item in (result_contract.get("scope_of_validity") or []) if item]
    assumptions = [str(item) for item in governance_details.get("assumptions_active", []) if item]
    gate_failures = [str(item) for item in governance_details.get("gate_failures", []) if item]
    blocking_unknowns = [str(item) for item in governance_details.get("unknowns_release_blocking", []) if item] or [
        str(item) for item in readiness.get("missing_critical_inputs", []) if item
    ]
    invalidation_reasons = [str(item) for item in result_contract.get("invalidation_reasons", []) if item] or [
        str(item) for item in invalidation_state.get("recompute_reasons", []) if item
    ]
    contract_obsolete = bool(result_contract.get("contract_obsolete"))
    recompute_required = bool(result_contract.get("invalidation_requires_recompute")) or bool(invalidation_state.get("requires_recompute"))
    return [
        _narrative_item(
            key="validity_scope",
            label="Scope of Validity",
            value=f"{len(scope)} marker(s)" if scope else "No explicit scope marker",
            detail=", ".join(scope) if scope else "No explicit scope marker transported",
            severity="low" if scope else "medium",
        ),
        _narrative_item(
            key="validity_assumptions",
            label="Active Assumptions",
            value=f"{len(assumptions)} active" if assumptions else "None visible",
            detail=", ".join(assumptions) if assumptions else "No active assumptions transported in the visible case",
            severity="medium" if assumptions else "low",
        ),
        _narrative_item(
            key="validity_constraints",
            label="Active Constraints",
            value=f"{len(gate_failures)} gate · {len(blocking_unknowns)} blocking",
            detail=" · ".join(
                part
                for part in [
                    f"Gate failures {', '.join(gate_failures)}" if gate_failures else None,
                    f"Blocking unknowns {', '.join(blocking_unknowns)}" if blocking_unknowns else None,
                ]
                if part
            )
            or "No active gate failure or blocking unknown visible",
            severity="high" if gate_failures or blocking_unknowns else "low",
        ),
        _narrative_item(
            key="validity_obsolescence",
            label="Obsolescence & Recompute",
            value="Recompute required" if recompute_required else "Obsolete" if contract_obsolete else "Current",
            detail=" · ".join(
                part
                for part in [
                    "Contract marked obsolete" if contract_obsolete else None,
                    "Qualification should not be relied on without recompute" if recompute_required else None,
                    f"Reasons {', '.join(invalidation_reasons[:4])}" if invalidation_reasons else None,
                ]
                if part
            )
            or "No active obsolescence or recompute requirement",
            severity="high" if recompute_required or contract_obsolete else "low",
        ),
    ]


def _build_visible_next_best_inputs(
    *,
    readiness: Dict[str, Any],
    result_contract: Dict[str, Any],
    invalidation_state: Dict[str, Any],
) -> List[VisibleNarrativeItem]:
    critical = [str(item) for item in readiness.get("missing_critical_inputs", []) if item]
    review = [str(item) for item in readiness.get("missing_review_inputs", []) if item]
    prioritized = (critical + review)[:3]
    requires_recompute = bool(invalidation_state.get("requires_recompute")) or bool(result_contract.get("invalidation_requires_recompute"))
    ready_for_qualification = bool(readiness.get("ready_for_qualification"))
    rfq = result_contract.get("rfq_admissibility")
    return [
        _narrative_item(
            key="next_input_focus",
            label="Next Best Inputs",
            value=f"{len(prioritized)} input(s)" if prioritized else "No immediate input gap",
            detail=", ".join(prioritized) if prioritized else "No prioritized next input can be derived from the active case semantics.",
            severity="high" if critical else "medium" if review else "low",
        ),
        _narrative_item(
            key="next_input_split",
            label="Input Priority Split",
            value=f"{len(critical)} critical · {len(review)} review",
            detail=" · ".join(
                part
                for part in [
                    f"Critical {', '.join(critical[:3])}" if critical else None,
                    f"Review {', '.join(review[:3])}" if review else None,
                ]
                if part
            )
            or "No active missing-input split",
            severity="high" if critical else "medium" if review else "low",
        ),
        _narrative_item(
            key="next_progress_step",
            label="Next Step Impact",
            value="Resolve critical inputs" if critical else "Resolve review inputs" if review else "Recompute first" if requires_recompute else "Proceed with qualification" if ready_for_qualification else "No derived next step",
            detail=" · ".join(
                part
                for part in [
                    f"Collect {', '.join(prioritized)}" if prioritized else None,
                    "Case change currently affects qualification reliability" if requires_recompute else None,
                    f"RFQ {rfq}" if rfq else None,
                ]
                if part
            )
            or None,
            severity="high" if critical or requires_recompute else "medium" if review else "low",
        ),
    ]


def _build_visible_suggested_next_questions(
    *,
    guidance_contract: Dict[str, Any],
) -> List[VisibleNarrativeItem]:
    ask_mode = str(guidance_contract.get("ask_mode") or "no_question_needed")
    requested_fields = [str(item) for item in guidance_contract.get("requested_fields", []) if item][:3]
    if requested_fields:
        value = "Critical input" if ask_mode == "critical_inputs" else "Review input"
        severity: Literal["medium", "high"] = "high" if ask_mode == "critical_inputs" else "medium"
        return [
            _narrative_item(
                key=f"suggested_question_{index + 1}",
                label=f"Question {index + 1}",
                value=value,
                detail=f"Please confirm {field}.",
                severity=severity,
            )
            for index, field in enumerate(requested_fields)
        ]
    if ask_mode == "recompute_first":
        return [_narrative_item(key="suggested_question_recompute", label="Next Step", value="Recompute required", detail="No new question is needed right now. Recompute stale qualification sections before relying on the current case.", severity="high")]
    if ask_mode == "qualification_ready":
        return [_narrative_item(key="suggested_question_ready", label="Next Step", value="Qualification ready", detail="No follow-up question is required from the current visible case. The next step is to proceed with qualification or review the result.", severity="low")]
    return [_narrative_item(key="suggested_question_none", label="Next Step", value="No suggested question", detail="No concrete follow-up question can be derived from the active case semantics.", severity="low")]


def _build_visible_handover_status(
    *,
    result_contract: Dict[str, Any],
    qualified_action_gate: Dict[str, Any],
    binding_level: str,
) -> VisibleNarrativeItem | None:
    rfq = result_contract.get("rfq_admissibility")
    release_status = result_contract.get("release_status")
    handover_ready = bool(qualified_action_gate.get("allowed")) and bool(qualified_action_gate.get("rfq_ready")) and binding_level == "RFQ_BASIS"
    if handover_ready:
        value = "Handover ready"
        severity: Literal["low", "medium", "high"] = "low"
    elif rfq == "ready" or binding_level == "RFQ_BASIS":
        value = "RFQ ready"
        severity = "low"
    elif binding_level == "QUALIFIED_PRESELECTION":
        value = "Prequalified"
        severity = "medium"
    else:
        value = "Guidance only"
        severity = "high"
    return _narrative_item(
        key="commercial_handover",
        label="Commercial Handover",
        value=value,
        detail=" · ".join(
            part
            for part in [
                f"Binding {binding_level}" if binding_level else None,
                f"Release {release_status}" if release_status else None,
                f"RFQ {rfq}" if rfq else None,
            ]
            if part
        )
        or None,
        severity=severity,
    )


def _build_visible_delta_status(
    *,
    invalidation_state: Dict[str, Any],
    result_contract: Dict[str, Any],
) -> VisibleNarrativeItem | None:
    requires_recompute = bool(invalidation_state.get("requires_recompute")) or bool(result_contract.get("invalidation_requires_recompute"))
    recompute_completed = bool(invalidation_state.get("recompute_completed"))
    reasons = [str(item) for item in invalidation_state.get("recompute_reasons", []) if item]
    if not requires_recompute and not recompute_completed and not reasons:
        return None
    return _narrative_item(
        key="delta_impact",
        label="Delta Impact",
        value="Qualification affected" if requires_recompute else "Qualification refreshed" if recompute_completed else "Case changed",
        detail=f"Reasons {', '.join(reasons[:4])}" if reasons else None,
        severity="high" if requires_recompute else "medium" if recompute_completed else "low",
    )


def _build_visible_case_summary(
    *,
    state: Dict[str, Any],
    active_case_state: Dict[str, Any],
    binding_level: str,
) -> List[VisibleNarrativeItem]:
    summary: List[VisibleNarrativeItem] = []
    case_meta = active_case_state.get("case_meta") or {}
    result_contract = active_case_state.get("result_contract") or {}
    readiness = active_case_state.get("readiness") or {}
    evidence_trace = active_case_state.get("evidence_trace") or {}
    audit_trail = active_case_state.get("audit_trail") or []
    sealing_spec = active_case_state.get("sealing_requirement_spec") or {}
    
    # Checkpoint
    cycle_id = case_meta.get("analysis_cycle_id") or result_contract.get("analysis_cycle_id")
    revision = case_meta.get("state_revision") or result_contract.get("state_revision")
    if cycle_id or revision is not None:
        latest_audit = audit_trail[-1] if audit_trail else {}
        summary.append(_narrative_item(
            key="checkpoint",
            label="Checkpoint",
            value=" · ".join(filter(None, [f"Cycle {cycle_id}" if cycle_id else None, f"Rev {revision}" if revision is not None else None])),
            detail=" · ".join(filter(None, [str(latest_audit.get("event_type", "")) if latest_audit.get("event_type") else None, str(latest_audit.get("timestamp", "")) if latest_audit.get("timestamp") else None])) or None
        ))
        
    # Resume Readiness
    case_id = case_meta.get("case_id")
    critical = [str(i) for i in (readiness.get("missing_critical_inputs") or []) if i]
    review = [str(i) for i in (readiness.get("missing_review_inputs") or []) if i]
    resumable = bool(case_id) and bool(readiness.get("ready_for_guidance"))
    summary.append(_narrative_item(
        key="resume_readiness",
        label="Resume Readiness",
        value="Resumable" if resumable else "Limited",
        detail=" · ".join(filter(None, [f"Case {case_id}" if case_id else None, f"Critical {', '.join(critical)}" if critical else None, f"Review {', '.join(review)}" if review else None])) or None,
        severity="high" if critical else "medium" if review else "low"
    ))
    
    # Evidence Basis
    evidence_refs = [str(r) for r in (result_contract.get("evidence_refs") or evidence_trace.get("used_evidence_refs") or []) if r]
    source_facts = [str(f) for f in (evidence_trace.get("source_fact_ids") or []) if f]
    count = int(result_contract.get("evidence_ref_count") or evidence_trace.get("evidence_ref_count") or len(evidence_refs) or 0)
    if count > 0 or source_facts:
        summary.append(_narrative_item(
            key="evidence_basis",
            label="Evidence Basis",
            value=f"{count} evidence ref(s)" if count > 0 else f"{len(source_facts)} source fact(s)",
            detail=" · ".join(filter(None, [f"Evidence {', '.join(evidence_refs)}" if evidence_refs else None, f"Source facts {', '.join(source_facts)}" if source_facts else None])) or None,
            severity="low" if count > 0 else "medium"
        ))
        
    # Current Case Summary
    qualification_results = active_case_state.get("qualification_results") or {}
    qualification_level = _resolve_qualification_level(qualification_results)
    release_status = result_contract.get("release_status")
    if qualification_level or release_status or binding_level:
        summary.append(_narrative_item(
            key="current_case_summary",
            label="Current Case Summary",
            value=str(release_status or (qualification_level.get("status") if qualification_level else "pending")),
            detail=" · ".join(filter(None, [
                f"Qualification {_humanize_token(str(qualification_level.get('status')))}" if qualification_level else None,
                f"Binding {binding_level}" if binding_level else None,
                "Qualification ready" if readiness.get("ready_for_qualification") else "Qualification pending"
            ])) or None,
            severity="high" if critical else "medium" if review else "low"
        ))

    # Source Binding
    qualification_refs = [str(entry.get("source_ref")) for entry in qualification_results.values() if entry.get("source_ref")]
    qualification_types = [str(entry.get("source_type")) for entry in qualification_results.values() if entry.get("source_type")]
    latest_audit_ref = audit_trail[-1].get("source_ref") if audit_trail else None
    refs = list(set(filter(None, [str(result_contract.get("source_ref")), *qualification_refs, str(latest_audit_ref) if latest_audit_ref else None])))
    if refs or qualification_types:
        summary.append(_narrative_item(
            key="source_binding",
            label="Source Binding",
            value=f"{len(refs)} bound source(s)" if refs else f"{len(qualification_types)} deterministic source(s)",
            detail=" · ".join(filter(None, [
                f"Types {', '.join(set(qualification_types))}" if qualification_types else None,
                f"Refs {', '.join(refs[:4])}" if refs else None
            ])) or None,
            severity="low" if refs else "medium"
        ))

    # Audit Trail Summary
    if audit_trail:
        latest = audit_trail[-1]
        first = audit_trail[0]
        summary.append(_narrative_item(
            key="audit_trail_summary",
            label="Audit Trail",
            value=f"{len(audit_trail)} event(s)",
            detail=" · ".join(filter(None, [f"Latest {latest.get('event_type')}" if latest.get('event_type') else None, str(latest.get('timestamp')) if latest.get('timestamp') else None, f"Started {first.get('event_type')}" if first.get('event_type') else None])) or None
        ))

    # Export Snapshot
    if sealing_spec:
        artifact = sealing_spec.get("render_artifact") or {}
        has_artifact = bool(artifact.get("filename"))
        summary.append(_narrative_item(
            key="export_snapshot",
            label="Technical Snapshot",
            value="Exportable snapshot" if has_artifact else "Structured snapshot",
            detail=" · ".join(filter(None, [
                str(artifact.get("filename")) if artifact.get("filename") else None,
                f"Render {sealing_spec.get('rendering_status')}" if sealing_spec.get("rendering_status") else None,
                f"Binding {sealing_spec.get('binding_level')}" if sealing_spec.get("binding_level") else None
            ])) or None,
            severity="low" if has_artifact else "medium"
        ))

    return summary


def _build_visible_failure_analysis(
    *,
    qualification_results: Dict[str, Any],
    readiness: Dict[str, Any],
) -> List[VisibleNarrativeItem]:
    hard_stops = _collect_detail_strings(qualification_results, "hard_stop")
    review_flags = _collect_detail_strings(qualification_results, "review_flags")
    missing_critical = [str(item) for item in readiness.get("missing_critical_inputs", []) if item]
    missing_review = [str(item) for item in readiness.get("missing_review_inputs", []) if item]
    return [
        _narrative_item(
            key="failure_mode",
            label="Failure Analysis",
            value="Hypothesis active" if review_flags or hard_stops else "No active hypothesis",
            detail="Projection from current deterministic signals and review semantics. Not a confirmed root cause." if review_flags or hard_stops else "No explicit failure hypothesis can be projected from the active case semantics.",
            severity="medium" if review_flags or hard_stops else "low",
        ),
        _narrative_item(
            key="failure_confirmed_limits",
            label="Confirmed Qualification Limits",
            value=f"{len(hard_stops)} hard stop(s)" if hard_stops else f"{len(review_flags)} review case(s)" if review_flags else "No active blocker",
            detail=" · ".join(
                part
                for part in [
                    f"Hard stops {', '.join(hard_stops)}" if hard_stops else None,
                    f"Review cases {', '.join(review_flags)}" if review_flags else None,
                ]
                if part
            )
            or "No deterministic blocker currently visible",
            severity="high" if hard_stops else "medium" if review_flags else "low",
        ),
        _narrative_item(
            key="failure_open_unknowns",
            label="Open Uncertainties",
            value=str(len(missing_critical) + len(missing_review)),
            detail=" · ".join(
                part
                for part in [
                    f"Critical {', '.join(missing_critical)}" if missing_critical else None,
                    f"Review {', '.join(missing_review)}" if missing_review else None,
                ]
                if part
            )
            or "No open uncertainty recorded",
            severity="high" if missing_critical else "medium" if missing_review else "low",
        ),
    ]


def _build_visible_coverage_scope(
    policy_context: Dict[str, Any] | None,
) -> List[VisibleNarrativeItem]:
    """0B.2: Translate coverage/boundary policy signals into narrative items.

    Max 1-2 items. Stable keys: 'coverage_boundary', 'escalation_context'.
    No new coverage logic — only translates signals already present in InteractionPolicyDecision.
    Fast paths with no policy_context return an empty list (lean, no overhead).
    """
    if not policy_context:
        return []

    items: List[VisibleNarrativeItem] = []
    coverage_status = policy_context.get("coverage_status")
    boundary_flags = list(policy_context.get("boundary_flags") or [])
    escalation_reason = policy_context.get("escalation_reason")

    # Item 1: coverage_boundary — emitted for non-trivial coverage states
    if coverage_status and coverage_status != "in_scope":
        severity_map: Dict[str, Literal["low", "medium", "high"]] = {
            "out_of_scope": "high",
            "partial": "medium",
            "orientation_only": "medium",
            "unknown": "medium",
        }
        value_map = {
            "partial": "Teilweise abgedeckt",
            "orientation_only": "Nur Orientierung verfügbar",
            "out_of_scope": "Außerhalb des Anwendungsbereichs",
            "unknown": "Abdeckung unbekannt",
        }
        value = value_map.get(str(coverage_status), _humanize_token(str(coverage_status)))
        severity: Literal["low", "medium", "high"] = severity_map.get(str(coverage_status), "medium")
        detail = ", ".join(_humanize_token(f) for f in boundary_flags) if boundary_flags else None
        items.append(_narrative_item(
            key="coverage_boundary",
            label="Coverage Boundary",
            value=value,
            detail=detail,
            severity=severity,
        ))
    elif coverage_status == "in_scope" and boundary_flags:
        # In-scope but flags present — low-severity note only
        items.append(_narrative_item(
            key="coverage_boundary",
            label="Coverage Boundary",
            value="In Scope",
            detail=", ".join(_humanize_token(f) for f in boundary_flags),
            severity="low",
        ))

    # Item 2: escalation_context — only when escalation_reason is set
    if escalation_reason:
        items.append(_narrative_item(
            key="escalation_context",
            label="Eskalationskontext",
            value=_humanize_token(str(escalation_reason)),
            detail=None,
            severity="medium",
        ))

    return items


def _build_visible_governed_summary(
    *,
    technical_direction: List[VisibleNarrativeItem],
    validity_envelope: List[VisibleNarrativeItem],
    handover_status: VisibleNarrativeItem | None,
    policy_context: Dict[str, Any] | None = None,
) -> str:
    direction = next((item for item in technical_direction if item.get("key") == "technical_direction_current"), None) or {}
    authority = next((item for item in technical_direction if item.get("key") == "technical_direction_authority"), None) or {}
    binding = next((item for item in technical_direction if item.get("key") == "technical_direction_binding"), None) or {}
    constraints = next((item for item in validity_envelope if item.get("key") == "validity_constraints"), None) or {}
    obsolescence = next((item for item in validity_envelope if item.get("key") == "validity_obsolescence"), None) or {}
    parts = [
        f"Aktuelle technische Richtung: {direction.get('value', 'N/A')}.",
        f"Autoritaet: {authority.get('value', 'N/A')}.",
        f"Bindungsrahmen: {binding.get('value', 'N/A')}.",
    ]
    if handover_status and handover_status.get("value"):
        parts.append(f"Handover-Status: {handover_status['value']}.")
    if constraints.get("detail"):
        parts.append(f"Constraints: {constraints['detail']}.")
    if obsolescence.get("value"):
        parts.append(f"Belastbarkeit: {obsolescence['value']}.")
    summary = " ".join(parts)
    # 0B.2: lightweight coverage prefix for guided downgrade paths only
    if policy_context:
        coverage_status = policy_context.get("coverage_status")
        escalation_reason = policy_context.get("escalation_reason")
        if coverage_status and coverage_status not in ("in_scope", None):
            prefix_map = {
                "partial": "[Teilweise abgedeckt]",
                "orientation_only": "[Nur Orientierung]",
                "out_of_scope": "[Außerhalb des Anwendungsbereichs]",
                "unknown": "[Abdeckung unbekannt]",
            }
            prefix = prefix_map.get(str(coverage_status))
            if prefix:
                summary = f"{prefix} {summary}"
        if escalation_reason:
            summary = f"{summary} Eskalation: {_humanize_token(str(escalation_reason))}."
    return summary


def _build_result_contract(
    *,
    sealing_state: Dict[str, Any],
    binding_level: str,
    invalidation_state: InvalidationState,
    qualified_action_gate: QualifiedActionGate,
    evidence_trace: EvidenceTrace,
) -> ResultContract:
    governance = sealing_state.get("governance") or {}
    cycle = sealing_state.get("cycle") or {}
    scope_markers = [str(item) for item in governance.get("scope_of_validity", []) if item]
    return {
        "analysis_cycle_id": cycle.get("analysis_cycle_id"),
        "state_revision": int(cycle.get("state_revision", 0) or 0),
        "binding_level": binding_level,
        "release_status": str(governance.get("release_status", "inadmissible")),
        "rfq_admissibility": str(governance.get("rfq_admissibility", "inadmissible")),
        "specificity_level": str(governance.get("specificity_level", "family_only")),
        "scope_of_validity": scope_markers or None,
        "contract_obsolete": bool(cycle.get("contract_obsolete")),
        "invalidation_requires_recompute": bool(invalidation_state.get("requires_recompute")),
        "invalidation_reasons": list(invalidation_state.get("recompute_reasons", [])),
        "qualified_action": {
            "action": normalize_qualified_action_id(qualified_action_gate.get("action")),
            "allowed": bool(qualified_action_gate.get("allowed")),
            "rfq_ready": bool(qualified_action_gate.get("rfq_ready")),
            "binding_level": str(qualified_action_gate.get("binding_level") or "ORIENTATION"),
            "summary": str(qualified_action_gate.get("summary") or "qualified_action_blocked"),
            "block_reasons": [str(item) for item in qualified_action_gate.get("block_reasons", [])],
        },
        "evidence_ref_count": int(evidence_trace.get("evidence_ref_count", 0) or 0),
        "evidence_refs": [str(item) for item in evidence_trace.get("used_evidence_refs", [])],
        "source_ref": "case_state.result_contract",
    }


def _resolve_effective_binding_level(
    binding_level: str,
    *,
    qualified_action_gate: QualifiedActionGate,
) -> str:
    gate_binding_level = str(qualified_action_gate.get("binding_level") or "")
    if gate_binding_level == "RFQ_BASIS" and bool(qualified_action_gate.get("allowed")):
        return "RFQ_BASIS"
    return binding_level


def _build_sealing_requirement_spec(
    *,
    runtime_path: str,
    result_contract: ResultContract,
    qualification_results: Dict[str, QualificationResultEntry],
    candidate_clusters: List[CandidateCluster],
) -> SealingRequirementSpec:
    selection_projection = (qualification_results.get("material_selection_projection") or {}).get("details") or {}
    selection_snapshot: Dict[str, Any] | None = None
    if selection_projection:
        selection_snapshot = {
            "winner_candidate_id": selection_projection.get("winner_candidate_id"),
            "direction_authority": selection_projection.get("direction_authority"),
            "viable_candidate_ids": list(selection_projection.get("viable_candidate_ids", [])),
            "qualified_candidate_ids": list(selection_projection.get("qualified_candidate_ids", [])),
            "candidate_source_origin": selection_projection.get("candidate_source_origin"),
            "output_blocked": bool(selection_projection.get("output_blocked", True)),
            "material_direction_contract": dict(
                selection_projection.get("material_direction_contract")
                or _build_material_direction_contract(
                    direction_authority=selection_projection.get("direction_authority"),
                    candidate_source_origin=selection_projection.get("candidate_source_origin"),
                )
            ),
        }

    sealing_requirement_spec: SealingRequirementSpec = {
        "contract_type": "sealing_requirement_spec",
        "contract_version": "sealing_requirement_spec_v1",
        "rendering_status": "rendered",
        "rendering_message": "Deterministic markdown artifact generated from sealing_requirement_spec.",
        "analysis_cycle_id": result_contract.get("analysis_cycle_id"),
        "state_revision": int(result_contract.get("state_revision", 0) or 0),
        "binding_level": str(
            (result_contract.get("qualified_action") or {}).get("binding_level")
            or result_contract.get("binding_level")
            or "ORIENTATION"
        ),
        "runtime_path": runtime_path,
        "release_status": str(result_contract.get("release_status", "inadmissible")),
        "rfq_admissibility": str(result_contract.get("rfq_admissibility", "inadmissible")),
        "specificity_level": str(result_contract.get("specificity_level", "family_only")),
        "scope_of_validity": result_contract.get("scope_of_validity"),
        "contract_obsolete": bool(result_contract.get("contract_obsolete")),
        "qualified_action": dict(result_contract.get("qualified_action") or {}),
        "selection_snapshot": selection_snapshot,
        "candidate_clusters": candidate_clusters,
        "source_ref": "case_state.sealing_requirement_spec",
    }
    sealing_requirement_spec["render_artifact"] = _build_rendered_sealing_requirement_spec_artifact(
        sealing_requirement_spec=sealing_requirement_spec,
        source_ref="case_state.rendered_sealing_requirement_spec",
    )
    return sealing_requirement_spec


def _slugify_artifact_fragment(value: str | None) -> str:
    raw = (value or "").strip().lower()
    sanitized = "".join(ch if ch.isalnum() else "-" for ch in raw)
    collapsed = "-".join(part for part in sanitized.split("-") if part)
    return collapsed or "case"


def _build_rendered_sealing_requirement_spec_artifact(
    *,
    sealing_requirement_spec: SealingRequirementSpec,
    source_ref: str,
) -> RenderArtifact:
    qualified_action = sealing_requirement_spec.get("qualified_action") or {}
    selection_snapshot = sealing_requirement_spec.get("selection_snapshot") or {}
    candidate_clusters = sealing_requirement_spec.get("candidate_clusters") or []
    analysis_cycle_id = str(sealing_requirement_spec.get("analysis_cycle_id") or "")
    cycle_fragment = _slugify_artifact_fragment(analysis_cycle_id)
    winner_candidate_id = selection_snapshot.get("winner_candidate_id") or "none"
    viable_candidate_ids = ", ".join(selection_snapshot.get("viable_candidate_ids", [])) or "none"
    qualified_candidate_ids = ", ".join(selection_snapshot.get("qualified_candidate_ids", [])) or "none"
    cluster_lines = [
        (
            f"- {cluster.get('cluster_key')}: "
            f"{', '.join(cluster.get('candidate_ids', [])) or 'none'}"
        )
        for cluster in candidate_clusters
        if isinstance(cluster, dict)
    ]
    if not cluster_lines:
        cluster_lines = ["- none"]

    content = "\n".join(
        [
            "# Sealing Requirement Spec",
            "",
            f"- Analysis Cycle ID: {analysis_cycle_id or 'n/a'}",
            f"- State Revision: {sealing_requirement_spec.get('state_revision', 0)}",
            f"- Binding Level: {sealing_requirement_spec.get('binding_level', 'ORIENTATION')}",
            f"- Release Status: {sealing_requirement_spec.get('release_status', 'inadmissible')}",
            f"- RFQ Admissibility: {sealing_requirement_spec.get('rfq_admissibility', 'inadmissible')}",
            f"- Specificity Level: {sealing_requirement_spec.get('specificity_level', 'family_only')}",
            f"- Contract Obsolete: {bool(sealing_requirement_spec.get('contract_obsolete'))}",
            "",
            "## Qualified Action",
            f"- Action: {normalize_qualified_action_id(qualified_action.get('action'))}",
            f"- Allowed: {bool(qualified_action.get('allowed'))}",
            f"- RFQ Ready: {bool(qualified_action.get('rfq_ready'))}",
            f"- Summary: {qualified_action.get('summary', 'qualified_action_blocked')}",
            "",
            "## Selection Snapshot",
            f"- Winner Candidate ID: {winner_candidate_id}",
            f"- Viable Candidate IDs: {viable_candidate_ids}",
            f"- Qualified Candidate IDs: {qualified_candidate_ids}",
            "",
            "## Candidate Clusters",
            *cluster_lines,
        ]
    )
    return {
        "artifact_type": "sealing_requirement_spec_markdown",
        "artifact_version": "sealing_requirement_spec_render_v1",
        "mime_type": "text/markdown",
        "filename": f"sealing-requirement-spec-{cycle_fragment}.md",
        "content": content,
        "source_ref": source_ref,
    }


def _build_candidate_clusters(
    qualification_results: Dict[str, QualificationResultEntry],
) -> List[CandidateCluster]:
    selection_projection = (qualification_results.get("material_selection_projection") or {}).get("details") or {}
    if not selection_projection:
        return []

    selection_status = str(
        (qualification_results.get("material_selection_projection") or {}).get("status")
        or "not_started"
    )
    winner_candidate_id = selection_projection.get("winner_candidate_id")
    candidate_source_origin = selection_projection.get("candidate_source_origin")
    direction_authority = selection_projection.get("direction_authority")
    blocked_candidate_ids = [
        str(item.get("candidate_id"))
        for item in selection_projection.get("blocked_candidates", [])
        if isinstance(item, dict) and item.get("candidate_id")
    ]

    cluster_specs = [
        ("selected", [winner_candidate_id] if winner_candidate_id else []),
        ("qualified_viable", selection_projection.get("qualified_candidate_ids", [])),
        ("viable", selection_projection.get("viable_candidate_ids", [])),
        ("exploratory", selection_projection.get("exploratory_candidate_ids", [])),
        ("transition", selection_projection.get("transition_candidate_ids", [])),
        ("blocked", blocked_candidate_ids),
    ]

    clusters: List[CandidateCluster] = []
    for cluster_key, raw_candidate_ids in cluster_specs:
        candidate_ids = [str(item) for item in raw_candidate_ids if item]
        if not candidate_ids:
            continue
        candidate_ids = list(dict.fromkeys(candidate_ids))
        clusters.append(
            {
                "cluster_key": cluster_key,
                "cluster_status": selection_status,
                "candidate_ids": candidate_ids,
                "candidate_count": len(candidate_ids),
                "winner_candidate_id": str(winner_candidate_id) if winner_candidate_id else None,
                "candidate_source_origin": (
                    str(candidate_source_origin) if candidate_source_origin else None
                ),
                "direction_authority": (
                    str(direction_authority) if direction_authority else None
                ),
                "material_direction_contract": _build_material_direction_contract(
                    direction_authority=direction_authority,
                    candidate_source_origin=candidate_source_origin,
                ),
                "source_ref": "case_state.candidate_clusters",
            }
        )
    return clusters


def _build_evidence_trace(state: Dict[str, Any], sealing_state: Dict[str, Any]) -> EvidenceTrace:
    evidence_refs: List[str] = []
    source_fact_ids: List[str] = []
    for card in state.get("relevant_fact_cards") or []:
        evidence_id = card.get("evidence_id") or card.get("id")
        if evidence_id:
            evidence_refs.append(str(evidence_id))

    selection = sealing_state.get("selection") or {}
    artifact = selection.get("recommendation_artifact") or {}
    evidence_refs.extend(str(item) for item in artifact.get("evidence_basis", []) if item)
    evidence_refs.extend(str(item) for item in artifact.get("trace_provenance_refs", []) if item)

    observed = sealing_state.get("observed") or {}
    for entry in observed.get("observed_inputs", []) or []:
        source_fact_ids.extend(str(item) for item in entry.get("source_fact_ids", []) if item)

    normalized = sealing_state.get("normalized") or {}
    for identity in (normalized.get("identity_records") or {}).values():
        source_fact_ids.extend(str(item) for item in identity.get("source_fact_ids", []) if item)

    deduped_refs = list(dict.fromkeys(evidence_refs + source_fact_ids))
    deduped_fact_ids = list(dict.fromkeys(source_fact_ids))
    return {
        "used_evidence_refs": deduped_refs,
        "source_fact_ids": deduped_fact_ids,
        "evidence_ref_count": len(deduped_refs),
    }


def _build_invalidation_state(
    state: Dict[str, Any],
    sealing_state: Dict[str, Any],
    working_profile: Dict[str, Any],
) -> InvalidationState:
    cycle = sealing_state.get("cycle") or {}
    current_snapshot = _build_material_input_snapshot(sealing_state, working_profile)
    current_fingerprint = _material_input_fingerprint(current_snapshot)
    current_provider_snapshot = _build_material_provider_snapshot(state)
    current_provider_fingerprint = _material_provider_fingerprint(current_provider_snapshot)
    previous_snapshot = cycle.get("material_input_snapshot") or {}
    previous_fingerprint = cycle.get("material_input_fingerprint")
    previous_provider_snapshot = cycle.get("provider_contract_snapshot") or {}
    previous_provider_fingerprint = cycle.get("provider_contract_fingerprint")
    fingerprint_mismatch = bool(previous_fingerprint and previous_fingerprint != current_fingerprint)
    provider_fingerprint_mismatch = bool(
        previous_provider_fingerprint and previous_provider_fingerprint != current_provider_fingerprint
    )
    requires_recompute = bool(cycle.get("contract_obsolete")) or fingerprint_mismatch or provider_fingerprint_mismatch
    reasons: List[str] = []
    if fingerprint_mismatch:
        reasons.extend(_diff_material_snapshots(previous_snapshot, current_snapshot))
    if provider_fingerprint_mismatch:
        reasons.extend(_diff_material_provider_snapshots(previous_provider_snapshot, current_provider_snapshot))
    if cycle.get("contract_obsolete_reason"):
        reasons.append(str(cycle.get("contract_obsolete_reason")))
    stale_sections: List[str] = []
    if requires_recompute:
        stale_sections.extend(
            [
                "qualification_results.material_core",
                "qualification_results.material_selection_projection",
            ]
        )
    if fingerprint_mismatch or cycle.get("contract_obsolete"):
        stale_sections.extend(
            [
                "engineering_signals",
                "derived_calculations",
            ]
        )
    input_recompute_completed = bool(
        not fingerprint_mismatch
        and cycle.get("last_material_recompute_previous_fingerprint")
        and cycle.get("last_material_recompute_current_fingerprint") == current_fingerprint
        and cycle.get("last_material_recompute_previous_fingerprint") != current_fingerprint
    )
    provider_recompute_completed = bool(
        not provider_fingerprint_mismatch
        and cycle.get("last_provider_recompute_previous_fingerprint")
        and cycle.get("last_provider_recompute_current_fingerprint") == current_provider_fingerprint
        and cycle.get("last_provider_recompute_previous_fingerprint") != current_provider_fingerprint
    )
    recompute_completed = bool(
        not requires_recompute
        and (input_recompute_completed or provider_recompute_completed)
    )
    if input_recompute_completed and cycle.get("last_material_recompute_reasons"):
        reasons.extend(str(item) for item in cycle.get("last_material_recompute_reasons", []) if item)
    if provider_recompute_completed and cycle.get("last_provider_recompute_reasons"):
        reasons.extend(str(item) for item in cycle.get("last_provider_recompute_reasons", []) if item)
    previous_display_fingerprint = (
        cycle.get("last_material_recompute_previous_fingerprint")
        if input_recompute_completed
        else previous_fingerprint
    )
    previous_provider_display_fingerprint = (
        cycle.get("last_provider_recompute_previous_fingerprint")
        if provider_recompute_completed
        else previous_provider_fingerprint
    )
    return {
        "requires_recompute": requires_recompute,
        "stale_sections": list(dict.fromkeys(stale_sections)),
        "recompute_reasons": list(dict.fromkeys(reasons)),
        "recompute_completed": recompute_completed,
        "material_input_revision": int(cycle.get("material_input_revision", cycle.get("state_revision", 0)) or 0),
        "previous_material_input_fingerprint": previous_display_fingerprint,
        "current_material_input_fingerprint": current_fingerprint,
        "provider_contract_revision": int(cycle.get("provider_contract_revision", cycle.get("state_revision", 0)) or 0),
        "previous_provider_contract_fingerprint": previous_provider_display_fingerprint,
        "current_provider_contract_fingerprint": current_provider_fingerprint,
        "matched_promoted_registry_record_ids": list(
            current_provider_snapshot.get("matched_promoted_registry_record_ids", [])
        ),
    }


def _build_audit_trail(
    *,
    cycle: Dict[str, Any],
    runtime_path: str,
    readiness: ReadinessState,
    rwdr_state: Dict[str, Any],
    qualification_results: Dict[str, QualificationResultEntry],
    qualified_action_gate: QualifiedActionGate,
    qualified_action_status: QualifiedActionStatus,
    qualified_action_history: List[QualifiedActionHistoryEntry],
    timestamp: str,
    version_provenance: VersionProvenance | None = None,
) -> List[AuditTrailEvent]:
    _projection_details: Dict[str, Any] = {
        "runtime_path": runtime_path,
        "analysis_cycle_id": cycle.get("analysis_cycle_id"),
        "state_revision": cycle.get("state_revision"),
    }
    if version_provenance is not None:
        _projection_details["version_provenance"] = dict(version_provenance)
    trail: List[AuditTrailEvent] = [
        {
            "event_type": "case_state_projection_built",
            "timestamp": timestamp,
            "source_ref": "agent.case_state",
            "details": _projection_details,
        },
        {
            "event_type": "readiness_snapshot",
            "timestamp": timestamp,
            "source_ref": "case_state.readiness",
            "details": {
                "ready_for_guidance": readiness.get("ready_for_guidance", False),
                "ready_for_qualification": readiness.get("ready_for_qualification", False),
                "missing_critical_inputs": list(readiness.get("missing_critical_inputs", [])),
                "missing_review_inputs": list(readiness.get("missing_review_inputs", [])),
            },
        },
    ]
    if qualification_results:
        review_flag_count = 0
        hard_stop_keys: List[str] = []
        result_statuses: Dict[str, str] = {}
        for key, entry in qualification_results.items():
            result_statuses[str(key)] = str(entry.get("status") or "unknown")
            details = entry.get("details") or {}
            review_flags = details.get("review_flags")
            if isinstance(review_flags, list):
                review_flag_count += len([item for item in review_flags if item])
            if details.get("hard_stop"):
                hard_stop_keys.append(str(key))
        trail.append(
            {
                "event_type": "qualification_snapshot",
                "timestamp": timestamp,
                "source_ref": "case_state.qualification_results",
                "details": {
                    "result_keys": list(qualification_results.keys()),
                    "result_statuses": result_statuses,
                    "review_flag_count": review_flag_count,
                    "hard_stop_keys": hard_stop_keys,
                },
            }
        )
    if qualified_action_gate:
        trail.append(
            {
                "event_type": "qualified_action_gate_snapshot",
                "timestamp": timestamp,
                "source_ref": "case_state.qualified_action_gate",
                "details": {
                    "allowed": qualified_action_gate.get("allowed"),
                    "block_reasons": list(qualified_action_gate.get("block_reasons", [])),
                },
            }
        )
    if qualified_action_status:
        trail.append(
            {
                "event_type": "qualified_action_status_snapshot",
                "timestamp": timestamp,
                "source_ref": "case_state.qualified_action_status",
                "details": {
                    "last_status": qualified_action_status.get("last_status"),
                    "executed": qualified_action_status.get("executed"),
                },
            }
        )
    if qualified_action_history:
        trail.append(
            {
                "event_type": "qualified_action_history_snapshot",
                "timestamp": timestamp,
                "source_ref": "case_state.qualified_action_history",
                "details": {
                    "history_count": len(qualified_action_history),
                    "latest_status": qualified_action_history[0].get("last_status"),
                },
            }
        )
    if cycle.get("provider_contract_fingerprint"):
        trail.append(
            {
                "event_type": "provider_contract_snapshot",
                "timestamp": timestamp,
                "source_ref": "material.provider_contract",
                "details": {
                    "provider_contract_revision": cycle.get("provider_contract_revision"),
                    "matched_promoted_registry_record_ids": list(
                        cycle.get("matched_promoted_registry_record_ids", [])
                    ),
                },
            }
        )
    if rwdr_state:
        trail.append(
            {
                "event_type": "rwdr_projection_snapshot",
                "timestamp": timestamp,
                "source_ref": "rwdr",
                "details": {
                    "has_input": bool(rwdr_state.get("input")),
                    "has_output": bool(rwdr_state.get("output")),
                },
            }
        )
    return trail


def _detect_active_domain(sealing_state: Dict[str, Any], rwdr_state: Dict[str, Any]) -> ActiveDomain:
    if rwdr_state.get("input") or rwdr_state.get("output") or (rwdr_state.get("flow") or {}).get("active"):
        return "rwdr_preselection"
    selection = sealing_state.get("selection") or {}
    governance = sealing_state.get("governance") or {}
    if selection or governance:
        return "material_static_seal_prequalification"
    return "unknown"


def _build_material_input_snapshot(
    sealing_state: Dict[str, Any],
    working_profile: Dict[str, Any],
) -> Dict[str, Any]:
    asserted = sealing_state.get("asserted") or {}
    normalized = sealing_state.get("normalized") or {}
    medium_profile = asserted.get("medium_profile") or {}
    machine_profile = asserted.get("machine_profile") or {}
    operating_conditions = asserted.get("operating_conditions") or {}
    identity_records = normalized.get("identity_records") or {}

    def _identity_value(field_name: str) -> Any:
        record = identity_records.get(field_name) or {}
        return record.get("normalized_value")

    snapshot = {
        "temperature_c": _normalize_snapshot_value(operating_conditions.get("temperature", working_profile.get("temperature")), "temperature"),
        "pressure_bar": _normalize_snapshot_value(operating_conditions.get("pressure", working_profile.get("pressure")), "pressure"),
        "medium": _normalize_snapshot_value(medium_profile.get("name", working_profile.get("medium")), "medium"),
        "material": _normalize_snapshot_value(machine_profile.get("material", working_profile.get("material")), "material"),
        "material_family": _normalize_snapshot_value(_identity_value("material_family"), "material_family"),
        "grade_name": _normalize_snapshot_value(_identity_value("grade_name"), "grade_name"),
        "manufacturer_name": _normalize_snapshot_value(_identity_value("manufacturer_name"), "manufacturer_name"),
    }
    return {key: value for key, value in snapshot.items() if value is not None}


def _build_material_provider_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    sealing_state = state.get("sealing_state") or {}
    selection = sealing_state.get("selection") or {}
    snapshot = build_material_provider_contract_snapshot(
        relevant_fact_cards=list(state.get("relevant_fact_cards") or []),
        seed_candidates=list(selection.get("candidates", [])),
    )
    return snapshot.model_dump(mode="python")


def _build_qualified_action_status(
    state: Dict[str, Any],
    *,
    qualified_action_gate: QualifiedActionGate,
) -> QualifiedActionStatus:
    """Blueprint Sections 02/08/12: persisted read-model for the last qualified action attempt."""

    previous_case_state = state.get("case_state") or {}
    previous_status = previous_case_state.get("qualified_action_status") or {}
    if not previous_status:
        return {
            "action": QUALIFIED_ACTION_DOWNLOAD_RFQ,
            "last_status": QUALIFIED_ACTION_STATUS_NONE,
            "allowed_at_execution_time": False,
            "executed": False,
            "block_reasons": [],
            "timestamp": "",
            "binding_level": str(qualified_action_gate.get("binding_level") or "ORIENTATION"),
            "runtime_path": "",
            "source_ref": "case_state.qualified_action_status",
            "action_payload_stub": None,
            "current_gate_allows_action": bool(qualified_action_gate.get("allowed")),
            "artifact_provenance": None,
        }

    return {
        "action": normalize_qualified_action_id(previous_status.get("action")),
        "last_status": normalize_qualified_action_lifecycle_status(previous_status.get("last_status")),
        "allowed_at_execution_time": bool(previous_status.get("allowed_at_execution_time")),
        "executed": bool(previous_status.get("executed")),
        "block_reasons": [str(item) for item in previous_status.get("block_reasons", [])],
        "timestamp": str(previous_status.get("timestamp") or ""),
        "binding_level": str(previous_status.get("binding_level") or qualified_action_gate.get("binding_level") or "ORIENTATION"),
        "runtime_path": str(previous_status.get("runtime_path") or ""),
        "source_ref": str(previous_status.get("source_ref") or "case_state.qualified_action_status"),
        "action_payload_stub": previous_status.get("action_payload_stub"),
        "current_gate_allows_action": bool(qualified_action_gate.get("allowed")),
        "artifact_provenance": _normalize_artifact_provenance(previous_status.get("artifact_provenance")),
    }


def _build_qualified_action_history(
    state: Dict[str, Any],
) -> List[QualifiedActionHistoryEntry]:
    previous_case_state = state.get("case_state") or {}
    previous_history = previous_case_state.get("qualified_action_history") or []
    return [_normalize_qualified_action_entry(item) for item in previous_history if isinstance(item, dict)]


def _normalize_qualified_action_entry(entry: Dict[str, Any]) -> QualifiedActionHistoryEntry:
    return {
        "action": normalize_qualified_action_id(entry.get("action")),
        "last_status": normalize_qualified_action_lifecycle_status(entry.get("last_status")),
        "allowed_at_execution_time": bool(entry.get("allowed_at_execution_time")),
        "executed": bool(entry.get("executed")),
        "block_reasons": [str(item) for item in entry.get("block_reasons", [])],
        "timestamp": str(entry.get("timestamp") or ""),
        "binding_level": str(entry.get("binding_level") or "ORIENTATION"),
        "runtime_path": str(entry.get("runtime_path") or ""),
        "source_ref": str(entry.get("source_ref") or "case_state.qualified_action_history"),
        "action_payload_stub": entry.get("action_payload_stub"),
        "current_gate_allows_action": bool(entry.get("current_gate_allows_action")),
        "artifact_provenance": _normalize_artifact_provenance(entry.get("artifact_provenance")),
    }


def _normalize_artifact_provenance(value: Any) -> Dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    if not any(value.get(key) for key in ("artifact_type", "artifact_version", "filename", "mime_type", "source_ref")):
        return None
    return {
        "artifact_type": str(value.get("artifact_type") or ""),
        "artifact_version": str(value.get("artifact_version") or ""),
        "filename": str(value.get("filename") or ""),
        "mime_type": str(value.get("mime_type") or ""),
        "source_ref": str(value.get("source_ref") or ""),
    }


def _build_qualified_action_gate(
    *,
    qualification_results: Dict[str, QualificationResultEntry],
    invalidation_state: InvalidationState,
) -> QualifiedActionGate:
    """Blueprint Sections 08/12: deterministic hard gate for qualified RFQ-style user actions."""

    block_reasons: List[str] = []
    material_core = qualification_results.get("material_core") or {}
    material_core_details = material_core.get("details") or {}
    selection_projection = qualification_results.get("material_selection_projection") or {}
    selection_details = selection_projection.get("details") or {}
    material_core_status = str(material_core.get("status") or "unknown")
    base_material_core_status = str(
        material_core_details.get("qualification_status") or material_core_status
    )

    if invalidation_state.get("requires_recompute"):
        block_reasons.append("requires_recompute")
    if material_core_status == "stale_requires_recompute" or selection_projection.get("status") == "stale_requires_recompute":
        block_reasons.append("stale_material_qualification")
    if base_material_core_status == "exploratory_candidate_source_only":
        block_reasons.append("exploratory_candidate_source_only")
    elif base_material_core_status != "neutral_rfq_basis_ready":
        block_reasons.append("material_core_not_rfq_ready")
    if not bool(material_core_details.get("has_promoted_candidate_source")):
        block_reasons.append("missing_promoted_candidate_source")
    if not bool(selection_details.get("has_promoted_candidate_source", material_core_details.get("has_promoted_candidate_source"))):
        block_reasons.append("provider_source_not_promoted")
    if bool(selection_details.get("output_blocked", True)):
        block_reasons.append("selection_output_blocked")

    allowed = len(block_reasons) == 0
    return {
        "action": QUALIFIED_ACTION_DOWNLOAD_RFQ,
        "allowed": allowed,
        "rfq_ready": allowed,
        "binding_level": "RFQ_BASIS" if allowed else "ORIENTATION",
        "source_type": "case_state.qualified_action_gate",
        "source_ref": "case_state._build_qualified_action_gate",
        "block_reasons": list(dict.fromkeys(block_reasons)),
        "summary": "qualified_action_enabled" if allowed else "qualified_action_blocked",
    }


def _material_input_fingerprint(snapshot: Dict[str, Any]) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _material_provider_fingerprint(snapshot: Dict[str, Any]) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _diff_material_snapshots(previous_snapshot: Dict[str, Any], current_snapshot: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    for key in sorted(set(previous_snapshot) | set(current_snapshot)):
        if previous_snapshot.get(key) != current_snapshot.get(key):
            reasons.append(f"{key}_changed")
    return reasons


def _diff_material_provider_snapshots(previous_snapshot: Dict[str, Any], current_snapshot: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    if previous_snapshot.get("matched_promoted_registry_record_ids", []) != current_snapshot.get("matched_promoted_registry_record_ids", []):
        reasons.append("matched_promoted_registry_record_ids_changed")
    if previous_snapshot.get("matched_promoted_candidate_ids", []) != current_snapshot.get("matched_promoted_candidate_ids", []):
        reasons.append("matched_promoted_candidate_ids_changed")
    previous_records = {
        str(record.get("registry_record_id")): record
        for record in previous_snapshot.get("registry_records", [])
        if record.get("registry_record_id")
    }
    current_records = {
        str(record.get("registry_record_id")): record
        for record in current_snapshot.get("registry_records", [])
        if record.get("registry_record_id")
    }
    for registry_record_id in sorted(previous_records.keys() - current_records.keys()):
        reasons.append(f"promoted_registry_record_missing:{registry_record_id}")
    for registry_record_id in sorted(current_records.keys() - previous_records.keys()):
        reasons.append(f"promoted_registry_record_added:{registry_record_id}")
    for registry_record_id in sorted(previous_records.keys() & current_records.keys()):
        previous_record = previous_records[registry_record_id]
        current_record = current_records[registry_record_id]
        if previous_record.get("promotion_state") != current_record.get("promotion_state"):
            reasons.append(f"promoted_registry_record_promotion_state_changed:{registry_record_id}")
        if previous_record != current_record:
            reasons.append(f"provider_record_payload_changed:{registry_record_id}")
    if previous_snapshot != current_snapshot:
        reasons.append("provider_contract_fingerprint_changed")
    return reasons


from app.agent.domain.normalization import normalize_material, normalize_medium, normalize_unit_value

def _normalize_snapshot_value(value: Any, key: Optional[str] = None) -> Any:
    if value is None:
        return None
    
    # 0B.3: Material and Medium normalization
    if key in ["material", "material_family", "material_normalized", "seal_material"]:
        return normalize_material(str(value))
    if key in ["medium", "medium_normalized", "medium_name"]:
        return normalize_medium(str(value))

    # 0B.3: Unit normalization
    if key:
        unit = _infer_unit(key)
        if unit and isinstance(value, (int, float)):
            norm_val, _ = normalize_unit_value(float(value), unit)
            value = norm_val

    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _put_raw_input(
    container: Dict[str, RawInputEntry],
    key: str,
    value: Any,
    unit: str | None,
    source_type: str,
    source_ref: str,
    confidence: float,
    confirmed: bool,
) -> None:
    if value is None or value == "" or key in container:
        return
    
    # 0B.3: Central normalization for units
    unit = unit or _infer_unit(key)
    if unit and isinstance(value, (int, float)):
        norm_val, _ = normalize_unit_value(float(value), unit)
        value = norm_val

    container[key] = {
        "value": value,
        "unit": unit,
        "source_type": source_type,
        "source_ref": source_ref,
        "confidence": confidence,
        "confirmed": confirmed,
    }


def _infer_unit(key: str) -> str | None:
    lowered = key.lower()
    if lowered.endswith("_mm"):
        return "mm"
    if lowered.endswith("_rpm"):
        return "rpm"
    if lowered.endswith("_bar"):
        return "bar"
    if lowered.endswith("_psi"):
        return "psi"
    if lowered.endswith("_c"):
        return "C"
    if lowered.endswith("_f"):
        return "F"
    
    if "diameter" in lowered or "width" in lowered:
        return "mm"
    if "speed" in lowered:
        return "rpm"
    if "pressure" in lowered:
        return "bar"
    if "temperature" in lowered:
        return "C"
    return None


def _model_to_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
