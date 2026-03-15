from __future__ import annotations

from typing import Any, Dict, List, TypedDict

from app.agent.agent.calc import calculate_physics
from app.agent.agent.utils import validate_material_risk


class DeterministicCalculationRecord(TypedDict, total=False):
    value: Any
    unit: str | None
    status: str
    source_type: str
    source_ref: str
    input_refs: List[str]
    formula_id: str


class DeterministicSignalRecord(TypedDict, total=False):
    value: Any
    signal_class: str
    severity: str
    source_type: str
    source_ref: str
    input_refs: List[str]


def build_calculation_foundation(
    sealing_state: Dict[str, Any],
    working_profile: Dict[str, Any],
    rwdr_state: Dict[str, Any],
) -> Dict[str, DeterministicCalculationRecord]:
    calculations: Dict[str, DeterministicCalculationRecord] = {}
    base_profile = _extract_base_profile(sealing_state, working_profile)
    computed_profile = calculate_physics(dict(base_profile))

    if computed_profile.get("v_m_s") is not None:
        calculations["surface_speed_mps"] = {
            "value": computed_profile["v_m_s"],
            "unit": "m/s",
            "status": "valid",
            "source_type": "deterministic_foundation",
            "source_ref": "deterministic_foundation.surface_speed_mps",
            "input_refs": ["shaft_diameter_mm", "max_speed_rpm"],
            "formula_id": "surface_speed_from_diameter_and_rpm_v1",
        }
    if computed_profile.get("pv_value") is not None:
        calculations["pv_value_bar_mps"] = {
            "value": computed_profile["pv_value"],
            "unit": "bar*m/s",
            "status": "valid",
            "source_type": "deterministic_foundation",
            "source_ref": "deterministic_foundation.pv_value_bar_mps",
            "input_refs": ["pressure_bar", "surface_speed_mps"],
            "formula_id": "pv_from_pressure_and_surface_speed_v1",
        }

    rwdr_derived = _model_to_payload(rwdr_state.get("derived")) or {}
    if rwdr_derived.get("surface_speed_mps") is not None:
        calculations["rwdr_surface_speed_mps"] = {
            "value": rwdr_derived["surface_speed_mps"],
            "unit": "m/s",
            "status": "valid",
            "source_type": "rwdr.derived",
            "source_ref": "rwdr.derived.surface_speed_mps",
            "input_refs": ["shaft_diameter_mm", "max_speed_rpm"],
            "formula_id": "rwdr_surface_speed_core_v1",
        }
    if rwdr_derived.get("confidence_score") is not None:
        calculations["rwdr_confidence_score"] = {
            "value": rwdr_derived["confidence_score"],
            "unit": None,
            "status": "valid",
            "source_type": "rwdr.derived",
            "source_ref": "rwdr.derived.confidence_score",
            "input_refs": [],
            "formula_id": "rwdr_confidence_score_v1",
        }
    return calculations


def build_engineering_signal_foundation(
    sealing_state: Dict[str, Any],
    working_profile: Dict[str, Any],
    rwdr_state: Dict[str, Any],
    derived_calculations: Dict[str, DeterministicCalculationRecord],
) -> Dict[str, DeterministicSignalRecord]:
    signals: Dict[str, DeterministicSignalRecord] = {}
    governance = sealing_state.get("governance") or {}
    selection = sealing_state.get("selection") or {}
    rwdr_derived = _model_to_payload(rwdr_state.get("derived")) or {}
    base_profile = _extract_base_profile(sealing_state, working_profile)

    risk_warning = validate_material_risk(base_profile)
    if risk_warning:
        signals["material_risk_warning"] = {
            "value": risk_warning,
            "signal_class": "warning",
            "severity": "medium",
            "source_type": "deterministic_foundation",
            "source_ref": "deterministic_foundation.material_risk_warning",
            "input_refs": ["pressure_bar", "material"],
        }

    if "surface_speed_mps" in derived_calculations:
        surface_speed_value = derived_calculations["surface_speed_mps"]["value"]
        signals["surface_speed_available"] = {
            "value": True,
            "signal_class": "availability",
            "severity": "low",
            "source_type": "deterministic_foundation",
            "source_ref": "deterministic_foundation.surface_speed_available",
            "input_refs": ["surface_speed_mps"],
        }
        if isinstance(surface_speed_value, (int, float)) and surface_speed_value > 10.0:
            signals["surface_speed_high"] = {
                "value": surface_speed_value,
                "signal_class": "threshold_warning",
                "severity": "high",
                "source_type": "deterministic_foundation",
                "source_ref": "deterministic_foundation.surface_speed_high",
                "input_refs": ["surface_speed_mps"],
            }

    if governance.get("conflicts"):
        signals["governance_conflicts_present"] = {
            "value": len(governance.get("conflicts", [])),
            "signal_class": "conflict_count",
            "severity": "high",
            "source_type": "sealing_state.governance",
            "source_ref": "sealing_state.governance.conflicts",
            "input_refs": [],
        }
    if governance.get("unknowns_release_blocking"):
        signals["release_blocking_unknowns_present"] = {
            "value": len(governance.get("unknowns_release_blocking", [])),
            "signal_class": "gate",
            "severity": "high",
            "source_type": "sealing_state.governance",
            "source_ref": "sealing_state.governance.unknowns_release_blocking",
            "input_refs": [],
        }
    if selection.get("output_blocked") is not None:
        signals["selection_output_blocked"] = {
            "value": bool(selection.get("output_blocked")),
            "signal_class": "gate",
            "severity": "high" if selection.get("output_blocked") else "low",
            "source_type": "sealing_state.selection",
            "source_ref": "sealing_state.selection.output_blocked",
            "input_refs": [],
        }

    rwdr_signal_fields = {
        "surface_speed_class": "classification",
        "tribology_risk_level": "risk_level",
        "pressure_risk_level": "risk_level",
        "exclusion_level": "classification",
        "geometry_fit_status": "fit_status",
        "ptfe_candidate_flag": "candidate_flag",
        "pressure_profile_required_flag": "requirement_flag",
        "dust_lip_required_flag": "requirement_flag",
        "heavy_duty_candidate_flag": "candidate_flag",
        "review_due_to_uncertainty": "review_flag",
        "review_due_to_water_pressure": "review_flag",
    }
    for field_name, signal_class in rwdr_signal_fields.items():
        if field_name not in rwdr_derived:
            continue
        value = rwdr_derived.get(field_name)
        if value in (None, False, "unknown"):
            continue
        signals[f"rwdr_{field_name}"] = {
            "value": value,
            "signal_class": signal_class,
            "severity": _infer_signal_severity(field_name, value),
            "source_type": "rwdr.derived",
            "source_ref": f"rwdr.derived.{field_name}",
            "input_refs": [],
        }

    return signals


def _extract_base_profile(sealing_state: Dict[str, Any], working_profile: Dict[str, Any]) -> Dict[str, Any]:
    asserted = sealing_state.get("asserted") or {}
    operating_conditions = asserted.get("operating_conditions") or {}
    machine_profile = asserted.get("machine_profile") or {}
    medium_profile = asserted.get("medium_profile") or {}

    profile: Dict[str, Any] = {}
    if working_profile.get("diameter") is not None:
        profile["diameter"] = working_profile.get("diameter")
    if working_profile.get("speed") is not None:
        profile["speed"] = working_profile.get("speed")
    if working_profile.get("pressure") is not None:
        profile["pressure"] = working_profile.get("pressure")
    elif operating_conditions.get("pressure") is not None:
        profile["pressure"] = operating_conditions.get("pressure")
    if working_profile.get("temperature") is not None:
        profile["temperature"] = working_profile.get("temperature")
    elif operating_conditions.get("temperature") is not None:
        profile["temperature"] = operating_conditions.get("temperature")
    if working_profile.get("material"):
        profile["material"] = working_profile.get("material")
    elif machine_profile.get("material"):
        profile["material"] = machine_profile.get("material")
    if working_profile.get("medium"):
        profile["medium"] = working_profile.get("medium")
    elif medium_profile.get("name"):
        profile["medium"] = medium_profile.get("name")
    return profile


def _infer_signal_severity(field_name: str, value: Any) -> str:
    if field_name.endswith("_risk_level") and str(value) in {"high", "critical"}:
        return "high"
    if field_name.endswith("_flag") and bool(value):
        return "medium"
    if field_name == "surface_speed_class" and str(value) in {"high", "over_limit"}:
        return "high"
    if field_name == "geometry_fit_status" and str(value) == "not_fit":
        return "high"
    return "low"


def _model_to_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value
