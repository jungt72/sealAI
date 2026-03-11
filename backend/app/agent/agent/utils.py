from typing import Dict, Any

def validate_material_risk(working_profile: Dict[str, Any]) -> str:
    """
    Validiert das Material-Risiko basierend auf Druck und Material.
    Wenn Druck > 200 bar UND Material == PTFE, wird eine Warnung generiert.
    """
    pressure = working_profile.get("pressure", 0)
    material = working_profile.get("material", "").upper()
    
    if pressure > 200 and "PTFE" in material:
        return "Material Risk: Hoher Druck (> 200 bar) bei PTFE-Dichtung festgestellt!"
    
    return ""
