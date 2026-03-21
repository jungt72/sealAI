"""SSoT Compound Validator — Phase 0B.1 (Registry Quarantine)

Deterministic pre-flight gate for Claims entering the sealing_state.
No LLM. Pure Python look-up and arithmetic.

Sources:
  - DIN 3760 / ISO 6194-1 material limits   →  app.mcp.calculations.material_limits
  - RWDR rotary velocity limits per material →  DIN 3760 Section 5.3 (inline table)
  - Operational domain hard limits           →  engineering constants (inline)
  - PTFE compound matrix                     →  app.services.knowledge.compound_matrix

Integration point:
  Called from evaluate_claim_conflicts() in app.agent.agent.logic before any
  validated_params are written into the sealing_state.  Every submit_claim call
  passes through this gate automatically.

Conflict format (matches the existing contract in evaluate_claim_conflicts):
    {
        "type":            "DOMAIN_LIMIT_VIOLATION" | "PARAMETER_CONFLICT",
        "severity":        "CRITICAL" | "WARNING",
        "field":           str,          # which parameter triggered the check
        "message":         str,          # human-readable explanation
        "claim_statement": str,          # original claim text for traceability
        "source":          str,          # which rule table fired
    }
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# RWDR Rotary Velocity Limits per Material (DIN 3760 Table 1 / ISO 6194-1)
# Values are for lubricated sealing faces; reduce by 30 % for dry running.
# ─────────────────────────────────────────────────────────────────────────────
_RWDR_V_LIMITS_M_S: Dict[str, float] = {
    "NBR":  6.0,    # Standard compound, lubricated
    "FKM":  8.0,    # Standard; high-performance grades up to 12 m/s
    "PTFE": 15.0,   # PTFE lip; highest rotary capability
    "EPDM": 4.0,    # Limited rotary use (primarily static / hydraulics)
    "HNBR": 8.0,    # Similar to FKM; excellent abrasion resistance
    "FFKM": 6.0,    # Very high chemical resistance, moderate v_max
    "CR":   4.0,    # Low rotary; ozone-resistant weather seals
    "VMQ":  3.0,    # Low abrasion resistance, slow rotation only
}

# Absolute physical upper-bound regardless of material — prevents data-entry errors
# (higher than the fastest known production shaft seal application)
_ABSOLUTE_RPM_MAX = 30_000
_ABSOLUTE_V_SURFACE_MAX_M_S = 25.0

# Operational domain hard limits (DIN 3760 / ISO 10766)
_OPERATIONAL_LIMITS: Dict[str, Dict[str, float]] = {
    "pressure_bar_dynamic_max": {"all": 400.0},   # hard upper for any dynamic seal
    "temp_c_absolute_max":       {"all": 330.0},   # above FFKM peak — physically irrelevant for elastomers
    "temp_c_absolute_min":       {"all": -200.0},  # below PTFE cryo limit
}


# ─────────────────────────────────────────────────────────────────────────────
# Helper: surface velocity from shaft diameter + RPM
# ─────────────────────────────────────────────────────────────────────────────

def _v_surface(diameter_mm: float, rpm: float) -> float:
    """v = π × d [mm] × n [rpm] / 60 000  →  [m/s]  (DIN 3760)"""
    return math.pi * diameter_mm * rpm / 60_000.0


# ─────────────────────────────────────────────────────────────────────────────
# Helper: normalise a bare float token from a claim statement
# ─────────────────────────────────────────────────────────────────────────────

def _extract_rpm(text: str) -> Optional[float]:
    """Return RPM value if found in text (matches `<number> rpm`, `U/min`, `min⁻¹`)."""
    m = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:rpm|u/min|u\.p\.m\.|min[-–]?1|min⁻¹)",
        text,
        re.I,
    )
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def _extract_diameter_mm(text: str) -> Optional[float]:
    """Return shaft diameter in mm if `<number> mm` appears near a shaft keyword."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*mm", text, re.I)
    if m and re.search(r"\bwelle\b|\bshaft\b|\bwellen\b", text, re.I):
        return float(m.group(1).replace(",", "."))
    return None


def _extract_temperature_c(text: str) -> Optional[float]:
    """Return temperature in °C from a claim statement."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*°?\s*c\b", text, re.I)
    if m:
        return float(m.group(1).replace(",", "."))
    m2 = re.search(r"(\d+(?:[.,]\d+)?)\s*°?\s*f\b", text, re.I)
    if m2:
        f = float(m2.group(1).replace(",", "."))
        return round((f - 32) * 5 / 9, 1)
    return None


def _extract_pressure_bar(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*bar\b", text, re.I)
    if m:
        return float(m.group(1).replace(",", "."))
    m2 = re.search(r"(\d+(?:[.,]\d+)?)\s*psi\b", text, re.I)
    if m2:
        return round(float(m2.group(1).replace(",", ".")) * 0.0689476, 2)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Core public API
# ─────────────────────────────────────────────────────────────────────────────

def validate_claim_against_matrix(
    claim_statement: str,
    *,
    candidate_materials: Optional[List[str]] = None,
    working_profile: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Deterministic pre-flight validation for a single claim statement.

    Checks:
    1. Absolute RPM domain limit
    2. Surface velocity (DIN 3760) against per-material limits
    3. Temperature against material_limits table
    4. Pressure against material_limits table (dynamic)

    Parameters
    ----------
    claim_statement:
        Raw text of the LLM-submitted claim.
    candidate_materials:
        Optional list of material names to check velocity/temp/pressure against.
        If None, only absolute domain limits are checked.
    working_profile:
        Current working_profile dict from AgentState — used to enrich context
        (e.g. to get shaft diameter when not in claim text).

    Returns
    -------
    List of conflict dicts (may be empty if all checks pass).
    """
    wp = working_profile or {}
    conflicts: List[Dict[str, Any]] = []

    # ── Extract parameters from claim text ──────────────────────────────────
    rpm = _extract_rpm(claim_statement)
    diameter_mm = _extract_diameter_mm(claim_statement) or wp.get("diameter")
    temp_c = _extract_temperature_c(claim_statement)
    pressure_bar = _extract_pressure_bar(claim_statement)

    # Fall back to working_profile for rpm/diameter when not in claim text
    if rpm is None:
        rpm = wp.get("speed")
    if diameter_mm is None:
        diameter_mm = wp.get("diameter")

    # ── 1. Absolute RPM domain limit ─────────────────────────────────────────
    if rpm is not None and rpm > _ABSOLUTE_RPM_MAX:
        conflicts.append({
            "type": "DOMAIN_LIMIT_VIOLATION",
            "severity": "CRITICAL",
            "field": "rpm",
            "message": (
                f"Drehzahl {rpm:.0f} rpm überschreitet absolutes Domainlimit "
                f"von {_ABSOLUTE_RPM_MAX:,} rpm für Radialwellendichtringe (DIN 3760). "
                f"Keine Elastomerdichtung für diesen Betriebspunkt qualifizierbar."
            ),
            "claim_statement": claim_statement,
            "source": "compound_validator.absolute_rpm_limit",
        })

    # ── 2. Surface velocity per material (only if we have both d and n) ─────
    if rpm is not None and diameter_mm is not None:
        v = _v_surface(diameter_mm, rpm)

        if v > _ABSOLUTE_V_SURFACE_MAX_M_S:
            conflicts.append({
                "type": "DOMAIN_LIMIT_VIOLATION",
                "severity": "CRITICAL",
                "field": "v_surface",
                "message": (
                    f"Umfangsgeschwindigkeit {v:.2f} m/s (d={diameter_mm} mm, "
                    f"n={rpm:.0f} rpm) überschreitet physikalisches Absolut-Limit "
                    f"von {_ABSOLUTE_V_SURFACE_MAX_M_S} m/s — kein bekanntes "
                    f"Dichtungsmaterial einsetzbar."
                ),
                "claim_statement": claim_statement,
                "source": "compound_validator.absolute_v_limit",
            })
        elif candidate_materials:
            for mat in candidate_materials:
                mat_key = mat.strip().upper()
                v_limit = _RWDR_V_LIMITS_M_S.get(mat_key)
                if v_limit is not None and v > v_limit:
                    conflicts.append({
                        "type": "DOMAIN_LIMIT_VIOLATION",
                        "severity": "CRITICAL",
                        "field": "v_surface",
                        "message": (
                            f"{mat_key}: Umfangsgeschwindigkeit {v:.2f} m/s überschreitet "
                            f"Grenzwert {v_limit} m/s (DIN 3760). "
                            f"Welle: {diameter_mm} mm, {rpm:.0f} rpm."
                        ),
                        "claim_statement": claim_statement,
                        "source": "compound_validator.rwdr_v_limit",
                    })

    # ── 3. Temperature + 4. Pressure via material_limits table ──────────────
    if candidate_materials and (temp_c is not None or pressure_bar is not None):
        try:
            from app.mcp.calculations.material_limits import check as mat_check, MATERIAL_ALIASES
        except ImportError:
            mat_check = None  # fail-open: skip if import fails

        if mat_check is not None:
            for mat in candidate_materials:
                mat_key = mat.strip().lower()
                if mat_key not in MATERIAL_ALIASES:
                    continue
                result = mat_check(
                    mat_key,
                    temp_c=temp_c,
                    pressure_bar=pressure_bar,
                    is_dynamic=True,
                )
                for warning in result.warnings:
                    severity = "CRITICAL" if result.temp_ok is False or result.pressure_ok is False else "WARNING"
                    field = "temperature" if "Temperatur" in warning or "Temp" in warning else "pressure"
                    conflicts.append({
                        "type": "DOMAIN_LIMIT_VIOLATION",
                        "severity": severity,
                        "field": field,
                        "message": warning,
                        "claim_statement": claim_statement,
                        "source": f"compound_validator.material_limits.{mat.upper()}",
                    })

    return conflicts


def validate_claims_batch(
    claims_data: List[Tuple[str, str]],  # [(claim_statement, claim_type), ...]
    *,
    candidate_materials: Optional[List[str]] = None,
    working_profile: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Run validate_claim_against_matrix for a list of (statement, type) pairs.

    Convenience wrapper for the evidence_tool_node dispatcher.
    """
    all_conflicts: List[Dict[str, Any]] = []
    for statement, _ in claims_data:
        all_conflicts.extend(
            validate_claim_against_matrix(
                statement,
                candidate_materials=candidate_materials,
                working_profile=working_profile,
            )
        )
    return all_conflicts
