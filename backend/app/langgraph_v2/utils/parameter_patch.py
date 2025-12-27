from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping

from pydantic import BaseModel, Field

from app.langgraph_v2.state import TechnicalParameters


def _build_allowed_keys() -> set[str]:
    keys: set[str] = set()
    for name, field in TechnicalParameters.model_fields.items():
        keys.add(name)
        alias = getattr(field, "alias", None)
        if isinstance(alias, str) and alias:
            keys.add(alias)
    return keys


ALLOWED_V2_PARAMETER_KEYS = _build_allowed_keys()


class ParametersPatchRequest(BaseModel):
    # Keep a default so we can return an explicit 400 "missing_chat_id" instead of a 422.
    chat_id: str = Field(default="", description="Conversation/thread id")
    parameters: Dict[str, Any] = Field(default_factory=dict)


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


__all__ = [
    "ALLOWED_V2_PARAMETER_KEYS",
    "ParametersPatchRequest",
    "sanitize_v2_parameter_patch",
    "merge_parameters",
]
