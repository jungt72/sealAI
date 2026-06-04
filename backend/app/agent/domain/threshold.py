from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agent.domain.rwdr_calc import RwdrCalcInput, calculate_rwdr


def _build_rwdr_threshold_payload(
    asserted_state: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]],
) -> Optional[RwdrCalcInput]:
    asserted = asserted_state or {}
    working = working_profile or {}
    operating = asserted.get("operating_conditions") or {}
    machine = asserted.get("machine_profile") or {}

    shaft_diameter = (
        machine.get("shaft_diameter_mm")
        or working.get("shaft_diameter_mm")
        or working.get("shaft_diameter")
        or working.get("diameter")
    )
    rpm = working.get("speed_rpm") or working.get("rpm") or working.get("speed")
    if shaft_diameter is None or rpm is None:
        return None

    return RwdrCalcInput(
        shaft_diameter_mm=float(shaft_diameter),
        rpm=float(rpm),
        pressure_bar=operating.get("pressure"),
        temperature_max_c=operating.get("temperature"),
        temperature_min_c=working.get("temperature_min_c"),
        surface_hardness_hrc=working.get("surface_hardness_hrc") or working.get("hrc"),
        runout_mm=working.get("runout_mm") or working.get("runout"),
        clearance_gap_mm=working.get("clearance_gap_mm") or working.get("clearance_gap"),
        elastomer_material=(
            machine.get("material")
            or working.get("material")
            or working.get("elastomer_material")
        ),
        medium=(asserted.get("medium_profile") or {}).get("name") or working.get("medium"),
        lubrication_mode=working.get("lubrication_mode") or working.get("lubrication"),
    )


def project_threshold_status(
    *,
    asserted_state: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    rwdr_input = _build_rwdr_threshold_payload(asserted_state, working_profile)
    if rwdr_input is None:
        return {
            "triggered_thresholds": [],
            "warning_thresholds": [],
            "blocking_thresholds": [],
            "threshold_status": "threshold_free",
            "usable_for_governed_step": True,
        }

    result = calculate_rwdr(rwdr_input)
    warning_thresholds: List[str] = []
    blocking_thresholds: List[str] = []

    if result.dn_warning:
        warning_thresholds.append("dn_warning")
    if result.hrc_warning:
        warning_thresholds.append("hrc_warning")
    if result.runout_warning:
        warning_thresholds.append("runout_warning")
    if result.pv_warning:
        warning_thresholds.append("pv_warning")
    if result.dry_running_risk:
        warning_thresholds.append("dry_running_risk")
    if result.geometry_warning:
        warning_thresholds.append("geometry_warning")

    if result.material_limit_exceeded:
        blocking_thresholds.append("material_limit_exceeded")
    if result.extrusion_risk:
        blocking_thresholds.append("extrusion_risk")
    if result.shrinkage_risk:
        blocking_thresholds.append("shrinkage_risk")
    if result.status == "critical":
        blocking_thresholds.append("rwdr_critical_status")

    warning_thresholds = list(dict.fromkeys(warning_thresholds))
    blocking_thresholds = list(dict.fromkeys(blocking_thresholds))
    triggered_thresholds = warning_thresholds + [t for t in blocking_thresholds if t not in warning_thresholds]

    if blocking_thresholds:
        threshold_status = "blocking_thresholds"
    elif warning_thresholds:
        threshold_status = "warning_thresholds"
    else:
        threshold_status = "threshold_free"

    return {
        "triggered_thresholds": triggered_thresholds,
        "warning_thresholds": warning_thresholds,
        "blocking_thresholds": blocking_thresholds,
        "threshold_status": threshold_status,
        "usable_for_governed_step": not bool(blocking_thresholds),
    }


def _threshold_scope_level(
    *,
    threshold_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
) -> str:
    threshold_status = str((threshold_projection or {}).get("threshold_status") or "threshold_free")
    domain_status = str((domain_scope_projection or {}).get("status") or "in_domain_scope")

    if domain_status in {"out_of_domain_scope", "escalation_required"} or threshold_status == "threshold_blocking":
        return "blocked"
    if domain_status == "in_domain_with_warning" or threshold_status == "threshold_warning":
        return "warning"
    return "neutral"


def compare_threshold_scope(
    *,
    previous_threshold_projection: Optional[Dict[str, Any]],
    current_threshold_projection: Optional[Dict[str, Any]],
    previous_domain_scope_projection: Optional[Dict[str, Any]],
    current_domain_scope_projection: Optional[Dict[str, Any]],
) -> str:
    previous_level = _threshold_scope_level(
        threshold_projection=previous_threshold_projection,
        domain_scope_projection=previous_domain_scope_projection,
    )
    current_level = _threshold_scope_level(
        threshold_projection=current_threshold_projection,
        domain_scope_projection=current_domain_scope_projection,
    )
    if previous_level == current_level:
        return "unchanged"
    return f"{previous_level}_to_{current_level}"
