"""P4 Live-Tile deterministic calculations for SEALAI v5 foundation."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Literal, Optional

import structlog

from app._legacy_v2.phase import PHASE
from app._legacy_v2.state import CalcResults, LiveCalcTile, SealAIState
from app.services.knowledge.entity_resolver import normalize_entity
from app.services.knowledge.chemical_repository import get_chemical_repository
from app.services.knowledge.material_repository import get_material_repository
from app.models.chemical_matrix import RatingEnum
from app._legacy_v2.utils.assertion_cycle import stamp_patch_with_assertion_binding

logger = structlog.get_logger("rag.nodes.p4_live_calc")

_NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:[.,]\d+)?")

_HRC_WARNING_MIN = 58.0
_HRC_CRITICAL_MIN = 55.0
_RUNOUT_WARNING_MAX_MM = 0.2
_RUNOUT_CRITICAL_MAX_MM = 0.3
_FRICTION_COEFF_PTFE = 0.15
_PTFE_ALPHA_PER_K = 1.2e-4

# RWDR expert limits
_RWDR_SPEED_LIMIT_NBR = 12.0
_RWDR_SPEED_LIMIT_MAX = 35.0
_RWDR_HRC_MIN_HIGH_SPEED = 45.0
_RWDR_HIGH_SPEED_THRESHOLD = 4.0


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        match = _NUMBER_PATTERN.search(raw.replace(",", "."))
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None
    return None


def _first_float(payload: Dict[str, Any], keys: Iterable[str]) -> Optional[float]:
    for key in keys:
        parsed = _coerce_float(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _collect_parameter_payload(state: SealAIState) -> Dict[str, Any]:
    """Single source of truth: pull parameters from asserted state plus staged normalized inputs.

    Engineering parameters live in working_profile.engineering_profile (LegacyWorkingProfile).
    Pillar 2 top-level fields (surface_hardness_hrc, medium, etc.) overlay when set.
    normalized_profile fills any remaining gaps; extracted_params is only a
    legacy mirror fallback while old readers are migrated.
    """
    # Base: flat engineering parameters from LegacyWorkingProfile
    payload = _to_dict(state.working_profile.engineering_profile)

    # Overlay: Pillar 2 top-level params that may be set independently of engineering_profile
    _P2_OVERLAY_FIELDS = (
        "medium", "pressure_bar", "temperature_c",
        "surface_hardness_hrc", "dp_dt_bar_per_s", "side_load_kn",
        "aed_required", "medium_additives", "fluid_contamination_iso",
        "pressure_spike_factor", "dynamic_type",
    )
    for field_name in _P2_OVERLAY_FIELDS:
        val = getattr(state.working_profile, field_name, None)
        if val is not None:
            payload[field_name] = val

    # Merge staged normalized parameters for any fields not yet in WorkingProfile schema.
    staged_payload = (
        state.working_profile.normalized_profile
        or state.working_profile.extracted_params
        or {}
    )
    if staged_payload:
        payload.update(staged_payload)
    return payload


def _to_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        result = model_dump(exclude_none=True)
        if isinstance(result, dict):
            return result
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        result = as_dict()
        if isinstance(result, dict):
            return result
    return {}


def _sanitize_primitive_parameters(payload: Dict[str, Any]) -> Dict[str, str | int | float]:
    sanitized: Dict[str, str | int | float] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (str, int, float)):
            if isinstance(value, str) and not value.strip():
                continue
            sanitized[str(key)] = value
    return sanitized


def _collect_captured_parameters(state: SealAIState) -> Dict[str, str | int | float]:
    """Legacy helper for UI, now purely derived from working_profile."""
    return _sanitize_primitive_parameters(_to_dict(state.working_profile.engineering_profile))


def _get_diameter_mm(payload: Dict[str, Any]) -> Optional[float]:
    return _first_float(
        payload,
        (
            "shaft_diameter",
            "shaft_d1",
            "d1",
            "d1",
            "d_shaft_nominal",
            "diameter",
            "nominal_diameter",
            "rod_diameter",
            "inner_diameter_mm",
        ),
    )


def calc_tribology(payload: Dict[str, Any], prev: Optional[LiveCalcTile] = None) -> Dict[str, Any]:
    diameter_mm = _get_diameter_mm(payload)
    rpm = _first_float(payload, ("speed_rpm", "rpm", "n", "n_max"))
    pressure_bar = _first_float(payload, ("pressure_max_bar", "pressure_bar", "pressure", "p_max"))
    hrc_value = _first_float(payload, ("surface_hardness_hrc", "hrc", "hrc_value", "shaft_hardness", "hardness"))
    runout_mm = _first_float(payload, ("runout_mm", "runout", "shaft_runout", "dynamic_runout"))
    temp_max_c = _first_float(payload, ("temperature_max_c", "temp_max_c", "temperature_max", "T_medium_max", "temp_max"))

    # Material extraction for RWDR logic
    material_raw = str(payload.get("elastomer_material") or payload.get("material") or "").strip()
    material = material_raw.upper()

    v_surface_m_s: Optional[float] = None
    if diameter_mm is not None and rpm is not None and diameter_mm >= 0 and rpm >= 0:
        v_surface_m_s = (diameter_mm * math.pi * rpm) / 60000.0
    elif prev:
        v_surface_m_s = prev.v_surface_m_s

    pv_value_mpa_m_s: Optional[float] = None
    if v_surface_m_s is not None and pressure_bar is not None and pressure_bar >= 0:
        pv_value_mpa_m_s = (pressure_bar * 0.1) * v_surface_m_s
    elif prev:
        pv_value_mpa_m_s = prev.pv_value_mpa_m_s

    friction_power_watts: Optional[float] = None
    if v_surface_m_s is not None and diameter_mm is not None:
        # RWDR Expert: Friction power estimation (P_r)
        # Standard RWDR approximation: Pr [W] ≈ 0.5 * d1 [mm] * vs [m/s]
        friction_power_watts = 0.5 * diameter_mm * v_surface_m_s
    elif prev:
        friction_power_watts = prev.friction_power_watts

    # HRC Warning: Standard limit OR RWDR expert high speed limit
    hrc_warning = False
    if hrc_value is not None:
        if hrc_value < _HRC_WARNING_MIN:
            hrc_warning = True
        # RWDR expert: < 45 HRC at high speed (v > 4 m/s)
        if v_surface_m_s is not None and v_surface_m_s > _RWDR_HIGH_SPEED_THRESHOLD and hrc_value < _RWDR_HRC_MIN_HIGH_SPEED:
            hrc_warning = True
    elif prev:
        hrc_warning = prev.hrc_warning

    notes = []
    material_limit_exceeded = False

    # Dynamic material profile lookup from structured knowledge base
    # Conservative fallback for standard elastomer assumptions when material is set
    speed_limit = _RWDR_SPEED_LIMIT_MAX
    pv_warning_limit = 2.0
    pv_critical_limit = 3.0
    temp_min_limit: Optional[float] = None
    temp_max_limit: Optional[float] = None
    resolved_material_id = material or "Material"

    if material_raw:
        norm_mat = normalize_entity("material", material_raw)
        repo = get_material_repository()
        mat_profile = repo.get_profile(norm_mat)
        if mat_profile:
            speed_limit = mat_profile.v_surface_max
            pv_warning_limit = mat_profile.pv_limit_warning
            pv_critical_limit = mat_profile.pv_limit_critical
            temp_min_limit = mat_profile.temp_min
            temp_max_limit = mat_profile.temp_max
            resolved_material_id = mat_profile.material_id
        else:
            speed_limit = 12.0
            pv_warning_limit = 1.5
            pv_critical_limit = 2.0
            resolved_material_id = norm_mat.upper() or resolved_material_id

    if material_raw and v_surface_m_s is not None and v_surface_m_s > speed_limit:
        material_limit_exceeded = True
        notes.append(
            f"Umfangsgeschwindigkeit ({v_surface_m_s:.1f} m/s) liegt über Limit für {resolved_material_id} ({speed_limit:.1f} m/s)."
        )

    if material_raw and temp_max_c is not None:
        if temp_min_limit is not None and temp_max_c < temp_min_limit:
            notes.append(
                f"Einsatztemperatur ({temp_max_c:.0f}°C) liegt unter dem Minimum ({temp_min_limit:.0f}°C) für {resolved_material_id}."
            )
        if temp_max_limit is not None and temp_max_c > temp_max_limit:
            material_limit_exceeded = True
            notes.append(
                f"Einsatztemperatur ({temp_max_c:.0f}°C) überschreitet das Maximum ({temp_max_limit:.0f}°C) für {resolved_material_id}."
            )

    # Speed validation: NBR limit (M6 override)
    if v_surface_m_s is not None and v_surface_m_s > _RWDR_SPEED_LIMIT_NBR and "NBR" in material:
        hrc_warning = True  # Keep for backward compatibility/UI signal

    runout_warning = bool(runout_mm is not None and runout_mm > _RUNOUT_WARNING_MAX_MM)
    if runout_mm is None and prev:
        runout_warning = prev.runout_warning

    pv_warning = bool(pv_value_mpa_m_s is not None and pv_value_mpa_m_s > pv_warning_limit)
    if pv_value_mpa_m_s is None and prev:
        pv_warning = prev.pv_warning
    pv_critical_exceeded = bool(pv_value_mpa_m_s is not None and pv_value_mpa_m_s > pv_critical_limit)
    if pv_value_mpa_m_s is not None:
        if pv_critical_exceeded:
            notes.append(
                f"PV-Wert ({pv_value_mpa_m_s:.2f} MPa*m/s) überschreitet das kritische Limit von {pv_critical_limit:.2f} für {resolved_material_id}."
            )
        elif pv_warning:
            notes.append(
                f"PV-Wert ({pv_value_mpa_m_s:.2f} MPa*m/s) überschreitet das Warnlimit von {pv_warning_limit:.2f} für {resolved_material_id}."
            )

    lubrication_mode = str(payload.get("lubrication_mode") or payload.get("lubrication") or "").strip().lower()
    medium = str(payload.get("medium") or payload.get("medium_type") or "").strip()
    dry_running_risk = bool(
        (lubrication_mode in {"dry", "none"} and (v_surface_m_s or 0.0) > 1.0)
        or (not medium and not lubrication_mode and (v_surface_m_s or 0.0) > 4.0)
    )

    critical = bool(
        (hrc_value is not None and hrc_value < _HRC_CRITICAL_MIN)
        or (runout_mm is not None and runout_mm > _RUNOUT_CRITICAL_MAX_MM)
        or pv_critical_exceeded
        or (v_surface_m_s is not None and v_surface_m_s > _RWDR_SPEED_LIMIT_MAX)
        or material_limit_exceeded
    )
    has_data = any(
        value is not None
        for value in (diameter_mm, rpm, pressure_bar, v_surface_m_s, pv_value_mpa_m_s, hrc_value, runout_mm)
    )
    return {
        "v_surface_m_s": v_surface_m_s,
        "pv_value_mpa_m_s": pv_value_mpa_m_s,
        "hrc_value": hrc_value,
        "hrc_warning": hrc_warning,
        "runout_warning": runout_warning,
        "pv_warning": pv_warning,
        "friction_power_watts": friction_power_watts,
        "dry_running_risk": dry_running_risk,
        "critical": critical,
        "has_data": has_data,
        "notes": notes,
    }


def calc_extrusion(payload: Dict[str, Any], prev: Optional[LiveCalcTile] = None) -> Dict[str, Any]:
    pressure_bar = _first_float(payload, ("pressure_bar", "pressure_max_bar", "pressure", "p_max"))
    clearance_gap_mm = _first_float(payload, ("clearance_gap_mm", "clearance_gap", "gap_mm"))

    if clearance_gap_mm is None and prev:
        clearance_gap_mm = prev.clearance_gap_mm

    extrusion_risk = bool(
        (pressure_bar is not None and pressure_bar > 100.0 and clearance_gap_mm is not None and clearance_gap_mm > 0.1)
        or (pressure_bar is not None and pressure_bar > 250.0 and clearance_gap_mm is None)
    )
    if pressure_bar is None and clearance_gap_mm is None and prev:
        extrusion_risk = prev.extrusion_risk

    return {
        "clearance_gap_mm": clearance_gap_mm,
        "extrusion_risk": extrusion_risk,
        "requires_backup_ring": extrusion_risk,
        "has_data": pressure_bar is not None or clearance_gap_mm is not None,
    }


def calc_geometry(payload: Dict[str, Any], prev: Optional[LiveCalcTile] = None) -> Dict[str, Any]:
    cross_section_d2 = _first_float(payload, ("cross_section_d2", "d2", "seal_cross_section"))
    groove_depth = _first_float(payload, ("groove_depth", "groove_depth_mm"))
    groove_width = _first_float(payload, ("groove_width", "groove_width_mm"))
    shaft_d1 = _first_float(payload, ("shaft_d1", "d1", "shaft_diameter"))
    seal_inner_d = _first_float(payload, ("seal_inner_d", "seal_inner_diameter", "seal_id"))

    compression_ratio_pct: Optional[float] = None
    if cross_section_d2 is not None and groove_depth is not None and cross_section_d2 > 0:
        compression_ratio_pct = ((cross_section_d2 - groove_depth) / cross_section_d2) * 100.0
    elif prev:
        compression_ratio_pct = prev.compression_ratio_pct

    groove_fill_pct: Optional[float] = None
    if (
        cross_section_d2 is not None
        and groove_depth is not None
        and groove_width is not None
        and groove_depth > 0
        and groove_width > 0
    ):
        area_seal = math.pi * ((cross_section_d2 / 2.0) ** 2)
        area_groove = groove_width * groove_depth
        if area_groove > 0:
            groove_fill_pct = (area_seal / area_groove) * 100.0
    elif prev:
        groove_fill_pct = prev.groove_fill_pct

    stretch_pct: Optional[float] = None
    if shaft_d1 is not None and seal_inner_d is not None and seal_inner_d > 0:
        stretch_pct = ((shaft_d1 - seal_inner_d) / seal_inner_d) * 100.0
    elif prev:
        stretch_pct = prev.stretch_pct

    geometry_warning = False
    if compression_ratio_pct is not None and (compression_ratio_pct < 8.0 or compression_ratio_pct > 30.0):
        geometry_warning = True
    if groove_fill_pct is not None and groove_fill_pct > 85.0:
        geometry_warning = True
    if stretch_pct is not None and stretch_pct > 6.0:
        geometry_warning = True
    
    if (
        cross_section_d2 is None and groove_depth is None and groove_width is None
        and shaft_d1 is None and seal_inner_d is None and prev
    ):
        geometry_warning = prev.geometry_warning

    has_data = any(
        value is not None
        for value in (cross_section_d2, groove_depth, groove_width, shaft_d1, seal_inner_d, compression_ratio_pct, groove_fill_pct, stretch_pct)
    )
    return {
        "compression_ratio_pct": compression_ratio_pct,
        "groove_fill_pct": groove_fill_pct,
        "stretch_pct": stretch_pct,
        "geometry_warning": geometry_warning,
        "has_data": has_data,
    }


def calc_thermal(payload: Dict[str, Any], prev: Optional[LiveCalcTile] = None) -> Dict[str, Any]:
    temp_min_c = _first_float(payload, ("temp_min_c", "temperature_min_c", "temperature_min", "T_medium_min", "temp_min"))
    temp_max_c = _first_float(payload, ("temp_max_c", "temperature_max_c", "temperature_max", "T_medium_max", "temp_max"))
    diameter_mm = _get_diameter_mm(payload)

    thermal_expansion_mm: Optional[float] = None
    if diameter_mm is not None and temp_min_c is not None and temp_max_c is not None:
        thermal_expansion_mm = diameter_mm * _PTFE_ALPHA_PER_K * (temp_max_c - temp_min_c)
    elif prev:
        thermal_expansion_mm = prev.thermal_expansion_mm

    shrinkage_risk = bool(temp_min_c is not None and temp_min_c < -50.0)
    if temp_min_c is None and prev:
        shrinkage_risk = prev.shrinkage_risk

    has_data = any(value is not None for value in (temp_min_c, temp_max_c, thermal_expansion_mm))
    return {
        "thermal_expansion_mm": thermal_expansion_mm,
        "shrinkage_risk": shrinkage_risk,
        "has_data": has_data,
    }


def calc_chemical_resistance(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic chemical compatibility check for RWDR (v8 Fast-Path)."""
    material_raw = str(payload.get("elastomer_material") or payload.get("material") or "").strip()
    medium_raw = str(payload.get("medium") or "").strip()

    if not material_raw or not medium_raw:
        return {"chem_warning": False, "chem_message": None}

    # Normalize entities
    mat = normalize_entity("material", material_raw)
    med = normalize_entity("medium", medium_raw)

    # Repository query
    repo = get_chemical_repository()
    comp = repo.get_compatibility(mat, med)

    warning = False
    message = ""

    if comp.rating == RatingEnum.A:
        warning = False
        message = "Chemisch beständig."
    elif comp.rating == RatingEnum.B:
        warning = True
        msg_parts = ["Bedingt geeignet."]
        if comp.conditions:
             msg_parts.append(f"Constraints: {', '.join(comp.conditions)}")
        message = " ".join(msg_parts)
    elif comp.rating == RatingEnum.C:
        warning = True
        msg_parts = ["Strikt ausgeschlossen."]
        if comp.failure_modes:
            msg_parts.append(f"Failure modes: {', '.join(comp.failure_modes)}")
        message = " ".join(msg_parts)
    elif comp.rating == RatingEnum.U:
        warning = True
        message = "Unzureichende Daten für diese Kombination."

    return {"chem_warning": warning, "chem_message": message}


def node_p4_live_calc(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Compute deterministic live-tile values and warnings across physics domains."""
    payload = _collect_parameter_payload(state)
    prev = state.working_profile.live_calc_tile

    tribology = calc_tribology(payload, prev=prev)
    extrusion = calc_extrusion(payload, prev=prev)
    geometry = calc_geometry(payload, prev=prev)
    thermal = calc_thermal(payload, prev=prev)
    chem = calc_chemical_resistance(payload)

    risk_flags = bool(extrusion["extrusion_risk"] or geometry["geometry_warning"] or thermal["shrinkage_risk"])
    base_critical = bool(tribology["critical"])
    warning_flags = bool(
        tribology["hrc_warning"]
        or tribology["runout_warning"]
        or tribology["pv_warning"]
        or tribology["dry_running_risk"]
        or chem["chem_warning"]
    )
    has_meaningful_output = any(
        value is not None
        for value in (
            tribology["v_surface_m_s"],
            tribology["pv_value_mpa_m_s"],
            tribology["friction_power_watts"],
            tribology["hrc_value"],
            geometry["compression_ratio_pct"],
            geometry["groove_fill_pct"],
            geometry["stretch_pct"],
            thermal["thermal_expansion_mm"],
            extrusion["clearance_gap_mm"],
        )
    )

    status: Literal["ok", "warning", "critical", "insufficient_data"]
    if risk_flags or base_critical:
        status = "critical"
    elif warning_flags:
        status = "warning"
    elif has_meaningful_output:
        status = "ok"
    else:
        status = "insufficient_data"

    captured_parameters = _collect_captured_parameters(state)

    calc_results = state.working_profile.calc_results or CalcResults()
    calc_results.v_surface_m_s = tribology["v_surface_m_s"]
    calc_results.pv_value_mpa_m_s = tribology["pv_value_mpa_m_s"]
    calc_results.friction_power_watts = tribology["friction_power_watts"]
    calc_results.hrc_warning = tribology["hrc_warning"]
    calc_results.notes = tribology.get("notes", [])

    tile = LiveCalcTile(
        v_surface_m_s=tribology["v_surface_m_s"],
        pv_value_mpa_m_s=tribology["pv_value_mpa_m_s"],
        hrc_value=tribology["hrc_value"],
        hrc_warning=tribology["hrc_warning"],
        runout_warning=tribology["runout_warning"],
        pv_warning=tribology["pv_warning"],
        friction_power_watts=tribology["friction_power_watts"],
        dry_running_risk=tribology["dry_running_risk"],
        clearance_gap_mm=extrusion["clearance_gap_mm"],
        extrusion_risk=extrusion["extrusion_risk"],
        requires_backup_ring=extrusion["requires_backup_ring"],
        compression_ratio_pct=geometry["compression_ratio_pct"],
        groove_fill_pct=geometry["groove_fill_pct"],
        stretch_pct=geometry["stretch_pct"],
        geometry_warning=geometry["geometry_warning"],
        thermal_expansion_mm=thermal["thermal_expansion_mm"],
        shrinkage_risk=thermal["shrinkage_risk"],
        chem_warning=chem["chem_warning"],
        chem_message=chem["chem_message"],
        status=status,
        parameters=captured_parameters,
    )

    logger.info(
        "p4_live_calc_done",
        v_surface_m_s=tile.v_surface_m_s,
        pv_value_mpa_m_s=tile.pv_value_mpa_m_s,
        friction_power_watts=tile.friction_power_watts,
        extrusion_risk=tile.extrusion_risk,
        requires_backup_ring=tile.requires_backup_ring,
        compression_ratio_pct=tile.compression_ratio_pct,
        groove_fill_pct=tile.groove_fill_pct,
        stretch_pct=tile.stretch_pct,
        thermal_expansion_mm=tile.thermal_expansion_mm,
        shrinkage_risk=tile.shrinkage_risk,
        status=tile.status,
        run_id=state.system.run_id,
        thread_id=state.conversation.thread_id,
    )

    return stamp_patch_with_assertion_binding(state, {
        "working_profile": {
            "calc_results": calc_results,
            "live_calc_tile": tile,
        },
        "reasoning": {
            "phase": PHASE.CALCULATION,
            "last_node": "node_p4_live_calc",
        },
    })


__all__ = ["node_p4_live_calc", "calc_tribology", "calc_extrusion", "calc_geometry", "calc_thermal", "_collect_captured_parameters"]
