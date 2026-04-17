"""Backend-owned deterministic check registry.

This module registers calculation/check metadata separately from risk scoring
and norm activation.  It currently exposes only deterministic RWDR results that
already exist in the codebase.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class EngineeringCheckDefinition:
    calc_id: str
    label: str
    formula_version: str
    required_inputs: tuple[str, ...]
    valid_paths: tuple[str, ...]
    output_key: str
    unit: str | None = None
    fallback_behavior: str = "insufficient_data_when_required_inputs_missing"
    guardrails: tuple[str, ...] = ()
    source_calc_type: str = "rwdr"


REGISTERED_CHECKS: tuple[EngineeringCheckDefinition, ...] = (
    EngineeringCheckDefinition(
        calc_id="rwdr_circumferential_speed",
        label="RWDR circumferential speed",
        formula_version="rwdr_calc_v1",
        required_inputs=("shaft_diameter_mm", "speed_rpm"),
        valid_paths=("rwdr",),
        output_key="v_surface_m_s",
        unit="m/s",
        guardrails=("diameter and speed must be present and non-negative",),
    ),
    EngineeringCheckDefinition(
        calc_id="rwdr_pv_precheck",
        label="RWDR PV precheck",
        formula_version="rwdr_calc_v1",
        required_inputs=("shaft_diameter_mm", "speed_rpm", "pressure_bar"),
        valid_paths=("rwdr",),
        output_key="pv_value_mpa_m_s",
        unit="MPa*m/s",
        guardrails=(
            "uses existing pressure_bar-based RWDR precheck only",
            "not a final effective contact-pressure PV model",
        ),
    ),
    EngineeringCheckDefinition(
        calc_id="rwdr_dn_value",
        label="RWDR Dn value",
        formula_version="rwdr_calc_v1",
        required_inputs=("shaft_diameter_mm", "speed_rpm"),
        valid_paths=("rwdr",),
        output_key="dn_value",
        unit="mm*min^-1",
        guardrails=("diameter and speed must be present and non-negative",),
    ),
)

_INPUT_ALIASES: dict[str, tuple[str, ...]] = {
    "shaft_diameter_mm": ("shaft_diameter_mm", "shaft_diameter", "diameter"),
    "speed_rpm": ("speed_rpm", "rpm", "speed"),
    "pressure_bar": ("pressure_bar", "pressure_max_bar", "pressure"),
}


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _has_profile_value(profile: dict[str, Any], key: str) -> bool:
    for alias in _INPUT_ALIASES.get(key, (key,)):
        value = profile.get(alias)
        if value not in (None, "", [], {}):
            return True
    return False


def _derivations_by_type(technical_derivations: Iterable[Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in technical_derivations:
        payload = _as_dict(item)
        calc_type = str(payload.get("calc_type") or "").strip()
        if calc_type and calc_type not in result:
            result[calc_type] = payload
    return result


def build_registered_check_results(
    *,
    profile: dict[str, Any],
    engineering_path: str | None,
    technical_derivations: Iterable[Any],
) -> list[dict[str, Any]]:
    """Project active registered checks with current result or missing-input fallback."""
    derivations = _derivations_by_type(technical_derivations)
    results: list[dict[str, Any]] = []

    for definition in REGISTERED_CHECKS:
        derivation = derivations.get(definition.source_calc_type)
        if engineering_path is not None:
            if engineering_path not in definition.valid_paths:
                continue
        elif derivation is None:
            continue

        missing_inputs = [
            input_key
            for input_key in definition.required_inputs
            if not _has_profile_value(profile, input_key)
        ]
        value = derivation.get(definition.output_key) if derivation is not None else None
        status = str((derivation or {}).get("status") or "insufficient_data")
        if value is None or missing_inputs:
            status = "insufficient_data"

        results.append(
            {
                "calc_id": definition.calc_id,
                "label": definition.label,
                "formula_version": definition.formula_version,
                "required_inputs": list(definition.required_inputs),
                "missing_inputs": missing_inputs,
                "valid_paths": list(definition.valid_paths),
                "output_key": definition.output_key,
                "unit": definition.unit,
                "status": status,
                "value": value if value is not None and not missing_inputs else None,
                "fallback_behavior": definition.fallback_behavior,
                "guardrails": list(definition.guardrails),
                "notes": [str(item) for item in list((derivation or {}).get("notes") or []) if item],
            }
        )

    return results
