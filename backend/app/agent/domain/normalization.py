import re
from typing import Dict, Optional, Tuple, Any, List
from app.agent.domain.parameters import PhysicalParameter

# Centralized Mapping Tables
_MATERIAL_SYNONYMS: Dict[str, str] = {
    "viton": "FKM",
    "nitril": "NBR",
    "teflon": "PTFE",
    "perfluorelastomer": "FFKM",
    "kalrez": "FFKM",
    "fkm": "FKM",
    "ptfe": "PTFE",
    "nbr": "NBR",
    "epdm": "EPDM",
    "silikon": "SILIKON",
    "silicone": "SILIKON",
}

_MEDIUM_SYNONYMS: Dict[str, str] = {
    "wasser": "Wasser",
    "water": "Wasser",
    "öl": "Öl",
    "oil": "Öl",
    "mineralöl": "Öl",
    "hydrauliköl": "Öl",
    "bio-öl": "Bio-Öl",
    "panolin": "Bio-Öl",
    "ester": "Bio-Öl",
    "hees": "Bio-Öl",
    "hlp": "Öl",
}

# Technical service-layer IDs for knowledge/retrieval lookups.
# Specific synonyms only — no generic fallback to avoid false normalizations.
_MEDIUM_ID_MAP: Dict[str, str] = {
    "bio-öl": "hees",
    "panolin": "hees",
    "ester": "hees",
    "hees": "hees",
    "mineralöl": "hlp",
    "hydrauliköl": "hlp",
    "öl": "hlp",
    "oil": "hlp",
    "hlp": "hlp",
    "wasser": "wasser",
    "water": "wasser",
}

# Consolidated Regex Patterns
_PATTERNS = {
    "temperature": re.compile(r"(\d+(?:[.,]\d+)?)\s*(c|f|grad|°c|°f)", re.I),
    "pressure": re.compile(r"(\d+(?:[.,]\d+)?)\s*(bar|psi|mpa)", re.I),
    "diameter": re.compile(r"(?:durchmesser|diameter)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(mm|millimeter)?|(\d+(?:[.,]\d+)?)\s*(mm|millimeter)", re.I),
    "speed": re.compile(r"(?:drehzahl|speed)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(rpm|u/min|1/min)?|(\d+(?:[.,]\d+)?)\s*(rpm|u/min|1/min)", re.I),
    "medium_water": re.compile(r"\b(wasser|water)\b", re.I),
    "medium_oil": re.compile(r"\b(öl|oil)\b", re.I),
}

def normalize_material(name: Optional[str]) -> Optional[str]:
    """Normalizes material name to canonical ID."""
    if not name:
        return None
    val = name.strip().lower()
    return _MATERIAL_SYNONYMS.get(val, name.strip())

def normalize_medium(name: Optional[str]) -> Optional[str]:
    """Normalizes medium name to canonical name.
    
    0B.3a: Conservative logic to prevent over-normalization.
    Specific synonyms are checked first. Generic substrings only via word boundaries.
    """
    if not name:
        return None
    val = name.strip().lower()
    
    # 1. Exact or specific synonym matches (Highest priority)
    if val in _MEDIUM_SYNONYMS:
        return _MEDIUM_SYNONYMS[val]
    
    # 2. Conservative keyword matching via word boundaries
    if _PATTERNS["medium_water"].search(val):
        return "Wasser"
    if _PATTERNS["medium_oil"].search(val):
        return "Öl"
        
    return name.strip()

def normalize_medium_id(name: Optional[str]) -> Optional[str]:
    """Normalizes medium name to technical service-layer lookup ID.

    Returns lowercase technical IDs used by retrieval and knowledge services:
    "hees", "hlp", "wasser".

    Conservative: only exact synonym matches are mapped. Unknown or ambiguous
    inputs are passed through unchanged (original strip, no forced lowercase)
    to avoid false collapsing in the service layer.
    """
    if not name:
        return None
    val = name.strip().lower()
    mapped = _MEDIUM_ID_MAP.get(val)
    if mapped is not None:
        return mapped
    # Unknown input: pass through without normalization
    return name.strip()

def normalize_unit_value(value: float, unit: str) -> Tuple[float, str]:
    """Normalizes a physical value to its base unit (bar, C)."""
    try:
        param = PhysicalParameter(value=value, unit=unit)
        return param.to_base_unit(), param.base_unit
    except Exception:
        return value, unit

def extract_parameters(text: str) -> Dict[str, Any]:
    """
    Centralized extraction and normalization of physical parameters from text.
    Returns normalized values in base units where possible.
    """
    results: Dict[str, Any] = {}
    
    # Temperature
    temp_match = _PATTERNS["temperature"].search(text)
    if temp_match:
        val = float(temp_match.group(1).replace(",", "."))
        unit = temp_match.group(2).replace("°", "").upper()
        if "GRAD" in unit: unit = "C"
        norm_val, _ = normalize_unit_value(val, unit)
        results["temperature_c"] = norm_val
        results["temperature_raw"] = temp_match.group(0)

    # Pressure
    pres_match = _PATTERNS["pressure"].search(text)
    if pres_match:
        val = float(pres_match.group(1).replace(",", "."))
        unit = pres_match.group(2).lower()
        norm_val, _ = normalize_unit_value(val, unit)
        results["pressure_bar"] = norm_val
        results["pressure_raw"] = pres_match.group(0)

    # Diameter
    diam_match = _PATTERNS["diameter"].search(text)
    if diam_match:
        # Match group 1 or 3
        val_str = diam_match.group(1) or diam_match.group(3)
        results["diameter_mm"] = float(val_str.replace(",", "."))

    # Speed
    speed_match = _PATTERNS["speed"].search(text)
    if speed_match:
        val_str = speed_match.group(1) or speed_match.group(3)
        results["speed_rpm"] = float(val_str.replace(",", "."))

    # Medium
    medium_norm = normalize_medium(text)
    if medium_norm != text:
        # Only if we found a specific keyword
        if any(kw in text.lower() for kw in ["wasser", "water", "öl", "oil", "mineralöl", "bio-öl"]):
            results["medium_normalized"] = medium_norm
            results["medium_raw"] = medium_norm # Simplified for now

    # Material
    for mat_syn in _MATERIAL_SYNONYMS:
        if re.search(r"\b" + re.escape(mat_syn) + r"\b", text, re.I):
            results["material_normalized"] = _MATERIAL_SYNONYMS[mat_syn]
            break

    return results
