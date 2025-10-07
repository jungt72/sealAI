"""Base helpers for validated LangGraph nodes."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel

Validator = Callable[[Dict[str, Any]], BaseModel]


def _model_to_dict(model: BaseModel) -> Dict[str, Any]:
    exporter = getattr(model, "model_dump", None)
    if callable(exporter):  # pydantic v2
        return exporter()
    return model.dict()  # type: ignore[return-value]


class IOValidatedNode:
    """Mixin that enforces validated input/output contracts for LangGraph nodes."""

    _in_validator: Optional[Validator] = None
    _out_validator: Optional[Validator] = None

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(payload or {})

        if self._in_validator is not None:
            validated_in = self._in_validator(data)
            data = _model_to_dict(validated_in)

        result = self._run(data)
        if not isinstance(result, dict):
            raise TypeError(f"{self.__class__.__name__}._run must return dict, got {type(result)!r}")

        if self._out_validator is not None:
            validated_out = self._out_validator(result)
            return _model_to_dict(validated_out)

        return result

    def _run(self, payload: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover - abstract
        raise NotImplementedError


__all__ = ["IOValidatedNode", "Validator"]
