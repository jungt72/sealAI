# backend/app/langgraph/nodes/discovery_intake.py
from __future__ import annotations
from typing import Any, Dict
from app.langgraph.state import (
    SealAIState,
    compute_requirements_coverage,
    merge_rwd_requirements,
    sanitize_rwd_requirements,
    validate_slots,
)

def discovery_intake(state: SealAIState) -> Dict[str, Any]:
    slots = validate_slots(state.get("slots") or {})
    incoming = slots.get("rwd_requirements")
    sanitized = sanitize_rwd_requirements(incoming)
    merged = merge_rwd_requirements(state.get("rwd_requirements"), sanitized)
    updates: Dict[str, Any] = {"slots": slots}
    if merged:
        coverage = compute_requirements_coverage(merged)
        updates["rwd_requirements"] = merged
        updates["requirements_coverage"] = coverage
    return updates
