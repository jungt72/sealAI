"""
SSoT Parameter Router — Blueprint Section 13

Maps flat UI parameter patches to the deep SSoT sealing_state layers.
No LLM. Pure deterministic routing and staleness bookkeeping.

Exports
-------
PARAM_TO_ASSERTED_SUB  – routing table (field → asserted sub-dict name)
MEDIUM_ALIASES         – partial German→English normalization
route_patch_to_ssot()  – main entry point (returns deep-copied updated state)
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

# ---------------------------------------------------------------------------
# Routing table: WorkingProfile key → sealing_state['asserted'] sub-dict
# Fields absent from this table are written to working_profile only
# (no asserted sub-dict equivalent — safe, they don't affect gate checks).
# ---------------------------------------------------------------------------
PARAM_TO_ASSERTED_SUB: dict[str, str] = {
    # operating_conditions
    "pressure_bar":           "operating_conditions",
    "pressure_raw":           "operating_conditions",
    "temperature_c":          "operating_conditions",
    "temperature_C":          "operating_conditions",
    "temperature_max_c":      "operating_conditions",  # Frontend alias
    "temperature_raw":        "operating_conditions",
    "pressure_max_bar":       "operating_conditions",
    "pressure_min_bar":       "operating_conditions",
    # machine_profile
    "shaft_diameter_mm":      "machine_profile",
    "shaft_diameter":         "machine_profile",       # Frontend alias
    "bore_diameter_mm":       "machine_profile",
    "piston_rod_diameter_mm": "machine_profile",
    "groove_width_mm":        "machine_profile",
    "groove_depth_mm":        "machine_profile",
    "rpm":                    "machine_profile",       # Frontend alias
    "speed_rpm":              "machine_profile",       # Frontend alias
    "shaft_runout_mm":        "machine_profile",
    "shaft_hardness_hrc":     "machine_profile",
    # medium_profile
    "medium":                 "medium_profile",
    "medium_detail":          "medium_profile",
    "medium_type":            "medium_profile",
    "medium_additives":       "medium_profile",
    "medium_viscosity":       "medium_profile",
    # installation_profile
    "dynamic_type":           "installation_profile",
    # Fields below are working_profile-only (no asserted sub-dict):
    # material, flange_standard, emission_class, industry_sector → omitted here
}

# ---------------------------------------------------------------------------
# Partial medium normalization — German user input → canonical English key
# used by downstream gate checks (case-sensitive exact match).
# Full normalization pipeline is Sprint 11+ work.
# ---------------------------------------------------------------------------
MEDIUM_ALIASES: dict[str, str] = {
    "wasser":       "water",
    "öl":           "oil",
    "oel":          "oil",
    "hydrauliköl":  "hydraulic_oil",
    "hydraulikoel": "hydraulic_oil",
    "kraftstoff":   "fuel",
    "benzin":       "fuel_gasoline",
    "diesel":       "fuel_diesel",
    "luft":         "air",
    "stickstoff":   "nitrogen",
    "dampf":        "steam",
    "säure":        "acid",
    "lauge":        "alkali",
}


def route_patch_to_ssot(patch: dict[str, Any], ssot_state: Any) -> Any:
    """Apply a flat parameter patch to the SSoT state and return an updated copy.

    Writes
    ------
    - sealing_state['asserted'][<sub>][field]  for fields in PARAM_TO_ASSERTED_SUB
    - agent_state['working_profile'][field]     always (flat mirror for frontend)

    Staleness obligations (Blueprint §13)
    --------------------------------------
    - sealing_state['handover']['rfq_confirmed']  = False
    - sealing_state['handover']['rfq_html_report'] = None
    - sealing_state['cycle']['state_revision']    += 1

    Parameters
    ----------
    patch:      Sanitized dict of {field: value} to apply.
    ssot_state: Current AgentState dict (not mutated).

    Returns
    -------
    Deep-copied AgentState with the patch applied.
    """
    updated: dict[str, Any] = deepcopy(dict(ssot_state))
    sealing: dict[str, Any] = dict(updated.get("sealing_state") or {})
    asserted: dict[str, Any] = dict(sealing.get("asserted") or {})
    flat_wp: dict[str, Any] = dict(updated.get("working_profile") or {})

    for field, value in patch.items():
        # Partial normalization for medium field
        if field == "medium" and isinstance(value, str):
            value = MEDIUM_ALIASES.get(value.lower(), value)

        sub = PARAM_TO_ASSERTED_SUB.get(field)
        if sub:
            sub_dict: dict[str, Any] = dict(asserted.get(sub) or {})
            sub_dict[field] = value
            asserted[sub] = sub_dict

        # Always mirror to flat working_profile
        flat_wp[field] = value

    # ── Staleness obligations ────────────────────────────────────────────────
    cycle: dict[str, Any] = dict(sealing.get("cycle") or {})
    cycle["state_revision"] = int(cycle.get("state_revision") or 0) + 1

    handover: dict[str, Any] = dict(sealing.get("handover") or {})
    handover["rfq_confirmed"] = False
    handover["rfq_html_report"] = None

    # ── Write back ───────────────────────────────────────────────────────────
    sealing["asserted"] = asserted
    sealing["cycle"] = cycle
    sealing["handover"] = handover
    updated["sealing_state"] = sealing
    updated["working_profile"] = flat_wp

    return updated
