# backend/app/services/langgraph/graph/consult/nodes/deterministic_calc.py
from __future__ import annotations

import math
from typing import Any, Dict

def _to_float(x, default=None):
    try:
        if x is None or x == "" or x == "unknown":
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).replace(" ", "").replace(",", ".")
        return float(s)
    except Exception:
        return default

def _max_defined(*vals):
    for v in vals:
        if v is not None:
            return v
    return None

def deterministic_calc_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministische Kernberechnungen (kein LLM):
      - v, ω, p (bar/Pa/MPa), PV (bar·m/s / MPa·m/s)
      - optional Reibkraft & Reibleistung (falls Parameter vorhanden)
    Ergänzt state['derived'] nicht-destruktiv und sendet ein UI-Snapshot-Event.
    """
    params: Dict[str, Any] = dict(state.get("params") or {})
    derived: Dict[str, Any] = dict(state.get("derived") or {})

    d_mm   = _max_defined(_to_float(params.get("wellen_mm")), _to_float(params.get("stange_mm")))
    rpm    = _max_defined(_to_float(params.get("drehzahl_u_min")), _to_float(params.get("n_u_min")), _to_float(params.get("rpm")))
    v_ms   = _max_defined(_to_float(params.get("relativgeschwindigkeit_ms")), _to_float(params.get("geschwindigkeit_m_s")), _to_float(params.get("v_ms")))
    p_bar  = _max_defined(_to_float(params.get("druck_bar")), _to_float(params.get("pressure_bar")))
    width_mm = _to_float(params.get("width_mm"))
    mu     = _to_float(params.get("mu"))
    p_contact_mpa = _to_float(params.get("contact_pressure_mpa"))
    axial_force_n = _to_float(params.get("axial_force_n"))

    # v
    if v_ms is None and d_mm is not None and rpm is not None and d_mm > 0 and rpm > 0:
        v_ms = math.pi * (d_mm / 1000.0) * (rpm / 60.0)

    # ω
    omega = 2.0 * math.pi * (rpm / 60.0) if rpm is not None else None

    # p
    p_pa = p_mpa = None
    if p_bar is not None:
        p_pa = p_bar * 1e5
        p_mpa = p_bar / 10.0

    # PV
    pv_bar_ms = pv_mpa_ms = None
    if p_bar is not None and v_ms is not None:
        pv_bar_ms = p_bar * v_ms
        pv_mpa_ms = (p_bar / 10.0) * v_ms

    # Reibung/Leistung (Variante A: über Axialkraft)
    friction_force_n = friction_power_w = None
    if axial_force_n is not None and mu is not None and v_ms is not None:
        friction_force_n = mu * axial_force_n
        friction_power_w = friction_force_n * v_ms
    # Variante B: Kontaktpressung * Fläche
    elif (p_contact_mpa is not None) and (d_mm is not None) and (width_mm is not None) and (mu is not None) and (v_ms is not None):
        d_m = d_mm / 1000.0
        b_m = width_mm / 1000.0
        area_m2 = math.pi * d_m * b_m
        normal_force_n = (p_contact_mpa * 1e6) * area_m2
        friction_force_n = mu * normal_force_n
        friction_power_w = friction_force_n * v_ms

    # write back
    calc = dict(derived.get("calculated") or {})
    if v_ms is not None:
        calc["umfangsgeschwindigkeit_m_s"] = round(v_ms, 6)
        calc["surface_speed_m_s"] = round(v_ms, 6)
    if omega is not None:
        calc["omega_rad_s"] = round(omega, 6)
    if p_bar is not None:
        calc["p_bar"] = round(p_bar, 6)
    if p_pa is not None:
        calc["p_pa"] = round(p_pa, 3)
    if p_mpa is not None:
        calc["p_mpa"] = round(p_mpa, 6)
    if pv_bar_ms is not None:
        calc["pv_bar_ms"] = round(pv_bar_ms, 6)
    if pv_mpa_ms is not None:
        calc["pv_mpa_ms"] = round(pv_mpa_ms, 6)
    if friction_force_n is not None:
        calc["friction_force_n"] = round(friction_force_n, 6)
    if friction_power_w is not None:
        calc["friction_power_w"] = round(friction_power_w, 6)

    flags = dict(derived.get("flags") or {})
    warnings = list(derived.get("warnings") or [])
    if pv_mpa_ms is not None and pv_mpa_ms > 0.5:
        warnings.append(f"PV-Kennzahl hoch ({pv_mpa_ms:.3f} MPa·m/s) – Material/Profil prüfen.")

    new_derived = dict(derived)
    new_derived["calculated"] = calc
    new_derived["flags"] = flags
    new_derived["warnings"] = warnings

    # UI-Snapshot für Sidebar
    ui_event = {"ui_action": "calc_snapshot", "derived": new_derived}

    # Kompatibilitätsalias
    if v_ms is not None:
        new_derived["relativgeschwindigkeit_ms"] = v_ms

    return {**state, "derived": new_derived, "phase": "deterministic_calc", "ui_event": ui_event}
