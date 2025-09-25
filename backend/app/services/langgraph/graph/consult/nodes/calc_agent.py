# backend/app/services/langgraph/graph/consult/nodes/calc_agent.py
from __future__ import annotations

import logging
from typing import Any, Dict

log = logging.getLogger(__name__)

def _num(x: Any) -> float | None:
    try:
        if x in (None, "", []):
            return None
        if isinstance(x, bool):
            return None
        return float(x)
    except Exception:
        return None

def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def _calc_rwdr(params: Dict[str, Any]) -> Dict[str, Any]:
    d_mm = _num(params.get("wellen_mm"))
    n_rpm = _num(params.get("drehzahl_u_min"))
    p_bar = _num(params.get("druck_bar"))
    tmax = _num(params.get("temp_max_c"))

    calc: Dict[str, Any] = {}
    if d_mm is not None and n_rpm is not None and d_mm > 0 and n_rpm >= 0:
        d_m = d_mm / 1000.0
        v_ms = 3.141592653589793 * d_m * (n_rpm / 60.0)
        calc["umfangsgeschwindigkeit_m_s"] = v_ms
        calc["surface_speed_m_s"] = round(v_ms, 3)

    if p_bar is not None and calc.get("umfangsgeschwindigkeit_m_s") is not None:
        calc["pv_indicator_bar_ms"] = p_bar * calc["umfangsgeschwindigkeit_m_s"]

    mat_whitelist: list[str] = []
    mat_blacklist: list[str] = []
    medium = (params.get("medium") or "").strip().lower()
    # KEINE harte PTFE-Blacklist bei Wasser
    if "wasser" in medium:
        mat_whitelist.extend(["EPDM", "FKM", "PTFE"])

    if tmax is not None:
        if tmax > 120:
            mat_whitelist.append("FKM")
        if tmax > 200:
            mat_whitelist.append("PTFE")

    reqs: list[str] = []
    flags: Dict[str, Any] = {}
    if p_bar is not None and p_bar > 1.0:
        flags["druckbelastet"] = True

    return {
        "calculated": calc,
        "material_whitelist": mat_whitelist,
        "material_blacklist": mat_blacklist,
        "requirements": reqs,
        "flags": flags,
    }

def _calc_hydraulics_rod(params: Dict[str, Any]) -> Dict[str, Any]:
    p_bar = _num(params.get("druck_bar"))
    v_lin = _num(params.get("geschwindigkeit_m_s"))
    tmax = _num(params.get("temp_max_c"))

    calc: Dict[str, Any] = {}
    if p_bar is not None and v_lin is not None:
        calc["pv_indicator_bar_ms"] = p_bar * v_lin

    flags: Dict[str, Any] = {}
    reqs: list[str] = []
    if p_bar is not None and p_bar >= 160:
        flags["extrusion_risk"] = True
        reqs.append("Stütz-/Back-up-Ring prüfen (≥160 bar).")

    mat_whitelist: list[str] = []
    if tmax is not None and tmax > 100:
        mat_whitelist.append("FKM")

    return {
        "calculated": calc,
        "flags": flags,
        "requirements": reqs,
        "material_whitelist": mat_whitelist,
        "material_blacklist": [],
    }

def calc_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Domänenspezifische Heuristiken ergänzen und mit derived mergen.
    Sendet ebenfalls einen calc_snapshot fürs UI.
    """
    domain = (state.get("domain") or "rwdr").strip().lower()
    params = dict(state.get("params") or {})
    derived_existing = dict(state.get("derived") or {})

    try:
        if domain == "hydraulics_rod":
            derived_new = _calc_hydraulics_rod(params)
        else:
            derived_new = _calc_rwdr(params)
    except Exception as e:
        log.warning("[calc_agent] calc_failed", exc=str(e))
        return {**state, "phase": "calc_agent"}

    derived_merged = _deep_merge(derived_existing, derived_new)

    v = (
        derived_merged.get("calculated", {}).get("umfangsgeschwindigkeit_m_s")
        or params.get("relativgeschwindigkeit_ms")
    )
    if v is not None:
        derived_merged["relativgeschwindigkeit_ms"] = v

    new_state = {**state, "derived": derived_merged, "phase": "calc_agent"}
    new_state["ui_event"] = {"ui_action": "calc_snapshot", "derived": derived_merged}
    return new_state
