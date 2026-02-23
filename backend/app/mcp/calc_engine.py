"""MCP Gasket Calculation Engine — pure-Python deterministic tool.

R1: LLMs never compute. All engineering calculations run through this
tool with typed I/O (CalcInput -> CalcOutput).

Registered as MCP tool with scope ``mcp:calc:execute``.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import structlog

from app.mcp.calc_schemas import CalcInput, CalcOutput

logger = structlog.get_logger("mcp.calc_engine")

# ---------------------------------------------------------------------------
# Scope for MCP tool registry
# ---------------------------------------------------------------------------

MCP_CALC_EXECUTE_SCOPES = frozenset({"mcp:calc:execute"})
CALC_GASKET_TOOL_NAME = "calc_gasket"

# ---------------------------------------------------------------------------
# Lookup tables — EN 1514-1 / EN 1092-1 / ASME B16.20 reference dimensions
# ---------------------------------------------------------------------------

# DN -> (gasket_inner_d_mm, gasket_outer_d_mm, bolt_circle_d_mm)
# Simplified subset covering common sizes for spiral-wound gaskets (EN 1514-1 Form IBC).
_EN_GASKET_DIMENSIONS: Dict[int, Tuple[float, float, float]] = {
    15: (21.3, 34.5, 65.0),
    20: (26.9, 42.5, 75.0),
    25: (33.7, 50.5, 85.0),
    32: (42.4, 62.5, 100.0),
    40: (48.3, 70.5, 110.0),
    50: (60.3, 82.5, 125.0),
    65: (76.1, 102.5, 145.0),
    80: (88.9, 114.5, 160.0),
    100: (114.3, 146.5, 190.0),
    125: (139.7, 172.5, 220.0),
    150: (168.3, 202.5, 250.0),
    200: (219.1, 262.5, 310.0),
    250: (273.0, 320.5, 370.0),
    300: (323.9, 372.5, 430.0),
    350: (355.6, 410.5, 470.0),
    400: (406.4, 462.5, 525.0),
    450: (457.0, 518.5, 585.0),
    500: (508.0, 572.5, 640.0),
    600: (610.0, 676.5, 755.0),
}

# ASME B16.20 spiral-wound gasket inner/outer based on NPS (DN approx).
# Simplified; real ASME dims differ by class — we use Class 150 reference.
_ASME_GASKET_DIMENSIONS: Dict[int, Tuple[float, float, float]] = {
    15: (21.3, 34.8, 66.7),
    20: (26.7, 42.9, 76.2),
    25: (33.4, 50.8, 88.9),
    40: (48.3, 69.9, 114.3),
    50: (60.3, 82.6, 127.0),
    80: (88.9, 114.3, 168.3),
    100: (114.3, 149.4, 200.0),
    150: (168.3, 206.4, 254.0),
    200: (219.1, 260.4, 311.2),
    250: (273.1, 319.2, 368.3),
    300: (323.9, 374.7, 431.8),
    400: (406.4, 463.6, 533.4),
    500: (508.0, 571.5, 641.4),
    600: (609.6, 676.3, 755.7),
}

# Bolt M-size → proof load in kN (Grade 8.8, ~80% proof stress).
_BOLT_CAPACITY_KN: Dict[str, float] = {
    "M10": 32.0,
    "M12": 47.0,
    "M14": 65.0,
    "M16": 88.0,
    "M18": 110.0,
    "M20": 137.0,
    "M22": 170.0,
    "M24": 198.0,
    "M27": 260.0,
    "M30": 318.0,
    "M33": 393.0,
    "M36": 466.0,
}

# Material temperature limits (generic upper bounds, °C).
_MATERIAL_T_MAX_C = 550.0  # Spiral-wound 316L + flexible graphite filler
_MATERIAL_P_MAX_BAR = 250.0  # Conservative spiral-wound pressure rating

# Critical media set (case-insensitive matching).
_CRITICAL_MEDIA = frozenset({
    "h2", "hydrogen", "wasserstoff",
    "o2", "oxygen", "sauerstoff",
    "cl2", "chlor", "chlorine",
    "hf", "flusssaeure", "fluorwasserstoff",
    "nh3", "ammoniak", "ammonia",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lookup_gasket_dims(
    dn: Optional[int], standard: Optional[str]
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Return (inner_d, outer_d, bolt_circle_d) from lookup tables."""
    if dn is None:
        return None, None, None

    std = (standard or "").upper().strip()
    if "ASME" in std or "B16" in std:
        table = _ASME_GASKET_DIMENSIONS
    else:
        table = _EN_GASKET_DIMENSIONS

    if dn in table:
        return table[dn]

    # Find closest DN
    available = sorted(table.keys())
    closest = min(available, key=lambda d: abs(d - dn))
    return table[closest]


def _bolt_capacity(bolt_size: Optional[str]) -> Optional[float]:
    """Return single-bolt capacity in kN from M-size string."""
    if not bolt_size:
        return None
    size = bolt_size.strip().upper()
    if not size.startswith("M"):
        return None
    return _BOLT_CAPACITY_KN.get(size)


def _is_critical_medium(medium: Optional[str]) -> bool:
    """Check if medium is in the critical media set."""
    if not medium:
        return False
    normalized = medium.strip().lower().replace(" ", "")
    return normalized in _CRITICAL_MEDIA


def _gasket_area(inner_d: float, outer_d: float) -> float:
    """Annular gasket seating area in mm^2."""
    return math.pi / 4.0 * (outer_d**2 - inner_d**2)


# ---------------------------------------------------------------------------
# Main calculation function
# ---------------------------------------------------------------------------


def mcp_calc_gasket(params: CalcInput) -> CalcOutput:
    """Deterministic gasket flange calculation (MCP tool).

    Computes gasket geometry, bolt loads, safety factors, and margins
    from the given input parameters. No LLM involvement (R1).
    """
    notes: List[str] = []
    warnings: List[str] = []

    # --- Gasket geometry ---
    inner_d, outer_d, bolt_circle_d = _lookup_gasket_dims(
        params.flange_dn, params.flange_standard
    )

    if inner_d is None or outer_d is None:
        # Fallback: use DN directly as approximate pipe OD
        dn = params.flange_dn or 100
        inner_d = float(dn)
        outer_d = float(dn) + 30.0
        bolt_circle_d = float(dn) + 60.0
        notes.append(f"DN{dn} not in lookup table; using approximate dimensions.")

    gasket_area_mm2 = _gasket_area(inner_d, outer_d)

    # --- Required gasket stress ---
    # Required seating force = pressure * bore area / gasket area
    # Simplified: F_req = p * A_bore, then sigma_req = F_req / A_gasket
    bore_area_mm2 = math.pi / 4.0 * inner_d**2
    pressure_mpa = params.pressure_max_bar * 0.1  # 1 bar = 0.1 MPa
    force_from_pressure_n = pressure_mpa * bore_area_mm2  # N (MPa * mm^2 = N)
    required_gasket_stress_mpa = force_from_pressure_n / gasket_area_mm2 if gasket_area_mm2 > 0 else 0.0

    # Minimum gasket seating stress (spiral-wound, flexible graphite filler)
    min_seating_stress_mpa = 69.0  # EN 13555 y-value for CG-type
    if required_gasket_stress_mpa < min_seating_stress_mpa:
        required_gasket_stress_mpa = min_seating_stress_mpa
        notes.append(
            f"Required stress raised to minimum seating stress ({min_seating_stress_mpa} MPa)."
        )

    # --- Bolt load ---
    bolt_capacity_per_bolt = _bolt_capacity(params.bolt_size)
    available_bolt_load_kn: Optional[float] = None
    safety_factor = 0.0

    if bolt_capacity_per_bolt is not None and params.bolt_count:
        available_bolt_load_kn = bolt_capacity_per_bolt * params.bolt_count
        available_force_n = available_bolt_load_kn * 1000.0  # kN -> N
        available_stress_mpa = available_force_n / gasket_area_mm2 if gasket_area_mm2 > 0 else 0.0
        safety_factor = available_stress_mpa / required_gasket_stress_mpa if required_gasket_stress_mpa > 0 else 0.0
    else:
        # Without bolt data, estimate conservative safety factor
        safety_factor = 1.0
        notes.append("Bolt data incomplete; safety factor set to 1.0 (unverified).")

    # --- Margins ---
    temperature_margin_c = _MATERIAL_T_MAX_C - params.temperature_max_c
    pressure_margin_bar = _MATERIAL_P_MAX_BAR - params.pressure_max_bar

    # --- Critical application check ---
    is_critical = (
        _is_critical_medium(params.medium)
        or params.pressure_max_bar > 100.0
        or params.temperature_max_c > 400.0
        or params.temperature_max_c < -40.0
    )

    # --- Warnings ---
    if safety_factor < 1.0 and available_bolt_load_kn is not None:
        warnings.append(
            f"Safety factor {safety_factor:.2f} < 1.0 — bolt load insufficient for required gasket stress."
        )
    if safety_factor < 1.5 and safety_factor >= 1.0 and available_bolt_load_kn is not None:
        warnings.append(
            f"Safety factor {safety_factor:.2f} < 1.5 — marginal bolt load; review recommended."
        )
    if temperature_margin_c < 0:
        warnings.append(
            f"Temperature {params.temperature_max_c} C exceeds material limit {_MATERIAL_T_MAX_C} C."
        )
    if pressure_margin_bar < 0:
        warnings.append(
            f"Pressure {params.pressure_max_bar} bar exceeds material limit {_MATERIAL_P_MAX_BAR} bar."
        )
    if params.cyclic_load:
        warnings.append("Cyclic load detected — fatigue analysis recommended.")
    if is_critical:
        warnings.append("Critical application flagged — enhanced QA/inspection required.")

    result = CalcOutput(
        gasket_inner_d_mm=round(inner_d, 1),
        gasket_outer_d_mm=round(outer_d, 1),
        bolt_circle_d_mm=round(bolt_circle_d, 1) if bolt_circle_d else None,
        required_gasket_stress_mpa=round(required_gasket_stress_mpa, 2),
        available_bolt_load_kn=round(available_bolt_load_kn, 1) if available_bolt_load_kn is not None else None,
        safety_factor=round(safety_factor, 2),
        temperature_margin_c=round(temperature_margin_c, 1),
        pressure_margin_bar=round(pressure_margin_bar, 1),
        is_critical_application=is_critical,
        notes=notes,
        warnings=warnings,
    )

    logger.info(
        "mcp_calc_gasket_done",
        dn=params.flange_dn,
        pressure_bar=params.pressure_max_bar,
        temperature_c=params.temperature_max_c,
        safety_factor=result.safety_factor,
        is_critical=result.is_critical_application,
        warning_count=len(warnings),
    )

    return result


# ---------------------------------------------------------------------------
# MCP tool spec for registry
# ---------------------------------------------------------------------------

CALC_GASKET_TOOL_SPEC = {
    "name": CALC_GASKET_TOOL_NAME,
    "description": (
        "Deterministic flange gasket calculation. Computes gasket geometry, "
        "bolt load verification, safety factors, and temperature/pressure margins. "
        "No LLM — pure engineering formulas."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "pressure_max_bar": {"type": "number", "description": "Max operating pressure in bar"},
            "temperature_max_c": {"type": "number", "description": "Max operating temperature in C"},
            "flange_standard": {"type": "string", "description": "Flange standard (e.g. EN 1092-1, ASME B16.5)"},
            "flange_dn": {"type": "integer", "description": "Nominal diameter DN"},
            "flange_pn": {"type": "integer", "description": "Nominal pressure PN"},
            "flange_class": {"type": "integer", "description": "ASME pressure class"},
            "bolt_count": {"type": "integer", "description": "Number of bolts"},
            "bolt_size": {"type": "string", "description": "Bolt size (e.g. M20)"},
            "medium": {"type": "string", "description": "Process medium"},
            "cyclic_load": {"type": "boolean", "description": "Whether cyclic loading is present"},
        },
        "required": ["pressure_max_bar", "temperature_max_c"],
    },
}


__all__ = [
    "CALC_GASKET_TOOL_NAME",
    "CALC_GASKET_TOOL_SPEC",
    "CalcInput",
    "CalcOutput",
    "MCP_CALC_EXECUTE_SCOPES",
    "mcp_calc_gasket",
]
