"""
Commercial / Handover Layer — Phase A6.

Deterministic boundary between the technical qualification result and the
downstream commercial process (RFQ portal, ERP, shop, etc.).

Rules:
- build_handover_payload() reads from the completed SealingAIState.
- is_handover_ready = True IFF governance.release_status == "rfq_ready"
  AND review.review_required is not True (no pending HITL review).
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

from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Readiness check (deterministic)
# ---------------------------------------------------------------------------

def _is_handover_ready(
    governance_state: Dict[str, Any],
    review_state: Dict[str, Any],
) -> bool:
    """Return True only when the case is technically qualified and has no pending review.

    Conditions (both must hold):
    1. governance.release_status == "rfq_ready"
    2. review.review_required is not True
    """
    release_status: str = governance_state.get("release_status", "inadmissible")
    review_required: bool = bool(review_state.get("review_required", False))
    return release_status == "rfq_ready" and not review_required


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

def build_handover_payload(sealing_state: Dict[str, Any]) -> Dict[str, Any]:
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
    governance_state: Dict[str, Any] = sealing_state.get("governance") or {}
    review_state: Dict[str, Any] = sealing_state.get("review") or {}
    selection_state: Dict[str, Any] = sealing_state.get("selection") or {}
    asserted_state: Dict[str, Any] = sealing_state.get("asserted") or {}

    ready = _is_handover_ready(governance_state, review_state)

    if not ready:
        return {
            "is_handover_ready": False,
            "target_system": None,
            "handover_payload": None,
        }

    # Build clean order-profile — no internals leak past this line
    material_ids = _extract_qualified_material_ids(selection_state)
    material_names = _extract_qualified_material_names(selection_state)
    param_block = _extract_confirmed_parameters(asserted_state)

    payload: Dict[str, Any] = {
        "qualified_material_ids": material_ids,
        "qualified_materials": material_names,
        "rfq_admissibility": governance_state.get("rfq_admissibility", "ready"),
    }
    payload.update(param_block)

    return {
        "is_handover_ready": True,
        "target_system": "rfq_portal",   # default; overrideable by future routing logic
        "handover_payload": payload,
    }
