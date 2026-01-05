"""
Improved Confidence Gate with Self-Critique Loop.
Routes to challenger for revision when confidence is below threshold.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from app.langgraph.state import SealAIState

logger = logging.getLogger(__name__)


def _min_confidence() -> float:
    """Minimum confidence threshold for approval."""
    try:
        return float(os.getenv("CONFIDENCE_GATE_MIN", "0.8"))
    except ValueError:
        return 0.8


def _max_review_loops() -> int:
    """Maximum number of review/revision loops before forcing approval."""
    try:
        return int(os.getenv("CONFIDENCE_GATE_MAX_LOOPS", "3"))
    except ValueError:
        return 3


def _extract_confidence(state: SealAIState) -> float:
    """
    Extract confidence score from state.
    Checks multiple locations: routing.confidence, checklist_result.confidence, or fallback.
    """
    # Check routing first
    routing = state.get("routing") or {}
    if "confidence" in routing:
        try:
            return float(routing["confidence"])
        except (TypeError, ValueError):
            pass
    
    # Check slots.checklist_result
    slots = state.get("slots") or {}
    checklist = slots.get("checklist_result") or {}
    if "confidence" in checklist:
        try:
            return float(checklist["confidence"])
        except (TypeError, ValueError):
            pass
    
    # Fallback to top-level confidence
    try:
        return float(state.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _extract_approved(state: SealAIState) -> bool:
    """Extract approval status from checklist_result."""
    slots = state.get("slots") or {}
    checklist = slots.get("checklist_result") or {}
    return bool(checklist.get("approved", False))


def confidence_gate_node(state: SealAIState) -> Dict[str, Any]:
    """
    Confidence Gate Node with Self-Critique Loop.
    
    Logic:
    - If confidence >= threshold AND approved: route to "approved"
    - If confidence < threshold AND loops < max: route to "needs_critique" (Challenger)
    - If loops >= max: force route to "force_approved" (prevent infinite loops)
    - If not approved but confidence ok: route to "needs_critique"
    
    Returns state updates with routing decision.
    """
    confidence = _extract_confidence(state)
    approved = _extract_approved(state)
    loops = int(state.get("review_loops", 0))
    min_conf = _min_confidence()
    max_loops = _max_review_loops()
    
    logger.info(
        f"Confidence Gate: confidence={confidence:.2f}, approved={approved}, "
        f"loops={loops}/{max_loops}, threshold={min_conf}"
    )
    
    # Decision logic
    if confidence >= min_conf and approved:
        decision = "approved"
        logger.info("✅ Confidence gate PASSED - routing to final output")
    elif loops >= max_loops:
        decision = "force_approved"
        logger.warning(
            f"⚠️ Max review loops ({max_loops}) reached - forcing approval despite "
            f"low confidence ({confidence:.2f})"
        )
    else:
        decision = "needs_critique"
        loops += 1
        logger.info(
            f"🔄 Confidence below threshold or not approved - routing to Challenger "
            f"(loop {loops}/{max_loops})"
        )
    
    updates: Dict[str, Any] = {
        "confidence": confidence,
        "review_loops": loops,
        "confidence_decision": decision,
    }
    
    # Update phase for tracking
    if decision == "needs_critique":
        updates["phase"] = "critique"
    elif decision in ("approved", "force_approved"):
        updates["phase"] = "finalized"
    
    return updates


def route_after_confidence_gate(state: SealAIState) -> str:
    """
    Routing function for conditional edges after confidence_gate_node.
    
    Returns:
        - "approved": Continue to final output
        - "needs_critique": Route to Challenger for revision
        - "force_approved": Force continue despite low confidence
    """
    decision = state.get("confidence_decision", "approved")
    
    if decision == "needs_critique":
        return "challenger"
    elif decision == "force_approved":
        return "force_approved"
    else:
        return "approved"


__all__ = ["confidence_gate_node", "route_after_confidence_gate"]
