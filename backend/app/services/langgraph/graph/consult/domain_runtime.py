# backend/app/services/langgraph/graph/consult/domain_runtime.py
from __future__ import annotations
import importlib
import logging
from typing import Any, Dict, List
from .state import Parameters, Derived

log = logging.getLogger(__name__)

def compute_domain(domain: str, params: Parameters) -> Derived:
    try:
        mod = importlib.import_module(f"app.services.langgraph.domains.{domain}.calculator")
        compute = getattr(mod, "compute")
        out = compute(params)  # type: ignore
        return {
            "calculated": dict(out.get("calculated", {})),
            "flags": dict(out.get("flags", {})),
            "warnings": list(out.get("warnings", [])),
            "requirements": list(out.get("requirements", [])),
        }
    except Exception as e:
        log.warning("Domain compute failed (%s): %s", domain, e)
        return {"calculated": {}, "flags": {}, "warnings": [], "requirements": []}

def missing_by_domain(domain: str, p: Parameters) -> List[str]:
    # ✅ Hydraulik-Stange nutzt stange_mm / nut_d_mm / nut_b_mm
    if domain == "hydraulics_rod":
        req = [
            "falltyp",
            "stange_mm",
            "nut_d_mm",
            "nut_b_mm",
            "medium",
            "temp_max_c",
            "druck_bar",
            "geschwindigkeit_m_s",
        ]
    else:
        req = [
            "falltyp",
            "wellen_mm",
            "gehause_mm",
            "breite_mm",
            "medium",
            "temp_max_c",
            "druck_bar",
            "drehzahl_u_min",
        ]

    def _is_missing(key: str, val: Any) -> bool:
        if val is None or val == "" or val == "unknown":
            return True
        if key == "druck_bar":
            try: float(val); return False
            except Exception: return True
        if key in ("wellen_mm", "gehause_mm", "breite_mm", "drehzahl_u_min", "geschwindigkeit_m_s",
                   "stange_mm", "nut_d_mm", "nut_b_mm"):
            try: return float(val) <= 0
            except Exception: return True
        if key == "temp_max_c":
            try: float(val); return False
            except Exception: return True
        return False

    return [k for k in req if _is_missing(k, p.get(k))]

def anomaly_messages(domain: str, params: Parameters, derived: Derived) -> List[str]:
    msgs: List[str] = []
    flags = (derived.get("flags") or {})
    if flags.get("requires_pressure_stage") and not flags.get("pressure_stage_ack"):
        msgs.append("Ein Überdruck >2 bar ist für Standard-Radialdichtringe kritisch. Dürfen Druckstufenlösungen geprüft werden?")
    if flags.get("speed_high"):
        msgs.append("Die Drehzahl/Umfangsgeschwindigkeit ist hoch – ist sie dauerhaft oder nur kurzzeitig (Spitzen)?")
    if flags.get("temp_very_high"):
        msgs.append("Die Temperatur ist sehr hoch. Handelt es sich um Dauer- oder Spitzentemperaturen?")
    if domain == "hydraulics_rod" and flags.get("extrusion_risk") and not flags.get("extrusion_risk_ack"):
        msgs.append("Bei dem Druck besteht Extrusionsrisiko. Darf eine Stütz-/Back-up-Ring-Lösung geprüft werden?")
    return msgs
