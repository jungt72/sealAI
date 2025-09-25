from __future__ import annotations
import re
from typing import Dict, Optional

_NUM = r"-?\d+(?:[.,]\d+)?"

def _to_float(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except Exception:
        return None

def pre_extract_params(text: str) -> Dict[str, object]:
    t = text or ""
    out: Dict[str, object] = {}

    m = re.search(r"(?:\b(?:rwdr|ba|bauform)\b\s*)?(\d{1,3})\s*[x×]\s*(\d{1,3})\s*[x×]\s*(\d{1,3})", t, re.I)
    if m:
        out["wellen_mm"]  = int(m.group(1))
        out["gehause_mm"] = int(m.group(2))
        out["breite_mm"]  = int(m.group(3))

    if re.search(r"\bhydraulik ?öl\b", t, re.I):
        out["medium"] = "Hydrauliköl"
    elif re.search(r"\böl\b", t, re.I):
        out["medium"] = "Öl"
    elif re.search(r"\bwasser\b", t, re.I):
        out["medium"] = "Wasser"

    m = re.search(r"(?:t\s*max|temp(?:eratur)?(?:\s*max)?|t)\s*[:=]?\s*(" + _NUM + r")\s*°?\s*c\b", t, re.I)
    if not m:
        m = re.search(r"\b(" + _NUM + r")\s*°?\s*c\b", t, re.I)
    if m:
        out["temp_max_c"] = _to_float(m.group(1))

    m = re.search(r"(?:\bdruck\b|[^a-z]p)\s*[:=]?\s*(" + _NUM + r")\s*bar\b", t, re.I)
    if not m:
        m = re.search(r"\b(" + _NUM + r")\s*bar\b", t, re.I)
    if m:
        out["druck_bar"] = _to_float(m.group(1))

    m = re.search(r"(?:\bn\b|drehzahl)\s*[:=]?\s*(\d{1,7})\s*(?:u/?min|rpm)\b", t, re.I)
    if not m:
        m = re.search(r"\b(\d{1,7})\s*(?:u/?min|rpm)\b", t, re.I)
    if m:
        out["drehzahl_u_min"] = int(m.group(1))

    m = re.search(r"\bbauform\s*[:=]?\s*([A-Z0-9]{1,4})\b|\b(BA|B1|B2|TC|SC)\b", t, re.I)
    if m:
        out["bauform"] = (m.group(1) or m.group(2) or "").upper()

    return out
