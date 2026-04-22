from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping

FieldPath = str


@dataclass(frozen=True, slots=True)
class CalcResult:
    outputs: Mapping[FieldPath, Any]
    status: str = "ok"
    missing_inputs: tuple[FieldPath, ...] = ()


@dataclass(frozen=True, slots=True)
class CalculationDefinition:
    calc_id: str
    version: str
    required_inputs: tuple[FieldPath, ...]
    outputs: tuple[FieldPath, ...]
    formula: Callable[[Mapping[str, Any]], CalcResult]
    engineering_path: str = "rwdr"


@dataclass(frozen=True, slots=True)
class CalcExecutionRecord:
    calc_id: str
    version: str
    inputs_used: Mapping[FieldPath, Any]
    outputs_produced: Mapping[FieldPath, Any]
    provenance: str = "calculated"


class CascadeLoopError(RuntimeError):
    pass


MAX_CASCADE_ITERATIONS = 20


class CascadingCalculationEngine:
    def __init__(self, calculations: tuple[CalculationDefinition, ...] | None = None) -> None:
        self._calculations = calculations or PTFE_RWDR_CALCULATIONS

    def execute_cascade(self, case: Mapping[str, Any]) -> tuple[dict[str, Any], list[CalcExecutionRecord]]:
        state = dict(case)
        executed: list[CalcExecutionRecord] = []
        signatures: set[tuple[str, tuple[tuple[str, Any], ...]]] = set()
        guard = 0
        changed = True
        while changed and guard < MAX_CASCADE_ITERATIONS:
            changed = False
            guard += 1
            for calc in self._calculations:
                if state.get("engineering_path", "rwdr") != calc.engineering_path:
                    continue
                if not _has_inputs(state, calc.required_inputs):
                    continue
                signature = (calc.calc_id, tuple((path, _get(state, path)) for path in calc.required_inputs))
                if signature in signatures:
                    continue
                result = calc.formula(state)
                signatures.add(signature)
                if result.status != "ok":
                    continue
                produced = {path: value for path, value in result.outputs.items() if _get(state, path) != value}
                if not produced:
                    continue
                for path, value in produced.items():
                    _set(state, path, value)
                executed.append(CalcExecutionRecord(calc.calc_id, calc.version, dict(signature[1]), produced))
                changed = True
        if guard >= MAX_CASCADE_ITERATIONS:
            raise CascadeLoopError("calculation cascade did not converge")
        return state, executed


def _get(data: Mapping[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _set(data: dict[str, Any], path: str, value: Any) -> None:
    current = data
    parts = path.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def _num(data: Mapping[str, Any], path: str) -> float:
    return float(_get(data, path))


def _has_inputs(data: Mapping[str, Any], paths: tuple[str, ...]) -> bool:
    return all(_get(data, path) is not None for path in paths)


def _circumferential_speed(case: Mapping[str, Any]) -> CalcResult:
    diameter = _num(case, "shaft.diameter_mm")
    rpm = _num(case, "operating.shaft_speed.rpm_nom")
    return CalcResult({"derived.surface_speed_ms": math.pi * diameter / 1000.0 * rpm / 60.0})


def _contact_pressure(case: Mapping[str, Any]) -> CalcResult:
    force = _num(case, "rwdr.lip.radial_force_n_per_mm")
    width = _num(case, "rwdr.lip.contact_width_mm")
    return CalcResult({"derived.contact_pressure_n_per_mm2": force / width})


def _pv_loading(case: Mapping[str, Any]) -> CalcResult:
    pressure = _num(case, "derived.contact_pressure_n_per_mm2")
    speed = _num(case, "derived.surface_speed_ms")
    return CalcResult({"derived.pv_loading": pressure * speed})


def _thermal_load_indicator(case: Mapping[str, Any]) -> CalcResult:
    pv = _num(case, "derived.pv_loading")
    friction = float(_get(case, "compound.friction_coefficient") or 0.12)
    diameter = _num(case, "shaft.diameter_mm")
    return CalcResult({"derived.heat_flux_w_per_mm": pv * friction * math.pi * diameter})


def _extrusion_gap_check(case: Mapping[str, Any]) -> CalcResult:
    pressure_bar = _num(case, "operating.pressure.max_bar")
    gap_mm = _num(case, "rwdr.extrusion_gap_mm")
    margin = max(0.0, 1.0 - (pressure_bar * gap_mm / 10.0))
    return CalcResult({"derived.extrusion_safety_margin": margin})


def _creep_gap_estimate(case: Mapping[str, Any]) -> CalcResult:
    force = _num(case, "rwdr.lip.radial_force_n_per_mm")
    temp = _num(case, "operating.temperature.nom_c")
    years = _num(case, "expected_service_duration_years")
    return CalcResult({"derived.estimated_creep_gap_um": max(0.0, (temp / 100.0) * years * 10.0 / force)})


def _temperature_headroom(case: Mapping[str, Any]) -> CalcResult:
    max_temp = _num(case, "operating.temperature.max_c")
    family = str(_get(case, "sealing_material_family") or "")
    limit = 260.0 if family.startswith("ptfe") else 180.0
    return CalcResult({"derived.temperature_headroom_c": limit - max_temp})


PTFE_RWDR_CALCULATIONS: tuple[CalculationDefinition, ...] = (
    CalculationDefinition("ptfe_rwdr.circumferential_speed", "1.0", ("shaft.diameter_mm", "operating.shaft_speed.rpm_nom"), ("derived.surface_speed_ms",), _circumferential_speed),
    CalculationDefinition("ptfe_rwdr.contact_pressure", "1.0", ("rwdr.lip.radial_force_n_per_mm", "rwdr.lip.contact_width_mm"), ("derived.contact_pressure_n_per_mm2",), _contact_pressure),
    CalculationDefinition("ptfe_rwdr.pv_loading", "1.0", ("derived.contact_pressure_n_per_mm2", "derived.surface_speed_ms"), ("derived.pv_loading",), _pv_loading),
    CalculationDefinition("ptfe_rwdr.thermal_load_indicator", "1.0", ("derived.pv_loading", "shaft.diameter_mm"), ("derived.heat_flux_w_per_mm",), _thermal_load_indicator),
    CalculationDefinition("ptfe_rwdr.extrusion_gap_check", "1.0", ("operating.pressure.max_bar", "rwdr.extrusion_gap_mm"), ("derived.extrusion_safety_margin",), _extrusion_gap_check),
    CalculationDefinition("ptfe_rwdr.creep_gap_estimate_simplified", "1.0", ("rwdr.lip.radial_force_n_per_mm", "operating.temperature.nom_c", "expected_service_duration_years"), ("derived.estimated_creep_gap_um",), _creep_gap_estimate),
    CalculationDefinition("ptfe_rwdr.compound_temperature_headroom", "1.0", ("operating.temperature.max_c", "sealing_material_family"), ("derived.temperature_headroom_c",), _temperature_headroom),
)
