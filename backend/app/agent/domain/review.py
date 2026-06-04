"""
HITL Review Trigger.

Rules are deterministic Python — the LLM never decides whether a review is needed.

Trigger conditions (evaluated in priority order):
1. release_status == "manufacturer_validation_required"
   → Review required: Hersteller-Validierung erforderlich.
2. demo_data_in_scope == True
   → Review required: Demo-Daten im Scope.

The returned dict is safe to merge into SealingAIState["review"].
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.agent.domain.critical_review import (
    CriticalReviewGovernanceSummary,
    CriticalReviewMatchingPackage,
    CriticalReviewRecommendationPackage,
    CriticalReviewRfqBasis,
    CriticalReviewSpecialistInput,
    critical_review_result_to_dict,
    run_critical_review_specialist,
)

# Human-readable trigger reasons (deterministic constants, never LLM text)
REASON_MANUFACTURER_VALIDATION = (
    "Hersteller-Validierung erforderlich — release_status ist manufacturer_validation_required."
)
REASON_DEMO_DATA = (
    "Datenbestand enthält nur Demo-/Referenzmaterial — keine produktiv freigegebenen Materialdaten vorhanden."
)


def _append_unique(items: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def evaluate_review_trigger(
    *,
    governance_state: Dict[str, Any],
    demo_data_in_scope: bool = False,
) -> Dict[str, Any]:
    """Return a ReviewLayer dict with review_required / review_state / review_reason set.

    Precedence: manufacturer_validation_required > demo_data_in_scope.

    If neither trigger fires, returns a clean "none" state.

    Args:
        governance_state: The GovernanceLayer dict from SealingAIState.
        demo_data_in_scope: Flag from the material registry (True when only demo data is available).

    Returns:
        Dict suitable for SealingAIState["review"].  Never raises.
    """
    release_status: str = governance_state.get("release_status", "inadmissible")

    if release_status == "manufacturer_validation_required":
        return {
            "review_required": True,
            "review_state": "pending",
            "review_reason": REASON_MANUFACTURER_VALIDATION,
            "reviewed_by": None,
            "review_decision": None,
            "review_note": None,
        }

    if demo_data_in_scope:
        return {
            "review_required": True,
            "review_state": "pending",
            "review_reason": REASON_DEMO_DATA,
            "reviewed_by": None,
            "review_decision": None,
            "review_note": None,
        }

    return {
        "review_required": False,
        "review_state": "none",
        "review_reason": "",
        "reviewed_by": None,
        "review_decision": None,
        "review_note": None,
    }


def evaluate_critical_review(
    *,
    governance_state: Dict[str, Any],
    review_state: Optional[Dict[str, Any]] = None,
    matching_outcome: Optional[Dict[str, Any]] = None,
    requirement_class: Optional[Dict[str, Any]] = None,
    rfq_object: Optional[Dict[str, Any]] = None,
    recipient_refs: Optional[list[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compatibility wrapper around the bounded critical-review specialist."""
    governance_state = dict(governance_state or {})
    review_state = dict(review_state or {})
    matching_outcome = dict(matching_outcome or {})
    requirement_class = dict(requirement_class or {})
    rfq_object = dict(rfq_object or {})
    result = run_critical_review_specialist(
        CriticalReviewSpecialistInput(
            governance_summary=CriticalReviewGovernanceSummary(
                release_status=str(governance_state.get("release_status") or "inadmissible"),
                rfq_admissibility=str(governance_state.get("rfq_admissibility") or "inadmissible"),
                unknowns_release_blocking=tuple(
                    str(item)
                    for item in list(governance_state.get("unknowns_release_blocking") or [])
                    if item is not None
                ),
                unknowns_manufacturer_validation=tuple(
                    str(item)
                    for item in list(governance_state.get("unknowns_manufacturer_validation") or [])
                    if item is not None
                ),
                scope_of_validity=tuple(
                    str(item)
                    for item in list(governance_state.get("scope_of_validity") or [])
                    if item is not None
                ),
                conflicts=tuple(
                    str(item)
                    for item in list(governance_state.get("conflicts") or [])
                    if item is not None
                ),
                review_required=bool(review_state.get("review_required", False)),
            ),
            recommendation_package=CriticalReviewRecommendationPackage(
                requirement_class=requirement_class or None,
            ),
            matching_package=CriticalReviewMatchingPackage(
                status=str(matching_outcome.get("status") or ""),
                selected_manufacturer_ref=dict(matching_outcome.get("selected_manufacturer_ref") or {}) or None,
            ),
            rfq_basis=CriticalReviewRfqBasis(
                rfq_object=rfq_object or None,
                recipient_refs=tuple(
                    dict(ref)
                    for ref in list(recipient_refs or [])
                    if isinstance(ref, dict) and ref
                ),
            ),
        )
    )
    return critical_review_result_to_dict(result)
