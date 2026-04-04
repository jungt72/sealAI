from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.agent.state.models import AssertedState, RequirementClass


@dataclass(frozen=True)
class RequirementClassSpecialistInput:
    normalized_parameters: Mapping[str, Any] | None = None
    asserted_state: AssertedState | None = None
    evidence_hints: Sequence[str] = ()
    geometry_install_hints: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class RequirementClassSpecialistResult:
    requirement_class_candidates: tuple[RequirementClass, ...] = ()
    preferred_requirement_class: RequirementClass | None = None
    open_points: tuple[str, ...] = ()
    scope_of_validity: tuple[str, ...] = ()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalized_value(mapping: Mapping[str, Any] | None, field_name: str) -> Any:
    if not mapping or field_name not in mapping:
        return None
    value = mapping[field_name]
    return getattr(value, "value", value)


def _specialist_value(payload: RequirementClassSpecialistInput, field_name: str) -> Any:
    asserted = payload.asserted_state
    if asserted is not None:
        claim = asserted.assertions.get(field_name)
        if claim is not None:
            return claim.asserted_value
    geometry_hints = payload.geometry_install_hints or {}
    if field_name in geometry_hints:
        return geometry_hints[field_name]
    return _normalized_value(payload.normalized_parameters, field_name)


def _has_rotary_install_hint(payload: RequirementClassSpecialistInput) -> bool:
    dynamic_type = str(_specialist_value(payload, "dynamic_type") or "").strip().lower()
    if dynamic_type in {"dynamic", "rotary", "rotierend"}:
        return True
    for field_name in ("shaft_diameter_mm", "speed_rpm"):
        if _specialist_value(payload, field_name) is not None:
            return True
    geometry_hints = payload.geometry_install_hints or {}
    return any(geometry_hints.get(field_name) is not None for field_name in ("shaft_diameter_mm", "speed_rpm"))


def _installation_text(payload: RequirementClassSpecialistInput) -> str:
    value = _specialist_value(payload, "installation")
    if value is None:
        geometry_hints = payload.geometry_install_hints or {}
        value = geometry_hints.get("installation")
    return str(value or "").strip().lower()


def _has_static_install_hint(payload: RequirementClassSpecialistInput) -> bool:
    text = _installation_text(payload)
    return any(marker in text for marker in ("flansch", "gehaeuse", "gehäuse", "statisch", "deckel", "platte"))


def _has_geometry_context(payload: RequirementClassSpecialistInput) -> bool:
    for field_name in ("installation", "shaft_diameter_mm", "speed_rpm"):
        if _specialist_value(payload, field_name) is not None:
            return True
    text = _installation_text(payload)
    return any(marker in text for marker in ("nut", "bohrung", "welle", "flansch", "gehaeuse", "gehäuse"))


def _append_unique(items: list[str], value: str | None) -> None:
    if value and value not in items:
        items.append(value)


def _class(class_id: str, description: str, seal_type: str) -> RequirementClass:
    return RequirementClass(class_id=class_id, description=description, seal_type=seal_type)


def run_requirement_class_specialist(
    payload: RequirementClassSpecialistInput,
) -> RequirementClassSpecialistResult:
    medium = str(_specialist_value(payload, "medium") or "").strip().lower()
    material = str(_specialist_value(payload, "material") or "").strip().upper()
    temp_c = _as_float(_specialist_value(payload, "temperature_c"))
    pressure_bar = _as_float(_specialist_value(payload, "pressure_bar"))

    candidates: list[RequirementClass] = []
    open_points: list[str] = []
    scope_of_validity: list[str] = []

    if not medium:
        return RequirementClassSpecialistResult(
            requirement_class_candidates=(),
            preferred_requirement_class=None,
            open_points=("medium",),
            scope_of_validity=("Requirement-class derivation requires a resolved medium.",),
        )

    rotary_hint = _has_rotary_install_hint(payload)
    if rotary_hint:
        _append_unique(
            scope_of_validity,
            "Geometry/install hints indicate a rotary installation context; seal-type context stays bounded.",
        )
    elif _has_static_install_hint(payload):
        _append_unique(
            scope_of_validity,
            "Installation hints indicate a static or flange-style sealing context; seal-type context stays bounded.",
        )

    if not _has_geometry_context(payload):
        _append_unique(open_points, "installation")
        _append_unique(
            scope_of_validity,
            "Requirement-class narrowing remains limited until the installation geometry is described.",
        )
    elif rotary_hint:
        if _specialist_value(payload, "shaft_diameter_mm") is None:
            _append_unique(open_points, "shaft_diameter_mm")
        if _specialist_value(payload, "speed_rpm") is None:
            _append_unique(open_points, "speed_rpm")

    preferred: RequirementClass | None = None

    if material == "PTFE":
        if "dampf" in medium or "steam" in medium:
            preferred = _class(
                "PTFE10",
                "PTFE steam sealing class for elevated thermal load.",
                "gasket",
            )
            _append_unique(scope_of_validity, "Derived from asserted PTFE material family and steam medium.")
        else:
            preferred = _class(
                "PTFE-GEN-1",
                "General PTFE sealing class for chemically broad service.",
                "gasket",
            )
            _append_unique(scope_of_validity, "Derived from asserted PTFE material family.")
    elif material == "FKM":
        if temp_c is not None and temp_c >= 150:
            preferred = _class(
                "FKM-HT-1",
                "High-temperature FKM sealing class.",
                "radial_shaft_seal",
            )
            _append_unique(scope_of_validity, "Derived from asserted FKM material family and elevated temperature.")
        else:
            preferred = _class(
                "FKM-GEN-1",
                "General FKM sealing class for elastomer service.",
                "radial_shaft_seal",
            )
            _append_unique(scope_of_validity, "Derived from asserted FKM material family.")
    elif "dampf" in medium or "steam" in medium:
        preferred = _class(
            "PTFE10",
            "PTFE steam sealing class for elevated thermal load.",
            "gasket",
        )
        _append_unique(open_points, "material")
        _append_unique(
            scope_of_validity,
            "Steam-led requirement class inferred without a confirmed material family.",
        )
    elif temp_c is not None and temp_c >= 150:
        preferred = _class(
            "FKM-HT-1",
            "High-temperature sealing class pending material-family confirmation.",
            "radial_shaft_seal",
        )
        _append_unique(open_points, "material")
        _append_unique(
            scope_of_validity,
            "Temperature-led requirement class inferred without a confirmed material family.",
        )
    elif pressure_bar is not None and pressure_bar >= 10:
        preferred = _class(
            "ROTARY-P1" if rotary_hint else "GENERAL-P1",
            "Pressure-led sealing class pending material-family confirmation.",
            "radial_shaft_seal" if rotary_hint else "gasket",
        )
        _append_unique(open_points, "material")
        _append_unique(
            scope_of_validity,
            "Pressure-led requirement class inferred without a confirmed material family.",
        )
    else:
        preferred = _class(
            "ROTARY-B1" if rotary_hint else "STATIC-B1" if _has_static_install_hint(payload) else "GENERAL-B1",
            "General sealing requirement — further qualification required.",
            "radial_shaft_seal" if rotary_hint else "gasket",
        )
        _append_unique(open_points, "material")
        _append_unique(
            scope_of_validity,
            "General fallback requirement class pending material-family confirmation.",
        )

    if preferred is not None:
        candidates.append(preferred)

    return RequirementClassSpecialistResult(
        requirement_class_candidates=tuple(candidates),
        preferred_requirement_class=preferred,
        open_points=tuple(open_points),
        scope_of_validity=tuple(scope_of_validity),
    )
