from __future__ import annotations

import time
from typing import Any, Callable, Dict, Mapping, MutableMapping, Tuple

from pydantic import BaseModel, Field

from app.langgraph_v2.state import TechnicalParameters


def _build_allowed_keys() -> tuple[set[str], Dict[str, str]]:
    keys: set[str] = set()
    alias_map: Dict[str, str] = {}
    for name, field in TechnicalParameters.model_fields.items():
        keys.add(name)
        alias = getattr(field, "alias", None)
        if isinstance(alias, str) and alias:
            keys.add(alias)
            alias_map[alias] = name
    return keys, alias_map


ALLOWED_V2_PARAMETER_KEYS, ALIAS_TO_CANONICAL = _build_allowed_keys()


class ParametersPatchRequest(BaseModel):
    # Keep a default so we can return an explicit 400 "missing_chat_id" instead of a 422.
    chat_id: str = Field(default="", description="Conversation/thread id")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    base_versions: Dict[str, int] | None = None


def _is_primitive(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def sanitize_v2_parameter_patch(patch: Mapping[str, Any]) -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    for key, value in dict(patch or {}).items():
        if key not in ALLOWED_V2_PARAMETER_KEYS:
            raise ValueError(f"Unknown parameter key: {key}")
        if not _is_primitive(value):
            raise ValueError(f"Invalid parameter value type for {key}: {type(value).__name__}")
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        canonical = ALIAS_TO_CANONICAL.get(key, key)
        sanitized[canonical] = value
    return sanitized


def merge_parameters(existing: Any, patch: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Merge a parameter patch into an existing `parameters` object.

    - Existing can be dict-like or a pydantic model with `model_dump`.
    - Patch is assumed already sanitized (allowed keys, primitive values).
    """
    base: Dict[str, Any] = {}
    if isinstance(existing, dict):
        base.update({k: v for k, v in existing.items() if v is not None})
    else:
        model_dump = getattr(existing, "model_dump", None)
        if callable(model_dump):
            try:
                dumped = model_dump(exclude_none=True)
                if isinstance(dumped, dict):
                    base.update(dumped)
            except Exception:
                pass
        else:
            as_dict = getattr(existing, "as_dict", None)
            if callable(as_dict):
                try:
                    dumped = as_dict()
                    if isinstance(dumped, dict):
                        base.update({k: v for k, v in dumped.items() if v is not None})
                except Exception:
                    pass

    base.update(dict(patch or {}))
    return base


def apply_parameter_patch_with_provenance(
    existing: Any,
    patch: Mapping[str, Any],
    provenance: Mapping[str, str] | None,
    *,
    source: str,
    allow_user_override: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Merge parameters while honoring provenance rules.

    - "user" provenance wins unless allow_user_override=True.
    - The source string is stored for each applied key.
    """
    merged = merge_parameters(existing, {})
    updated_provenance: MutableMapping[str, str] = dict(provenance or {})
    for key, value in dict(patch or {}).items():
        existing_source = updated_provenance.get(key)
        if existing_source == "user" and source != "user" and not allow_user_override:
            continue
        merged[key] = value
        updated_provenance[key] = source
    return merged, dict(updated_provenance)


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        normalized = trimmed.replace(",", ".")
        num = ""
        for ch in normalized:
            if ch.isdigit() or ch in ".-+":
                num += ch
            elif num:
                break
        try:
            return float(num)
        except Exception:
            return None
    return None


def _select_first_number(payload: Mapping[str, Any], keys: tuple[str, ...]) -> tuple[str | None, float | None]:
    for key in keys:
        if key in payload:
            value = _parse_number(payload.get(key))
            if value is not None:
                return key, value
    return None, None


def _validate_cross_field(
    proposed: Mapping[str, Any],
    candidate_fields: set[str],
) -> list[Dict[str, Any]]:
    rejects: list[Dict[str, Any]] = []

    pressure_min_key, pressure_min = _select_first_number(proposed, ("pressure_min",))
    pressure_max_key, pressure_max = _select_first_number(proposed, ("pressure_max",))
    pressure_op_key, pressure_op = _select_first_number(proposed, ("pressure_bar", "pressure"))

    if pressure_min is not None and pressure_max is not None and pressure_min > pressure_max:
        fields = []
        if pressure_min_key in candidate_fields:
            fields.append(pressure_min_key)
        if pressure_max_key in candidate_fields:
            fields.append(pressure_max_key)
        if fields:
            for field in fields:
                rejects.append(
                    {
                        "field": field,
                        "reason": "pressure_range_invalid",
                        "details": {
                            "rule": "min<=max",
                            "min": pressure_min,
                            "max": pressure_max,
                        },
                    }
                )

    if pressure_op is not None and pressure_min is not None and pressure_op < pressure_min:
        if pressure_op_key in candidate_fields:
            rejects.append(
                {
                    "field": pressure_op_key,
                    "reason": "pressure_range_invalid",
                    "details": {
                        "rule": "min<=op",
                        "min": pressure_min,
                        "op": pressure_op,
                    },
                }
            )
        elif pressure_min_key in candidate_fields:
            rejects.append(
                {
                    "field": pressure_min_key,
                    "reason": "pressure_range_invalid",
                    "details": {
                        "rule": "min<=op",
                        "min": pressure_min,
                        "op": pressure_op,
                    },
                }
            )

    if pressure_op is not None and pressure_max is not None and pressure_op > pressure_max:
        if pressure_op_key in candidate_fields:
            rejects.append(
                {
                    "field": pressure_op_key,
                    "reason": "pressure_range_invalid",
                    "details": {
                        "rule": "op<=max",
                        "op": pressure_op,
                        "max": pressure_max,
                    },
                }
            )
        elif pressure_max_key in candidate_fields:
            rejects.append(
                {
                    "field": pressure_max_key,
                    "reason": "pressure_range_invalid",
                    "details": {
                        "rule": "op<=max",
                        "op": pressure_op,
                        "max": pressure_max,
                    },
                }
            )

    temp_min_key, temp_min = _select_first_number(proposed, ("temp_min", "temperature_min"))
    temp_max_key, temp_max = _select_first_number(proposed, ("temp_max", "temperature_max"))
    temp_op_key, temp_op = _select_first_number(proposed, ("temperature_C",))

    if temp_min is not None and temp_max is not None and temp_min > temp_max:
        fields = []
        if temp_min_key in candidate_fields:
            fields.append(temp_min_key)
        if temp_max_key in candidate_fields:
            fields.append(temp_max_key)
        if fields:
            for field in fields:
                rejects.append(
                    {
                        "field": field,
                        "reason": "temperature_range_invalid",
                        "details": {
                            "rule": "min<=max",
                            "min": temp_min,
                            "max": temp_max,
                        },
                    }
                )

    if temp_op is not None and temp_min is not None and temp_op < temp_min:
        if temp_op_key in candidate_fields:
            rejects.append(
                {
                    "field": temp_op_key,
                    "reason": "temperature_range_invalid",
                    "details": {
                        "rule": "min<=op",
                        "min": temp_min,
                        "op": temp_op,
                    },
                }
            )
        elif temp_min_key in candidate_fields:
            rejects.append(
                {
                    "field": temp_min_key,
                    "reason": "temperature_range_invalid",
                    "details": {
                        "rule": "min<=op",
                        "min": temp_min,
                        "op": temp_op,
                    },
                }
            )

    if temp_op is not None and temp_max is not None and temp_op > temp_max:
        if temp_op_key in candidate_fields:
            rejects.append(
                {
                    "field": temp_op_key,
                    "reason": "temperature_range_invalid",
                    "details": {
                        "rule": "op<=max",
                        "op": temp_op,
                        "max": temp_max,
                    },
                }
            )
        elif temp_max_key in candidate_fields:
            rejects.append(
                {
                    "field": temp_max_key,
                    "reason": "temperature_range_invalid",
                    "details": {
                        "rule": "op<=max",
                        "op": temp_op,
                        "max": temp_max,
                    },
                }
            )

    return rejects


def apply_parameter_patch_lww(
    existing: Any,
    patch: Mapping[str, Any],
    provenance: Mapping[str, str] | None,
    *,
    source: str,
    allow_user_override: bool = False,
    parameter_versions: Mapping[str, int] | None = None,
    parameter_updated_at: Mapping[str, float] | None = None,
    base_versions: Mapping[str, int] | None = None,
    now: Callable[[], float] | None = None,
) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, int], Dict[str, float], list[str], list[Dict[str, Any]]]:
    """
    Apply a parameter patch with per-field LWW version checks.

    - If base_versions is provided and base_v < current_v, the field is rejected as stale.
    - Applied fields increment version and get updated_at set to server time.
    """
    merged = merge_parameters(existing, {})
    updated_provenance: MutableMapping[str, str] = dict(provenance or {})
    merged_versions: Dict[str, int] = dict(parameter_versions or {})
    merged_updated_at: Dict[str, float] = dict(parameter_updated_at or {})
    applied_fields: list[str] = []
    rejected_fields: list[Dict[str, Any]] = []
    now_fn = now or time.time

    candidate_patch: Dict[str, Any] = {}

    for key, value in dict(patch or {}).items():
        current_v = int(merged_versions.get(key, 0))
        if base_versions is not None:
            base_v = int(base_versions.get(key, current_v))
            if base_v < current_v:
                rejected_fields.append({"field": key, "reason": "stale"})
                continue

        existing_source = updated_provenance.get(key)
        if existing_source == "user" and source != "user" and not allow_user_override:
            continue

        candidate_patch[key] = value

    if candidate_patch:
        proposed = merge_parameters(merged, candidate_patch)
        rejects = _validate_cross_field(proposed, set(candidate_patch.keys()))
        rejected_fields.extend(rejects)
        for reject in rejects:
            field = reject.get("field")
            if isinstance(field, str):
                candidate_patch.pop(field, None)

    for key, value in candidate_patch.items():
        current_v = int(merged_versions.get(key, 0))
        merged[key] = value
        updated_provenance[key] = source
        merged_versions[key] = current_v + 1
        merged_updated_at[key] = float(now_fn())
        applied_fields.append(key)

    return (
        merged,
        dict(updated_provenance),
        merged_versions,
        merged_updated_at,
        applied_fields,
        rejected_fields,
    )


__all__ = [
    "ALLOWED_V2_PARAMETER_KEYS",
    "ParametersPatchRequest",
    "sanitize_v2_parameter_patch",
    "merge_parameters",
    "apply_parameter_patch_with_provenance",
    "apply_parameter_patch_lww",
]
