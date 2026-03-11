from typing import Dict, Any

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
    
    return state
