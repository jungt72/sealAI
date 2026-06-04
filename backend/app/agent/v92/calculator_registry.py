"""V9.2 deterministic calculator registry.

The registry is the typed boundary for deterministic engineering calculations:
input normalization, dependency tracking, snapshot hashes, output units and
claim boundaries live here rather than in prompt code or frontend adapters.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from app.agent.v92.models import CalculationResult
from app.mcp.calculations.chemical_resistance import (
    lookup as lookup_chemical_resistance,
)
from app.mcp.calculations.material_limits import check as check_material_limits


CalculatorFn = Callable[["CalculationRequest"], CalculationResult]


class MissingEngineeringField(BaseModel):
    field_name: str
    reason: str = "required_for_calculation"
    unit: str | None = None
    required_for: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CalculationRequest(BaseModel):
    calculator_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    case_revision: int = 0
    trace_id: str | None = None

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True, slots=True)
class RegisteredCalculator:
    calculator_id: str
    version: str
    required_inputs: tuple[str, ...]
    output_keys: tuple[str, ...]
    calculate: CalculatorFn


def stable_snapshot_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def output_snapshot_hash(outputs: Mapping[str, Any]) -> str:
    return stable_snapshot_hash(outputs)


def _first_present(
    inputs: Mapping[str, Any], names: Iterable[str]
) -> tuple[str | None, Any]:
    for name in names:
        value = inputs.get(name)
        if value not in (None, ""):
            return name, value
    return None, None


def _to_positive_float(value: Any) -> float | None:
    try:
        parsed = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _surface_speed_from_rpm_and_diameter(
    request: CalculationRequest,
) -> CalculationResult:
    diameter_key, diameter_raw = _first_present(
        request.inputs,
        ("shaft_diameter_mm", "diameter_mm", "shaft_diameter"),
    )
    rpm_key, rpm_raw = _first_present(
        request.inputs,
        ("speed_rpm", "rpm", "rotational_speed_rpm"),
    )
    diameter_mm = _to_positive_float(diameter_raw)
    rpm = _to_positive_float(rpm_raw)
    missing = []
    if diameter_mm is None:
        missing.append("shaft_diameter_mm")
    if rpm is None:
        missing.append("speed_rpm")

    dependencies = ["shaft_diameter_mm", "speed_rpm"]
    input_snapshot = {
        "case_revision": request.case_revision,
        "shaft_diameter_mm": diameter_mm,
        "speed_rpm": rpm,
        "source_fields": {
            "shaft_diameter_mm": diameter_key,
            "speed_rpm": rpm_key,
        },
    }
    input_hash = stable_snapshot_hash(input_snapshot)

    if missing:
        return CalculationResult(
            calculation_id="rwdr.surface_speed",
            version="surface_speed_from_rpm_and_diameter.v1",
            calculator="surface_speed_from_rpm_and_diameter",
            status="insufficient_data",
            claim_level="L3_deterministic_calculation",
            input_snapshot_hash=input_hash,
            formula_refs=["generic_circumferential_speed_v1: pi * d_mm * rpm / 60000"],
            validity_status="input_missing",
            limitations=[
                "Calculation is blocked until shaft diameter and rotational speed are both known."
            ],
            missing_inputs=missing,
            dependencies=dependencies,
            notes=["Missing or non-positive inputs are not estimated."],
        )

    surface_speed = math.pi * diameter_mm * rpm / 60000.0
    outputs = {"v_surface_m_s": round(surface_speed, 3)}
    return CalculationResult(
        calculation_id="rwdr.surface_speed",
        version="surface_speed_from_rpm_and_diameter.v1",
        calculator="surface_speed_from_rpm_and_diameter",
        status="ok",
        claim_level="L3_deterministic_calculation",
        input_snapshot_hash=input_hash,
        outputs=outputs,
        units={"v_surface_m_s": "m/s"},
        formula_refs=["generic_circumferential_speed_v1: pi * d_mm * rpm / 60000"],
        output_snapshot_hash=output_snapshot_hash(outputs),
        validity_status="valid_for_screening",
        engineering_signals=[
            "deterministic_intermediate_value",
            "surface_speed_screening",
        ],
        limitations=[
            "Surface speed is a deterministic intermediate value, not a seal suitability or release claim."
        ],
        dependencies=dependencies,
        notes=[
            "Calculated from asserted shaft diameter and rotational speed.",
            "No manufacturer, compound or standards conformity claim is implied.",
        ],
    )


def _material_value(inputs: Mapping[str, Any]) -> tuple[str | None, Any]:
    return _first_present(
        inputs,
        ("material", "material_family", "sealing_material_family", "compound_family"),
    )


def _temperature_window_screening(request: CalculationRequest) -> CalculationResult:
    material_key, material_raw = _material_value(request.inputs)
    _, temp_raw = _first_present(
        request.inputs,
        ("temperature_c", "temperature_max_c", "operating_temperature_c"),
    )
    _, pressure_raw = _first_present(
        request.inputs, ("pressure_bar", "operating_pressure_bar")
    )
    material = str(material_raw or "").strip()
    temperature_c = _to_positive_or_signed_float(temp_raw)
    pressure_bar = (
        _to_positive_float(pressure_raw) if pressure_raw not in (None, "") else None
    )
    missing = []
    if not material:
        missing.append("material")
    if temperature_c is None:
        missing.append("temperature_c")
    input_hash = stable_snapshot_hash(
        {
            "case_revision": request.case_revision,
            "material": material or None,
            "temperature_c": temperature_c,
            "pressure_bar": pressure_bar,
            "source_fields": {"material": material_key},
        }
    )
    if missing:
        return CalculationResult(
            calculation_id="material.temperature_window_screening",
            version="material_temperature_window_screening.v1",
            calculator="temperature_window_screening",
            status="insufficient_data",
            claim_level="L3_deterministic_calculation",
            input_snapshot_hash=input_hash,
            formula_refs=["material_limits.check"],
            validity_status="input_missing",
            limitations=[
                "Material-family temperature screening is blocked until material and temperature are known."
            ],
            missing_inputs=missing,
            dependencies=["material", "temperature_c", "pressure_bar"],
        )
    try:
        checked = check_material_limits(
            material=material,
            temp_c=temperature_c,
            pressure_bar=pressure_bar,
            is_dynamic=bool(
                request.inputs.get("is_dynamic") or request.inputs.get("dynamic")
            ),
        )
    except KeyError as exc:
        outputs = {"material": material, "lookup_status": "unknown_material"}
        return CalculationResult(
            calculation_id="material.temperature_window_screening",
            version="material_temperature_window_screening.v1",
            calculator="temperature_window_screening",
            status="warning",
            claim_level="L3_deterministic_calculation",
            input_snapshot_hash=input_hash,
            outputs=outputs,
            units={"material": "text", "lookup_status": "text"},
            formula_refs=["material_limits.check"],
            output_snapshot_hash=output_snapshot_hash(outputs),
            validity_status="requires_expert_review",
            limitations=[
                "Unknown material family cannot be screened against deterministic limits."
            ],
            dependencies=["material", "temperature_c", "pressure_bar"],
            notes=[str(exc)],
        )
    limits = checked.limits
    outputs = {
        "material": limits.name,
        "temperature_c": temperature_c,
        "temp_min_c": limits.temp_min_c,
        "temp_max_c": limits.temp_max_c,
        "temp_peak_c": limits.temp_peak_c,
        "temp_ok": checked.temp_ok,
        "pressure_bar": pressure_bar,
        "pressure_ok": checked.pressure_ok,
    }
    status = (
        "ok"
        if checked.temp_ok is True and checked.pressure_ok is not False
        else "warning"
    )
    validity = "valid_for_screening" if status == "ok" else "requires_expert_review"
    return CalculationResult(
        calculation_id="material.temperature_window_screening",
        version="material_temperature_window_screening.v1",
        calculator="temperature_window_screening",
        status=status,
        claim_level="L3_deterministic_calculation",
        input_snapshot_hash=input_hash,
        outputs={key: value for key, value in outputs.items() if value is not None},
        units={
            "material": "text",
            "temperature_c": "degC",
            "temp_min_c": "degC",
            "temp_max_c": "degC",
            "temp_peak_c": "degC",
            "temp_ok": "bool_or_warning",
            "pressure_bar": "bar",
            "pressure_ok": "bool",
        },
        formula_refs=["material_limits.check"],
        output_snapshot_hash=output_snapshot_hash(
            {key: value for key, value in outputs.items() if value is not None}
        ),
        validity_status=validity,
        engineering_signals=["material_family_temperature_screening"],
        limitations=[
            "Material-family limits are screening data and do not establish compound or product suitability."
        ],
        dependencies=["material", "temperature_c", "pressure_bar"],
        notes=[str(item) for item in checked.warnings] + [checked.recommendation],
    )


def _material_family_counterindication_check(
    request: CalculationRequest,
) -> CalculationResult:
    material_key, material_raw = _material_value(request.inputs)
    _, medium_raw = _first_present(
        request.inputs, ("medium", "medium_name", "fluid", "chemical")
    )
    material = str(material_raw or "").strip()
    medium = str(medium_raw or "").strip()
    missing = []
    if not material:
        missing.append("material")
    if not medium:
        missing.append("medium")
    input_hash = stable_snapshot_hash(
        {
            "case_revision": request.case_revision,
            "material": material or None,
            "medium": medium or None,
            "source_fields": {"material": material_key},
        }
    )
    if missing:
        return CalculationResult(
            calculation_id="material.chemical_resistance_screening",
            version="material_family_counterindication_check.v1",
            calculator="material_family_counterindication_check",
            status="insufficient_data",
            claim_level="L3_deterministic_calculation",
            input_snapshot_hash=input_hash,
            formula_refs=["chemical_resistance.lookup"],
            validity_status="input_missing",
            limitations=[
                "Chemical resistance screening is blocked until material family and medium are known."
            ],
            missing_inputs=missing,
            dependencies=["material", "medium"],
        )
    try:
        result = lookup_chemical_resistance(medium=medium, material=material)
    except KeyError as exc:
        outputs = {"material": material, "medium": medium, "rating": "X"}
        return CalculationResult(
            calculation_id="material.chemical_resistance_screening",
            version="material_family_counterindication_check.v1",
            calculator="material_family_counterindication_check",
            status="warning",
            claim_level="L3_deterministic_calculation",
            input_snapshot_hash=input_hash,
            outputs=outputs,
            units={"material": "text", "medium": "text", "rating": "text"},
            formula_refs=["chemical_resistance.lookup"],
            output_snapshot_hash=output_snapshot_hash(outputs),
            validity_status="requires_expert_review",
            limitations=[
                "Unknown medium/material pair requires evidence or expert review."
            ],
            dependencies=["material", "medium"],
            notes=[str(exc)],
        )
    outputs = {
        "medium": result.medium,
        "material": result.material,
        "rating": result.rating,
        "note": result.note,
        "temp_limit_c": result.temp_limit_c,
        "source": result.source,
    }
    status = "warning" if result.rating in {"B", "C", "X"} else "ok"
    validity = (
        "valid_for_screening"
        if result.rating in {"A", "B"}
        else "requires_expert_review"
    )
    return CalculationResult(
        calculation_id="material.chemical_resistance_screening",
        version="material_family_counterindication_check.v1",
        calculator="material_family_counterindication_check",
        status=status,
        claim_level="L3_deterministic_calculation",
        input_snapshot_hash=input_hash,
        outputs={key: value for key, value in outputs.items() if value is not None},
        units={
            "medium": "text",
            "material": "text",
            "rating": "text",
            "note": "text",
            "temp_limit_c": "degC",
            "source": "text",
        },
        formula_refs=["chemical_resistance.lookup"],
        output_snapshot_hash=output_snapshot_hash(
            {key: value for key, value in outputs.items() if value is not None}
        ),
        validity_status=validity,
        engineering_signals=["material_family_chemical_resistance_screening"],
        limitations=[
            "Chemical resistance table result is material-family screening only; compound and product evidence remain separate."
        ],
        dependencies=["material", "medium"],
        notes=[result.recommendation],
        guardrail_violations=["counterindication_rating_c"]
        if result.rating == "C"
        else [],
    )


def _to_positive_or_signed_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


class CalculatorRegistry:
    def __init__(
        self, calculators: Iterable[RegisteredCalculator] | None = None
    ) -> None:
        self._calculators: dict[str, RegisteredCalculator] = {}
        for calculator in calculators or ():
            self.register(calculator)

    def register(self, calculator: RegisteredCalculator) -> None:
        self._calculators[calculator.calculator_id] = calculator

    def get(self, calculator_id: str) -> RegisteredCalculator:
        return self._calculators[calculator_id]

    def list_calculators(self) -> list[RegisteredCalculator]:
        return [self._calculators[key] for key in sorted(self._calculators)]

    def calculate(
        self,
        calculator_id: str,
        *,
        inputs: Mapping[str, Any],
        case_revision: int = 0,
        trace_id: str | None = None,
    ) -> CalculationResult:
        calculator = self.get(calculator_id)
        return calculator.calculate(
            CalculationRequest(
                calculator_id=calculator_id,
                inputs=dict(inputs),
                case_revision=case_revision,
                trace_id=trace_id,
            )
        )

    def affected_calculator_ids_for_fields(
        self, changed_fields: Iterable[str]
    ) -> list[str]:
        changed = {str(field) for field in changed_fields if field}
        affected = [
            calculator.calculator_id
            for calculator in self.list_calculators()
            if changed.intersection(calculator.required_inputs)
        ]
        return list(dict.fromkeys(affected))

    def missing_fields_for(
        self,
        calculator_id: str,
        inputs: Mapping[str, Any],
    ) -> list[MissingEngineeringField]:
        result = self.calculate(calculator_id, inputs=inputs)
        return [
            MissingEngineeringField(
                field_name=field,
                unit="mm"
                if "diameter" in field
                else ("rpm" if "rpm" in field else None),
                required_for=[calculator_id],
            )
            for field in result.missing_inputs
        ]


def get_calculator_registry() -> CalculatorRegistry:
    registry = CalculatorRegistry()
    registry.register(
        RegisteredCalculator(
            calculator_id="surface_speed_from_rpm_and_diameter",
            version="surface_speed_from_rpm_and_diameter.v1",
            required_inputs=("shaft_diameter_mm", "speed_rpm"),
            output_keys=("v_surface_m_s",),
            calculate=_surface_speed_from_rpm_and_diameter,
        )
    )
    registry.register(
        RegisteredCalculator(
            calculator_id="temperature_window_screening",
            version="material_temperature_window_screening.v1",
            required_inputs=("material", "temperature_c"),
            output_keys=("temp_ok", "temp_min_c", "temp_max_c", "temp_peak_c"),
            calculate=_temperature_window_screening,
        )
    )
    registry.register(
        RegisteredCalculator(
            calculator_id="material_family_counterindication_check",
            version="material_family_counterindication_check.v1",
            required_inputs=("material", "medium"),
            output_keys=("rating", "note", "temp_limit_c"),
            calculate=_material_family_counterindication_check,
        )
    )
    return registry


__all__ = [
    "CalculationRequest",
    "CalculatorRegistry",
    "MissingEngineeringField",
    "RegisteredCalculator",
    "get_calculator_registry",
    "output_snapshot_hash",
    "stable_snapshot_hash",
]
