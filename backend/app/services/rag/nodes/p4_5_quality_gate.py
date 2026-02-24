"""P4.5 Deterministic Quality Gate for SEALAI v4.4.0 (Sprint 7).

Pure Python — no LLM involvement. Implements the 8-check quality matrix
from the concept doc (Table 10). Each check has a defined severity:

  WARNING  — informational, does not block P5
  CRITICAL — blocker, prevents P5 path until resolved
  FLAG     — sets is_critical_application flag for downstream watermarking

When any CRITICAL check fires, ``has_blockers=True`` and the graph routes
to a blocker notification instead of continuing to P5.

Checks:
  1. Thermischer Puffer    (WARNING)
  2. Druckpuffer           (WARNING)
  3. Medienverträglichkeit (CRITICAL)
  4. Flanschklassen-Match  (CRITICAL)
  5. Bolt-Load-Check       (CRITICAL)
  6. Zyklische Belastung   (WARNING)
  7. Emissionskonformität  (WARNING)
  8. is_critical Flag      (FLAG)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

import structlog
from pydantic import BaseModel, ConfigDict, Field

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState

logger = structlog.get_logger("rag.nodes.p4_5_quality_gate")


# ---------------------------------------------------------------------------
# Severity type
# ---------------------------------------------------------------------------

Severity = Literal["WARNING", "CRITICAL", "FLAG"]


# ---------------------------------------------------------------------------
# Check result model
# ---------------------------------------------------------------------------


class QGateCheck(BaseModel):
    """Single quality gate check result."""

    check_id: str
    name: str
    severity: Severity
    passed: bool
    message: str
    alternatives: List[str] = Field(default_factory=list)
    remediation_steps: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class QGateResult(BaseModel):
    """Aggregate quality gate result."""

    checks: List[QGateCheck] = Field(default_factory=list)
    has_blockers: bool = False
    blocker_count: int = 0
    warning_count: int = 0
    flag_count: int = 0
    critique_log: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Known compatible media per material family (simplified reference table)
# ---------------------------------------------------------------------------

# Spiral-wound gasket with flexible graphite filler — common default.
# In production this would come from material DB / RAG results.
_DEFAULT_COMPATIBLE_MEDIA = frozenset({
    "wasser", "water",
    "dampf", "steam",
    "luft", "air",
    "stickstoff", "nitrogen", "n2",
    "erdgas", "natural gas", "methan", "methane",
    "kohlenwasserstoff", "hydrocarbon",
    "oel", "öl", "oil",
    "co2",
    "argon", "ar",
    "helium", "he",
})

# Media explicitly incompatible with standard graphite-filled spiral-wound gaskets.
_INCOMPATIBLE_MEDIA = frozenset({
    "flusssäure", "flusssaeure", "hf", "hydrofluoric acid",
    "königswasser", "koenigswasser", "aqua regia",
    "chromsäure", "chromsaeure", "chromic acid",
    "perchlorsäure", "perchlorsaeure", "perchloric acid",
})

# Default cyclic rating for spiral-wound graphite gaskets.
_DEFAULT_CYCLIC_RATING = "B"  # B = limited cyclic capability

# Emission class certifications available for default gasket type.
_DEFAULT_EMISSION_CERTS = frozenset({
    "ta-luft", "ta luft",
    "vdi 2440",
})

# Material temperature / pressure limits (same as calc_engine for consistency).
_MATERIAL_T_MAX_C = 550.0
_MATERIAL_P_MAX_BAR = 250.0


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _get_alternative_materials_for_medium(medium: str) -> List[str]:
    """Return pragmatic fallback material options for aggressive media."""
    medium_lower = (medium or "").strip().lower()

    if any(token in medium_lower for token in ("hf", "flusssäure", "flusssaeure", "hydrofluoric")):
        return [
            "PTFE (virgin, ungefuellt)",
            "Kalrez 4079 (FFKM)",
            "Kalrez 6375 (FFKM)",
            "FFKM 70 Shore",
        ]
    if any(token in medium_lower for token in ("chromsäure", "chromsaeure", "chromic")):
        return [
            "Kalrez 4079 (FFKM)",
            "PTFE",
            "EPDM (bei niedrigen Konzentrationen)",
        ]
    if any(token in medium_lower for token in ("h2so4", "schwefelsäure", "schwefelsaeure", "sulfuric")):
        return [
            "Kalrez 4079 (FFKM)",
            "PTFE",
            "Viton/FKM (bei <70% Konzentration)",
        ]
    if any(token in medium_lower for token in ("naoh", "koh", "natronlauge", "caustic")):
        return [
            "Kalrez 4079 (FFKM)",
            "EPDM",
            "Viton/FKM (bei <50% Konzentration)",
        ]
    return [
        "Kalrez 4079 (FFKM, universell)",
        "PTFE (chemisch inert)",
    ]


def _calculate_required_flange_class(safety_factor: float) -> str:
    """Suggest a conservative flange class upgrade from low safety factor."""
    if safety_factor < 0.6:
        return "ASME Class 600 / PN100+"
    if safety_factor < 0.8:
        return "ASME Class 300 / PN63"
    return "ASME Class 150 / PN40"


def _format_blocker_summary(blockers: List[QGateCheck]) -> str:
    lines: List[str] = []
    for blocker in blockers:
        lines.append(blocker.message)
        if blocker.alternatives:
            lines.append("ALTERNATIVEN:")
            lines.extend(f"  - {alt}" for alt in blocker.alternatives)
        if blocker.remediation_steps:
            lines.append("EMPFOHLENE MASSNAHMEN:")
            lines.extend(f"  - {step}" for step in blocker.remediation_steps)
    return "\n".join(lines)


def _check_thermal_margin(
    calc_result: Dict[str, Any],
    profile: Dict[str, Any],
) -> QGateCheck:
    """Check 1: Thermischer Puffer (WARNING).

    Fires if (mat.t_max - profile.temp_max) < profile.temp_max * 0.15
    """
    temp_max = profile.get("temperature_max_c")
    temperature_margin = calc_result.get("temperature_margin_c")

    if temp_max is None or temperature_margin is None:
        return QGateCheck(
            check_id="thermal_margin",
            name="Thermischer Puffer",
            severity="WARNING",
            passed=True,
            message="Thermischer Puffer nicht prüfbar (fehlende Daten).",
            details={"skipped": True},
        )

    threshold = float(temp_max) * 0.15
    margin = float(temperature_margin)
    passed = margin >= threshold

    return QGateCheck(
        check_id="thermal_margin",
        name="Thermischer Puffer",
        severity="WARNING",
        passed=passed,
        message=(
            f"Thermische Reserve {margin:.1f} °C ist ausreichend (>= {threshold:.1f} °C)."
            if passed
            else f"Thermische Reserve {margin:.1f} °C unterschreitet Schwelle von {threshold:.1f} °C (15% von {temp_max} °C)."
        ),
        details={
            "temperature_max_c": temp_max,
            "temperature_margin_c": margin,
            "threshold_c": round(threshold, 1),
        },
    )


def _check_pressure_margin(
    calc_result: Dict[str, Any],
    profile: Dict[str, Any],
) -> QGateCheck:
    """Check 2: Druckpuffer (WARNING).

    Fires if (mat.p_max - profile.pressure_max) < profile.pressure_max * 0.10
    """
    pressure_max = profile.get("pressure_max_bar")
    pressure_margin = calc_result.get("pressure_margin_bar")

    if pressure_max is None or pressure_margin is None:
        return QGateCheck(
            check_id="pressure_margin",
            name="Druckpuffer",
            severity="WARNING",
            passed=True,
            message="Druckpuffer nicht prüfbar (fehlende Daten).",
            details={"skipped": True},
        )

    threshold = float(pressure_max) * 0.10
    margin = float(pressure_margin)
    passed = margin >= threshold

    return QGateCheck(
        check_id="pressure_margin",
        name="Druckpuffer",
        severity="WARNING",
        passed=passed,
        message=(
            f"Druckreserve {margin:.1f} bar ist ausreichend (>= {threshold:.1f} bar)."
            if passed
            else f"Druckreserve {margin:.1f} bar unterschreitet Schwelle von {threshold:.1f} bar (10% von {pressure_max} bar)."
        ),
        details={
            "pressure_max_bar": pressure_max,
            "pressure_margin_bar": margin,
            "threshold_bar": round(threshold, 1),
        },
    )


def _check_medium_compatibility(
    profile: Dict[str, Any],
) -> QGateCheck:
    """Check 3: Medienverträglichkeit (CRITICAL).

    Fires if profile.medium is in the incompatible media set.
    """
    medium = profile.get("medium")

    if not medium:
        return QGateCheck(
            check_id="medium_compatibility",
            name="Medienverträglichkeit",
            severity="CRITICAL",
            passed=True,
            message="Medium nicht angegeben — Verträglichkeitsprüfung übersprungen.",
            details={"skipped": True},
        )

    medium_lower = str(medium).strip().lower()

    if medium_lower in _INCOMPATIBLE_MEDIA:
        alternatives = _get_alternative_materials_for_medium(str(medium))
        return QGateCheck(
            check_id="medium_compatibility",
            name="Medienverträglichkeit",
            severity="CRITICAL",
            passed=False,
            message=f"BLOCKER: Medium '{medium}' ist mit dem Standard-Dichtungswerkstoff nicht verträglich.",
            alternatives=alternatives,
            remediation_steps=[
                f"Wechsel auf ein kompatibles Material: {', '.join(alternatives)}",
                "Mediumkonzentration und Temperatur gegen Beständigkeitsdatenblatt prüfen",
                "Chemische Beständigkeit mit Herstellerguide verifizieren",
            ],
            details={"medium": medium, "incompatible": True},
        )

    if medium_lower in _DEFAULT_COMPATIBLE_MEDIA:
        return QGateCheck(
            check_id="medium_compatibility",
            name="Medienverträglichkeit",
            severity="CRITICAL",
            passed=True,
            message=f"Medium '{medium}' ist mit dem Standard-Dichtungswerkstoff verträglich.",
            details={"medium": medium, "compatible": True},
        )

    alternatives = _get_alternative_materials_for_medium(str(medium))
    # Unknown medium — flag as critical because we can't confirm compatibility.
    return QGateCheck(
        check_id="medium_compatibility",
        name="Medienverträglichkeit",
        severity="CRITICAL",
        passed=False,
        message=f"BLOCKER: Medium '{medium}' — Verträglichkeit kann nicht automatisch bestätigt werden.",
        alternatives=alternatives,
        remediation_steps=[
            "Medium spezifizieren (Konzentration, Reinheit, Temperaturbereich)",
            f"Vorab mit robusten Alternativen prüfen: {', '.join(alternatives)}",
            "Freigabe durch chemische Beständigkeitsdatenbank einholen",
        ],
        details={"medium": medium, "unknown": True},
    )


def _check_flange_class_match(
    calc_result: Dict[str, Any],
    profile: Dict[str, Any],
) -> QGateCheck:
    """Check 4: Flanschklassen-Match (CRITICAL).

    Fires if calc_result.safety_factor < 1.0 (i.e., required load exceeds capacity).
    This is a proxy for: "required class > specified class".
    """
    safety_factor = calc_result.get("safety_factor")
    flange_pn = profile.get("flange_pn")
    flange_class = profile.get("flange_class")

    if safety_factor is None:
        return QGateCheck(
            check_id="flange_class_match",
            name="Flanschklassen-Match",
            severity="CRITICAL",
            passed=True,
            message="Flanschklassen-Prüfung nicht möglich (kein Sicherheitsfaktor berechnet).",
            details={"skipped": True},
        )

    sf = float(safety_factor)
    passed = sf >= 1.0

    if passed:
        return QGateCheck(
            check_id="flange_class_match",
            name="Flanschklassen-Match",
            severity="CRITICAL",
            passed=True,
            message=f"Sicherheitsfaktor {sf:.2f} >= 1.0 — Flanschklasse ausreichend.",
            details={
                "safety_factor": sf,
                "flange_pn": flange_pn,
                "flange_class": flange_class,
            },
        )

    required_class = _calculate_required_flange_class(sf)
    return QGateCheck(
        check_id="flange_class_match",
        name="Flanschklassen-Match",
        severity="CRITICAL",
        passed=False,
        message=f"BLOCKER: Flanschklasse/Verschraubung unzureichend (Sicherheitsfaktor {sf:.2f} < 1.0).",
        alternatives=[
            f"Upgrade auf {required_class}",
            "Hoeherfeste Schrauben (z.B. A4-80 statt A4-70)",
            "Betriebstemperatur reduzieren (Richtwert: -20%)",
        ],
        remediation_steps=[
            f"Flanschdruckstufe auf mindestens {required_class} anheben",
            "Schraubenmaterial und Vorspannkraftkonzept aktualisieren",
            "Betriebsfenster (Druck/Temperatur) neu freigeben",
        ],
        details={
            "safety_factor": sf,
            "flange_pn": flange_pn,
            "flange_class": flange_class,
            "required_class": required_class,
        },
    )


def _check_bolt_load(
    calc_result: Dict[str, Any],
    profile: Dict[str, Any],
) -> QGateCheck:
    """Check 5: Bolt-Load-Check (CRITICAL).

    Fires if available bolt load is insufficient for required gasket stress.
    Uses the safety factor as the decisive metric.
    """
    available_bolt_load = calc_result.get("available_bolt_load_kn")
    safety_factor = calc_result.get("safety_factor")
    required_stress = calc_result.get("required_gasket_stress_mpa")

    if available_bolt_load is None:
        return QGateCheck(
            check_id="bolt_load",
            name="Bolt-Load-Check",
            severity="CRITICAL",
            passed=True,
            message="Schraubenkraft nicht berechenbar (fehlende Schraubendaten) — manuelle Prüfung empfohlen.",
            details={"skipped": True, "reason": "missing_bolt_data"},
        )

    sf = float(safety_factor) if safety_factor is not None else 0.0
    passed = sf >= 1.0

    return QGateCheck(
        check_id="bolt_load",
        name="Bolt-Load-Check",
        severity="CRITICAL",
        passed=passed,
        message=(
            f"Verfügbare Schraubenkraft {available_bolt_load:.1f} kN ausreichend (SF={sf:.2f})."
            if passed
            else f"Verfügbare Schraubenkraft {available_bolt_load:.1f} kN NICHT ausreichend (SF={sf:.2f} < 1.0) — BLOCKER."
        ),
        details={
            "available_bolt_load_kn": available_bolt_load,
            "required_gasket_stress_mpa": required_stress,
            "safety_factor": sf,
        },
    )


def _check_cyclic_load(
    profile: Dict[str, Any],
) -> QGateCheck:
    """Check 6: Zyklische Belastung (WARNING).

    Fires if profile.cyclic_load == True and material cyclic rating < 'B'.
    """
    cyclic_load = profile.get("cyclic_load", False)

    if not cyclic_load:
        return QGateCheck(
            check_id="cyclic_load",
            name="Zyklische Belastung",
            severity="WARNING",
            passed=True,
            message="Keine zyklische Belastung angegeben.",
            details={"cyclic_load": False},
        )

    # Default material has rating "B" — limited cyclic capability.
    # Rating < "B" would mean "C" or worse, but for our default material
    # cyclic_load=True with rating "B" triggers a warning per concept doc.
    mat_rating = _DEFAULT_CYCLIC_RATING
    passed = mat_rating >= "B"

    # Per concept doc: cyclic_load=True AND mat.cyclic_rating < 'B' → WARNING.
    # Since default is exactly "B", we pass but still warn about cyclic conditions.
    return QGateCheck(
        check_id="cyclic_load",
        name="Zyklische Belastung",
        severity="WARNING",
        passed=passed,
        message=(
            f"Zyklische Belastung erkannt — Werkstoff-Zyklenfestigkeit Klasse '{mat_rating}' ist grenzwertig. Ermüdungsanalyse empfohlen."
            if passed
            else f"Zyklische Belastung erkannt — Werkstoff-Zyklenfestigkeit Klasse '{mat_rating}' unzureichend."
        ),
        details={"cyclic_load": True, "material_cyclic_rating": mat_rating},
    )


def _check_emission_compliance(
    profile: Dict[str, Any],
) -> QGateCheck:
    """Check 7: Emissionskonformität (WARNING).

    Fires if emission_class is specified but material doesn't hold the cert.
    """
    emission_class = profile.get("emission_class")

    if not emission_class:
        return QGateCheck(
            check_id="emission_compliance",
            name="Emissionskonformität",
            severity="WARNING",
            passed=True,
            message="Keine Emissionsklasse gefordert.",
            details={"emission_class": None},
        )

    emission_lower = str(emission_class).strip().lower()
    has_cert = emission_lower in _DEFAULT_EMISSION_CERTS

    return QGateCheck(
        check_id="emission_compliance",
        name="Emissionskonformität",
        severity="WARNING",
        passed=has_cert,
        message=(
            f"Emissionsklasse '{emission_class}' durch Werkstoff abgedeckt."
            if has_cert
            else f"Emissionsklasse '{emission_class}' — Nachweis für Standard-Werkstoff NICHT vorhanden."
        ),
        details={
            "emission_class": emission_class,
            "available_certs": sorted(_DEFAULT_EMISSION_CERTS),
            "certified": has_cert,
        },
    )


def _check_critical_flag(
    calc_result: Dict[str, Any],
    profile: Dict[str, Any],
) -> QGateCheck:
    """Check 8: is_critical Flag (FLAG).

    Sets is_critical_application=True for: H2, O2, >100 bar, >400°C, <-40°C.
    """
    is_critical = bool(calc_result.get("is_critical_application", False))

    reasons: List[str] = []
    medium = str(profile.get("medium") or "").strip().lower()
    critical_media = {"h2", "hydrogen", "wasserstoff", "o2", "oxygen", "sauerstoff"}
    if medium in critical_media:
        reasons.append(f"Kritisches Medium: {profile.get('medium')}")

    pressure = profile.get("pressure_max_bar")
    if pressure is not None and float(pressure) > 100.0:
        reasons.append(f"Hochdruck: {pressure} bar > 100 bar")

    temp = profile.get("temperature_max_c")
    if temp is not None:
        if float(temp) > 400.0:
            reasons.append(f"Hochtemperatur: {temp} °C > 400 °C")
        if float(temp) < -40.0:
            reasons.append(f"Kryogen: {temp} °C < -40 °C")

    # Ensure flag matches calc_engine result OR own detection
    effective_critical = is_critical or bool(reasons)

    return QGateCheck(
        check_id="critical_flag",
        name="is_critical Flag",
        severity="FLAG",
        passed=not effective_critical,  # "passed" = no flag needed
        message=(
            "Keine kritische Anwendung erkannt."
            if not effective_critical
            else f"Kritische Anwendung: {'; '.join(reasons) or 'von P4b erkannt'}. Wasserzeichen erforderlich."
        ),
        details={
            "is_critical_application": effective_critical,
            "reasons": reasons,
        },
    )


def _check_unit_consistency(state: SealAIState) -> List[str]:
    """Check for mixed engineering units in generated answer text."""
    errors: List[str] = []
    text = str(state.get("final_answer", "") or state.get("final_text", "") or "").lower()

    if not text:
        return errors

    if "bar" in text and "psi" in text:
        errors.append("WARNING: Text enthält sowohl 'bar' als auch 'psi'. Mögliche Einheiten-Verwirrung.")
    if ("°c" in text or " c" in text) and ("°f" in text or " f" in text):
        errors.append("WARNING: Text enthält sowohl '°C' als auch '°F'.")

    return errors


def _check_physics_plausibility(state: SealAIState) -> List[str]:
    """Check for obvious physics violations in generated answer text."""
    errors: List[str] = []
    text = str(state.get("final_answer", "") or state.get("final_text", "") or "")

    if not text:
        return errors

    temps = re.findall(r"(\d+(?:\.\d+)?)\s*°C", text, flags=re.IGNORECASE)
    text_upper = text.upper()

    for temp_str in temps:
        try:
            temp = float(temp_str)
        except ValueError:
            continue
        if temp > 350.0 and "PTFE" in text_upper:
            errors.append(
                f"CRITICAL: Temperatur {temp}°C ist zu hoch für PTFE (Limit ~260-300°C)."
            )

    return errors


# ---------------------------------------------------------------------------
# Run all checks
# ---------------------------------------------------------------------------


def run_quality_gate(
    calc_result: Dict[str, Any],
    profile: Dict[str, Any],
) -> QGateResult:
    """Execute all 8 quality gate checks and return aggregate result.

    Args:
        calc_result: CalcOutput dict from P4b (calculation_result).
        profile: WorkingProfile dict (or extracted_params).

    Returns:
        QGateResult with all checks, blocker status, and critique_log.
    """
    checks = [
        _check_thermal_margin(calc_result, profile),
        _check_pressure_margin(calc_result, profile),
        _check_medium_compatibility(profile),
        _check_flange_class_match(calc_result, profile),
        _check_bolt_load(calc_result, profile),
        _check_cyclic_load(profile),
        _check_emission_compliance(profile),
        _check_critical_flag(calc_result, profile),
    ]

    blockers = [c for c in checks if c.severity == "CRITICAL" and not c.passed]
    warnings = [c for c in checks if c.severity == "WARNING" and not c.passed]
    flags = [c for c in checks if c.severity == "FLAG" and not c.passed]

    critique_log: List[str] = []
    for c in checks:
        if not c.passed:
            critique_log.append(f"[{c.severity}] {c.name}: {c.message}")

    return QGateResult(
        checks=checks,
        has_blockers=bool(blockers),
        blocker_count=len(blockers),
        warning_count=len(warnings),
        flag_count=len(flags),
        critique_log=critique_log,
    )


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------


def node_p4_5_qgate(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """P4.5 Quality Gate — deterministic check matrix after P4b calculation.

    Reads calculation_result and working_profile from state.
    Routes to resume_router (no blockers) or blocker notification (has blockers).
    """
    calc_result = state.calculation_result or {}
    wp = state.working_profile
    profile = wp.model_dump() if wp is not None else {}

    # Merge extracted_params as fallback for profile fields
    extracted = state.extracted_params or {}
    for key, value in extracted.items():
        if key not in profile or profile[key] is None:
            profile[key] = value

    logger.info(
        "p4_5_qgate_start",
        has_calc_result=bool(calc_result),
        has_profile=bool(profile),
        run_id=state.run_id,
        thread_id=state.thread_id,
    )

    # If no calculation result, skip quality gate (P4b was skipped)
    if not calc_result:
        logger.info(
            "p4_5_qgate_skip",
            reason="no_calculation_result",
            run_id=state.run_id,
        )
        return {
            "phase": PHASE.QUALITY_GATE,
            "last_node": "node_p4_5_qgate",
            "critique_log": [],
            "qgate_has_blockers": False,
        }

    result = run_quality_gate(calc_result, profile)
    extra_findings: List[str] = []
    extra_findings.extend(_check_unit_consistency(state))
    extra_findings.extend(_check_physics_plausibility(state))
    if extra_findings:
        result.critique_log.extend(extra_findings)
        result.warning_count += sum(1 for msg in extra_findings if msg.startswith("WARNING:"))
        extra_criticals = sum(1 for msg in extra_findings if msg.startswith("CRITICAL:"))
        if extra_criticals:
            result.blocker_count += extra_criticals
            result.has_blockers = True

    # Prometheus metrics — never raises, must not degrade reliability
    try:
        from app.core.metrics import qgate_checks_total
        for chk in result.checks:
            qgate_checks_total.labels(
                check_name=chk.check_id,
                severity=chk.severity,
                passed=str(chk.passed),
            ).inc()
    except Exception:  # noqa: BLE001
        pass

    # Update is_critical_application from FLAG check
    critical_check = next(
        (c for c in result.checks if c.check_id == "critical_flag"), None
    )
    is_critical = False
    if critical_check and not critical_check.passed:
        is_critical = critical_check.details.get("is_critical_application", False)

    logger.info(
        "p4_5_qgate_done",
        has_blockers=result.has_blockers,
        blocker_count=result.blocker_count,
        warning_count=result.warning_count,
        flag_count=result.flag_count,
        is_critical=is_critical,
        critique_log_count=len(result.critique_log),
        run_id=state.run_id,
    )

    update: Dict[str, Any] = {
        "phase": PHASE.QUALITY_GATE,
        "last_node": "node_p4_5_qgate",
        "critique_log": result.critique_log,
        "qgate_has_blockers": result.has_blockers,
        "qgate_result": result.model_dump(),
        "is_critical_application": is_critical or state.is_critical_application,
    }

    if result.has_blockers:
        blockers = [c for c in result.checks if c.severity == "CRITICAL" and not c.passed]
        update["error"] = "Quality Gate BLOCKER:\n" + _format_blocker_summary(blockers)

    return update


__all__ = [
    "QGateCheck",
    "QGateResult",
    "node_p4_5_qgate",
    "run_quality_gate",
    "_check_unit_consistency",
    "_check_physics_plausibility",
]
