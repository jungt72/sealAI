from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, NotRequired, TypedDict

from app.agent.domain.medium_registry import classify_medium_value
from app.agent.domain.normalization import (
    MediumSpecialistInput,
    normalize_material,
    normalize_unit_value,
    run_medium_specialist,
)
from app.agent.domain.manufacturer_rfq import (
    ManufacturerCapabilityPackage,
    ManufacturerRfqAdmissibleRequestPackage,
    ManufacturerRfqScopePackage,
    ManufacturerRfqSpecialistInput,
    project_dispatch_intent_from_rfq_send_payload,
    project_rfq_payload_basis_from_specialist_result,
    run_manufacturer_rfq_specialist,
)
from app.agent.services.medium_context import normalize_medium_context_key, resolve_medium_context


PROJECTION_VERSION = "visible_case_narrative_v1"
CASE_STATE_BUILDER_VERSION = "case_state_builder_v1"
DETERMINISTIC_SERVICE_VERSION = "deterministic_stack_v1"
DETERMINISTIC_DATA_VERSION = "promoted_registry_v1"
QUALIFIED_ACTION_AUDIT_EVENT = "qualified_action"
QUALIFIED_ACTION_DOWNLOAD_RFQ = "download_rfq"
QUALIFIED_ACTION_STATUS_NONE = "none"
QUALIFIED_ACTION_STATUS_BLOCKED = "blocked"
QUALIFIED_ACTION_STATUS_EXECUTED = "executed"

QualifiedActionId = Literal["download_rfq"]
QualifiedActionLifecycleStatus = Literal["none", "blocked", "executed"]
QualifiedActionAuditEventType = Literal["qualified_action"]


class VersionProvenance(TypedDict, total=False):
    model_id: str | None
    model_version: str | None
    prompt_version: str
    prompt_hash: str
    visible_reply_prompt_version: str
    visible_reply_prompt_hash: str
    policy_version: str
    projection_version: str
    case_state_builder_version: str
    service_version: str
    rwdr_config_version: str | None
    data_version: str


class VisibleNarrativeItem(TypedDict, total=False):
    key: str
    label: str
    value: str
    detail: str | None
    severity: Literal["low", "medium", "high"]


class VisibleCaseNarrative(TypedDict, total=False):
    governed_summary: str
    technical_direction: list[VisibleNarrativeItem]
    validity_envelope: list[VisibleNarrativeItem]
    next_best_inputs: list[VisibleNarrativeItem]
    suggested_next_questions: list[VisibleNarrativeItem]
    failure_analysis: list[VisibleNarrativeItem]
    case_summary: list[VisibleNarrativeItem]
    qualification_status: list[VisibleNarrativeItem]
    coverage_scope: list[VisibleNarrativeItem]


class BoundaryContract(TypedDict, total=False):
    binding_level: str
    coverage_status: str | None
    boundary_flags: list[str]
    escalation_reason: str | None


class CaseMeta(TypedDict, total=False):
    case_id: str
    session_id: str
    analysis_cycle_id: str | None
    state_revision: int
    snapshot_parent_revision: int | None
    version: int
    phase: str
    runtime_path: str
    binding_level: str
    lifecycle_status: str
    version_provenance: VersionProvenance
    policy_narrative_snapshot: dict[str, Any]
    boundary_contract: BoundaryContract


class CaseState(TypedDict, total=False):
    case_meta: CaseMeta
    requirement_class: dict[str, Any] | None
    recipient_selection: dict[str, Any] | None
    observed_inputs: dict[str, Any]
    normalized_parameters: dict[str, Any]
    parameter_meta: dict[str, Any]
    derived_engineering_values: dict[str, Any]
    evidence_state: dict[str, Any]
    governance_state: dict[str, Any]
    matching_state: dict[str, Any]
    rfq_state: dict[str, Any]
    manufacturer_state: dict[str, Any]
    raw_inputs: dict[str, Any]
    normalization_identity_snapshot: dict[str, Any]
    derived_calculations: dict[str, Any]
    engineering_signals: dict[str, Any]
    qualification_results: dict[str, Any]
    result_contract: dict[str, Any]
    medium_capture: dict[str, Any]
    medium_classification: dict[str, Any]
    medium_context: dict[str, Any]
    candidate_clusters: list[dict[str, Any]]
    sealing_requirement_spec: dict[str, Any]
    qualified_action_gate: dict[str, Any]
    qualified_action_history: list[dict[str, Any]]
    readiness: dict[str, Any]
    invalidation_state: dict[str, Any]
    audit_trail: list[dict[str, Any]]


def build_default_candidate_clusters() -> list[dict[str, Any]]:
    return []


def build_default_result_contract(*, analysis_cycle_id: str | None = None, state_revision: int = 0) -> dict[str, Any]:
    return {
        "contract_type": "structured_recommendation_contract",
        "contract_version": "structured_recommendation_contract_v1",
        "analysis_cycle_id": analysis_cycle_id,
        "state_revision": state_revision,
        "binding_level": "ORIENTATION",
        "release_status": "inadmissible",
        "rfq_admissibility": "inadmissible",
        "specificity_level": "family_only",
        "contract_obsolete": False,
        "invalidation_requires_recompute": False,
        "invalidation_reasons": [],
        "required_disclaimers": [],
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
        "scope_of_validity": [],
        "assumptions_active": [],
        "blocking_unknowns": [],
        "manufacturer_validation_required": False,
        "review_required": False,
        "conflict_summary": [],
        "candidate_summary": {},
        "recommendation_identity": None,
        "requirement_class": None,
        "requirement_class_hint": None,
        "source_ref": "case_state.default_result_contract",
    }


def build_default_sealing_requirement_spec(*, analysis_cycle_id: str | None = None, state_revision: int = 0) -> dict[str, Any]:
    return {
        "contract_type": "sealing_requirement_spec",
        "contract_version": "sealing_requirement_spec_v1",
        "analysis_cycle_id": analysis_cycle_id,
        "state_revision": state_revision,
        "binding_level": "ORIENTATION",
        "runtime_path": "",
        "release_status": "inadmissible",
        "rfq_admissibility": "inadmissible",
        "specificity_level": "family_only",
        "contract_obsolete": False,
        "qualified_action": {
            "action": QUALIFIED_ACTION_DOWNLOAD_RFQ,
            "allowed": False,
            "rfq_ready": False,
            "binding_level": "ORIENTATION",
            "summary": "qualified_action_blocked",
            "block_reasons": [],
        },
        "candidate_clusters": [],
        "requirement_class": None,
        "source_ref": "case_state.default_sealing_requirement_spec",
    }


def normalize_qualified_action_id(action: Any) -> QualifiedActionId:
    return QUALIFIED_ACTION_DOWNLOAD_RFQ


def _build_recommendation_identity(
    *,
    candidate_projection: dict[str, Any],
    specificity_level: str,
) -> dict[str, Any] | None:
    candidate_id = candidate_projection.get("candidate_id")
    material_family = candidate_projection.get("material_family")
    if not candidate_id or not material_family:
        return None
    return {
        "candidate_id": candidate_id,
        "candidate_kind": candidate_projection.get("candidate_kind"),
        "material_family": material_family,
        "grade_name": candidate_projection.get("grade_name"),
        "manufacturer_name": candidate_projection.get("manufacturer_name"),
        "specificity_level": specificity_level,
    }


def _build_requirement_class_hint(
    recommendation_identity: dict[str, Any] | None,
) -> str | None:
    if not recommendation_identity:
        return None
    material_family = recommendation_identity.get("material_family")
    specificity_level = recommendation_identity.get("specificity_level")
    candidate_id = recommendation_identity.get("candidate_id")
    grade_name = recommendation_identity.get("grade_name")
    manufacturer_name = recommendation_identity.get("manufacturer_name")
    if not material_family or not specificity_level:
        return None
    if specificity_level == "family_only":
        return f"family::{material_family}"
    if specificity_level == "subfamily":
        if grade_name:
            return f"subfamily::{material_family}::{grade_name}"
        return f"subfamily::{candidate_id}"
    if specificity_level == "compound_required":
        if manufacturer_name:
            return f"compound::{candidate_id}"
        if grade_name:
            return f"compound::{material_family}::{grade_name}"
    return f"candidate::{candidate_id}"


def _derive_requirement_class_basis(
    *,
    requirement_class_hint: str | None,
    specificity_level: str | None,
) -> str | None:
    hint = str(requirement_class_hint or "").strip()
    if hint.startswith("family::"):
        return "family"
    if hint.startswith("subfamily::"):
        return "subfamily"
    if hint.startswith("compound::"):
        return "compound"
    if hint.startswith("candidate::"):
        return "candidate"
    if specificity_level == "family_only":
        return "family"
    if specificity_level == "subfamily":
        return "subfamily"
    if specificity_level == "compound_required":
        return "compound"
    if specificity_level == "product_family_required":
        return "candidate"
    return None


def _requirement_class_source(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def _build_requirement_class(
    *,
    persisted_requirement_class: dict[str, Any] | None,
    recommendation_identity: dict[str, Any] | None,
    requirement_class_hint: str | None,
    specificity_level: str | None,
) -> dict[str, Any] | None:
    persisted = dict(persisted_requirement_class or {})
    persisted_requirement_class_id = str(
        persisted.get("requirement_class_id")
        or persisted.get("class_id")
        or ""
    ).strip()
    requirement_class_id = persisted_requirement_class_id or str(requirement_class_hint or "").strip()
    if not requirement_class_id:
        return None

    identity = dict(recommendation_identity or {})
    material_family = identity.get("material_family") or persisted.get("material_family")
    candidate_id = identity.get("candidate_id") or persisted.get("candidate_id")
    candidate_kind = identity.get("candidate_kind") or persisted.get("candidate_kind")
    grade_name = identity.get("grade_name") or persisted.get("grade_name")
    manufacturer_name = identity.get("manufacturer_name") or persisted.get("manufacturer_name")
    resolved_specificity = (
        identity.get("specificity_level")
        or specificity_level
        or persisted.get("specificity_level")
    )

    requirement_class = {
        "object_type": "requirement_class",
        "object_version": "requirement_class_v1",
        "requirement_class_id": requirement_class_id,
        "derivation_basis": _derive_requirement_class_basis(
            requirement_class_hint=requirement_class_id,
            specificity_level=str(resolved_specificity or "").strip() or None,
        ),
        "specificity_level": resolved_specificity,
        "material_family": material_family,
        "manufacturer_specific": bool(manufacturer_name),
    }
    if candidate_id:
        requirement_class["candidate_id"] = candidate_id
    if candidate_kind:
        requirement_class["candidate_kind"] = candidate_kind
    if grade_name:
        requirement_class["grade_name"] = grade_name
    if manufacturer_name:
        requirement_class["manufacturer_name"] = manufacturer_name
    if persisted.get("description"):
        requirement_class["description"] = persisted.get("description")
    if persisted.get("seal_type"):
        requirement_class["seal_type"] = persisted.get("seal_type")
    return requirement_class


def _build_conflict_summary(conflicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for conflict in conflicts:
        summary.append(
            {
                "type": conflict.get("type"),
                "severity": conflict.get("severity"),
                "message": conflict.get("message"),
                "field": conflict.get("field"),
            }
        )
    return summary


def _build_match_candidates(
    *,
    candidates: list[dict[str, Any]],
    candidate_projection: dict[str, Any],
    viable_candidate_ids: list[str],
    blocked_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    match_candidates: list[dict[str, Any]] = []
    blocked_by_id = {
        str(candidate.get("candidate_id")): dict(candidate)
        for candidate in blocked_candidates
        if candidate.get("candidate_id")
    }
    if candidates:
        for candidate in candidates:
            candidate_id = candidate.get("candidate_id")
            viability_status = "viable" if candidate_id in viable_candidate_ids else "blocked"
            blocked = blocked_by_id.get(str(candidate_id))
            match_candidates.append(
                {
                    "candidate_id": candidate_id,
                    "candidate_kind": candidate.get("candidate_kind"),
                    "material_family": candidate.get("material_family"),
                    "grade_name": candidate.get("grade_name"),
                    "manufacturer_name": candidate.get("manufacturer_name"),
                    "viability_status": viability_status,
                    "block_reason": blocked.get("reason") if blocked else candidate.get("block_reason"),
                    "evidence_refs": list(candidate.get("evidence_refs") or []),
                }
            )
        return match_candidates
    if candidate_projection:
        candidate_id = candidate_projection.get("candidate_id")
        match_candidates.append(
            {
                "candidate_id": candidate_id,
                "candidate_kind": candidate_projection.get("candidate_kind"),
                "material_family": candidate_projection.get("material_family"),
                "grade_name": candidate_projection.get("grade_name"),
                "manufacturer_name": candidate_projection.get("manufacturer_name"),
                "viability_status": "viable" if candidate_id in viable_candidate_ids else "projected",
                "block_reason": None,
                "evidence_refs": list(candidate_projection.get("evidence_refs") or []),
            }
        )
    return match_candidates


def _build_matching_blocking_reasons(
    *,
    contract_obsolete: bool,
    review_required: bool,
    output_blocked: bool,
    blocking_unknowns: list[Any],
    viable_candidate_ids: list[str],
    candidate_clusters: list[dict[str, Any]],
    recommendation_identity: dict[str, Any] | None,
) -> list[str]:
    reasons: list[str] = []
    if contract_obsolete:
        reasons.append("contract_obsolete")
    if review_required:
        reasons.append("review_required")
    if output_blocked:
        reasons.append("output_blocked")
    if blocking_unknowns:
        reasons.append("unknowns_release_blocking")
    if not viable_candidate_ids and not candidate_clusters and recommendation_identity is None:
        reasons.append("no_matching_basis")
    return reasons


def _derive_matchability_status(
    *,
    contract_obsolete: bool,
    review_required: bool,
    release_status: str,
    has_matching_basis: bool,
    blocking_reasons: list[str],
) -> str:
    if contract_obsolete:
        return "blocked_contract_obsolete"
    if review_required:
        return "blocked_review_required"
    if not has_matching_basis:
        return "not_ready_no_matching_basis"
    if release_status in {"manufacturer_validation_required", "rfq_ready", "approved"} and not blocking_reasons:
        return "ready_for_matching"
    if release_status == "precheck_only":
        return "not_ready_precheck"
    return "not_ready_governance_blocked"


def _build_rfq_blocking_reasons(
    *,
    rfq_admissibility: str,
    contract_obsolete: bool,
    review_required: bool,
    critical_review_status: str,
    critical_review_passed: bool,
    critical_review_blocking_findings: list[str],
    manufacturer_validation_required: bool,
    unknowns_release_blocking: list[Any],
    handover_ready: bool,
    recommendation_identity: dict[str, Any] | None,
    match_candidates: list[dict[str, Any]],
    qualified_action_gate: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if contract_obsolete:
        reasons.append("contract_obsolete")
    if review_required:
        reasons.append("review_required")
    if critical_review_status == "not_run":
        reasons.append("critical_review_missing")
    elif not critical_review_passed:
        reasons.append("critical_review_failed")
    if critical_review_blocking_findings:
        reasons.append("critical_review_blocking_findings")
    if manufacturer_validation_required:
        reasons.append("manufacturer_validation_required")
    if rfq_admissibility == "provisional":
        reasons.append("rfq_admissibility_provisional")
    elif rfq_admissibility != "ready":
        reasons.append("rfq_admissibility_inadmissible")
    if unknowns_release_blocking:
        reasons.append("unknowns_release_blocking")
    if not recommendation_identity:
        reasons.append("no_recommendation_identity")
    if not match_candidates:
        reasons.append("no_match_candidates")
    if not handover_ready and not bool(qualified_action_gate.get("allowed", False)):
        reasons.append("handover_not_ready")
    return reasons


def _build_rfq_open_points(
    *,
    review_required: bool,
    manufacturer_validation_required: bool,
    unknowns_manufacturer_validation: list[Any],
    unknowns_release_blocking: list[Any],
    soft_findings: list[str],
    required_corrections: list[str],
) -> list[str]:
    open_points: list[str] = []
    if manufacturer_validation_required:
        open_points.append("manufacturer_validation_required")
    if review_required:
        open_points.append("review_required")
    open_points.extend(str(item) for item in unknowns_manufacturer_validation if item is not None)
    open_points.extend(str(item) for item in unknowns_release_blocking if item is not None)
    open_points.extend(str(item) for item in soft_findings if item is not None)
    open_points.extend(str(item) for item in required_corrections if item is not None)
    return list(dict.fromkeys(open_points))


def _build_manufacturer_refs(
    *,
    recommendation_identity: dict[str, Any] | None,
    match_candidates: list[dict[str, Any]],
    qualified_materials: list[dict[str, Any]],
    handover_ready: bool,
) -> list[dict[str, Any]]:
    refs_by_name: dict[str, dict[str, Any]] = {}

    def _upsert(entry: dict[str, Any], *, source: str) -> None:
        manufacturer_name = str(entry.get("manufacturer_name") or "").strip()
        if not manufacturer_name:
            return
        ref = refs_by_name.setdefault(
            manufacturer_name,
            {
                "manufacturer_name": manufacturer_name,
                "candidate_ids": [],
                "material_families": [],
                "grade_names": [],
                "candidate_kinds": [],
                "capability_hints": [],
                "source_refs": [],
                "qualified_for_rfq": False,
            },
        )
        for field, key in (
            ("candidate_id", "candidate_ids"),
            ("material_family", "material_families"),
            ("grade_name", "grade_names"),
            ("candidate_kind", "candidate_kinds"),
        ):
            value = entry.get(field)
            if value and value not in ref[key]:
                ref[key].append(value)
        if source not in ref["source_refs"]:
            ref["source_refs"].append(source)
        if entry.get("candidate_kind") == "manufacturer_grade" and "manufacturer_grade_candidate" not in ref["capability_hints"]:
            ref["capability_hints"].append("manufacturer_grade_candidate")
        if source == "rfq_qualified_material" and "rfq_qualified_material" not in ref["capability_hints"]:
            ref["capability_hints"].append("rfq_qualified_material")
        if handover_ready:
            ref["qualified_for_rfq"] = True

    if recommendation_identity:
        _upsert(dict(recommendation_identity), source="recommendation_identity")
    for candidate in match_candidates:
        _upsert(dict(candidate), source="match_candidate")
    for material in qualified_materials:
        _upsert(dict(material), source="rfq_qualified_material")

    return list(refs_by_name.values())


def _build_manufacturer_capabilities(
    *,
    manufacturer_refs: list[dict[str, Any]],
    requirement_class: dict[str, Any] | None,
    match_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    capabilities: list[dict[str, Any]] = []
    requirement_class_id = (requirement_class or {}).get("requirement_class_id")

    evidence_refs_by_manufacturer: dict[str, list[str]] = {}
    for candidate in match_candidates:
        manufacturer_name = str(candidate.get("manufacturer_name") or "").strip()
        if not manufacturer_name:
            continue
        refs = evidence_refs_by_manufacturer.setdefault(manufacturer_name, [])
        for evidence_ref in list(candidate.get("evidence_refs") or []):
            if evidence_ref and evidence_ref not in refs:
                refs.append(evidence_ref)

    for ref in manufacturer_refs:
        manufacturer_name = str(ref.get("manufacturer_name") or "").strip()
        if not manufacturer_name:
            continue
        capability = {
            "object_type": "manufacturer_capability",
            "object_version": "manufacturer_capability_v1",
            "manufacturer_name": manufacturer_name,
            "capability_sources": list(ref.get("source_refs") or []),
            "capability_hints": list(ref.get("capability_hints") or []),
            "material_families": list(ref.get("material_families") or []),
            "grade_names": list(ref.get("grade_names") or []),
            "candidate_kinds": list(ref.get("candidate_kinds") or []),
            "candidate_ids": list(ref.get("candidate_ids") or []),
            "rfq_qualified": bool(ref.get("qualified_for_rfq", False)),
        }
        if requirement_class_id:
            capability["requirement_class_ids"] = [requirement_class_id]
        evidence_refs = evidence_refs_by_manufacturer.get(manufacturer_name) or []
        if evidence_refs:
            capability["evidence_refs"] = list(evidence_refs)
        capabilities.append(capability)

    return capabilities


def build_dispatch_intent(rfq_dispatch: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(rfq_dispatch, dict):
        return None
    dispatch_blockers = list(dict.fromkeys(str(item) for item in rfq_dispatch.get("dispatch_blockers") or []))
    recipient_refs = [
        dict(ref) for ref in list(rfq_dispatch.get("recipient_refs") or []) if isinstance(ref, dict)
    ]
    return {
        "object_type": "dispatch_intent",
        "object_version": "dispatch_intent_v1",
        "dispatch_ready": bool(rfq_dispatch.get("dispatch_ready")),
        "dispatch_status": rfq_dispatch.get("dispatch_status"),
        "dispatch_blockers": dispatch_blockers,
        "recipient_refs": recipient_refs,
        "selected_manufacturer_ref": dict(rfq_dispatch.get("selected_manufacturer_ref") or {}) if isinstance(rfq_dispatch.get("selected_manufacturer_ref"), dict) else None,
        "recipient_selection": dict(rfq_dispatch.get("recipient_selection") or {}) if isinstance(rfq_dispatch.get("recipient_selection"), dict) else None,
        "requirement_class": dict(rfq_dispatch.get("requirement_class") or {}) if isinstance(rfq_dispatch.get("requirement_class"), dict) else None,
        "recommendation_identity": dict(rfq_dispatch.get("recommendation_identity") or {}) if isinstance(rfq_dispatch.get("recommendation_identity"), dict) else None,
        "rfq_object_basis": dict(rfq_dispatch.get("rfq_object_basis") or {}) if isinstance(rfq_dispatch.get("rfq_object_basis"), dict) else None,
        "source": "canonical_rfq_dispatch",
    }


def _build_recipient_selection(
    *,
    manufacturer_refs: list[dict[str, Any]],
    manufacturer_capabilities: list[dict[str, Any]],
    matching_outcome: dict[str, Any] | None,
    recommendation_identity: dict[str, Any] | None,
    requirement_class: dict[str, Any] | None,
) -> dict[str, Any]:
    selected_manufacturer_ref = None
    if isinstance(matching_outcome, dict):
        selected = matching_outcome.get("selected_manufacturer_ref")
        if isinstance(selected, dict) and selected:
            selected_manufacturer_ref = dict(selected)

    candidate_recipient_refs = [dict(ref) for ref in manufacturer_refs if isinstance(ref, dict) and ref]
    requirement_class_id = str((requirement_class or {}).get("requirement_class_id") or "").strip()
    recommendation_candidate_id = str((recommendation_identity or {}).get("candidate_id") or "").strip()
    capability_by_manufacturer: dict[str, dict[str, Any]] = {}
    capability_qualified_names: set[str] = set()
    for capability in manufacturer_capabilities:
        if not isinstance(capability, dict):
            continue
        manufacturer_name = str(capability.get("manufacturer_name") or "").strip()
        if not manufacturer_name:
            continue
        capability_by_manufacturer[manufacturer_name] = dict(capability)
        requirement_class_ids = {
            str(item) for item in list(capability.get("requirement_class_ids") or []) if item
        }
        candidate_ids = {
            str(item) for item in list(capability.get("candidate_ids") or []) if item
        }
        rfq_qualified = bool(capability.get("rfq_qualified", False))
        if requirement_class_id and requirement_class_id not in requirement_class_ids:
            continue
        if recommendation_candidate_id:
            if recommendation_candidate_id in candidate_ids:
                capability_qualified_names.add(manufacturer_name)
                continue
            if rfq_qualified:
                capability_qualified_names.add(manufacturer_name)
                continue
        elif requirement_class_id:
            capability_qualified_names.add(manufacturer_name)

    if capability_qualified_names:
        candidate_recipient_refs = [
            ref
            for ref in candidate_recipient_refs
            if str(ref.get("manufacturer_name") or "").strip() in capability_qualified_names
        ]

    selected_recipient_refs: list[dict[str, Any]] = []
    non_selected_recipient_refs: list[dict[str, Any]] = []
    selected_name = str((selected_manufacturer_ref or {}).get("manufacturer_name") or "").strip()
    selected_candidate_ids = set(str(item) for item in list((selected_manufacturer_ref or {}).get("candidate_ids") or []) if item)

    for ref in candidate_recipient_refs:
        ref_name = str(ref.get("manufacturer_name") or "").strip()
        ref_candidate_ids = set(str(item) for item in list(ref.get("candidate_ids") or []) if item)
        is_selected = False
        if selected_name and ref_name == selected_name:
            is_selected = True
        elif selected_candidate_ids and ref_candidate_ids.intersection(selected_candidate_ids):
            is_selected = True
        if is_selected:
            selected_recipient_refs.append(dict(ref))
        else:
            non_selected_recipient_refs.append(dict(ref))

    selection_ready = bool(selected_recipient_refs)
    if selection_ready:
        selection_status = "selected_recipient"
    elif candidate_recipient_refs:
        selection_status = "candidate_pool_only"
    else:
        selection_status = "no_recipient_candidates"

    return {
        "object_type": "recipient_selection",
        "object_version": "recipient_selection_v1",
        "selection_status": selection_status,
        "recipient_selection_ready": selection_ready,
        "selected_recipient_refs": selected_recipient_refs,
        "candidate_recipient_refs": candidate_recipient_refs,
        "non_selected_recipient_refs": non_selected_recipient_refs,
        "selection_basis_summary": {
            "candidate_count": len(candidate_recipient_refs),
            "selected_count": len(selected_recipient_refs),
            "has_selected_manufacturer_ref": bool(selected_manufacturer_ref),
            "derived_from_matching_outcome": bool(selected_manufacturer_ref),
            "capability_qualified_candidate_count": len(capability_qualified_names),
            "capability_requirement_class_id": requirement_class_id or None,
            "capability_recommendation_candidate_id": recommendation_candidate_id or None,
        },
        "selected_manufacturer_ref": selected_manufacturer_ref,
        "recommendation_identity": recommendation_identity,
        "requirement_class": dict(requirement_class) if requirement_class else None,
    }


def _infer_unit(key: str) -> str | None:
    lowered = key.lower()
    if "pressure" in lowered:
        return "bar"
    if "temperature_f" in lowered:
        return "F"
    if "temperature" in lowered:
        return "C"
    if "diameter" in lowered:
        return "mm"
    if "speed" in lowered:
        return "rpm"
    return None


def _normalize_snapshot_value(value: Any, key: str) -> Any:
    lowered = key.lower()
    if lowered == "material":
        normalized = normalize_material(value)
        return value if normalized in {"FKM", "FFKM"} and str(value).strip().lower() in {"viton", "kalrez"} else normalized
    if lowered == "medium":
        result = run_medium_specialist(
            MediumSpecialistInput(candidate_media_tokens=(str(value or ""),))
        )
        return result.canonical_medium or value
    if lowered.endswith("_f"):
        return normalize_unit_value(float(value), "F")[0]
    if lowered.endswith("_psi"):
        return normalize_unit_value(float(value), "psi")[0]
    return value


def _resolve_selected_partner_id(
    *,
    existing_recipient_selection: dict[str, Any] | None,
    recipient_selection: dict[str, Any] | None,
    selection_layer: dict[str, Any] | None,
) -> str | None:
    for source in (existing_recipient_selection or {}, recipient_selection or {}):
        selected_partner_id = source.get("selected_partner_id")
        if isinstance(selected_partner_id, str) and selected_partner_id.strip():
            return selected_partner_id.strip()

        selected_manufacturer_ref = source.get("selected_manufacturer_ref")
        if isinstance(selected_manufacturer_ref, dict):
            manufacturer_name = str(selected_manufacturer_ref.get("manufacturer_name") or "").strip()
            if manufacturer_name:
                return manufacturer_name

        selected_recipient_refs = source.get("selected_recipient_refs") or []
        if selected_recipient_refs and isinstance(selected_recipient_refs[0], dict):
            manufacturer_name = str(selected_recipient_refs[0].get("manufacturer_name") or "").strip()
            if manufacturer_name:
                return manufacturer_name

    selected_partner_id = (selection_layer or {}).get("selected_partner_id")
    if isinstance(selected_partner_id, str) and selected_partner_id.strip():
        return selected_partner_id.strip()
    return None


def _current_medium_label(state: dict[str, Any], existing_case_state: dict[str, Any]) -> str | None:
    state_medium_context = dict(state.get("medium_context") or {})
    medium_context_label = str(state_medium_context.get("medium_label") or "").strip()
    if medium_context_label:
        return medium_context_label

    sealing_state = dict(state.get("sealing_state") or {})
    asserted_conditions = dict((sealing_state.get("asserted") or {}).get("operating_conditions") or {})
    normalized_parameters = dict((sealing_state.get("normalized") or {}).get("normalized_parameters") or {})
    working_profile = dict(state.get("working_profile") or {})
    existing_normalized = dict(existing_case_state.get("normalized_parameters") or {})
    for value in (
        working_profile.get("medium"),
        asserted_conditions.get("medium"),
        normalized_parameters.get("medium"),
        existing_normalized.get("medium"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return None


def _resolve_medium_context(
    *,
    state: dict[str, Any],
    existing_case_state: dict[str, Any],
) -> dict[str, Any]:
    medium_label = _current_medium_label(state, existing_case_state)
    medium_key = normalize_medium_context_key(medium_label)
    if not medium_key:
        return {}

    existing_context = dict(existing_case_state.get("medium_context") or {})
    if (
        existing_context.get("status") == "available"
        and existing_context.get("source_medium_key") == medium_key
    ):
        return existing_context

    return resolve_medium_context(medium_label, previous=existing_context).model_dump()


def build_case_state(
    state: dict[str, Any],
    *,
    session_id: str,
    runtime_path: str,
    binding_level: str,
    version_provenance: VersionProvenance | None = None,
    policy_context: dict[str, Any] | None = None,
) -> CaseState:
    existing_case_state = dict(state.get("case_state") or {})
    existing_case_meta = dict(existing_case_state.get("case_meta") or {})
    sealing_state = dict(state.get("sealing_state") or {})
    observed_layer = dict(sealing_state.get("observed") or {})
    normalized_layer = dict(sealing_state.get("normalized") or {})
    governance_layer = dict(sealing_state.get("governance") or {})
    selection_layer = dict(sealing_state.get("selection") or {})
    handover_layer = dict(sealing_state.get("handover") or {})
    review_layer = dict(sealing_state.get("review") or {})
    existing_rfq_state = dict(existing_case_state.get("rfq_state") or {})
    recommendation_artifact = dict(selection_layer.get("recommendation_artifact") or {})
    candidate_projection = dict(recommendation_artifact.get("candidate_projection") or {})
    working_profile = dict(state.get("working_profile") or {})
    medium_capture_bucket = dict(state.get("medium_capture") or existing_case_state.get("medium_capture") or {})
    medium_classification_bucket = dict(state.get("medium_classification") or existing_case_state.get("medium_classification") or {})
    if not medium_classification_bucket:
        inferred_medium = _current_medium_label(state, existing_case_state)
        if inferred_medium:
            decision = classify_medium_value(inferred_medium)
            medium_classification_bucket = {
                "canonical_label": decision.canonical_label,
                "family": decision.family,
                "confidence": decision.confidence,
                "status": decision.status,
                "normalization_source": decision.normalization_source,
                "mapping_confidence": decision.mapping_confidence,
                "matched_alias": decision.matched_alias,
                "source_registry_key": decision.registry_key,
                "followup_question": decision.followup_question,
            }
    medium_context_bucket = _resolve_medium_context(state=state, existing_case_state=existing_case_state)
    relevant_fact_cards = list(state.get("relevant_fact_cards") or [])
    cycle = ((state.get("sealing_state") or {}).get("cycle") or {})
    state_revision = int(existing_case_meta.get("state_revision", cycle.get("state_revision", 0)) or 0)
    required_disclaimers = list(
        ((existing_case_state.get("governance_state") or {}).get("required_disclaimers") or [])
        or governance_layer.get("scope_of_validity")
        or []
    )
    case_meta: CaseMeta = {
        "case_id": session_id,
        "session_id": session_id,
        "analysis_cycle_id": existing_case_meta.get("analysis_cycle_id", cycle.get("analysis_cycle_id")),
        "state_revision": state_revision,
        "snapshot_parent_revision": existing_case_meta.get("snapshot_parent_revision", cycle.get("snapshot_parent_revision")),
        "version": int(existing_case_meta.get("version", state_revision) or state_revision),
        "phase": str(existing_case_meta.get("phase") or cycle.get("phase") or ""),
        "runtime_path": runtime_path,
        "binding_level": str(existing_case_meta.get("binding_level") or binding_level),
    }
    if version_provenance is not None:
        vp = dict(version_provenance)
        if vp.get("model_id") is not None and vp.get("model_version") is None:
            vp["model_version"] = vp["model_id"]
        case_meta["version_provenance"] = vp  # type: ignore[assignment]
    if policy_context is not None:
        case_meta["policy_narrative_snapshot"] = dict(policy_context)
        case_meta["boundary_contract"] = {
            "binding_level": binding_level,
            "coverage_status": policy_context.get("coverage_status"),
            "boundary_flags": list(policy_context.get("boundary_flags", [])),
            "escalation_reason": policy_context.get("escalation_reason"),
        }
    audit_event = {
        "event_type": "case_state_projection_built",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_ref": "case_state.build_case_state",
        "details": {},
    }
    if version_provenance is not None:
        audit_event["details"]["version_provenance"] = dict(case_meta["version_provenance"])
    observed_inputs_bucket = {
        "records": list(observed_layer.get("observed_inputs") or []),
        "raw_parameters": dict(observed_layer.get("raw_parameters") or {}),
    }
    normalized_parameters_bucket = dict(normalized_layer.get("normalized_parameters") or {})
    parameter_meta_bucket = dict(
        existing_case_state.get("parameter_meta")
        or normalized_layer.get("identity_records")
        or {}
    )
    derived_engineering_values_bucket = dict(
        existing_case_state.get("derived_engineering_values")
        or existing_case_state.get("derived_calculations")
        or {}
    )
    evidence_state_bucket = dict(existing_case_state.get("evidence_state") or {})
    evidence_state_bucket.setdefault("evidence_available", bool(relevant_fact_cards))
    evidence_state_bucket.setdefault("evidence_ref_count", len(relevant_fact_cards))
    evidence_state_bucket.setdefault(
        "evidence_refs",
        [
            str(card.get("evidence_id") or card.get("id"))
            for card in relevant_fact_cards
            if card.get("evidence_id") or card.get("id")
        ],
    )
    evidence_state_bucket.setdefault(
        "retrieval_refs",
        [
            {
                "id": card.get("evidence_id") or card.get("id"),
                "source_ref": card.get("source_ref"),
                "topic": card.get("topic"),
            }
            for card in relevant_fact_cards
        ],
    )
    if state.get("run_meta"):
        evidence_state_bucket.setdefault("rag_path", (state.get("run_meta") or {}).get("rag_path"))
    governance_state_bucket = dict(existing_case_state.get("governance_state") or {})
    critical_review_status = str(
        governance_state_bucket.get("critical_review_status")
        or existing_rfq_state.get("critical_review_status")
        or review_layer.get("critical_review_status")
        or "not_run"
    )
    critical_review_passed = bool(
        governance_state_bucket.get(
            "critical_review_passed",
            existing_rfq_state.get("critical_review_passed", review_layer.get("critical_review_passed", False)),
        )
    )
    critical_review_blocking_findings = list(
        governance_state_bucket.get("blocking_findings")
        or existing_rfq_state.get("blocking_findings")
        or review_layer.get("blocking_findings")
        or []
    )
    critical_review_soft_findings = list(
        governance_state_bucket.get("soft_findings")
        or existing_rfq_state.get("soft_findings")
        or review_layer.get("soft_findings")
        or []
    )
    critical_review_required_corrections = list(
        governance_state_bucket.get("required_corrections")
        or existing_rfq_state.get("required_corrections")
        or review_layer.get("required_corrections")
        or []
    )
    governance_state_bucket.update(
        {
            "release_status": governance_state_bucket.get("release_status", governance_layer.get("release_status", "inadmissible")),
            "rfq_admissibility": governance_state_bucket.get("rfq_admissibility", governance_layer.get("rfq_admissibility", "inadmissible")),
            "specificity_level": governance_state_bucket.get("specificity_level", governance_layer.get("specificity_level", "family_only")),
            "scope_of_validity": list(governance_state_bucket.get("scope_of_validity") or governance_layer.get("scope_of_validity") or []),
            "assumptions_active": list(governance_state_bucket.get("assumptions_active") or governance_layer.get("assumptions_active") or []),
            "unknowns_release_blocking": list(governance_state_bucket.get("unknowns_release_blocking") or governance_layer.get("unknowns_release_blocking") or []),
            "unknowns_manufacturer_validation": list(governance_state_bucket.get("unknowns_manufacturer_validation") or governance_layer.get("unknowns_manufacturer_validation") or []),
            "conflicts": list(governance_state_bucket.get("conflicts") or governance_layer.get("conflicts") or []),
            "review_state": governance_state_bucket.get("review_state", review_layer.get("review_state")),
            "review_required": bool(governance_state_bucket.get("review_required", review_layer.get("review_required", False))),
            "critical_review_status": critical_review_status,
            "critical_review_passed": critical_review_passed and not critical_review_blocking_findings,
            "blocking_findings": critical_review_blocking_findings,
            "soft_findings": critical_review_soft_findings,
            "required_corrections": critical_review_required_corrections,
            "required_disclaimers": required_disclaimers,
            "binding_level": str(governance_state_bucket.get("binding_level") or binding_level),
        }
    )
    matching_state_bucket = dict(existing_case_state.get("matching_state") or {})
    candidate_clusters = list(
        existing_case_state.get("candidate_clusters")
        or selection_layer.get("candidate_clusters")
        or []
    )
    viable_candidate_ids = list(selection_layer.get("viable_candidate_ids") or [])
    blocked_candidates = list(selection_layer.get("blocked_candidates") or [])
    matching_state_bucket.update(
        {
            "selection_status": selection_layer.get("selection_status", "not_started"),
            "winner_candidate_id": selection_layer.get("winner_candidate_id"),
            "viable_candidate_ids": viable_candidate_ids,
            "blocked_candidates": blocked_candidates,
            "candidate_clusters": candidate_clusters,
            "output_blocked": bool(selection_layer.get("output_blocked", True)),
            "recommendation_artifact": recommendation_artifact or None,
        }
    )
    matching_outcome = (
        matching_state_bucket.get("matching_outcome")
        or existing_case_state.get("matching_outcome")
        or sealing_state.get("matching_outcome")
    )
    rfq_state_bucket = dict(existing_case_state.get("rfq_state") or {})
    critical_review_gate_blocker = None
    if critical_review_status == "not_run":
        critical_review_gate_blocker = "critical_review_missing"
    elif not governance_state_bucket.get("critical_review_passed", False):
        critical_review_gate_blocker = "critical_review_failed"
    rfq_handover_ready = (
        bool(rfq_state_bucket.get("handover_ready", handover_layer.get("is_handover_ready", False)))
        and governance_state_bucket["rfq_admissibility"] == "ready"
        and bool(governance_state_bucket.get("critical_review_passed", False))
        and not critical_review_blocking_findings
    )
    if governance_state_bucket["rfq_admissibility"] == "ready":
        default_rfq_status = "ready" if rfq_handover_ready else (
            "critical_review_pending" if critical_review_status == "not_run" else "blocked_critical_review"
        )
    else:
        default_rfq_status = governance_state_bucket["rfq_admissibility"]
    rfq_state_bucket.update(
        {
            "rfq_admissibility": rfq_state_bucket.get("rfq_admissibility", governance_layer.get("rfq_admissibility", "inadmissible")),
            "rfq_ready": rfq_handover_ready,
            "status": default_rfq_status,
            "critical_review_status": critical_review_status,
            "critical_review_passed": bool(governance_state_bucket.get("critical_review_passed", False)),
            "blocking_findings": critical_review_blocking_findings,
            "soft_findings": critical_review_soft_findings,
            "required_corrections": critical_review_required_corrections,
            "handover_ready": rfq_handover_ready,
            "handover_status": rfq_state_bucket.get("handover_status", handover_layer.get("handover_status")),
            "handover_payload_present": bool(rfq_state_bucket.get("handover_payload_present", bool(handover_layer.get("handover_payload")))),
            "rfq_html_report_present": bool(
                rfq_state_bucket.get(
                    "rfq_html_report_present",
                    bool(handover_layer.get("rfq_html_report"))
                    or bool(handover_layer.get("rfq_html_report_present", False)),
                )
            ),
            "rfq_confirmed": bool(rfq_state_bucket.get("rfq_confirmed", handover_layer.get("rfq_confirmed", False))),
            "rfq_handover_initiated": bool(
                rfq_state_bucket.get("rfq_handover_initiated", handover_layer.get("handover_completed", False))
            ),
            "qualified_action_gate": dict(existing_case_state.get("qualified_action_gate") or {}),
        }
    )
    result_contract = dict(
        existing_case_state.get("result_contract")
        or build_default_result_contract(
            analysis_cycle_id=cycle.get("analysis_cycle_id"),
            state_revision=state_revision,
        )
    )
    persisted_recommendation_identity = dict(
        result_contract.get("recommendation_identity")
        or matching_state_bucket.get("recommendation_identity")
        or {}
    )
    recommendation_identity = persisted_recommendation_identity or _build_recommendation_identity(
        candidate_projection=candidate_projection,
        specificity_level=governance_state_bucket["specificity_level"],
    )
    requirement_class_hint = (
        result_contract.get("requirement_class_hint")
        or matching_state_bucket.get("requirement_class_hint")
        or _build_requirement_class_hint(recommendation_identity)
    )
    persisted_requirement_class = dict(
        existing_case_state.get("requirement_class")
        or _requirement_class_source(governance_layer.get("requirement_class"))
        or result_contract.get("requirement_class")
        or matching_state_bucket.get("requirement_class")
        or rfq_state_bucket.get("requirement_class")
        or (existing_case_state.get("manufacturer_state") or {}).get("requirement_class")
        or (existing_case_state.get("sealing_requirement_spec") or {}).get("requirement_class")
        or {}
    )
    requirement_class = _build_requirement_class(
        persisted_requirement_class=persisted_requirement_class,
        recommendation_identity=recommendation_identity,
        requirement_class_hint=requirement_class_hint,
        specificity_level=governance_state_bucket["specificity_level"],
    )
    match_candidates = _build_match_candidates(
        candidates=list(selection_layer.get("candidates") or []),
        candidate_projection=candidate_projection,
        viable_candidate_ids=viable_candidate_ids,
        blocked_candidates=blocked_candidates,
    )
    candidate_summary = {
        "selection_status": matching_state_bucket.get("selection_status"),
        "winner_candidate_id": matching_state_bucket.get("winner_candidate_id"),
        "viable_candidate_ids": list(matching_state_bucket.get("viable_candidate_ids") or []),
        "blocked_candidates": list(matching_state_bucket.get("blocked_candidates") or []),
        "candidate_projection": candidate_projection or None,
    }
    blocking_reasons = _build_matching_blocking_reasons(
        contract_obsolete=bool(cycle.get("contract_obsolete", False)),
        review_required=bool(governance_state_bucket.get("review_required", False)),
        output_blocked=bool(matching_state_bucket.get("output_blocked", True)),
        blocking_unknowns=list(governance_state_bucket.get("unknowns_release_blocking") or []),
        viable_candidate_ids=viable_candidate_ids,
        candidate_clusters=candidate_clusters,
        recommendation_identity=recommendation_identity,
    )
    has_matching_basis = bool(recommendation_identity or viable_candidate_ids or candidate_clusters or match_candidates)
    matchability_status = _derive_matchability_status(
        contract_obsolete=bool(cycle.get("contract_obsolete", False)),
        review_required=bool(governance_state_bucket.get("review_required", False)),
        release_status=governance_state_bucket["release_status"],
        has_matching_basis=has_matching_basis,
        blocking_reasons=blocking_reasons,
    )
    matching_state_bucket.update(
        {
            "matchable": matchability_status == "ready_for_matching",
            "ready_for_matching": matchability_status == "ready_for_matching",
            "matchability_status": matchability_status,
            "blocking_reasons": blocking_reasons,
            "matching_basis_summary": {
                "release_status": governance_state_bucket["release_status"],
                "rfq_admissibility": governance_state_bucket["rfq_admissibility"],
                "specificity_level": governance_state_bucket["specificity_level"],
                "selection_status": matching_state_bucket.get("selection_status"),
                "candidate_count": len(list(selection_layer.get("candidates") or [])) or len(match_candidates),
                "viable_candidate_count": len(viable_candidate_ids),
                "evidence_ref_count": int(evidence_state_bucket.get("evidence_ref_count", 0) or 0),
            },
            "recommendation_identity": recommendation_identity,
            "requirement_class": dict(requirement_class) if requirement_class else None,
            "requirement_class_hint": requirement_class_hint,
            "manufacturer_validation_required": governance_state_bucket["release_status"] == "manufacturer_validation_required",
            "review_required": bool(governance_state_bucket.get("review_required", False)),
            "candidate_summary": candidate_summary,
            "match_candidates": match_candidates,
            "handover_status": rfq_state_bucket.get("handover_status"),
            "handover_ready": bool(rfq_state_bucket.get("handover_ready", False)),
            "contract_obsolete": bool(cycle.get("contract_obsolete", False)),
            "matching_outcome": matching_outcome,
        }
    )
    result_contract.update(
        {
            "contract_type": "structured_recommendation_contract",
            "contract_version": "structured_recommendation_contract_v1",
            "analysis_cycle_id": cycle.get("analysis_cycle_id"),
            "state_revision": state_revision,
            "binding_level": binding_level,
            "release_status": governance_state_bucket["release_status"],
            "rfq_admissibility": governance_state_bucket["rfq_admissibility"],
            "specificity_level": governance_state_bucket["specificity_level"],
            "contract_obsolete": bool(cycle.get("contract_obsolete", False)),
            "invalidation_reasons": [cycle.get("contract_obsolete_reason")] if cycle.get("contract_obsolete_reason") else [],
            "required_disclaimers": required_disclaimers,
            "evidence_ref_count": evidence_state_bucket.get("evidence_ref_count", 0),
            "evidence_refs": list(evidence_state_bucket.get("evidence_refs") or []),
            "scope_of_validity": list(governance_state_bucket.get("scope_of_validity") or []),
            "assumptions_active": list(governance_state_bucket.get("assumptions_active") or []),
            "blocking_unknowns": list(governance_state_bucket.get("unknowns_release_blocking") or []),
            "manufacturer_validation_required": governance_state_bucket["release_status"] == "manufacturer_validation_required",
            "review_required": bool(governance_state_bucket.get("review_required", False)),
            "conflict_summary": _build_conflict_summary(list(governance_state_bucket.get("conflicts") or [])),
            "candidate_summary": candidate_summary,
            "recommendation_identity": recommendation_identity,
            "requirement_class": dict(requirement_class) if requirement_class else None,
            "requirement_class_hint": requirement_class_hint,
        }
    )
    qualified_action_gate = dict(existing_case_state.get("qualified_action_gate") or {})
    qualified_action_block_reasons = list(governance_layer.get("unknowns_release_blocking") or [])
    if critical_review_gate_blocker and critical_review_gate_blocker not in qualified_action_block_reasons:
        qualified_action_block_reasons.append(critical_review_gate_blocker)
    for finding in critical_review_blocking_findings:
        if finding not in qualified_action_block_reasons:
            qualified_action_block_reasons.append(finding)
    qualified_action_gate.update(
        {
            "action": QUALIFIED_ACTION_DOWNLOAD_RFQ,
            "allowed": rfq_handover_ready,
            "rfq_ready": governance_state_bucket["rfq_admissibility"] == "ready" and bool(governance_state_bucket.get("critical_review_passed", False)),
            "binding_level": binding_level,
            "summary": "qualified_action_ready" if rfq_handover_ready else "qualified_action_blocked",
            "block_reasons": qualified_action_block_reasons,
        }
    )
    rfq_blocking_reasons = _build_rfq_blocking_reasons(
        rfq_admissibility=governance_state_bucket["rfq_admissibility"],
        contract_obsolete=bool(cycle.get("contract_obsolete", False)),
        review_required=bool(governance_state_bucket.get("review_required", False)),
        critical_review_status=critical_review_status,
        critical_review_passed=bool(governance_state_bucket.get("critical_review_passed", False)),
        critical_review_blocking_findings=critical_review_blocking_findings,
        manufacturer_validation_required=governance_state_bucket["release_status"] == "manufacturer_validation_required",
        unknowns_release_blocking=list(governance_state_bucket.get("unknowns_release_blocking") or []),
        handover_ready=rfq_handover_ready,
        recommendation_identity=recommendation_identity,
        match_candidates=match_candidates,
        qualified_action_gate=qualified_action_gate,
    )
    rfq_open_points = list(
        dict.fromkeys(
            list(rfq_state_bucket.get("open_points") or [])
            + _build_rfq_open_points(
                review_required=bool(governance_state_bucket.get("review_required", False)),
                manufacturer_validation_required=governance_state_bucket["release_status"] == "manufacturer_validation_required",
                unknowns_manufacturer_validation=list(governance_state_bucket.get("unknowns_manufacturer_validation") or []),
                unknowns_release_blocking=list(governance_state_bucket.get("unknowns_release_blocking") or []),
                soft_findings=critical_review_soft_findings,
                required_corrections=critical_review_required_corrections,
            )
        )
    )
    qualified_materials = list((handover_layer.get("handover_payload") or {}).get("qualified_materials") or [])
    manufacturer_refs = _build_manufacturer_refs(
        recommendation_identity=recommendation_identity,
        match_candidates=match_candidates,
        qualified_materials=qualified_materials,
        handover_ready=bool(rfq_state_bucket.get("handover_ready", False)),
    )
    manufacturer_capabilities = _build_manufacturer_capabilities(
        manufacturer_refs=manufacturer_refs,
        requirement_class=requirement_class,
        match_candidates=match_candidates,
    )
    recipient_selection = _build_recipient_selection(
        manufacturer_refs=manufacturer_refs,
        manufacturer_capabilities=manufacturer_capabilities,
        matching_outcome=matching_outcome if isinstance(matching_outcome, dict) else None,
        recommendation_identity=recommendation_identity,
        requirement_class=requirement_class,
    )
    selected_partner_id = _resolve_selected_partner_id(
        existing_recipient_selection=existing_case_state.get("recipient_selection"),
        recipient_selection=recipient_selection,
        selection_layer=selection_layer,
    )
    if selected_partner_id:
        recipient_selection = dict(recipient_selection)
        recipient_selection["selected_partner_id"] = selected_partner_id
    matching_outcome_selected_ref = (
        dict(matching_outcome.get("selected_manufacturer_ref") or {})
        if isinstance(matching_outcome, dict)
        and isinstance(matching_outcome.get("selected_manufacturer_ref"), dict)
        else None
    )
    selected_recipient_refs = list(recipient_selection.get("selected_recipient_refs") or [])
    candidate_recipient_refs = list(recipient_selection.get("candidate_recipient_refs") or [])
    manufacturer_rfq_payload = ManufacturerRfqSpecialistInput(
        admissible_request_package=ManufacturerRfqAdmissibleRequestPackage(
            matchability_status=str(
                matching_state_bucket.get("matchability_status")
                or ("ready_for_matching" if matching_state_bucket.get("matchable") else "not_ready")
            ),
            rfq_admissibility=governance_state_bucket["rfq_admissibility"],
            requirement_class=dict(requirement_class) if requirement_class else None,
            confirmed_parameters=dict((handover_layer.get("handover_payload") or {}).get("confirmed_parameters") or {}),
            dimensions=dict((handover_layer.get("handover_payload") or {}).get("dimensions") or {}),
        ),
        manufacturer_capabilities=ManufacturerCapabilityPackage(
            match_candidates=tuple(
                dict(item) for item in match_candidates if isinstance(item, dict) and item
            ),
            manufacturer_refs=tuple(
                dict(item) for item in manufacturer_refs if isinstance(item, dict) and item
            ),
            manufacturer_capabilities=tuple(
                dict(item) for item in manufacturer_capabilities if isinstance(item, dict) and item
            ),
            winner_candidate_id=str(
                selection_layer.get("winner_candidate_id")
                or matching_state_bucket.get("winner_candidate_id")
                or ""
            )
            or None,
            recommendation_identity=dict(recommendation_identity) if recommendation_identity else None,
            selected_manufacturer_ref=(
                matching_outcome_selected_ref
                or (
                    dict(selected_recipient_refs[0])
                    if selected_recipient_refs and isinstance(selected_recipient_refs[0], dict)
                    else None
                )
            ),
        ),
        scope_package=ManufacturerRfqScopePackage(
            scope_of_validity=tuple(str(item) for item in list(governance_state_bucket.get("scope_of_validity") or []) if item is not None),
            open_points=tuple(str(item) for item in rfq_open_points if item is not None),
        ),
        rfq_object={
            "object_type": "rfq_payload_basis",
            "object_version": "rfq_payload_basis_v1",
            "requirement_class": dict(requirement_class) if requirement_class else None,
            "qualified_material_ids": list((handover_layer.get("handover_payload") or {}).get("qualified_material_ids") or []),
            "qualified_materials": list((handover_layer.get("handover_payload") or {}).get("qualified_materials") or []),
            "confirmed_parameters": dict((handover_layer.get("handover_payload") or {}).get("confirmed_parameters") or {}),
            "dimensions": dict((handover_layer.get("handover_payload") or {}).get("dimensions") or {}),
            "target_system": handover_layer.get("target_system"),
            "payload_present": bool(handover_layer.get("handover_payload")),
        },
        recipient_refs=tuple(
            dict(ref)
            for ref in (
                selected_recipient_refs
                or candidate_recipient_refs
            )
            if isinstance(ref, dict) and ref
        ),
        review_required=bool(governance_state_bucket.get("review_required", False)),
        contract_obsolete=bool(cycle.get("contract_obsolete", False)),
    )
    manufacturer_rfq_result = run_manufacturer_rfq_specialist(manufacturer_rfq_payload)
    rfq_payload_basis = project_rfq_payload_basis_from_specialist_result(
        manufacturer_rfq_result,
        payload=manufacturer_rfq_payload,
        recommendation_identity=dict(recommendation_identity) if recommendation_identity else None,
        requirement_class=dict(requirement_class) if requirement_class else None,
        requirement_class_hint=requirement_class_hint,
    )
    manufacturer_state_bucket = dict(existing_case_state.get("manufacturer_state") or {})
    manufacturer_state_bucket.update(
        {
            "manufacturer_specific": bool(manufacturer_refs),
            "manufacturer_specificity_status": "manufacturer_specific" if manufacturer_refs else "not_yet_specific_enough",
            "manufacturer_refs": manufacturer_refs,
            "manufacturer_capabilities": manufacturer_capabilities,
            "manufacturer_basis_summary": {
                "manufacturer_count": len(manufacturer_refs),
                "capability_count": len(manufacturer_capabilities),
                "qualified_material_count": len(qualified_materials),
                "match_candidate_count": len(match_candidates),
                "has_recommendation_manufacturer": bool((recommendation_identity or {}).get("manufacturer_name")),
            },
            "recommendation_identity": recommendation_identity,
            "requirement_class": dict(requirement_class) if requirement_class else None,
            "requirement_class_hint": requirement_class_hint,
            "qualified_materials": qualified_materials,
            "rfq_ready": bool(rfq_state_bucket.get("rfq_ready", False)),
            "handover_ready": bool(rfq_state_bucket.get("handover_ready", False)),
        }
    )
    rfq_dispatch = project_dispatch_intent_from_rfq_send_payload(
        dict(manufacturer_rfq_result.rfq_send_payload or {}),
        projection="rfq_dispatch",
        recipient_selection=recipient_selection,
        handover_status=rfq_state_bucket.get("handover_status"),
        dispatch_open_points=rfq_open_points,
    )
    rfq_state_bucket.update(
        {
            "status": rfq_state_bucket.get(
                "status",
                "ready" if governance_state_bucket["rfq_admissibility"] == "ready" else governance_state_bucket["rfq_admissibility"],
            ),
            "blocking_reasons": rfq_blocking_reasons,
            "blockers": rfq_blocking_reasons,
            "open_points": rfq_open_points,
            "readiness_basis_summary": {
                "release_status": governance_state_bucket["release_status"],
                "rfq_admissibility": governance_state_bucket["rfq_admissibility"],
                "review_required": bool(governance_state_bucket.get("review_required", False)),
                "critical_review_status": critical_review_status,
                "critical_review_passed": bool(governance_state_bucket.get("critical_review_passed", False)),
                "handover_status": rfq_state_bucket.get("handover_status"),
                "handover_ready": rfq_handover_ready,
                "qualified_action_allowed": bool(qualified_action_gate.get("allowed", False)),
                "matchable": bool(matching_state_bucket.get("matchable", False)),
                "matchability_status": matching_state_bucket.get("matchability_status"),
            },
            "recommendation_identity": recommendation_identity,
            "requirement_class": dict(requirement_class) if requirement_class else None,
            "requirement_class_hint": requirement_class_hint,
            "recipient_selection": recipient_selection,
            "manufacturer_validation_required": governance_state_bucket["release_status"] == "manufacturer_validation_required",
            "review_required": bool(governance_state_bucket.get("review_required", False)),
            "contract_obsolete": bool(cycle.get("contract_obsolete", False)),
            "rfq_object": rfq_payload_basis,
            "rfq_send_payload": dict(manufacturer_rfq_result.rfq_send_payload or {}),
            "rfq_dispatch": rfq_dispatch,
            "qualified_action_gate": dict(qualified_action_gate),
        }
    )
    readiness_bucket = dict(existing_case_state.get("readiness") or {})
    readiness_bucket.update(
        {
            "release_status": governance_state_bucket["release_status"],
            "rfq_admissibility": governance_state_bucket["rfq_admissibility"],
            "review_required": governance_state_bucket["review_required"],
            "handover_ready": rfq_state_bucket["handover_ready"],
        }
    )
    invalidation_state_bucket = dict(existing_case_state.get("invalidation_state") or {})
    invalidation_state_bucket.update(
        {
            "contract_obsolete": bool(cycle.get("contract_obsolete", False)),
            "contract_obsolete_reason": cycle.get("contract_obsolete_reason"),
            "superseded_by_cycle": cycle.get("superseded_by_cycle"),
            "analysis_cycle_id": cycle.get("analysis_cycle_id"),
        }
    )
    return {
        "case_meta": case_meta,
        "requirement_class": dict(requirement_class) if requirement_class else None,
        "recipient_selection": recipient_selection,
        "observed_inputs": observed_inputs_bucket,
        "normalized_parameters": normalized_parameters_bucket,
        "parameter_meta": parameter_meta_bucket,
        "derived_engineering_values": derived_engineering_values_bucket,
        "evidence_state": evidence_state_bucket,
        "governance_state": governance_state_bucket,
        "matching_state": matching_state_bucket,
        "rfq_state": rfq_state_bucket,
        "manufacturer_state": manufacturer_state_bucket,
        "raw_inputs": dict(existing_case_state.get("raw_inputs") or observed_inputs_bucket.get("raw_parameters") or {}),
        "normalization_identity_snapshot": dict(parameter_meta_bucket),
        "derived_calculations": dict(derived_engineering_values_bucket),
        "engineering_signals": {
            "working_profile_keys": sorted(working_profile.keys()),
            "fact_card_count": len(relevant_fact_cards),
        },
        "qualification_results": {
            "selection_status": matching_state_bucket.get("selection_status"),
            "output_blocked": matching_state_bucket.get("output_blocked"),
            "release_status": governance_state_bucket.get("release_status"),
        },
        "result_contract": result_contract,
        "medium_capture": medium_capture_bucket,
        "medium_classification": medium_classification_bucket,
        "medium_context": medium_context_bucket,
        "candidate_clusters": list(matching_state_bucket.get("candidate_clusters") or []),
        "sealing_requirement_spec": {
            **build_default_sealing_requirement_spec(
                analysis_cycle_id=cycle.get("analysis_cycle_id"),
                state_revision=state_revision,
            ),
            "runtime_path": runtime_path,
            "release_status": governance_state_bucket["release_status"],
            "rfq_admissibility": governance_state_bucket["rfq_admissibility"],
            "specificity_level": governance_state_bucket["specificity_level"],
            "contract_obsolete": bool(cycle.get("contract_obsolete", False)),
            "candidate_clusters": list(matching_state_bucket.get("candidate_clusters") or []),
            "candidate_summary": candidate_summary,
            "recommendation_identity": recommendation_identity,
            "requirement_class": dict(requirement_class) if requirement_class else None,
            "requirement_class_hint": requirement_class_hint,
            "scope_of_validity": list(governance_state_bucket.get("scope_of_validity") or []),
            "blocking_unknowns": list(governance_state_bucket.get("unknowns_release_blocking") or []),
            "manufacturer_validation_required": governance_state_bucket["release_status"] == "manufacturer_validation_required",
        },
        "qualified_action_gate": qualified_action_gate,
        "qualified_action_history": list(existing_case_state.get("qualified_action_history") or []),
        "readiness": readiness_bucket,
        "invalidation_state": invalidation_state_bucket,
        "audit_trail": [audit_event],
    }


def sync_case_state_to_state(
    state: dict[str, Any],
    *,
    session_id: str,
    runtime_path: str,
    binding_level: str,
    version_provenance: VersionProvenance | None = None,
    policy_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updated = dict(state)
    updated["case_state"] = build_case_state(
        state,
        session_id=session_id,
        runtime_path=runtime_path,
        binding_level=binding_level,
        version_provenance=version_provenance,
        policy_context=policy_context,
    )
    return updated


def ensure_case_state(
    state: dict[str, Any],
    *,
    session_id: str,
    runtime_path: str,
    binding_level: str,
    version_provenance: VersionProvenance | None = None,
    policy_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updated = dict(state)
    updated["case_state"] = build_case_state(
        updated,
        session_id=session_id,
        runtime_path=runtime_path,
        binding_level=binding_level,
        version_provenance=version_provenance,
        policy_context=policy_context,
    )
    return updated


def sync_material_cycle_control(state: dict[str, Any]) -> dict[str, Any]:
    return dict(state)


def get_material_input_snapshot_and_fingerprint(state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    snapshot = dict((((state.get("sealing_state") or {}).get("asserted")) or {}).get("operating_conditions") or {})
    return snapshot, str(sorted(snapshot.items()))


def get_material_provider_snapshot_and_fingerprint(state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    snapshot = {"fact_card_count": len(state.get("relevant_fact_cards") or [])}
    return snapshot, str(sorted(snapshot.items()))


def resolve_next_step_contract(state: dict[str, Any]) -> dict[str, Any]:
    cycle = ((state.get("sealing_state") or {}).get("cycle") or {})
    return {
        "ask_mode": "guided",
        "requested_fields": [],
        "reason_code": "bounded_default",
        "impact_hint": None,
        "rfq_admissibility": ((state.get("case_state") or {}).get("result_contract") or {}).get("rfq_admissibility", "inadmissible"),
        "state_revision": int(cycle.get("state_revision", 0) or 0),
    }


def build_conversation_guidance_contract(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "binding_level": "ORIENTATION",
        "next_step_contract": resolve_next_step_contract(state),
    }


def _coverage_prefix(coverage_status: str | None) -> str:
    if coverage_status == "partial":
        return "[Teilweise abgedeckt] "
    if coverage_status == "orientation_only":
        return "[Nur Orientierung] "
    if coverage_status == "out_of_scope":
        return "[Außerhalb des Scopes] "
    return ""


def _build_visible_coverage_scope(policy_context: dict[str, Any] | None) -> list[VisibleNarrativeItem]:
    if not policy_context:
        return []
    coverage_status = policy_context.get("coverage_status")
    boundary_flags = list(policy_context.get("boundary_flags", []))
    items: list[VisibleNarrativeItem] = []
    emit_boundary = coverage_status in {"partial", "orientation_only", "out_of_scope"} or bool(boundary_flags)
    if "no_manufacturer_release" in boundary_flags:
        items.append(
            {
                "key": "manufacturer_release",
                "label": "Manufacturer Release",
                "value": "Nicht freigegeben",
                "detail": "no_manufacturer_release",
                "severity": "medium",
            }
        )
    if emit_boundary:
        severity = "low" if coverage_status == "in_scope" else "medium"
        if coverage_status == "out_of_scope":
            severity = "high"
        items.append(
            {
                "key": "coverage_boundary",
                "label": "Coverage Boundary",
                "value": str(coverage_status or "boundary"),
                "detail": ", ".join(boundary_flags) if boundary_flags else None,
                "severity": severity,  # type: ignore[typeddict-item]
            }
        )
    if policy_context.get("escalation_reason"):
        items.append(
            {
                "key": "escalation_context",
                "label": "Escalation",
                "value": str(policy_context["escalation_reason"]),
                "detail": None,
                "severity": "medium",
            }
        )
    return items


def build_visible_case_narrative(
    *,
    state: dict[str, Any],
    case_state: dict[str, Any] | None,
    binding_level: str,
    policy_context: dict[str, Any] | None = None,
) -> VisibleCaseNarrative:
    del state, binding_level
    effective_policy = policy_context
    case_meta = (case_state or {}).get("case_meta") or {}
    if effective_policy is None:
        effective_policy = case_meta.get("policy_narrative_snapshot")
    if effective_policy is None and case_meta.get("boundary_contract"):
        effective_policy = dict(case_meta.get("boundary_contract") or {})
    coverage_scope = _build_visible_coverage_scope(effective_policy)
    summary = "Aktuelle technische Richtung: No active technical direction."
    prefix = _coverage_prefix((effective_policy or {}).get("coverage_status"))
    if prefix:
        summary = prefix + summary
    if effective_policy and effective_policy.get("escalation_reason"):
        summary = f"{summary} Eskalation: {effective_policy['escalation_reason']}"
    return {
        "governed_summary": summary,
        "technical_direction": [],
        "validity_envelope": [],
        "next_best_inputs": [],
        "suggested_next_questions": [],
        "failure_analysis": [],
        "case_summary": [],
        "qualification_status": [],
        "coverage_scope": coverage_scope,
    }
