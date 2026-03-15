from typing import Dict, Optional
from app.agent.domain.normalization import normalize_material, normalize_medium_id

def normalize_entity(entity_type: str, user_input: str) -> str:
    """
    Normalizes user input for materials and media into canonical service-layer IDs.
    Example: 'Viton' -> 'FKM', 'Bio-Öl' -> 'hees', 'HLP' -> 'hlp'.

    0B.3b: medium now uses normalize_medium_id() to restore the technical
    service-/knowledge-layer lookup contract broken by 0B.3a.
    material continues to use normalize_material() (uppercase canonical IDs).
    """
    if not user_input:
        return ""

    if entity_type == "material":
        norm = normalize_material(user_input)
        return norm or user_input
    elif entity_type == "medium":
        norm = normalize_medium_id(user_input)
        return norm or user_input

    return user_input.strip().lower()
