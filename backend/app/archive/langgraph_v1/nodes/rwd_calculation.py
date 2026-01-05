from __future__ import annotations

import math
from typing import Any, Dict

from app.langgraph.prompts.prompt_loader import render_prompt
from app.langgraph.state import (
    RwdCalcResults,
    SealAIState,
    ensure_phase,
)


def _surface_speed_m_per_s(diameter_mm: float, speed_rpm: float) -> float:
    # Umfangsgeschwindigkeit v = π * d * n / 60 (d in Metern)
    diameter_m = diameter_mm / 1000.0
    return math.pi * diameter_m * speed_rpm / 60.0


def rwd_calculation_node(state: SealAIState) -> Dict[str, Any]:
    phase = ensure_phase(state)
    if phase != "berechnung":
        return {"phase": phase}

    requirements = state.get("rwd_requirements") or {}
    results: RwdCalcResults = RwdCalcResults()
    missing: Dict[str, str] = {}

    shaft_diameter = requirements.get("shaft_diameter")
    speed_rpm = requirements.get("speed_rpm")
    if isinstance(shaft_diameter, (int, float)) and isinstance(speed_rpm, (int, float)):
        results["surface_speed_m_per_s"] = round(_surface_speed_m_per_s(shaft_diameter, speed_rpm), 4)
    else:
        missing["surface_speed"] = "shaft_diameter & speed_rpm"

    pressure_inner = requirements.get("pressure_inner")
    pressure_outer = requirements.get("pressure_outer") or 0.0
    if isinstance(pressure_inner, (int, float)):
        pressure_delta = float(pressure_inner) - float(pressure_outer)
        results["pressure_delta"] = round(pressure_delta, 4)
        if "surface_speed_m_per_s" in results:
            pv_value = results["surface_speed_m_per_s"] * pressure_delta
            results["pv_value"] = round(pv_value, 4)
    else:
        missing["pressure_delta"] = "pressure_inner"

    slots = dict(state.get("slots") or {})
    if not results:
        text = render_prompt(
            "rwd_calculation_missing.de.j2",
            missing_fields=list(missing.values()) or ["Eingangsdaten"],
        )
        slots["candidate_answer"] = text
        slots["candidate_source"] = "rwd_calculation_missing"
        return {"slots": slots, "phase": "berechnung"}

    summary_parts = []
    if "surface_speed_m_per_s" in results:
        summary_parts.append(f"v = {results['surface_speed_m_per_s']:.3f} m/s")
    if "pv_value" in results:
        summary_parts.append(f"PV = {results['pv_value']:.3f} (bar·m/s)")
    if "pressure_delta" in results:
        summary_parts.append(f"Δp = {results['pressure_delta']:.3f} bar")

    slots["rwd_calc_summary"] = ", ".join(summary_parts)
    return {
        "slots": slots,
        "rwd_calc_results": results,
        "phase": "auswahl",
    }


__all__ = ["rwd_calculation_node"]
