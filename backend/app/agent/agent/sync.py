"""Read-model projection helpers for the active agent runtime.

RWDR domain logic must stay in the dedicated RWDR modules:
- `domain/rwdr_core.py` for deterministic derivation
- `domain/rwdr_decision.py` for deterministic output decisions
- `agent/rwdr_orchestration.py` for flow control

This module is projection-only. It may reshape runtime state for API/stream/UI
consumers, but it must never compute new RWDR engineering results.
"""

from typing import Any, Dict


def _model_to_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def project_rwdr_output(rwdr_state: Dict[str, Any] | None) -> Any:
    """Return the structured RWDR output payload if present."""
    if not rwdr_state:
        return None
    return _model_to_payload(rwdr_state.get("output"))


def project_rwdr_read_model(rwdr_state: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Project the active RWDR runtime slice into a stable read model."""
    if not rwdr_state:
        return None

    rwdr_flow = rwdr_state.get("flow", {}) or {}
    return {
        "active": rwdr_flow.get("active", False),
        "stage": rwdr_flow.get("stage"),
        "missing_fields": list(rwdr_flow.get("missing_fields", [])),
        "next_field": rwdr_flow.get("next_field"),
        "ready_for_decision": rwdr_flow.get("ready_for_decision", False),
        "decision_executed": rwdr_flow.get("decision_executed", False),
        "draft": _model_to_payload(rwdr_state.get("draft")),
        "input": _model_to_payload(rwdr_state.get("input")),
        "derived": _model_to_payload(rwdr_state.get("derived")),
        "output": project_rwdr_output(rwdr_state),
    }

def sync_working_profile_to_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synchronisiert das working_profile mit dem sealing_state und generiert das LiveCalcTile (Phase H8).
    Wird nach jedem Agent-Turn oder manuellen User-Update (PATCH) aufgerufen.
    """
    wp = state.get("working_profile", {})
    ss = state.get("sealing_state", {})
    
    if ss:
        if "asserted" not in ss: ss["asserted"] = {}
        if "machine_profile" not in ss["asserted"]: ss["asserted"]["machine_profile"] = {}
        
        # Wave 1: Upstream Sync von working_profile nach asserted wurde entfernt.
        # Heuristische Daten aus wp dürfen nicht mehr direkt in ss["asserted"] schreiben.
        pass

    # Rück-Synchronisation von Asserted nach Working (Phase K17 - LLM as Truth)
    if ss.get("asserted"):
        # Medium
        mp = ss["asserted"].get("medium_profile", {})
        if mp.get("name"): wp["medium"] = mp["name"]
        
        # Machine / Material
        mapr = ss["asserted"].get("machine_profile", {})
        if mapr.get("material"): wp["material"] = mapr["material"]
        
        # Operating Conditions
        oc = ss["asserted"].get("operating_conditions", {})
        if oc.get("pressure"): wp["pressure"] = oc["pressure"]
        if oc.get("temperature"): wp["temperature"] = oc["temperature"]

    # Erzeuge LiveCalcTile Mapping für das Frontend (Phase H8 Sync)
    live_calc_tile = {
        "v_surface_m_s": wp.get("v_m_s"),
        "pv_value_mpa_m_s": round(wp.get("pv_value", 0) / 10.0, 3) if wp.get("pv_value") else None,
        "status": "ok" if wp.get("v_m_s") else "insufficient_data",
        "parameters": {
            "speed": wp.get("speed"),
            "diameter": wp.get("diameter"),
            "pressure": wp.get("pressure"),
            "temperature": wp.get("temperature"),
            "medium": wp.get("medium"),
            "eccentricity": wp.get("eccentricity"),
            "material": wp.get("material"),
            "seal_material": wp.get("seal_material")
        },
        "risk_warning": wp.get("risk_warning"),
        "alternatives": wp.get("alternatives")
    }

    # --- CHEMISCHE BESTÄNDIGKEIT (Phase K18 KI-gesteuert) ---
    # 1. KI-Bewertung aus dem Asserted State (LLM/Claims) hat IMMER Vorrang
    medium_profile = ss.get("asserted", {}).get("medium_profile", {})
    rating = medium_profile.get("resistance_rating")
    swelling = medium_profile.get("expected_swelling")
    notes = medium_profile.get("resistance_notes")

    # 2. Wenn kein Medium erkannt wurde (Phase K18 Message)
    if not wp.get("medium"):
        notes = "Bitte Medium im Chat nennen (z.B. Schokolade)."
        rating = "N/A"
        swelling = "N/A"
    elif not rating:
        # Medium ist da, aber noch keine KI-Bewertung im Asserted State
        rating = "..."
        swelling = "..."
        notes = f"KI-Gutachter bewertet Beständigkeit für {wp.get('medium')}..."

    # 3. Sicherstellen, dass das Tile niemals leer ist
    live_calc_tile["chemical_resistance"] = {
        "rating": rating,
        "swelling": swelling,
        "temp_limit": "Materialspezifisch",
        "notes": notes
    }

    wp["live_calc_tile"] = live_calc_tile

    rwdr_projection = project_rwdr_read_model(ss.get("rwdr"))
    if rwdr_projection is not None:
        wp["rwdr"] = rwdr_projection
    else:
        wp.pop("rwdr", None)
    
    return state
