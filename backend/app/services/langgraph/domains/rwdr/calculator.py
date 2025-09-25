# backend/app/services/langgraph/domains/rwdr/calculator.py
from __future__ import annotations
from typing import Dict, Any
import math


def _to_float(x, default=0.0):
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).replace(" ", "").replace(".", "").replace(",", ".")
        return float(s)
    except Exception:
        return default


def compute(params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}
    out = {"calculated": {}, "flags": {}, "warnings": [], "requirements": []}

    d_mm = _to_float(p.get("wellen_mm"))
    rpm = _to_float(p.get("drehzahl_u_min"))
    t_max = _to_float(p.get("temp_max_c"))
    press_bar = _to_float(p.get("druck_bar"))
    medium = (p.get("medium") or "").lower()
    bauform = (p.get("bauform") or "").upper()

    # Umfangsgeschwindigkeit [m/s]
    v = 0.0
    if d_mm > 0 and rpm > 0:
        v = math.pi * (d_mm / 1000.0) * (rpm / 60.0)
    v = round(v, 3)

    # Beide Keys setzen (Deutsch+Englisch), damit Templates/Alt-Code beides finden
    out["calculated"]["umfangsgeschwindigkeit_m_s"] = v
    out["calculated"]["surface_speed_m_s"] = v

    # Flags
    if press_bar > 2.0:
        out["flags"]["requires_pressure_stage"] = True
    if v >= 20.0:
        out["flags"]["speed_high"] = True
    if t_max >= 120.0:
        out["flags"]["temp_very_high"] = True

    # Material-Guidance (Whitelist/Blacklist)
    whitelist, blacklist = set(), set()

    # RWDR Bauform BA: Standard ist Elastomer-Lippe (NBR/FKM). PTFE nur Spezialprofile.
    if bauform.startswith("BA"):
        blacklist.add("PTFE")
        if any(k in medium for k in ("hydraulik", "öl", "oel", "oil")):
            if t_max <= 100:
                whitelist.update(["NBR", "FKM"])   # NBR präferiert, FKM ok
            else:
                whitelist.add("FKM")
                blacklist.add("NBR")
        else:
            whitelist.update(["FKM", "NBR"])

    # Druckrestriktion für PTFE (Standard-RWDR): ab ~0.5 bar vermeiden
    if press_bar > 0.5:
        blacklist.add("PTFE")

    # Chemie / sehr hohe Temp → PTFE als mögliche Alternative zulassen
    if any(k in medium for k in ("chem", "lösemittel", "loesemittel", "solvent")) or t_max > 180:
        whitelist.add("PTFE")

    out["calculated"]["material_whitelist"] = sorted(whitelist) if whitelist else []
    out["calculated"]["material_blacklist"] = sorted(blacklist) if blacklist else []

    # Anforderungen (menschlich lesbar)
    if whitelist:
        out["requirements"].append("Bevorzuge Materialien: " + ", ".join(sorted(whitelist)))
    if blacklist:
        out["requirements"].append("Vermeide Materialien: " + ", ".join(sorted(blacklist)))
    if out["flags"].get("requires_pressure_stage"):
        out["requirements"].append("Druckstufe oder Drucktaugliches Profil erforderlich (>2 bar).")
    if out["flags"].get("speed_high"):
        out["requirements"].append("Hohe Umfangsgeschwindigkeit (>= 20 m/s) berücksichtigen.")

    return out
