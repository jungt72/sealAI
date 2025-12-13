from __future__ import annotations

import re
from typing import Dict, Optional, Pattern


def _parse_number(match: Optional[re.Match[str]]) -> Optional[float]:
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _compile_pattern(pattern: str, flags: int = 0) -> Pattern[str]:
    return re.compile(pattern, flags | re.IGNORECASE)


def extract_parameters_from_text(text: str) -> Dict[str, float | str]:
    params: Dict[str, float | str] = {}
    if not text:
        return params

    normalized = text.lower()

    # Pressure [bar]
    pressure_match = _compile_pattern(r"(\d+(?:[.,]\d+)?)\s*bar").search(normalized)
    pressure_value = _parse_number(pressure_match)
    if pressure_value is not None:
        params["pressure_bar"] = pressure_value

    # Temperature [°C]
    temp_match = _compile_pattern(r"(\d+(?:[.,]\d+)?)\s*(?:°c|grad|celsius)").search(normalized)
    temp_value = _parse_number(temp_match)
    if temp_value is not None:
        params["temperature_C"] = temp_value

    # Shaft diameter [mm]
    diameter_keywords = (
        r"(?:wellendurchmesser|wellendruchmesser|wellen(?:durchmesser)?|welle(?:n)?|"
        r"shaft(?:diameter)?|durchmesser|diameter|ø|⌀)"
    )
    diameter_pattern = _compile_pattern(
        rf"{diameter_keywords}[^\d\r\n]*?(\d+(?:[.,]\d+)?)(?:\s*(?:mm|millimeter))?"
    )
    diameter_match = diameter_pattern.search(text)
    if diameter_match is None:
        diameter_fallback = _compile_pattern(
            rf"{diameter_keywords}[^\d\r\n]*?(\d+(?:[.,]\d+)?)"
        ).search(text)
        diameter_match = diameter_fallback
    diameter_value = _parse_number(diameter_match)
    if diameter_value is not None:
        params["shaft_diameter"] = diameter_value

    # Rotational speed [RPM]
    speed_patterns = [
        r"(\d+(?:[.,]\d+)?)\s*(?:rpm|u/min|1/min|umdrehungen|1/minute)",
        r"drehzahl[^\d\r\n]*?(\d+(?:[.,]\d+)?)",
        r"n\s*[:=]?\s*(\d+(?:[.,]\d+)?)",
    ]
    speed_value: Optional[float] = None
    for pattern in speed_patterns:
        speed_match = _compile_pattern(pattern).search(normalized)
        speed_value = _parse_number(speed_match)
        if speed_value is not None:
            params["speed_rpm"] = speed_value
            break

    # Medium heuristic
    if "öl" in normalized or "oil" in normalized:
        params["medium"] = "oil"
    elif "wasser" in normalized or "water" in normalized:
        params["medium"] = "water"
    elif "gas" in normalized:
        params["medium"] = "gas"
    elif "chemikalie" in normalized or "chemical" in normalized:
        params["medium"] = "chemical"

    return params
