from typing import Dict

_MATERIAL_SYNONYMS: Dict[str, str] = {
    "viton": "fkm",
    "nitril": "nbr",
    "teflon": "ptfe",
    "perfluorelastomer": "ffkm",
}

_MEDIUM_SYNONYMS: Dict[str, str] = {
    "bio-öl": "hees",
    "panolin": "hees",
    "ester": "hees",
    "mineralöl": "hlp",
    "hydrauliköl": "hlp",
    "öl": "hlp",
    "water": "wasser",
}

def normalize_entity(entity_type: str, user_input: str) -> str:
    """
    Normalizes user input for materials and media into canonical IDs.
    Example: 'Viton' -> 'fkm', 'Bio-Öl' -> 'hees'.
    """
    if not user_input:
        return ""
    
    val = user_input.strip().lower()
    
    if entity_type == "material":
        return _MATERIAL_SYNONYMS.get(val, val)
    elif entity_type == "medium":
        return _MEDIUM_SYNONYMS.get(val, val)
    
    return val
