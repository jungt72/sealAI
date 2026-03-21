from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, Mapping, MutableMapping, Tuple

from pydantic import BaseModel, Field

from app.services.rag.state import WorkingProfile
from app._legacy_v2.state.governance_types import IdentityClass


def _build_allowed_keys() -> set[str]:
    keys: set[str] = set()
    for name, field in WorkingProfile.model_fields.items():
        keys.add(name)
        alias = getattr(field, "alias", None)
        if isinstance(alias, str) and alias:
            keys.add(alias)
    return keys


ALLOWED_V2_PARAMETER_KEYS = _build_allowed_keys()
IDENTITY_CLASS_VALUES = (
    IdentityClass.CONFIRMED.value,
    IdentityClass.PROBABLE.value,
    IdentityClass.FAMILY_ONLY.value,
    IdentityClass.UNRESOLVED.value,
)
_GENERIC_IDENTITY_VALUES = {
    "material",
    "werkstoff",
    "produkt",
    "product",
    "compound",
    "family",
    "familie",
    "medium",
    "fluid",
}
_MATERIAL_FAMILY_CODES = {
    "PTFE",
    "TFM",
    "FKM",
    "FFKM",
    "NBR",
    "HNBR",
    "EPDM",
    "VMQ",
    "MVQ",
    "PU",
    "PUR",
    "PEEK",
    "POM",
    "PA",
    "UHMWPE",
    "ETFE",
    "PCTFE",
}
_MEDIUM_EXACT_ALIASES = {
    "water": "water",
    "wasser": "water",
    "steam": "steam",
    "dampf": "steam",
    "oil": "oil",
    "öl": "oil",
    "oel": "oil",
    "hydraulikoel": "oil",
    "hydrauliköl": "oil",
    "gas": "gas",
    "air": "air",
    "luft": "air",
    "oxygen": "oxygen",
    "sauerstoff": "oxygen",
    "hydrogen": "hydrogen",
    "wasserstoff": "hydrogen",
    "h2": "hydrogen",
    "chemical": "chemical",
    "chemikalie": "chemical",
}
_MEDIUM_FAMILY_MARKERS = {
    "water": ("water", "wasser"),
    "steam": ("steam", "dampf"),
    "oil": ("oil", "öl", "oel", "hydraulik"),
    "gas": ("gas",),
    "air": ("air", "luft"),
    "oxygen": ("oxygen", "sauerstoff"),
    "hydrogen": ("hydrogen", "wasserstoff", "h2"),
    "chemical": ("chemical", "chem", "chemikal"),
}
_NORM_PATTERN = re.compile(r"^(?:DIN|EN|ISO|ASTM|ASME|API|ANSI)\b[\w .:/+-]*$", re.IGNORECASE)
_IDENTITY_GUARDED_FIELDS = frozenset(
    {
        "medium",
        "material",
        "seal_material",
        "trade_name",
        "product",
        "product_name",
        "seal_family",
        "flange_standard",
    }
)


class ParametersPatchRequest(BaseModel):
    # Keep a default so we can return an explicit 400 "missing_chat_id" instead of a 422.
    chat_id: str = Field(default="", description="Conversation/thread id")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    base_versions: Dict[str, int] | None = None


def _is_primitive(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _normalize_identity_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _build_identity_record(key: str, value: Any, *, source: str) -> Dict[str, Any]:
    raw_text = _normalize_identity_text(value)
    lowered = raw_text.lower()
    normalized_value: Any = raw_text
    identity_class = IdentityClass.UNRESOLVED.value
    notes: list[str] = []

    if key == "medium":
        if lowered in _MEDIUM_EXACT_ALIASES:
            normalized_value = _MEDIUM_EXACT_ALIASES[lowered]
            identity_class = IdentityClass.CONFIRMED.value
            notes.append("canonical_medium_match")
        else:
            for canonical, markers in _MEDIUM_FAMILY_MARKERS.items():
                if any(marker in lowered for marker in markers):
                    normalized_value = canonical
                    identity_class = IdentityClass.FAMILY_ONLY.value
                    notes.append("medium_family_match_only")
                    break
            if not raw_text:
                notes.append("empty_medium")
            elif identity_class == IdentityClass.UNRESOLVED.value:
                notes.append("medium_not_in_canonical_set")
    elif key in {"material", "seal_material", "seal_family"}:
        if not raw_text or lowered in _GENERIC_IDENTITY_VALUES:
            notes.append("generic_material_identity")
        elif raw_text.upper() in _MATERIAL_FAMILY_CODES:
            normalized_value = raw_text.upper()
            identity_class = IdentityClass.FAMILY_ONLY.value
            notes.append("material_family_only")
        elif any(code in raw_text.upper() for code in _MATERIAL_FAMILY_CODES):
            identity_class = IdentityClass.FAMILY_ONLY.value
            notes.append("material_family_embedded")
        else:
            identity_class = IdentityClass.PROBABLE.value
            notes.append("material_identity_needs_lookup_confirmation")
    elif key in {"trade_name", "product", "product_name"}:
        if not raw_text or lowered in _GENERIC_IDENTITY_VALUES:
            notes.append("generic_product_identity")
        else:
            identity_class = IdentityClass.PROBABLE.value
            notes.append("product_identity_needs_lookup_confirmation")
    elif key == "flange_standard":
        if raw_text and _NORM_PATTERN.match(raw_text):
            normalized_value = raw_text.upper()
            identity_class = IdentityClass.CONFIRMED.value
            notes.append("norm_pattern_match")
        elif raw_text:
            identity_class = IdentityClass.PROBABLE.value
            notes.append("norm_identity_needs_confirmation")
        else:
            notes.append("empty_norm_identity")
    else:
        identity_class = IdentityClass.CONFIRMED.value
        notes.append("non_identity_guarded_parameter")

    lookup_allowed = identity_class == IdentityClass.CONFIRMED.value
    promotion_allowed = identity_class == IdentityClass.CONFIRMED.value
    return {
        "raw_value": value,
        "normalized_value": normalized_value,
        "identity_class": identity_class,
        "normalization_notes": notes,
        "normalization_source": source,
        "lookup_allowed": lookup_allowed,
        "promotion_allowed": promotion_allowed,
    }


def stage_parameter_identity_metadata(
    existing_identity: Mapping[str, Any] | None,
    patch: Mapping[str, Any],
    *,
    source: str,
    applied_fields: list[str] | None = None,
) -> Dict[str, Any]:
    updated_identity: Dict[str, Any] = dict(existing_identity or {})
    target_fields = applied_fields if applied_fields is not None else list(dict(patch or {}).keys())
    for key in target_fields:
        if key not in patch:
            continue
        updated_identity[key] = _build_identity_record(key, patch.get(key), source=source)
    return updated_identity


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
        sanitized[key] = value
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


def _build_observed_inputs(
    patch: Mapping[str, Any],
    applied_fields: list[str],
    identity: Dict[str, Any],
    *,
    source: str,
    existing_observed: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Capture raw user/LLM values before any normalization or promotion.

    Each entry records the original value as received, the extraction source,
    and the identity classification assigned at staging time.  Values are
    append-only: an earlier observation is never overwritten by a later one
    for the same field.
    """
    observed: Dict[str, Any] = dict(existing_observed or {})
    for key in applied_fields:
        if key in observed:
            continue
        raw_value = patch.get(key)
        if raw_value is None:
            continue
        identity_record = identity.get(key)
        identity_class_raw = "identity_unresolved"
        if isinstance(identity_record, dict):
            identity_class_raw = str(identity_record.get("identity_class") or "identity_unresolved")
        elif hasattr(identity_record, "identity_class"):
            identity_class_raw = str(getattr(identity_record, "identity_class", "identity_unresolved"))
        
        identity_class = IdentityClass.normalize(identity_class_raw).value
        observed[key] = {
            "raw": raw_value,
            "source": source,
            "identity_class_at_capture": identity_class,
        }
    return observed


def stage_extracted_parameter_patch(
    existing: Any,
    patch: Mapping[str, Any],
    provenance: Mapping[str, str] | None,
    identity: Mapping[str, Any] | None = None,
    *,
    source: str,
    allow_user_override: bool = False,
    existing_observed_inputs: Mapping[str, Any] | None = None,
) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, Any], list[str], Dict[str, Any]]:
    """Stage extracted parameters without promoting them into asserted state.

    Returns a 5-tuple: (merged_params, provenance, identity, applied_fields,
    observed_inputs).  The ``observed_inputs`` dict captures the raw value as
    received before any normalization — append-only, never overwritten.
    """
    merged_before = merge_parameters(existing, {})
    merged, updated_provenance = apply_parameter_patch_with_provenance(
        existing,
        patch,
        provenance,
        source=source,
        allow_user_override=allow_user_override,
    )
    applied_fields = [key for key in dict(patch or {}) if merged_before.get(key) != merged.get(key)]
    updated_identity = stage_parameter_identity_metadata(
        identity,
        patch,
        source=source,
        applied_fields=applied_fields,
    )
    observed = _build_observed_inputs(
        patch,
        applied_fields,
        updated_identity,
        source=source,
        existing_observed=existing_observed_inputs,
    )
    return merged, updated_provenance, updated_identity, applied_fields, observed


def build_normalized_parameter_patch(
    patch: Mapping[str, Any],
    identity: Mapping[str, Any] | None,
    *,
    applied_fields: list[str] | None = None,
) -> Dict[str, Any]:
    """Build the explicit normalized layer from raw/staged patch data.

    Identity-guarded fields use their deterministic ``normalized_value`` when
    present. Non-identity-guarded fields keep the sanitized input value.
    """
    normalized: Dict[str, Any] = {}
    target_fields = applied_fields if applied_fields is not None else list(dict(patch or {}).keys())
    for key in target_fields:
        if key not in patch:
            continue
        value = patch.get(key)
        normalized_value = value
        if key in _IDENTITY_GUARDED_FIELDS:
            meta = dict((identity or {}).get(key) or {})
            normalized_value = meta.get("normalized_value", value)
        normalized[key] = normalized_value
    return normalized


def build_asserted_parameter_patch_from_normalized(
    normalized_patch: Mapping[str, Any],
    identity: Mapping[str, Any] | None,
    *,
    applied_fields: list[str] | None = None,
) -> Dict[str, Any]:
    """Promote only deterministic/allowed normalized values into asserted state."""
    asserted: Dict[str, Any] = {}
    target_fields = applied_fields if applied_fields is not None else list(dict(normalized_patch or {}).keys())
    for key in target_fields:
        if key not in normalized_patch:
            continue
        if key in _IDENTITY_GUARDED_FIELDS:
            meta = dict((identity or {}).get(key) or {})
            identity_class = str(meta.get("identity_class") or "")
            if identity_class and IdentityClass.normalize(identity_class) != IdentityClass.CONFIRMED:
                continue
        asserted[key] = normalized_patch.get(key)
    return asserted


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


def promote_parameter_patch_to_asserted(
    existing_asserted: Any,
    patch: Mapping[str, Any],
    asserted_provenance: Mapping[str, str] | None,
    *,
    source: str,
    existing_extracted: Any = None,
    extracted_provenance: Mapping[str, str] | None = None,
    allow_user_override: bool = False,
    parameter_versions: Mapping[str, int] | None = None,
    parameter_updated_at: Mapping[str, float] | None = None,
    base_versions: Mapping[str, int] | None = None,
    now: Callable[[], float] | None = None,
) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, int], Dict[str, float], Dict[str, Any], Dict[str, str], list[str], list[Dict[str, Any]]]:
    """Deprecated direct path: raw patches must pass through the normalized layer."""
    raise ValueError(
        "Direct raw patch promotion into asserted state is disabled; "
        "use apply_parameter_patch_to_state_layers()."
    )


def apply_parameter_patch_to_state_layers(
    existing_asserted: Any,
    existing_normalized: Any,
    patch: Mapping[str, Any],
    asserted_provenance: Mapping[str, str] | None,
    normalized_provenance: Mapping[str, str] | None,
    identity: Mapping[str, Any] | None,
    observed_inputs: Mapping[str, Any] | None,
    *,
    source: str,
    allow_user_override: bool = False,
    parameter_versions: Mapping[str, int] | None = None,
    parameter_updated_at: Mapping[str, float] | None = None,
    base_versions: Mapping[str, int] | None = None,
    now: Callable[[], float] | None = None,
) -> Tuple[
    Dict[str, Any],
    Dict[str, str],
    Dict[str, int],
    Dict[str, float],
    Dict[str, Any],
    Dict[str, str],
    Dict[str, Any],
    Dict[str, Any],
    list[str],
    list[str],
    list[Dict[str, Any]],
]:
    """Apply a raw user patch via observed -> normalized -> asserted layers."""
    patch_fields = list(dict(patch or {}).keys())
    (
        merged_normalized,
        merged_normalized_provenance,
        merged_identity,
        _staged_fields,
        merged_observed_inputs,
    ) = stage_extracted_parameter_patch(
        existing_normalized,
        patch,
        normalized_provenance,
        identity,
        source=source,
        allow_user_override=allow_user_override,
        existing_observed_inputs=observed_inputs,
    )

    normalized_patch = build_normalized_parameter_patch(
        patch,
        merged_identity,
        applied_fields=patch_fields,
    )
    normalized_state = merge_parameters(existing_normalized, normalized_patch)
    accepted_stage_fields = list(patch_fields)
    existing_asserted_state = merge_parameters(existing_asserted, {})
    assertion_candidate_fields = [
        key for key in accepted_stage_fields if existing_asserted_state.get(key) != normalized_patch.get(key)
    ]
    asserted_patch = build_asserted_parameter_patch_from_normalized(
        normalized_patch,
        merged_identity,
        applied_fields=assertion_candidate_fields,
    )
    (
        merged_asserted,
        merged_asserted_provenance,
        merged_versions,
        merged_updated_at,
        asserted_fields,
        rejected_fields,
    ) = apply_parameter_patch_lww(
        existing_asserted,
        asserted_patch,
        asserted_provenance,
        source=source,
        allow_user_override=allow_user_override,
        parameter_versions=parameter_versions,
        parameter_updated_at=parameter_updated_at,
        base_versions=base_versions,
        now=now,
    )

    return (
        merged_asserted,
        merged_asserted_provenance,
        merged_versions,
        merged_updated_at,
        normalized_state,
        merged_normalized_provenance,
        merged_identity,
        merged_observed_inputs,
        accepted_stage_fields,
        asserted_fields,
        rejected_fields,
    )


__all__ = [
    "ALLOWED_V2_PARAMETER_KEYS",
    "IDENTITY_CLASS_VALUES",
    "ParametersPatchRequest",
    "sanitize_v2_parameter_patch",
    "merge_parameters",
    "apply_parameter_patch_with_provenance",
    "stage_extracted_parameter_patch",
    "build_normalized_parameter_patch",
    "build_asserted_parameter_patch_from_normalized",
    "_build_observed_inputs",
    "stage_parameter_identity_metadata",
    "apply_parameter_patch_lww",
    "apply_parameter_patch_to_state_layers",
    "promote_parameter_patch_to_asserted",
]
