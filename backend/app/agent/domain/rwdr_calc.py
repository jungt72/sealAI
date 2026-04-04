"""
RWDR Deterministic Calculation Core.

Pure-function physics engine for RWDR (Radialwellendichtring) analysis.
All formulas are deterministic; no LLM calls, no external service dependencies.

DIN 3760 reference for Umfangsgeschwindigkeit: v = (d * π * n) / 60 000 [m/s]

Public API:
- calculate_rwdr(input: RwdrCalcInput) → RwdrCalcResult
- calc_tribology(payload: dict) → dict
- calc_extrusion(payload: dict) → dict
- calc_geometry(payload: dict) → dict
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Optional

# ---------------------------------------------------------------------------
# Expert limits
# ---------------------------------------------------------------------------

_HRC_WARNING_MIN = 58.0
_HRC_CRITICAL_MIN = 55.0
_RUNOUT_WARNING_MAX_MM = 0.2
_RUNOUT_CRITICAL_MAX_MM = 0.3
_DN_WARNING_THRESHOLD = 500_000.0   # mm·min⁻¹ — Dn = d × n (CLAUDE.md)
_FRICTION_COEFF_PTFE = 0.15
_PTFE_ALPHA_PER_K = 1.2e-4

# RWDR expert limits (preserved verbatim)
_RWDR_SPEED_LIMIT_NBR = 12.0
_RWDR_SPEED_LIMIT_MAX = 35.0
_RWDR_HRC_MIN_HIGH_SPEED = 45.0
_RWDR_HIGH_SPEED_THRESHOLD = 4.0

# ---------------------------------------------------------------------------
# Static material profile table (standard RWDR elastomers; conservative fallbacks)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RwdrMaterialProfile:
    material_id: str
    v_surface_max: float        # m/s — Umfangsgeschwindigkeit Limit
    pv_limit_warning: float     # MPa·m/s
    pv_limit_critical: float    # MPa·m/s
    temp_min: Optional[float]   # °C
    temp_max: Optional[float]   # °C


_MATERIAL_PROFILES: Dict[str, RwdrMaterialProfile] = {
    "NBR":    RwdrMaterialProfile("NBR",    v_surface_max=12.0, pv_limit_warning=1.5, pv_limit_critical=2.0,  temp_min=-40.0, temp_max=100.0),
    "FKM":    RwdrMaterialProfile("FKM",    v_surface_max=16.0, pv_limit_warning=2.0, pv_limit_critical=3.0,  temp_min=-20.0, temp_max=200.0),
    "PTFE":   RwdrMaterialProfile("PTFE",   v_surface_max=20.0, pv_limit_warning=3.0, pv_limit_critical=5.0,  temp_min=-60.0, temp_max=260.0),
    "EPDM":   RwdrMaterialProfile("EPDM",   v_surface_max=8.0,  pv_limit_warning=1.0, pv_limit_critical=1.5,  temp_min=-50.0, temp_max=150.0),
    "HNBR":   RwdrMaterialProfile("HNBR",   v_surface_max=14.0, pv_limit_warning=2.0, pv_limit_critical=3.0,  temp_min=-30.0, temp_max=150.0),
    "FFKM":   RwdrMaterialProfile("FFKM",   v_surface_max=25.0, pv_limit_warning=3.0, pv_limit_critical=5.0,  temp_min=-20.0, temp_max=327.0),
    "SILIKON": RwdrMaterialProfile("SILIKON",v_surface_max=6.0,  pv_limit_warning=0.5, pv_limit_critical=1.0,  temp_min=-60.0, temp_max=200.0),
    "VMQ":    RwdrMaterialProfile("VMQ",    v_surface_max=6.0,  pv_limit_warning=0.5, pv_limit_critical=1.0,  temp_min=-60.0, temp_max=200.0),
    "ACM":    RwdrMaterialProfile("ACM",    v_surface_max=10.0, pv_limit_warning=1.5, pv_limit_critical=2.5,  temp_min=-30.0, temp_max=150.0),
}

# Alias normalization for common trade/synonym names
_MATERIAL_ALIASES: Dict[str, str] = {
    "VITON": "FKM",
    "KALREZ": "FFKM",
    "NITRIL": "NBR",
    "NITRILKAUTSCHUK": "NBR",
    "PERBUNAN": "NBR",
    "TEFLON": "PTFE",
    "TECNOFLON": "FKM",
}


def _resolve_material_profile(material_raw: str) -> Optional[RwdrMaterialProfile]:
    """Return the RwdrMaterialProfile for *material_raw*, or None if unknown."""
    upper = material_raw.strip().upper()
    # Direct match
    if upper in _MATERIAL_PROFILES:
        return _MATERIAL_PROFILES[upper]
    # Alias match
    canonical = _MATERIAL_ALIASES.get(upper)
    if canonical:
        return _MATERIAL_PROFILES.get(canonical)
    # Substring match (e.g. "FKM A75" → FKM)
    for key in _MATERIAL_PROFILES:
        if key in upper:
            return _MATERIAL_PROFILES[key]
    return None


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

_NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


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


def _get_diameter_mm(payload: Dict[str, Any]) -> Optional[float]:
    return _first_float(
        payload,
        (
            "shaft_diameter",
            "shaft_d1",
            "d1",
            "d_shaft_nominal",
            "diameter",
            "nominal_diameter",
            "rod_diameter",
            "inner_diameter_mm",
        ),
    )


# ---------------------------------------------------------------------------
# Pure calculation functions
# ---------------------------------------------------------------------------

def calc_tribology(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Tribology calculations for RWDR: v_surface, pv-value, Dn-value, warnings."""
    diameter_mm = _get_diameter_mm(payload)
    rpm = _first_float(payload, ("speed_rpm", "rpm", "n", "n_max"))
    pressure_bar = _first_float(payload, ("pressure_max_bar", "pressure_bar", "pressure", "p_max"))
    hrc_value = _first_float(payload, ("surface_hardness_hrc", "hrc", "hrc_value", "shaft_hardness", "hardness"))
    runout_mm = _first_float(payload, ("runout_mm", "runout", "shaft_runout", "dynamic_runout"))
    temp_max_c = _first_float(payload, ("temperature_max_c", "temp_max_c", "temperature_max", "T_medium_max", "temp_max"))

    material_raw = str(payload.get("elastomer_material") or payload.get("material") or "").strip()
    material = material_raw.upper()

    # Dn-Wert: Dn = d × n [mm·min⁻¹] — kinematic bearing indicator (CLAUDE.md)
    dn_value: Optional[float] = None
    if diameter_mm is not None and rpm is not None and diameter_mm >= 0 and rpm >= 0:
        dn_value = diameter_mm * rpm

    # DIN 3760: v = (d * π * n) / 60 000 [m/s]
    v_surface_m_s: Optional[float] = None
    if diameter_mm is not None and rpm is not None and diameter_mm >= 0 and rpm >= 0:
        v_surface_m_s = (diameter_mm * math.pi * rpm) / 60000.0

    # PV value [MPa·m/s]
    pv_value_mpa_m_s: Optional[float] = None
    if v_surface_m_s is not None and pressure_bar is not None and pressure_bar >= 0:
        pv_value_mpa_m_s = (pressure_bar * 0.1) * v_surface_m_s

    # Friction power (RWDR expert approximation): Pr [W] ≈ 0.5 * d1 [mm] * vs [m/s]
    friction_power_watts: Optional[float] = None
    if v_surface_m_s is not None and diameter_mm is not None:
        friction_power_watts = 0.5 * diameter_mm * v_surface_m_s

    # HRC warning: standard limit + RWDR expert high-speed limit
    hrc_warning = False
    if hrc_value is not None:
        if hrc_value < _HRC_WARNING_MIN:
            hrc_warning = True
        if v_surface_m_s is not None and v_surface_m_s > _RWDR_HIGH_SPEED_THRESHOLD and hrc_value < _RWDR_HRC_MIN_HIGH_SPEED:
            hrc_warning = True

    notes: List[str] = []
    material_limit_exceeded = False

    # Material profile lookup — static table (replaces get_material_repository())
    speed_limit = _RWDR_SPEED_LIMIT_MAX
    pv_warning_limit = 2.0
    pv_critical_limit = 3.0
    temp_min_limit: Optional[float] = None
    temp_max_limit: Optional[float] = None
    resolved_material_id = material or "Material"

    if material_raw:
        mat_profile = _resolve_material_profile(material_raw)
        if mat_profile:
            speed_limit = mat_profile.v_surface_max
            pv_warning_limit = mat_profile.pv_limit_warning
            pv_critical_limit = mat_profile.pv_limit_critical
            temp_min_limit = mat_profile.temp_min
            temp_max_limit = mat_profile.temp_max
            resolved_material_id = mat_profile.material_id
        else:
            # Conservative fallback (preserved from legacy)
            speed_limit = 12.0
            pv_warning_limit = 1.5
            pv_critical_limit = 2.0

    if material_raw and v_surface_m_s is not None and v_surface_m_s > speed_limit:
        material_limit_exceeded = True
        notes.append(
            f"Umfangsgeschwindigkeit ({v_surface_m_s:.1f} m/s) liegt über Limit "
            f"für {resolved_material_id} ({speed_limit:.1f} m/s)."
        )

    if material_raw and temp_max_c is not None:
        if temp_min_limit is not None and temp_max_c < temp_min_limit:
            notes.append(
                f"Einsatztemperatur ({temp_max_c:.0f}°C) liegt unter dem Minimum "
                f"({temp_min_limit:.0f}°C) für {resolved_material_id}."
            )
        if temp_max_limit is not None and temp_max_c > temp_max_limit:
            material_limit_exceeded = True
            notes.append(
                f"Einsatztemperatur ({temp_max_c:.0f}°C) überschreitet das Maximum "
                f"({temp_max_limit:.0f}°C) für {resolved_material_id}."
            )

    # NBR speed limit (preserved verbatim)
    if v_surface_m_s is not None and v_surface_m_s > _RWDR_SPEED_LIMIT_NBR and "NBR" in material:
        hrc_warning = True

    runout_warning = bool(runout_mm is not None and runout_mm > _RUNOUT_WARNING_MAX_MM)

    # Dn warning: Dn > 500 000 mm·min⁻¹ indicates elevated bearing/seal stress
    dn_warning = bool(dn_value is not None and dn_value > _DN_WARNING_THRESHOLD)
    if dn_warning:
        notes.append(
            f"Dn-Wert ({dn_value:.0f} mm·min⁻¹) überschreitet Richtwert "
            f"{_DN_WARNING_THRESHOLD:.0f} mm·min⁻¹ — erhöhte tribologische Beanspruchung."
        )

    pv_warning = bool(pv_value_mpa_m_s is not None and pv_value_mpa_m_s > pv_warning_limit)
    pv_critical_exceeded = bool(pv_value_mpa_m_s is not None and pv_value_mpa_m_s > pv_critical_limit)
    if pv_value_mpa_m_s is not None:
        if pv_critical_exceeded:
            notes.append(
                f"PV-Wert ({pv_value_mpa_m_s:.2f} MPa*m/s) überschreitet das kritische "
                f"Limit von {pv_critical_limit:.2f} für {resolved_material_id}."
            )
        elif pv_warning:
            notes.append(
                f"PV-Wert ({pv_value_mpa_m_s:.2f} MPa*m/s) überschreitet das Warnlimit "
                f"von {pv_warning_limit:.2f} für {resolved_material_id}."
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
        v is not None
        for v in (diameter_mm, rpm, pressure_bar, v_surface_m_s, pv_value_mpa_m_s, hrc_value, runout_mm, dn_value)
    )

    return {
        "v_surface_m_s": v_surface_m_s,
        "pv_value_mpa_m_s": pv_value_mpa_m_s,
        "dn_value": dn_value,
        "dn_warning": dn_warning,
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


def calc_extrusion(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extrusion-gap risk check."""
    pressure_bar = _first_float(payload, ("pressure_bar", "pressure_max_bar", "pressure", "p_max"))
    clearance_gap_mm = _first_float(payload, ("clearance_gap_mm", "clearance_gap", "gap_mm"))

    extrusion_risk = bool(
        (pressure_bar is not None and pressure_bar > 100.0 and clearance_gap_mm is not None and clearance_gap_mm > 0.1)
        or (pressure_bar is not None and pressure_bar > 250.0 and clearance_gap_mm is None)
    )

    return {
        "clearance_gap_mm": clearance_gap_mm,
        "extrusion_risk": extrusion_risk,
        "requires_backup_ring": extrusion_risk,
        "has_data": pressure_bar is not None or clearance_gap_mm is not None,
    }


def calc_geometry(payload: Dict[str, Any]) -> Dict[str, Any]:
    """O-ring / seal geometry checks: compression ratio, groove fill, radial gap."""
    cross_section_d2 = _first_float(payload, ("cross_section_d2", "d2", "seal_cross_section"))
    groove_depth = _first_float(payload, ("groove_depth", "groove_depth_mm"))
    groove_width = _first_float(payload, ("groove_width", "groove_width_mm"))
    shaft_d1 = _first_float(payload, ("shaft_d1", "d1", "shaft_diameter"))
    seal_inner_d = _first_float(payload, ("seal_inner_d", "seal_inner_diameter", "seal_id"))

    compression_ratio_pct: Optional[float] = None
    if cross_section_d2 is not None and groove_depth is not None and cross_section_d2 > 0:
        compression_ratio_pct = ((cross_section_d2 - groove_depth) / cross_section_d2) * 100.0

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

    stretch_pct: Optional[float] = None
    if shaft_d1 is not None and seal_inner_d is not None and seal_inner_d > 0:
        stretch_pct = ((shaft_d1 - seal_inner_d) / seal_inner_d) * 100.0

    geometry_warning = False
    if compression_ratio_pct is not None and (compression_ratio_pct < 8.0 or compression_ratio_pct > 30.0):
        geometry_warning = True
    if groove_fill_pct is not None and groove_fill_pct > 85.0:
        geometry_warning = True
    if stretch_pct is not None and stretch_pct > 6.0:
        geometry_warning = True

    has_data = any(
        v is not None
        for v in (cross_section_d2, groove_depth, groove_width, shaft_d1, seal_inner_d,
                  compression_ratio_pct, groove_fill_pct, stretch_pct)
    )
    return {
        "compression_ratio_pct": compression_ratio_pct,
        "groove_fill_pct": groove_fill_pct,
        "stretch_pct": stretch_pct,
        "geometry_warning": geometry_warning,
        "has_data": has_data,
    }


def calc_thermal(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Thermal expansion / shrinkage check (preserved verbatim from p4_live_calc.py)."""
    temp_min_c = _first_float(payload, ("temp_min_c", "temperature_min_c", "temperature_min", "T_medium_min", "temp_min"))
    temp_max_c = _first_float(payload, ("temp_max_c", "temperature_max_c", "temperature_max", "T_medium_max", "temp_max"))
    diameter_mm = _get_diameter_mm(payload)

    thermal_expansion_mm: Optional[float] = None
    if diameter_mm is not None and temp_min_c is not None and temp_max_c is not None:
        thermal_expansion_mm = diameter_mm * _PTFE_ALPHA_PER_K * (temp_max_c - temp_min_c)

    shrinkage_risk = bool(temp_min_c is not None and temp_min_c < -50.0)

    has_data = any(v is not None for v in (temp_min_c, temp_max_c, thermal_expansion_mm))
    return {
        "thermal_expansion_mm": thermal_expansion_mm,
        "shrinkage_risk": shrinkage_risk,
        "has_data": has_data,
    }


# ---------------------------------------------------------------------------
# Typed I/O models for the agent tool
# ---------------------------------------------------------------------------

@dataclass
class RwdrCalcInput:
    """Typed input for calculate_rwdr().

    All lengths in mm, speeds in rpm, pressures in bar, temperatures in °C.
    shaft_diameter_mm and rpm are the only required fields for basic tribology.
    """
    shaft_diameter_mm: float
    rpm: float
    pressure_bar: Optional[float] = None
    temperature_max_c: Optional[float] = None
    temperature_min_c: Optional[float] = None
    surface_hardness_hrc: Optional[float] = None
    runout_mm: Optional[float] = None
    clearance_gap_mm: Optional[float] = None
    elastomer_material: Optional[str] = None
    medium: Optional[str] = None
    lubrication_mode: Optional[str] = None    # "dry" | "none" | "" for lubricated
    # Geometry (optional, for compression/fill checks)
    cross_section_d2_mm: Optional[float] = None
    groove_depth_mm: Optional[float] = None
    groove_width_mm: Optional[float] = None
    seal_inner_diameter_mm: Optional[float] = None


@dataclass
class RwdrCalcResult:
    """Typed output from calculate_rwdr()."""
    # Tribology
    v_surface_m_s: Optional[float]
    pv_value_mpa_m_s: Optional[float]
    dn_value: Optional[float]
    friction_power_watts: Optional[float]
    # Warnings
    dn_warning: bool
    hrc_warning: bool
    runout_warning: bool
    pv_warning: bool
    dry_running_risk: bool
    material_limit_exceeded: bool
    # Geometry
    compression_ratio_pct: Optional[float]
    groove_fill_pct: Optional[float]
    stretch_pct: Optional[float]
    geometry_warning: bool
    # Thermal
    thermal_expansion_mm: Optional[float]
    shrinkage_risk: bool
    # Extrusion
    clearance_gap_mm: Optional[float]
    extrusion_risk: bool
    requires_backup_ring: bool
    # Overall
    status: Literal["ok", "warning", "critical", "insufficient_data"]
    notes: List[str]


# ---------------------------------------------------------------------------
# Top-level entry point (pure function — no state, no LLM)
# ---------------------------------------------------------------------------

def calculate_rwdr(inp: RwdrCalcInput) -> RwdrCalcResult:
    """Run all RWDR sub-calculations for the given input and return a typed result.

    This is the canonical entry point for the agent tool.  It is deterministic,
    stateless, and never calls an LLM.

    Args:
        inp: RwdrCalcInput with shaft_diameter_mm and rpm as the only required fields.

    Returns:
        RwdrCalcResult with all calculated values and warning flags.
    """
    payload: Dict[str, Any] = {
        "shaft_diameter": inp.shaft_diameter_mm,
        "speed_rpm": inp.rpm,
        "pressure_bar": inp.pressure_bar,
        "temp_max_c": inp.temperature_max_c,
        "temp_min_c": inp.temperature_min_c,
        "surface_hardness_hrc": inp.surface_hardness_hrc,
        "runout_mm": inp.runout_mm,
        "clearance_gap_mm": inp.clearance_gap_mm,
        "elastomer_material": inp.elastomer_material,
        "medium": inp.medium,
        "lubrication_mode": inp.lubrication_mode,
        "cross_section_d2": inp.cross_section_d2_mm,
        "groove_depth": inp.groove_depth_mm,
        "groove_width": inp.groove_width_mm,
        "seal_inner_d": inp.seal_inner_diameter_mm,
    }

    tribo = calc_tribology(payload)
    extru = calc_extrusion(payload)
    geom = calc_geometry(payload)
    therm = calc_thermal(payload)

    risk_flags = bool(extru["extrusion_risk"] or geom["geometry_warning"] or therm["shrinkage_risk"])
    base_critical = bool(tribo["critical"])
    warning_flags = bool(
        tribo["dn_warning"]
        or tribo["hrc_warning"]
        or tribo["runout_warning"]
        or tribo["pv_warning"]
        or tribo["dry_running_risk"]
    )
    has_meaningful_output = any(
        v is not None
        for v in (
            tribo["v_surface_m_s"],
            tribo["pv_value_mpa_m_s"],
            tribo["friction_power_watts"],
            tribo["hrc_value"],
            geom["compression_ratio_pct"],
            geom["groove_fill_pct"],
            geom["stretch_pct"],
            therm["thermal_expansion_mm"],
            extru["clearance_gap_mm"],
        )
    )

    if risk_flags or base_critical:
        status: Literal["ok", "warning", "critical", "insufficient_data"] = "critical"
    elif warning_flags:
        status = "warning"
    elif has_meaningful_output:
        status = "ok"
    else:
        status = "insufficient_data"

    return RwdrCalcResult(
        v_surface_m_s=tribo["v_surface_m_s"],
        pv_value_mpa_m_s=tribo["pv_value_mpa_m_s"],
        dn_value=tribo["dn_value"],
        friction_power_watts=tribo["friction_power_watts"],
        dn_warning=tribo["dn_warning"],
        hrc_warning=tribo["hrc_warning"],
        runout_warning=tribo["runout_warning"],
        pv_warning=tribo["pv_warning"],
        dry_running_risk=tribo["dry_running_risk"],
        material_limit_exceeded=bool(tribo.get("critical") and not (
            (tribo.get("hrc_value") or 999) < _HRC_CRITICAL_MIN
            or (tribo.get("runout_warning"))
        )),
        compression_ratio_pct=geom["compression_ratio_pct"],
        groove_fill_pct=geom["groove_fill_pct"],
        stretch_pct=geom["stretch_pct"],
        geometry_warning=geom["geometry_warning"],
        thermal_expansion_mm=therm["thermal_expansion_mm"],
        shrinkage_risk=therm["shrinkage_risk"],
        clearance_gap_mm=extru["clearance_gap_mm"],
        extrusion_risk=extru["extrusion_risk"],
        requires_backup_ring=extru["requires_backup_ring"],
        status=status,
        notes=tribo["notes"],
    )
