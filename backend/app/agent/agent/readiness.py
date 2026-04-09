from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional


def has_confirmed_core_params(asserted_state: Optional[Dict[str, Any]]) -> bool:
    as_ = asserted_state or {}
    oc = as_.get("operating_conditions") or {}
    return bool(
        (as_.get("medium_profile") or {}).get("name")
        and oc.get("pressure") is not None
        and oc.get("temperature") is not None
    )


def is_sufficient_for_structured(asserted_state: Optional[Dict[str, Any]]) -> bool:
    return has_confirmed_core_params(asserted_state)


def _governance_projection_blocks_output(governance_state: Dict[str, Any]) -> bool:
    if governance_state.get("release_status") != "rfq_ready":
        return True
    if governance_state.get("rfq_admissibility") != "ready":
        return True
    if governance_state.get("specificity_level") != "compound_required":
        return True
    if governance_state.get("unknowns_release_blocking"):
        return True
    if governance_state.get("gate_failures"):
        return True
    return any(str(conflict.get("severity") or "").upper() in {"CRITICAL", "BLOCKING_UNKNOWN"} for conflict in governance_state.get("conflicts", []))


def is_releasable(
    asserted_state: Optional[Dict[str, Any]],
    governance_state: Optional[Dict[str, Any]],
) -> bool:
    if not is_sufficient_for_structured(asserted_state):
        return False
    return not _governance_projection_blocks_output(governance_state or {})


OutputReadinessStatus = Literal[
    "releasable",
    "insufficient_inputs",
    "governance_blocked",
    "review_pending",
    "evidence_missing",
    "demo_data_quarantine",
    "conflict_unresolved",
    "integrity_unusable",
    "domain_scope_blocked",
]

EvidenceProvenanceStatus = Literal[
    "no_evidence",
    "thin_evidence",
    "grounded_evidence",
]

ReviewEscalationStatus = Literal[
    "releasable",
    "review_pending",
    "escalation_needed",
    "ambiguous_but_reviewable",
    "withheld_no_evidence",
    "withheld_demo_data",
    "withheld_missing_core_inputs",
]


@dataclass(frozen=True)
class OutputReadinessDecision:
    releasable: bool
    status: OutputReadinessStatus
    blocking_reason: str


def evaluate_output_readiness(
    asserted_state: Optional[Dict[str, Any]],
    governance_state: Optional[Dict[str, Any]],
    *,
    review_state: Optional[Dict[str, Any]] = None,
    evidence_available: bool = True,
    demo_data_present: bool = False,
    conflict_status_projection: Optional[Dict[str, Any]] = None,
    parameter_integrity_projection: Optional[Dict[str, Any]] = None,
    domain_scope_projection: Optional[Dict[str, Any]] = None,
) -> OutputReadinessDecision:
    if not is_sufficient_for_structured(asserted_state):
        return OutputReadinessDecision(
            releasable=False,
            status="insufficient_inputs",
            blocking_reason=(
                "Required core params (medium, pressure, temperature) "
                "not yet confirmed in asserted_state."
            ),
        )

    if demo_data_present:
        return OutputReadinessDecision(
            releasable=False,
            status="demo_data_quarantine",
            blocking_reason=(
                "Demo data is in scope — governed output quarantined "
                "until real evidence is available."
            ),
        )

    if not evidence_available:
        return OutputReadinessDecision(
            releasable=False,
            status="evidence_missing",
            blocking_reason=(
                "Evidence basis not available — governed output cannot be "
                "released without qualified evidence."
            ),
        )

    if parameter_integrity_projection and not parameter_integrity_projection.get("usable_for_structured_step", True):
        return OutputReadinessDecision(
            releasable=False,
            status="integrity_unusable",
            blocking_reason=(
                "Parameter integrity is not sufficient for structured use — "
                "unit, normalization, or plausibility clarification is required."
            ),
        )

    if domain_scope_projection and not domain_scope_projection.get("usable_for_governed_step", True):
        return OutputReadinessDecision(
            releasable=False,
            status="domain_scope_blocked",
            blocking_reason=(
                "Domain thresholds or scope gates block governed output — "
                "the current case is outside the deterministic recommendation scope."
            ),
        )

    if (conflict_status_projection or {}).get("conflict_still_open"):
        return OutputReadinessDecision(
            releasable=False,
            status="conflict_unresolved",
            blocking_reason=(
                "Parameter conflict remains open — governed output cannot be "
                "released until the conflicting value is clarified."
            ),
        )

    review = review_state or {}
    if review.get("review_required"):
        reason = review.get("review_reason") or "not specified"
        return OutputReadinessDecision(
            releasable=False,
            status="review_pending",
            blocking_reason=f"HITL review pending — {reason}",
        )

    if _governance_projection_blocks_output(governance_state or {}):
        return OutputReadinessDecision(
            releasable=False,
            status="governance_blocked",
            blocking_reason=(
                "Governance projection blocks output (release_status, "
                "gate_failures, or blocking unknowns)."
            ),
        )

    return OutputReadinessDecision(
        releasable=True,
        status="releasable",
        blocking_reason="",
    )


CaseReadinessStatus = Literal[
    "incomplete",
    "sufficient_but_blocked",
    "releasable",
    "handover_ready",
]


def project_case_readiness(
    asserted_state: Optional[Dict[str, Any]],
    governance_state: Optional[Dict[str, Any]],
    *,
    review_state: Optional[Dict[str, Any]] = None,
    evidence_available: bool = True,
    demo_data_present: bool = False,
) -> CaseReadinessStatus:
    if not is_sufficient_for_structured(asserted_state):
        return "incomplete"

    decision = evaluate_output_readiness(
        asserted_state,
        governance_state,
        review_state=review_state,
        evidence_available=evidence_available,
        demo_data_present=demo_data_present,
    )

    if not decision.releasable:
        if decision.status == "review_pending":
            review = review_state or {}
            if review.get("review_state") == "approved":
                return "handover_ready"
            return "sufficient_but_blocked"
        return "sufficient_but_blocked"

    review = review_state or {}
    review_required = review.get("review_required", False)
    review_resolved = review.get("review_state") in ("approved", "none")
    if review_required and not review_resolved:
        return "releasable"

    return "handover_ready"
