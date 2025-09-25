# Hydraulik – Stangendichtung: deterministische Checks
from typing import Dict, Any

def _to_float(v, default=None):
    try:
        if v is None or v == "" or v == "unknown":
            return default
        return float(v)
    except Exception:
        return default

def compute(params: Dict[str, Any]) -> Dict[str, Any]:
    # Pflicht-/Kernparameter
    p_bar   = _to_float(params.get("druck_bar"))
    t_max   = _to_float(params.get("temp_max_c"))
    speed   = _to_float(params.get("geschwindigkeit_m_s"))  # optional
    bore    = _to_float(params.get("nut_d_mm"))              # ✅ Nut-Ø D (mm)
    rod     = _to_float(params.get("stange_mm"))             # ✅ Stangen-Ø (mm)

    flags = {}
    warnings = []
    reqs = []

    # Extrusionsrisiko grob ab ~160–200 bar (ohne Stützring / je nach Spalt)
    if p_bar is not None and p_bar >= 160:
        flags["extrusion_risk"] = True
        reqs.append("Stütz-/Back-up-Ring prüfen (≥160 bar).")

    if t_max is not None and t_max > 100:
        warnings.append(f"Hohe Temperatur ({t_max:.0f} °C) – Werkstoffwahl prüfen.")

    if speed is not None and speed > 0.6:
        warnings.append(f"Hohe Stangengeschwindigkeit ({speed:.2f} m/s) – Reibung/Stick-Slip beachten.")

    # Plausibilitäts-Hinweis (Spaltmaß sehr klein)
    if bore and rod and bore - rod < 2.0:
        warnings.append("Sehr kleiner Spalt zwischen Bohrung und Stange (< 2 mm).")

    return {
        "calculated": {
            "druck_bar": p_bar,
            "temp_max_c": t_max,
            "geschwindigkeit_m_s": speed,
            "bohrung_mm": bore,
            "stange_mm": rod,
        },
        "flags": flags,
        "warnings": warnings,
        "requirements": reqs,
    }
