"""
HITL Review Trigger — Phase A3.

Rules are deterministic Python — the LLM never decides whether a review is needed.

Trigger conditions (evaluated in priority order):
1. release_status == "manufacturer_validation_required"
   → Review required: Hersteller-Validierung erforderlich.
2. demo_data_in_scope == True (registry quarantine, Phase 0B.1)
   → Review required: Demo-Daten im Scope.

The returned dict is safe to merge into SealingAIState["review"].
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Human-readable trigger reasons (deterministic constants, never LLM text)
REASON_MANUFACTURER_VALIDATION = (
    "Hersteller-Validierung erforderlich — release_status ist manufacturer_validation_required."
)
REASON_DEMO_DATA = (
    "Demo-Daten im Scope — governe Materialdaten nicht vorhanden (Registry quarantined)."
)


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
        demo_data_in_scope: Flag from MaterialQualificationCoreOutput (Phase 0B.1).

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
