from __future__ import annotations
from typing import Dict, Any
from math import pi

def intake_validate(state: Dict[str, Any]) -> Dict[str, Any]:
    p = state.get("params", {}) or {}
    missing = []
    for k in ("medium", "pressure_bar", "temp_max_c"):
        if p.get(k) is None:
            missing.append(k)
    if state.get("mode") == "consult" and p.get("speed_rpm") is None:
        missing.append("speed_rpm")
    state.setdefault("derived", {}).setdefault("notes", [])
    if missing:
        state.setdefault("ui_events", []).append({
            "ui_action": "open_form",
            "payload": {"form_id": "rwdr_params_v1", "missing": missing, "prefill": p}
        })
    return state

def _v_m_s(d_mm: float, rpm: float) -> float:
    return pi * (d_mm/1000.0) * (rpm/60.0)

def _dn(d_mm: float, rpm: float) -> float:
    return d_mm * rpm

def calc_core(state: Dict[str, Any]) -> Dict[str, Any]:
    p = state.get("params", {}) or {}
    d = state.get("derived", {}) or {}
    shaft = p.get("shaft_d")
    rpm = p.get("speed_rpm")
    pressure = p.get("pressure_bar")
    if shaft and rpm:
        v = _v_m_s(shaft, rpm)
        d["v_m_s"] = round(v, 4)
        d["dn_value"] = round(_dn(shaft, rpm), 2)
    if pressure and "v_m_s" in d:
        d["pv_indicator_bar_ms"] = round(float(pressure) * float(d["v_m_s"]), 4)
    state["derived"] = d
    return state

def calc_advanced(state: Dict[str, Any]) -> Dict[str, Any]:
    p = state.get("params", {}) or {}
    notes = state.setdefault("derived", {}).setdefault("notes", [])
    if p.get("temp_max_c", 0) > 200:
        notes.append("Hohe Temperatur: Fluorpolymere prüfen.")
    if (p.get("pressure_bar") or 0) > 5:
        notes.append("Druck > 5 bar: Stützelement/Extrusionsschutz prüfen.")
    return state
