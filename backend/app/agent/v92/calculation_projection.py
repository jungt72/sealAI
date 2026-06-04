"""Projection helpers for the persisted V9.2 calculation ledger.

The LangGraph compute node may expose transient ``compute_results`` during a
turn, but persisted sessions keep deterministic outputs in
``state.calculation.results``.  These helpers make that ledger usable by UI
projections, answer context and professional checks without mutating state.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.domain.seal_packs import pack_for_calc_id


_RWDR_OUTPUT_KEYS: tuple[str, ...] = (
    "v_surface_m_s",
    "pv_value_mpa_m_s",
    "dn_value",
    "temperature_headroom_c",
    "pressure_window",
)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return dict(model_dump(mode="python"))
    return {}


def _calculation_results(calculation_or_results: Any) -> list[Any]:
    if calculation_or_results is None:
        return []
    results = getattr(calculation_or_results, "results", None)
    if results is not None:
        return list(results or [])
    if isinstance(calculation_or_results, Iterable) and not isinstance(
        calculation_or_results, (str, bytes, Mapping)
    ):
        return list(calculation_or_results)
    return []


def _clean_text_list(values: Iterable[Any]) -> list[str]:
    return [str(item) for item in values if item not in (None, "")]


def _ledger_item(result: Any) -> dict[str, Any]:
    payload = _as_dict(result)
    outputs = dict(payload.get("outputs") or {})
    calc_id = str(payload.get("calculation_id") or payload.get("calc_type") or "unknown")
    status = str(payload.get("status") or "insufficient_data")
    notes = _clean_text_list(payload.get("notes") or [])
    notes.extend(_clean_text_list(payload.get("limitations") or []))
    missing_inputs = _clean_text_list(payload.get("missing_inputs") or [])
    if missing_inputs:
        notes.append("Fehlende Eingaben: " + ", ".join(missing_inputs))
    item: dict[str, Any] = {
        "calc_type": calc_id,
        "calculation_id": calc_id,
        "calculator": payload.get("calculator"),
        "status": status,
        "notes": notes,
        "missing_inputs": missing_inputs,
        "dependencies": _clean_text_list(payload.get("dependencies") or []),
        "units": dict(payload.get("units") or {}),
        "validity_status": payload.get("validity_status"),
        "claim_level": payload.get("claim_level"),
        "outputs": outputs,
    }
    item.update({key: value for key, value in outputs.items() if value is not None})
    if "value" not in item:
        for key in _RWDR_OUTPUT_KEYS:
            if item.get(key) is not None:
                item["value"] = item[key]
                break
    return item


def _is_rwdr_ledger_item(item: Mapping[str, Any]) -> bool:
    calc_id = str(item.get("calculation_id") or item.get("calc_type") or "")
    calculator = str(item.get("calculator") or "")
    # P1-1 PR3: rwdr ownership by pack id-pattern, not a core string branch.
    if pack_for_calc_id(calc_id) is not None:
        return True
    if calculator in {"surface_speed_from_rpm_and_diameter", "CascadingCalculationEngine"}:
        return True
    return any(item.get(key) is not None for key in _RWDR_OUTPUT_KEYS)


def _merge_status(current: str | None, incoming: str) -> str:
    if not current:
        return incoming
    if current == "ok" or incoming == "ok":
        return "ok"
    if current == "warning" or incoming == "warning":
        return "warning"
    if current == "stale" or incoming == "stale":
        return "stale"
    if current == "blocked" or incoming == "blocked":
        return "blocked"
    return incoming or current


def _merge_unique(existing: list[str], incoming: Iterable[Any]) -> list[str]:
    seen = set(existing)
    for item in _clean_text_list(incoming):
        if item not in seen:
            existing.append(item)
            seen.add(item)
    return existing


def calculation_ledger_derivations(calculation_or_results: Any) -> list[dict[str, Any]]:
    """Return technical-derivation dicts from persisted CalculationState results.

    The first item aggregates RWDR outputs under ``calc_type='rwdr'`` because
    existing professional checks consume that historic compute-result shape.
    Individual ledger entries are preserved afterwards for transparency.
    """
    items = [_ledger_item(result) for result in _calculation_results(calculation_or_results)]
    if not items:
        return []

    rwdr: dict[str, Any] | None = None
    for item in items:
        if not _is_rwdr_ledger_item(item):
            continue
        if rwdr is None:
            rwdr = {
                "calc_type": "rwdr",
                "calculation_id": "rwdr.ledger",
                "status": item.get("status") or "insufficient_data",
                "notes": [],
                "missing_inputs": [],
                "dependencies": [],
                "outputs": {},
            }
        rwdr["status"] = _merge_status(str(rwdr.get("status") or ""), str(item.get("status") or ""))
        _merge_unique(rwdr["notes"], item.get("notes") or [])
        _merge_unique(rwdr["missing_inputs"], item.get("missing_inputs") or [])
        _merge_unique(rwdr["dependencies"], item.get("dependencies") or [])
        outputs = dict(item.get("outputs") or {})
        rwdr["outputs"].update({key: value for key, value in outputs.items() if value is not None})
        for key in _RWDR_OUTPUT_KEYS:
            if item.get(key) is not None:
                rwdr[key] = item[key]
                rwdr["outputs"][key] = item[key]

    derivations: list[dict[str, Any]] = []
    if rwdr is not None:
        for key in _RWDR_OUTPUT_KEYS:
            if rwdr.get(key) is not None:
                rwdr["value"] = rwdr[key]
                break
        derivations.append(rwdr)

    derivations.extend(item for item in items if item.get("calc_type") != "rwdr")
    return derivations

