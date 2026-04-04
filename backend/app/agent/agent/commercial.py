"""
Commercial / Handover Layer.

Deterministic boundary between the technical qualification result and the
downstream commercial process (RFQ portal, ERP, shop, etc.).

Rules:
- build_handover_payload() reads from the completed SealingAIState.
- is_handover_ready = True IFF governance.release_status == "rfq_ready"
  AND review.review_required is not True (no pending HITL review)
  AND review.critical_review_passed is True.
- The returned handover_payload contains ONLY clean order-profile data:
    qualified_material_ids, confirmed_parameters, dimensions (if present).
- The following are NEVER included in the payload:
    governance internals (gate_failures, conflicts, unknowns_*),
    reasoning artefacts (raw LLM claims, sealing_state cycle internals),
    demo-data flags,
    HITL review state.
- No external API calls are made here. This module is purely structural.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Readiness check (deterministic)
# ---------------------------------------------------------------------------

def _is_handover_ready(
    governance_state: Dict[str, Any],
    review_state: Dict[str, Any],
) -> bool:
    """Return True only when the case is technically qualified and has no pending review.

    Conditions (all must hold):
    1. governance.release_status == "rfq_ready"
    2. review.review_required is not True
    3. review.critical_review_passed is True and has no blocking findings
    """
    release_status: str = governance_state.get("release_status", "inadmissible")
    review_required: bool = bool(review_state.get("review_required", False))
    critical_review_passed: bool = bool(review_state.get("critical_review_passed", False))
    blocking_findings = list(review_state.get("blocking_findings") or [])
    return (
        release_status == "rfq_ready"
        and not review_required
        and critical_review_passed
        and not blocking_findings
    )


def _critical_review_reason(review_state: Dict[str, Any]) -> str:
    status = str(review_state.get("critical_review_status") or "not_run")
    blocking_findings = [
        str(item)
        for item in list(review_state.get("blocking_findings") or [])
        if str(item or "").strip()
    ]
    if status == "not_run":
        return "Critical review is mandatory before RFQ handover."
    if blocking_findings:
        return "Critical review blocked RFQ handover: " + ", ".join(blocking_findings) + "."
    return "Critical review did not pass."


def _project_handover_status(
    governance_state: Dict[str, Any],
    review_state: Dict[str, Any],
    selection_state: Dict[str, Any],
) -> tuple[str, str]:
    """Return deterministic handover semantics without expanding the commercial payload."""
    if _is_handover_ready(governance_state, review_state):
        return "releasable", "Governed output is releasable and handover-ready."
    if not bool(review_state.get("critical_review_passed", False)):
        return "reviewable", _critical_review_reason(review_state)

    projection = selection_state.get("review_escalation_projection") or {}
    if projection.get("handover_possible"):
        return "handoverable", str(projection.get("reason") or "Human handover is possible.")
    if projection.get("review_meaningful"):
        return "reviewable", str(projection.get("reason") or "Human review is meaningful.")
    return "not_handoverable", str(
        projection.get("reason") or "Case requires clarification or review before handover."
    )


def _resolve_handover_shell_inputs(
    *,
    sealing_state: Dict[str, Any],
    canonical_case_state: Dict[str, Any] | None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    case_state = dict(canonical_case_state or {})
    canonical_governance_state = dict(case_state.get("governance_state") or {})
    governance_state = dict(sealing_state.get("governance") or {})
    review_state = dict(sealing_state.get("review") or {})

    effective_governance_state = dict(governance_state)
    if canonical_governance_state.get("release_status") is not None:
        effective_governance_state["release_status"] = canonical_governance_state.get("release_status")
    if canonical_governance_state.get("rfq_admissibility") is not None:
        effective_governance_state["rfq_admissibility"] = canonical_governance_state.get("rfq_admissibility")

    effective_review_state = dict(review_state)
    if canonical_governance_state.get("review_required") is not None:
        effective_review_state["review_required"] = bool(canonical_governance_state.get("review_required"))
    if canonical_governance_state.get("review_state") is not None:
        effective_review_state["review_state"] = canonical_governance_state.get("review_state")

    return effective_governance_state, effective_review_state


def _pick_primary_match_candidate(
    *,
    winner_candidate_id: Optional[str],
    match_candidates: list[Dict[str, Any]],
    recommendation_identity: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if winner_candidate_id:
        for candidate in match_candidates:
            if candidate.get("candidate_id") == winner_candidate_id:
                return dict(candidate)
    for candidate in match_candidates:
        if candidate.get("viability_status") == "viable":
            return dict(candidate)
    if recommendation_identity:
        return dict(recommendation_identity)
    return None


def _find_manufacturer_ref(
    recipient_selection: Optional[Dict[str, Any]],
    manufacturer_refs: list[Dict[str, Any]],
    manufacturer_capabilities: list[Dict[str, Any]],
    requirement_class: Optional[Dict[str, Any]],
    primary_match_candidate: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not primary_match_candidate:
        return None
    manufacturer_name = primary_match_candidate.get("manufacturer_name")
    candidate_id = primary_match_candidate.get("candidate_id")
    requirement_class_id = str((requirement_class or {}).get("requirement_class_id") or "").strip()

    preferred_refs: list[Dict[str, Any]] = []
    if isinstance(recipient_selection, dict):
        preferred_refs.extend(
            dict(ref)
            for ref in list(recipient_selection.get("selected_recipient_refs") or [])
            if isinstance(ref, dict) and ref
        )
        preferred_refs.extend(
            dict(ref)
            for ref in list(recipient_selection.get("candidate_recipient_refs") or [])
            if isinstance(ref, dict) and ref
        )

    capability_refs: list[Dict[str, Any]] = []
    for capability in manufacturer_capabilities:
        if not isinstance(capability, dict):
            continue
        capability_requirement_class_ids = {
            str(item) for item in list(capability.get("requirement_class_ids") or []) if item
        }
        if requirement_class_id and capability_requirement_class_ids and requirement_class_id not in capability_requirement_class_ids:
            continue
        capability_candidate_ids = list(capability.get("candidate_ids") or [])
        capability_ref: Dict[str, Any] = {
            "manufacturer_name": capability.get("manufacturer_name"),
            "candidate_ids": capability_candidate_ids,
            "material_families": list(capability.get("material_families") or []),
            "grade_names": list(capability.get("grade_names") or []),
            "candidate_kinds": list(capability.get("candidate_kinds") or []),
            "capability_hints": list(capability.get("capability_hints") or []),
            "source_refs": list(capability.get("capability_sources") or []),
            "qualified_for_rfq": bool(capability.get("rfq_qualified", False)),
        }
        capability_refs.append(capability_ref)

    for ref in preferred_refs + [dict(ref) for ref in manufacturer_refs if isinstance(ref, dict) and ref] + capability_refs:
        if manufacturer_name and ref.get("manufacturer_name") == manufacturer_name:
            return dict(ref)
        if candidate_id and candidate_id in list(ref.get("candidate_ids") or []):
            return dict(ref)
    return None


def _resolve_dispatch_runtime_source(state: Dict[str, Any]) -> tuple[Dict[str, Any], str]:
    case_state: Dict[str, Any] = state.get("case_state") or {}
    sealing_state: Dict[str, Any] = state.get("sealing_state") or {}

    dispatch_intent = case_state.get("dispatch_intent") or sealing_state.get("dispatch_intent") or {}
    if isinstance(dispatch_intent, dict) and dispatch_intent:
        return dict(dispatch_intent), "dispatch_intent"

    rfq_state: Dict[str, Any] = case_state.get("rfq_state") or {}
    rfq_dispatch = rfq_state.get("rfq_dispatch") or {}
    if isinstance(rfq_dispatch, dict) and rfq_dispatch:
        return dict(rfq_dispatch), "canonical_rfq_dispatch_fallback"

    return {}, "missing_dispatch_basis"


def _resolve_canonical_matching_outcome_core(case_state: Dict[str, Any]) -> Dict[str, Any]:
    matching_state = dict(case_state.get("matching_state") or {})
    matching_outcome = (
        matching_state.get("matching_outcome")
        or case_state.get("matching_outcome")
        or {}
    )
    return dict(matching_outcome or {})


def build_matching_outcome(state: Dict[str, Any]) -> Dict[str, Any]:
    """Build a minimal deterministic matching outcome from canonical truth when available.

    Preference order:
    1. Canonical case_state.matching_state / manufacturer_state
    2. Runtime sealing_state.selection fallback

    No scoring model is introduced. Prioritization is explicit:
    winner candidate > first viable candidate > recommendation identity.
    """
    case_state: Dict[str, Any] = state.get("case_state") or {}
    sealing_state: Dict[str, Any] = state.get("sealing_state") or {}

    matching_state: Dict[str, Any] = case_state.get("matching_state") or {}
    manufacturer_state: Dict[str, Any] = case_state.get("manufacturer_state") or {}
    rfq_state: Dict[str, Any] = case_state.get("rfq_state") or {}
    result_contract: Dict[str, Any] = case_state.get("result_contract") or {}
    recipient_selection: Dict[str, Any] = (
        case_state.get("recipient_selection")
        or rfq_state.get("recipient_selection")
        or {}
    )

    selection_state: Dict[str, Any] = sealing_state.get("selection") or {}
    governance_state: Dict[str, Any] = sealing_state.get("governance") or {}
    review_state: Dict[str, Any] = sealing_state.get("review") or {}

    matchability_status = str(
        matching_state.get("matchability_status")
        or ("ready_for_matching" if matching_state.get("matchable") else "not_ready")
    )
    contract_obsolete = bool(
        matching_state.get("contract_obsolete")
        or rfq_state.get("contract_obsolete")
        or result_contract.get("contract_obsolete")
    )
    review_required = bool(
        matching_state.get("review_required", rfq_state.get("review_required", review_state.get("review_required", False)))
    )
    match_candidates = list(matching_state.get("match_candidates") or [])
    manufacturer_refs = list(manufacturer_state.get("manufacturer_refs") or [])
    manufacturer_capabilities = list(manufacturer_state.get("manufacturer_capabilities") or [])
    winner_candidate_id = matching_state.get("winner_candidate_id") or selection_state.get("winner_candidate_id")
    recommendation_identity = (
        matching_state.get("recommendation_identity")
        or manufacturer_state.get("recommendation_identity")
        or result_contract.get("recommendation_identity")
    )
    requirement_class = (
        matching_state.get("requirement_class")
        or manufacturer_state.get("requirement_class")
        or rfq_state.get("requirement_class")
        or result_contract.get("requirement_class")
        or case_state.get("requirement_class")
    )
    requirement_class_hint = (
        (requirement_class or {}).get("requirement_class_id")
        or matching_state.get("requirement_class_hint")
        or manufacturer_state.get("requirement_class_hint")
        or rfq_state.get("requirement_class_hint")
        or result_contract.get("requirement_class_hint")
    )

    status = "not_ready"
    reason = str(matchability_status or "not_ready")
    primary_match_candidate: Optional[Dict[str, Any]] = None

    if contract_obsolete:
        status = "blocked_contract_obsolete"
        reason = "Contract is obsolete and matching output must not be treated as current."
    elif review_required:
        status = "blocked_review_required"
        reason = "Matching remains blocked until required review is resolved."
    elif matchability_status != "ready_for_matching":
        status = f"blocked_{matchability_status}"
        reason = f"Matching is not releasable: {matchability_status}."
    else:
        primary_match_candidate = _pick_primary_match_candidate(
            winner_candidate_id=winner_candidate_id,
            match_candidates=match_candidates,
            recommendation_identity=dict(recommendation_identity) if isinstance(recommendation_identity, dict) else None,
        )
        if primary_match_candidate:
            status = "matched_primary_candidate"
            reason = "Primary match candidate selected from canonical winner/viable candidate truth."
        else:
            status = "blocked_no_match_candidates"
            reason = "No viable or projected match candidate is available."

    selected_manufacturer_ref = _find_manufacturer_ref(
        recipient_selection=recipient_selection if isinstance(recipient_selection, dict) else None,
        manufacturer_refs=manufacturer_refs,
        manufacturer_capabilities=manufacturer_capabilities,
        requirement_class=dict(requirement_class) if isinstance(requirement_class, dict) else None,
        primary_match_candidate=primary_match_candidate,
    )

    outcome = {
        "status": status,
        "reason": reason,
        "matchability_status": matchability_status,
        "requirement_class": dict(requirement_class) if isinstance(requirement_class, dict) and requirement_class else None,
        "requirement_class_hint": requirement_class_hint,
        "primary_match_candidate": primary_match_candidate,
        "selected_manufacturer_ref": selected_manufacturer_ref,
        "review_required": review_required,
        "contract_obsolete": contract_obsolete,
        "manufacturer_validation_required": bool(
            matching_state.get(
                "manufacturer_validation_required",
                governance_state.get("release_status") == "manufacturer_validation_required",
            )
        ),
    }

    canonical_matching_outcome = _resolve_canonical_matching_outcome_core(case_state)
    for key in (
        "status",
        "reason",
        "matchability_status",
        "requirement_class",
        "requirement_class_hint",
        "primary_match_candidate",
        "selected_manufacturer_ref",
        "review_required",
        "contract_obsolete",
        "manufacturer_validation_required",
    ):
        value = canonical_matching_outcome.get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            outcome[key] = dict(value)
        elif isinstance(value, list):
            outcome[key] = list(value)
        else:
            outcome[key] = value

    return outcome


def build_dispatch_trigger(state: Dict[str, Any]) -> Dict[str, Any]:
    dispatch_source, source_name = _resolve_dispatch_runtime_source(state)
    recipient_refs = [
        dict(ref) for ref in list(dispatch_source.get("recipient_refs") or []) if isinstance(ref, dict) and ref
    ]
    dispatch_blockers = list(
        dict.fromkeys(str(item) for item in list(dispatch_source.get("dispatch_blockers") or []) if item)
    )
    selected_manufacturer_ref = (
        dict(dispatch_source.get("selected_manufacturer_ref") or {})
        if isinstance(dispatch_source.get("selected_manufacturer_ref"), dict)
        and dispatch_source.get("selected_manufacturer_ref")
        else None
    )
    requirement_class = (
        dict(dispatch_source.get("requirement_class") or {})
        if isinstance(dispatch_source.get("requirement_class"), dict)
        and dispatch_source.get("requirement_class")
        else None
    )
    recommendation_identity = (
        dict(dispatch_source.get("recommendation_identity") or {})
        if isinstance(dispatch_source.get("recommendation_identity"), dict)
        and dispatch_source.get("recommendation_identity")
        else None
    )

    if not dispatch_source:
        trigger_allowed = False
        trigger_status = "trigger_blocked_missing_dispatch_basis"
        trigger_reason = "No runtime dispatch basis is available for an internal trigger."
    elif bool(dispatch_source.get("dispatch_ready")):
        trigger_allowed = True
        trigger_status = "trigger_ready"
        trigger_reason = "Runtime dispatch basis is ready for an internal trigger."
    elif (
        str(dispatch_source.get("dispatch_status") or "") == "not_ready_no_recipients"
        or not recipient_refs
    ):
        if "no_recipient_refs" not in dispatch_blockers:
            dispatch_blockers.append("no_recipient_refs")
        trigger_allowed = False
        trigger_status = "trigger_blocked_no_recipients"
        trigger_reason = "Internal dispatch trigger remains blocked because no recipients are available."
    else:
        trigger_allowed = False
        trigger_status = "trigger_blocked_dispatch_not_ready"
        trigger_reason = "Internal dispatch trigger remains blocked until dispatch readiness is achieved."

    return {
        "object_type": "dispatch_trigger",
        "object_version": "dispatch_trigger_v1",
        "trigger_allowed": trigger_allowed,
        "trigger_status": trigger_status,
        "trigger_reason": trigger_reason,
        "trigger_blockers": dispatch_blockers,
        "recipient_refs": recipient_refs,
        "selected_manufacturer_ref": selected_manufacturer_ref,
        "requirement_class": requirement_class,
        "recommendation_identity": recommendation_identity,
        "source": source_name,
    }


def build_dispatch_dry_run(state: Dict[str, Any]) -> Dict[str, Any]:
    case_state: Dict[str, Any] = state.get("case_state") or {}
    sealing_state: Dict[str, Any] = state.get("sealing_state") or {}

    dispatch_trigger = case_state.get("dispatch_trigger") or sealing_state.get("dispatch_trigger") or {}
    if not isinstance(dispatch_trigger, dict) or not dispatch_trigger:
        dispatch_trigger = build_dispatch_trigger(state)

    trigger_blockers = list(
        dict.fromkeys(str(item) for item in list(dispatch_trigger.get("trigger_blockers") or []) if item)
    )
    recipient_refs = [
        dict(ref) for ref in list(dispatch_trigger.get("recipient_refs") or []) if isinstance(ref, dict) and ref
    ]
    selected_manufacturer_ref = (
        dict(dispatch_trigger.get("selected_manufacturer_ref") or {})
        if isinstance(dispatch_trigger.get("selected_manufacturer_ref"), dict)
        and dispatch_trigger.get("selected_manufacturer_ref")
        else None
    )
    requirement_class = (
        dict(dispatch_trigger.get("requirement_class") or {})
        if isinstance(dispatch_trigger.get("requirement_class"), dict)
        and dispatch_trigger.get("requirement_class")
        else None
    )
    recommendation_identity = (
        dict(dispatch_trigger.get("recommendation_identity") or {})
        if isinstance(dispatch_trigger.get("recommendation_identity"), dict)
        and dispatch_trigger.get("recommendation_identity")
        else None
    )

    trigger_status = str(dispatch_trigger.get("trigger_status") or "")
    if bool(dispatch_trigger.get("trigger_allowed")):
        dry_run_ready = True
        would_dispatch = True
        dry_run_status = "dry_run_ready"
        dry_run_reason = "Dry-run indicates dispatch would proceed in the current runtime turn."
    elif trigger_status == "trigger_blocked_no_recipients":
        dry_run_ready = False
        would_dispatch = False
        dry_run_status = "dry_run_blocked_no_recipients"
        dry_run_reason = "Dry-run indicates dispatch would not proceed because no recipients are available."
    elif trigger_status == "trigger_blocked_missing_dispatch_basis":
        dry_run_ready = False
        would_dispatch = False
        dry_run_status = "dry_run_blocked_missing_dispatch_basis"
        dry_run_reason = "Dry-run indicates dispatch would not proceed because no dispatch basis is available."
    else:
        dry_run_ready = False
        would_dispatch = False
        dry_run_status = "dry_run_blocked"
        dry_run_reason = "Dry-run indicates dispatch would not proceed in the current runtime turn."

    return {
        "object_type": "dispatch_dry_run",
        "object_version": "dispatch_dry_run_v1",
        "dry_run_ready": dry_run_ready,
        "dry_run_status": dry_run_status,
        "dry_run_reason": dry_run_reason,
        "dry_run_blockers": trigger_blockers,
        "recipient_refs": recipient_refs,
        "selected_manufacturer_ref": selected_manufacturer_ref,
        "requirement_class": requirement_class,
        "recommendation_identity": recommendation_identity,
        "trigger_source": dispatch_trigger.get("source"),
        "would_dispatch": would_dispatch,
        "source": "dispatch_trigger",
    }


def build_dispatch_event(state: Dict[str, Any]) -> Dict[str, Any]:
    case_state: Dict[str, Any] = state.get("case_state") or {}
    sealing_state: Dict[str, Any] = state.get("sealing_state") or {}

    dispatch_trigger = case_state.get("dispatch_trigger") or sealing_state.get("dispatch_trigger") or {}
    if not isinstance(dispatch_trigger, dict) or not dispatch_trigger:
        dispatch_trigger = build_dispatch_trigger(state)

    dispatch_dry_run = case_state.get("dispatch_dry_run") or sealing_state.get("dispatch_dry_run") or {}
    if not isinstance(dispatch_dry_run, dict) or not dispatch_dry_run:
        dispatch_dry_run = build_dispatch_dry_run(state)

    trigger_blockers = list(
        dict.fromkeys(str(item) for item in list(dispatch_trigger.get("trigger_blockers") or []) if item)
    )
    recipient_refs = [
        dict(ref) for ref in list(dispatch_trigger.get("recipient_refs") or []) if isinstance(ref, dict) and ref
    ]
    selected_manufacturer_ref = (
        dict(dispatch_trigger.get("selected_manufacturer_ref") or {})
        if isinstance(dispatch_trigger.get("selected_manufacturer_ref"), dict)
        and dispatch_trigger.get("selected_manufacturer_ref")
        else None
    )
    requirement_class = (
        dict(dispatch_trigger.get("requirement_class") or {})
        if isinstance(dispatch_trigger.get("requirement_class"), dict)
        and dispatch_trigger.get("requirement_class")
        else None
    )
    recommendation_identity = (
        dict(dispatch_trigger.get("recommendation_identity") or {})
        if isinstance(dispatch_trigger.get("recommendation_identity"), dict)
        and dispatch_trigger.get("recommendation_identity")
        else None
    )

    trigger_status = str(dispatch_trigger.get("trigger_status") or "")
    if bool(dispatch_trigger.get("trigger_allowed")):
        event_kind = "dispatch_would_run"
        event_status = "event_dispatch_would_run"
        event_reason = "Internal dispatch event indicates dispatch would run in the current turn."
        would_dispatch = True
    elif trigger_status == "trigger_blocked_no_recipients":
        event_kind = "dispatch_no_recipients"
        event_status = "event_dispatch_no_recipients"
        event_reason = "Internal dispatch event indicates dispatch is blocked because no recipients are available."
        would_dispatch = False
    elif trigger_status == "trigger_blocked_missing_dispatch_basis":
        event_kind = "dispatch_missing_basis"
        event_status = "event_dispatch_missing_basis"
        event_reason = "Internal dispatch event indicates dispatch is blocked because no dispatch basis is available."
        would_dispatch = False
    else:
        event_kind = "dispatch_blocked"
        event_status = "event_dispatch_blocked"
        event_reason = "Internal dispatch event indicates dispatch would not run in the current turn."
        would_dispatch = False

    case_meta = dict(case_state.get("case_meta") or {})
    cycle = dict(sealing_state.get("cycle") or {})
    state_revision = (
        case_meta.get("state_revision")
        if case_meta.get("state_revision") is not None
        else cycle.get("state_revision")
    )
    analysis_cycle_id = (
        case_meta.get("analysis_cycle_id")
        or cycle.get("analysis_cycle_id")
    )
    session_id = (
        case_meta.get("session_id")
        or state.get("session_id")
        or state.get("inquiry_id")
    )
    requirement_class_id = str((requirement_class or {}).get("requirement_class_id") or "")
    selected_manufacturer_name = str((selected_manufacturer_ref or {}).get("manufacturer_name") or "")
    recommendation_candidate_id = str((recommendation_identity or {}).get("candidate_id") or "")
    recipient_signature = [
        {
            "manufacturer_name": str(ref.get("manufacturer_name") or ""),
            "candidate_ids": sorted(str(item) for item in list(ref.get("candidate_ids") or []) if item),
        }
        for ref in recipient_refs
    ]
    identity_basis = {
        "session_id": str(session_id or ""),
        "analysis_cycle_id": str(analysis_cycle_id or ""),
        "state_revision": state_revision,
        "event_status": event_status,
        "trigger_status": trigger_status,
        "trigger_source": str(dispatch_trigger.get("source") or ""),
        "dry_run_status": str(dispatch_dry_run.get("dry_run_status") or ""),
        "requirement_class_id": requirement_class_id,
        "selected_manufacturer_name": selected_manufacturer_name,
        "recommendation_candidate_id": recommendation_candidate_id,
        "recipient_signature": recipient_signature,
    }
    identity_payload = json.dumps(identity_basis, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    event_key = hashlib.sha256(identity_payload.encode("utf-8")).hexdigest()

    return {
        "object_type": "dispatch_event",
        "object_version": "dispatch_event_v1",
        "event_id": f"dispatch_event::{event_key}",
        "event_key": event_key,
        "event_identity": identity_basis,
        "event_kind": event_kind,
        "event_status": event_status,
        "event_reason": event_reason,
        "event_blockers": trigger_blockers,
        "would_dispatch": would_dispatch,
        "recipient_refs": recipient_refs,
        "selected_manufacturer_ref": selected_manufacturer_ref,
        "requirement_class": requirement_class,
        "recommendation_identity": recommendation_identity,
        "trigger_source": dispatch_trigger.get("source"),
        "dry_run_status": dispatch_dry_run.get("dry_run_status"),
        "source": "dispatch_trigger",
    }


def build_dispatch_bridge(state: Dict[str, Any]) -> Dict[str, Any]:
    case_state: Dict[str, Any] = state.get("case_state") or {}
    sealing_state: Dict[str, Any] = state.get("sealing_state") or {}

    dispatch_event = case_state.get("dispatch_event") or sealing_state.get("dispatch_event") or {}
    if not isinstance(dispatch_event, dict) or not dispatch_event:
        dispatch_event = build_dispatch_event(state)

    bridge_blockers = list(
        dict.fromkeys(str(item) for item in list(dispatch_event.get("event_blockers") or []) if item)
    )
    recipient_refs = [
        dict(ref) for ref in list(dispatch_event.get("recipient_refs") or []) if isinstance(ref, dict) and ref
    ]
    selected_manufacturer_ref = (
        dict(dispatch_event.get("selected_manufacturer_ref") or {})
        if isinstance(dispatch_event.get("selected_manufacturer_ref"), dict)
        and dispatch_event.get("selected_manufacturer_ref")
        else None
    )
    requirement_class = (
        dict(dispatch_event.get("requirement_class") or {})
        if isinstance(dispatch_event.get("requirement_class"), dict)
        and dispatch_event.get("requirement_class")
        else None
    )
    recommendation_identity = (
        dict(dispatch_event.get("recommendation_identity") or {})
        if isinstance(dispatch_event.get("recommendation_identity"), dict)
        and dispatch_event.get("recommendation_identity")
        else None
    )

    event_status = str(dispatch_event.get("event_status") or "")
    if bool(dispatch_event.get("would_dispatch")):
        bridge_ready = True
        bridge_status = "bridge_ready"
        bridge_reason = "Technical dispatch bridge is ready for later transport consumption."
    elif event_status == "event_dispatch_no_recipients":
        bridge_ready = False
        bridge_status = "bridge_blocked_no_recipients"
        bridge_reason = "Technical dispatch bridge remains blocked because no recipients are available."
    elif event_status == "event_dispatch_missing_basis":
        bridge_ready = False
        bridge_status = "bridge_blocked_missing_basis"
        bridge_reason = "Technical dispatch bridge remains blocked because no dispatch basis is available."
    else:
        bridge_ready = False
        bridge_status = "bridge_blocked"
        bridge_reason = "Technical dispatch bridge remains blocked in the current runtime turn."

    return {
        "object_type": "dispatch_bridge",
        "object_version": "dispatch_bridge_v1",
        "bridge_ready": bridge_ready,
        "bridge_status": bridge_status,
        "bridge_reason": bridge_reason,
        "bridge_blockers": bridge_blockers,
        "event_id": dispatch_event.get("event_id"),
        "event_key": dispatch_event.get("event_key"),
        "trigger_status": dispatch_event.get("event_identity", {}).get("trigger_status"),
        "dry_run_status": dispatch_event.get("dry_run_status"),
        "recipient_refs": recipient_refs,
        "selected_manufacturer_ref": selected_manufacturer_ref,
        "requirement_class": requirement_class,
        "recommendation_identity": recommendation_identity,
        "bridge_payload_summary": {
            "recipient_count": len(recipient_refs),
            "requirement_class_id": str((requirement_class or {}).get("requirement_class_id") or ""),
            "candidate_id": str((recommendation_identity or {}).get("candidate_id") or ""),
        },
        "source": "dispatch_event",
    }


def build_dispatch_handoff(state: Dict[str, Any]) -> Dict[str, Any]:
    case_state: Dict[str, Any] = state.get("case_state") or {}
    sealing_state: Dict[str, Any] = state.get("sealing_state") or {}

    dispatch_bridge = case_state.get("dispatch_bridge") or sealing_state.get("dispatch_bridge") or {}
    if not isinstance(dispatch_bridge, dict) or not dispatch_bridge:
        dispatch_bridge = build_dispatch_bridge(state)

    handoff_blockers = list(
        dict.fromkeys(str(item) for item in list(dispatch_bridge.get("bridge_blockers") or []) if item)
    )
    recipient_refs = [
        dict(ref) for ref in list(dispatch_bridge.get("recipient_refs") or []) if isinstance(ref, dict) and ref
    ]
    selected_manufacturer_ref = (
        dict(dispatch_bridge.get("selected_manufacturer_ref") or {})
        if isinstance(dispatch_bridge.get("selected_manufacturer_ref"), dict)
        and dispatch_bridge.get("selected_manufacturer_ref")
        else None
    )
    requirement_class = (
        dict(dispatch_bridge.get("requirement_class") or {})
        if isinstance(dispatch_bridge.get("requirement_class"), dict)
        and dispatch_bridge.get("requirement_class")
        else None
    )
    recommendation_identity = (
        dict(dispatch_bridge.get("recommendation_identity") or {})
        if isinstance(dispatch_bridge.get("recommendation_identity"), dict)
        and dispatch_bridge.get("recommendation_identity")
        else None
    )

    bridge_status = str(dispatch_bridge.get("bridge_status") or "")
    if bool(dispatch_bridge.get("bridge_ready")):
        handoff_ready = True
        handoff_status = "handoff_ready"
        handoff_reason = "Internal dispatch handoff payload is ready for later transport consumption."
    elif bridge_status == "bridge_blocked_no_recipients":
        handoff_ready = False
        handoff_status = "handoff_blocked_no_recipients"
        handoff_reason = "Internal dispatch handoff payload remains blocked because no recipients are available."
    elif bridge_status == "bridge_blocked_missing_basis":
        handoff_ready = False
        handoff_status = "handoff_blocked_missing_basis"
        handoff_reason = "Internal dispatch handoff payload remains blocked because no bridge basis is available."
    else:
        handoff_ready = False
        handoff_status = "handoff_blocked"
        handoff_reason = "Internal dispatch handoff payload remains blocked in the current runtime turn."

    manufacturer_names = sorted(
        {
            str(ref.get("manufacturer_name") or "").strip()
            for ref in recipient_refs
            if str(ref.get("manufacturer_name") or "").strip()
        }
    )

    return {
        "object_type": "dispatch_handoff_payload",
        "object_version": "dispatch_handoff_payload_v1",
        "handoff_ready": handoff_ready,
        "handoff_status": handoff_status,
        "handoff_reason": handoff_reason,
        "handoff_blockers": handoff_blockers,
        "event_id": dispatch_bridge.get("event_id"),
        "event_key": dispatch_bridge.get("event_key"),
        "bridge_status": bridge_status,
        "recipient_refs": recipient_refs,
        "selected_manufacturer_ref": selected_manufacturer_ref,
        "requirement_class": requirement_class,
        "recommendation_identity": recommendation_identity,
        "payload_summary": {
            "recipient_count": len(recipient_refs),
            "requirement_class_id": str((requirement_class or {}).get("requirement_class_id") or ""),
            "candidate_id": str((recommendation_identity or {}).get("candidate_id") or ""),
            "manufacturer_names": manufacturer_names,
        },
        "source": "dispatch_bridge",
    }


def build_dispatch_transport_envelope(state: Dict[str, Any]) -> Dict[str, Any]:
    case_state: Dict[str, Any] = state.get("case_state") or {}
    sealing_state: Dict[str, Any] = state.get("sealing_state") or {}

    dispatch_handoff = case_state.get("dispatch_handoff") or sealing_state.get("dispatch_handoff") or {}
    if not isinstance(dispatch_handoff, dict) or not dispatch_handoff:
        dispatch_handoff = build_dispatch_handoff(state)

    envelope_blockers = list(
        dict.fromkeys(str(item) for item in list(dispatch_handoff.get("handoff_blockers") or []) if item)
    )
    recipient_refs = [
        dict(ref) for ref in list(dispatch_handoff.get("recipient_refs") or []) if isinstance(ref, dict) and ref
    ]
    selected_manufacturer_ref = (
        dict(dispatch_handoff.get("selected_manufacturer_ref") or {})
        if isinstance(dispatch_handoff.get("selected_manufacturer_ref"), dict)
        and dispatch_handoff.get("selected_manufacturer_ref")
        else None
    )
    requirement_class = (
        dict(dispatch_handoff.get("requirement_class") or {})
        if isinstance(dispatch_handoff.get("requirement_class"), dict)
        and dispatch_handoff.get("requirement_class")
        else None
    )
    recommendation_identity = (
        dict(dispatch_handoff.get("recommendation_identity") or {})
        if isinstance(dispatch_handoff.get("recommendation_identity"), dict)
        and dispatch_handoff.get("recommendation_identity")
        else None
    )

    handoff_status = str(dispatch_handoff.get("handoff_status") or "")
    if bool(dispatch_handoff.get("handoff_ready")):
        envelope_ready = True
        envelope_status = "envelope_ready"
        envelope_reason = "Internal transport envelope is ready for later sender/connector consumption."
    elif handoff_status == "handoff_blocked_no_recipients":
        envelope_ready = False
        envelope_status = "envelope_blocked_no_recipients"
        envelope_reason = "Internal transport envelope remains blocked because no recipients are available."
    elif handoff_status == "handoff_blocked_missing_basis":
        envelope_ready = False
        envelope_status = "envelope_blocked_missing_basis"
        envelope_reason = "Internal transport envelope remains blocked because no handoff basis is available."
    else:
        envelope_ready = False
        envelope_status = "envelope_blocked"
        envelope_reason = "Internal transport envelope remains blocked in the current runtime turn."

    manufacturer_names = sorted(
        {
            str(ref.get("manufacturer_name") or "").strip()
            for ref in recipient_refs
            if str(ref.get("manufacturer_name") or "").strip()
        }
    )

    return {
        "object_type": "dispatch_transport_envelope",
        "object_version": "dispatch_transport_envelope_v1",
        "envelope_ready": envelope_ready,
        "envelope_status": envelope_status,
        "envelope_reason": envelope_reason,
        "envelope_blockers": envelope_blockers,
        "event_id": dispatch_handoff.get("event_id"),
        "event_key": dispatch_handoff.get("event_key"),
        "handoff_status": handoff_status,
        "recipient_refs": recipient_refs,
        "selected_manufacturer_ref": selected_manufacturer_ref,
        "requirement_class": requirement_class,
        "recommendation_identity": recommendation_identity,
        "payload_summary": {
            "recipient_count": len(recipient_refs),
            "manufacturer_names": manufacturer_names,
            "requirement_class_id": str((requirement_class or {}).get("requirement_class_id") or ""),
            "candidate_id": str((recommendation_identity or {}).get("candidate_id") or ""),
        },
        "source": "dispatch_handoff",
    }


# ---------------------------------------------------------------------------
# Confirmed-parameter extractor (internal)
# ---------------------------------------------------------------------------

_ALLOWED_PARAMETER_KEYS = frozenset({
    "temperature_c",
    "temperature_raw",
    "pressure_bar",
    "pressure_raw",
    "medium",
    "dynamic_type",
})

_ALLOWED_DIMENSION_KEYS = frozenset({
    "shaft_diameter_mm",
    "bore_diameter_mm",
    "groove_width_mm",
    "groove_depth_mm",
    "piston_rod_diameter_mm",
})


def _extract_confirmed_parameters(asserted_state: Dict[str, Any]) -> Dict[str, Any]:
    """Pull only confirmed technical parameters from the asserted layer.

    Operating conditions (temperature/pressure/medium) come from
    asserted.operating_conditions; dimensions from asserted.machine_profile.
    No governance internals, no reasoning artefacts.
    """
    operating = asserted_state.get("operating_conditions") or {}
    machine = asserted_state.get("machine_profile") or {}

    params: Dict[str, Any] = {}
    for key in _ALLOWED_PARAMETER_KEYS:
        value = operating.get(key)
        if value is not None:
            params[key] = value

    dimensions: Dict[str, Any] = {}
    for key in _ALLOWED_DIMENSION_KEYS:
        value = machine.get(key)
        if value is not None:
            dimensions[key] = value

    result: Dict[str, Any] = {}
    if params:
        result["confirmed_parameters"] = params
    if dimensions:
        result["dimensions"] = dimensions
    return result


def _extract_qualified_material_ids(selection_state: Dict[str, Any]) -> list[str]:
    """Return the list of viable (qualified) candidate IDs from the selection layer."""
    return list(selection_state.get("viable_candidate_ids") or [])


def _extract_qualified_material_names(selection_state: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Return a minimal name-card for each viable candidate (id + family + grade)."""
    candidates: list[Dict[str, Any]] = selection_state.get("candidates") or []
    viable_ids: set[str] = set(selection_state.get("viable_candidate_ids") or [])
    result: list[Dict[str, Any]] = []
    for c in candidates:
        cid = c.get("candidate_id")
        if cid in viable_ids:
            entry: Dict[str, Any] = {"candidate_id": cid}
            if c.get("material_family"):
                entry["material_family"] = c["material_family"]
            if c.get("grade_name"):
                entry["grade_name"] = c["grade_name"]
            if c.get("manufacturer_name"):
                entry["manufacturer_name"] = c["manufacturer_name"]
            result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_handover_payload(
    sealing_state: Dict[str, Any],
    *,
    canonical_case_state: Dict[str, Any] | None = None,
    canonical_rfq_object: Dict[str, Any] | None = None,
    rfq_admissibility: str | None = None,
) -> Dict[str, Any]:
    """Build the commercial handover dict from a completed SealingAIState.

    Returns a dict with keys:
        is_handover_ready   bool
        target_system       str | None
        handover_payload    dict | None  — None when is_handover_ready is False

    The handover_payload (when present) contains:
        qualified_material_ids   list[str]
        qualified_materials      list[{candidate_id, material_family, grade_name, …}]
        confirmed_parameters     dict  (temperature, pressure, medium)
        dimensions               dict  (optional, only when present in asserted)
        rfq_admissibility        str   ("ready" when rfq_ready)

    What is NEVER included:
        gate_failures, conflicts, unknowns_*, cycle state,
        raw LLM claims, observed/normalized internals,
        demo_data flags, HITL review fields, reasoning artefacts.
    """
    governance_state, review_state = _resolve_handover_shell_inputs(
        sealing_state=sealing_state,
        canonical_case_state=canonical_case_state,
    )
    canonical_case_state = dict(canonical_case_state or {})
    canonical_rfq_state = dict(canonical_case_state.get("rfq_state") or {})
    raw_handover = dict(sealing_state.get("handover") or {})
    selection_state: Dict[str, Any] = sealing_state.get("selection") or {}
    asserted_state: Dict[str, Any] = sealing_state.get("asserted") or {}

    handover_ready = _is_handover_ready(governance_state, review_state)
    handover_status, handover_reason = _project_handover_status(
        governance_state,
        review_state,
        selection_state,
    )

    if handover_ready is False:
        return {
            "is_handover_ready": False,
            "handover_status": handover_status,
            "handover_reason": handover_reason,
            "target_system": None,
            "handover_payload": None,
        }

    if not canonical_rfq_object and canonical_rfq_state.get("rfq_object"):
        canonical_rfq_object = dict(canonical_rfq_state.get("rfq_object") or {})

    resolved_rfq_admissibility = rfq_admissibility or governance_state.get("rfq_admissibility", "ready")
    target_system = "rfq_portal"

    if canonical_rfq_object:
        canonical_basis = build_handover_payload_basis_from_rfq_object(
            canonical_rfq_object,
            rfq_admissibility=resolved_rfq_admissibility,
        )
        payload = dict(canonical_basis.get("handover_payload") or {})
        target_system = str(canonical_basis.get("target_system") or target_system)
    else:
        # Build clean order-profile — no internals leak past this line
        material_ids = _extract_qualified_material_ids(selection_state)
        material_names = _extract_qualified_material_names(selection_state)
        param_block = _extract_confirmed_parameters(asserted_state)

        payload = {
            "qualified_material_ids": material_ids,
            "qualified_materials": material_names,
            "rfq_admissibility": resolved_rfq_admissibility,
        }
        payload.update(param_block)
    handover = {
        "is_handover_ready": True,
        "handover_status": handover_status,
        "handover_reason": handover_reason,
        "target_system": target_system,   # default; overrideable by future routing logic
        "handover_payload": payload,
    }
    if canonical_rfq_state.get("rfq_confirmed") is not None:
        handover["rfq_confirmed"] = bool(canonical_rfq_state.get("rfq_confirmed"))
    elif raw_handover.get("rfq_confirmed") is not None:
        handover["rfq_confirmed"] = bool(raw_handover.get("rfq_confirmed"))

    if canonical_rfq_state.get("rfq_handover_initiated") is not None:
        handover["handover_completed"] = bool(canonical_rfq_state.get("rfq_handover_initiated"))
    elif raw_handover.get("handover_completed") is not None:
        handover["handover_completed"] = bool(raw_handover.get("handover_completed"))

    if canonical_rfq_state.get("rfq_html_report_present") is not None:
        handover["rfq_html_report_present"] = bool(canonical_rfq_state.get("rfq_html_report_present"))
    elif raw_handover.get("rfq_html_report_present") is not None:
        handover["rfq_html_report_present"] = bool(raw_handover.get("rfq_html_report_present"))
    elif raw_handover.get("rfq_html_report") is not None:
        handover["rfq_html_report_present"] = bool(raw_handover.get("rfq_html_report"))

    if raw_handover.get("rfq_html_report") is not None:
        handover["rfq_html_report"] = raw_handover.get("rfq_html_report")

    return handover


def build_handover_payload_basis_from_rfq_object(
    rfq_object: Dict[str, Any] | None,
    *,
    rfq_admissibility: str | None,
) -> Dict[str, Any]:
    """Return the bounded non-body handover payload basis from canonical rfq_object.

    This bridge is intentionally narrow:
    - only non-body, handover-facing payload basis fields
    - no RFQ HTML body authority
    - no dispatch or transport authority
    """
    basis = dict(rfq_object or {})
    payload: Dict[str, Any] = {
        "qualified_material_ids": list(basis.get("qualified_material_ids") or []),
        "qualified_materials": list(basis.get("qualified_materials") or []),
        "confirmed_parameters": dict(basis.get("confirmed_parameters") or {}),
        "dimensions": dict(basis.get("dimensions") or {}),
        "rfq_admissibility": rfq_admissibility or "ready",
    }
    return {
        "handover_payload": payload,
        "target_system": basis.get("target_system"),
    }
