from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, NotRequired, TypedDict

from app.agent.domain.normalization import normalize_material, normalize_medium, normalize_unit_value


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
    version: int
    runtime_path: str
    binding_level: str
    lifecycle_status: str
    version_provenance: VersionProvenance
    policy_narrative_snapshot: dict[str, Any]
    boundary_contract: BoundaryContract


class CaseState(TypedDict, total=False):
    case_meta: CaseMeta
    raw_inputs: dict[str, Any]
    normalization_identity_snapshot: dict[str, Any]
    derived_calculations: dict[str, Any]
    engineering_signals: dict[str, Any]
    qualification_results: dict[str, Any]
    result_contract: dict[str, Any]
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
        "analysis_cycle_id": analysis_cycle_id,
        "state_revision": state_revision,
        "binding_level": "ORIENTATION",
        "release_status": "inadmissible",
        "rfq_admissibility": "inadmissible",
        "specificity_level": "family_only",
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
        "source_ref": "case_state.default_sealing_requirement_spec",
    }


def normalize_qualified_action_id(action: Any) -> QualifiedActionId:
    return QUALIFIED_ACTION_DOWNLOAD_RFQ


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
        return normalize_medium(value)
    if lowered.endswith("_f"):
        return normalize_unit_value(float(value), "F")[0]
    if lowered.endswith("_psi"):
        return normalize_unit_value(float(value), "psi")[0]
    return value


def build_case_state(
    state: dict[str, Any],
    *,
    session_id: str,
    runtime_path: str,
    binding_level: str,
    version_provenance: VersionProvenance | None = None,
    policy_context: dict[str, Any] | None = None,
) -> CaseState:
    cycle = ((state.get("sealing_state") or {}).get("cycle") or {})
    state_revision = int(cycle.get("state_revision", 0) or 0)
    case_meta: CaseMeta = {
        "case_id": session_id,
        "session_id": session_id,
        "analysis_cycle_id": cycle.get("analysis_cycle_id"),
        "state_revision": state_revision,
        "version": state_revision,
        "runtime_path": runtime_path,
        "binding_level": binding_level,
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
    return {
        "case_meta": case_meta,
        "raw_inputs": {},
        "normalization_identity_snapshot": dict(((state.get("sealing_state") or {}).get("normalized") or {}).get("identity_records") or {}),
        "derived_calculations": {},
        "engineering_signals": {},
        "qualification_results": {},
        "result_contract": build_default_result_contract(
            analysis_cycle_id=cycle.get("analysis_cycle_id"),
            state_revision=state_revision,
        ),
        "candidate_clusters": [],
        "sealing_requirement_spec": build_default_sealing_requirement_spec(
            analysis_cycle_id=cycle.get("analysis_cycle_id"),
            state_revision=state_revision,
        ),
        "qualified_action_gate": {
            "action": QUALIFIED_ACTION_DOWNLOAD_RFQ,
            "allowed": False,
            "rfq_ready": False,
            "binding_level": binding_level,
            "summary": "qualified_action_blocked",
            "block_reasons": [],
        },
        "qualified_action_history": [],
        "readiness": {},
        "invalidation_state": {},
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


def sync_material_cycle_control(state: dict[str, Any]) -> dict[str, Any]:
    return dict(state)


def get_material_input_snapshot_and_fingerprint(state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    snapshot = dict((((state.get("sealing_state") or {}).get("asserted")) or {}).get("operating_conditions") or {})
    return snapshot, str(sorted(snapshot.items()))


def get_material_provider_snapshot_and_fingerprint(state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    snapshot = {"fact_card_count": len(state.get("relevant_fact_cards") or [])}
    return snapshot, str(sorted(snapshot.items()))


def case_lifecycle_requires_review(case_state: dict[str, Any] | None) -> bool:
    lifecycle = (((case_state or {}).get("case_meta") or {}).get("lifecycle_status"))
    return lifecycle in {"review_pending", "out_of_scope"}


def sync_case_lifecycle_status(
    *,
    case_state: dict[str, Any],
    lifecycle_status: str,
) -> dict[str, Any]:
    updated = dict(case_state)
    case_meta = dict(updated.get("case_meta") or {})
    case_meta["lifecycle_status"] = lifecycle_status
    updated["case_meta"] = case_meta
    return updated


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
