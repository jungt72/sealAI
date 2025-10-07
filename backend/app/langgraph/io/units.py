"""Unit normalization helpers for LangGraph IO models."""
from __future__ import annotations

from typing import Iterable

from .schema import ParameterBag, ParamValue, Unit

# Conversion constants
KELVIN_SHIFT = 273.15
BAR_TO_PA = 100_000.0


def _copy_param(value: ParamValue, **updates) -> ParamValue:
    copier = getattr(value, "model_copy", None)
    if callable(copier):  # pydantic v2
        return copier(update=updates)
    return value.copy(update=updates)  # type: ignore[return-value]


def to_canonical(param: ParamValue) -> ParamValue:
    """Return a ParamValue converted into canonical SI units."""
    raw = param.value
    if isinstance(raw, bool):
        return param

    if param.unit is Unit.celsius and isinstance(raw, (int, float)):
        return _copy_param(param, value=float(raw) + KELVIN_SHIFT, unit=Unit.kelvin)

    if param.unit is Unit.bar and isinstance(raw, (int, float)):
        return _copy_param(param, value=float(raw) * BAR_TO_PA, unit=Unit.pascal)

    return param


def normalize_bag(bag: ParameterBag) -> ParameterBag:
    """Normalize all parameter values within a ParameterBag."""
    items: Iterable[ParamValue] = (to_canonical(item) for item in bag.items)
    return ParameterBag.from_iterable(items)


__all__ = ["KELVIN_SHIFT", "BAR_TO_PA", "to_canonical", "normalize_bag"]
