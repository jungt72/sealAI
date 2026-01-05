"""Simplified ToolNode implementation to execute Python callables."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Iterable, List, Sequence, Tuple

try:  # Optional dependency
    from pydantic import BaseModel  # type: ignore

    _PYDANTIC_BASE = BaseModel
except Exception:  # pragma: no cover
    _PYDANTIC_BASE = None  # type: ignore

from .graph import _serialise_payload


def _coerce_state_dict(state: Any) -> Dict[str, Any]:
    if state is None:
        return {}
    if hasattr(state, "model_dump") and callable(state.model_dump):
        return state.model_dump()
    if hasattr(state, "dict") and callable(state.dict):
        return state.dict()
    if isinstance(state, dict):
        return dict(state)
    raise TypeError(f"Unsupported state object for ToolNode: {type(state)!r}")


class _ToolSpec:
    """Wrap a tool callable so it can be executed uniformly."""

    def __init__(self, tool: Any) -> None:
        if hasattr(tool, "invoke") and callable(tool.invoke):
            self._callable: Callable[..., Any] = tool.invoke  # type: ignore[assignment]
            self.name = getattr(tool, "name", tool.__class__.__name__)
        elif callable(tool):
            self._callable = tool  # type: ignore[assignment]
            self.name = getattr(tool, "__name__", tool.__class__.__name__)
        else:
            raise TypeError(f"ToolNode received unsupported tool: {tool!r}")

    def invoke(self, state_payload: Dict[str, Any]) -> Any:
        return _execute_tool(self._callable, state_payload)


def _execute_tool(func: Callable[..., Any], state_payload: Dict[str, Any]) -> Any:
    slots = dict(state_payload.get("slots", {}))
    try:
        return func(**slots)
    except TypeError:
        pass

    signature = inspect.signature(func)
    params: Sequence[inspect.Parameter] = tuple(signature.parameters.values())

    if len(params) == 1:
        param = params[0]
        annotation = param.annotation

        if _PYDANTIC_BASE and isinstance(annotation, type) and issubclass(annotation, _PYDANTIC_BASE):
            model = annotation(**slots)  # type: ignore[call-arg]
            return func(model)

        if annotation in (dict, inspect._empty):
            return func(slots)

        if param.name in slots:
            return func(slots[param.name])

    if hasattr(func, "__call__"):
        return func(state_payload)

    raise TypeError(f"Unable to determine how to call tool {func!r}")


class ToolNode:
    """Execute configured tools and append structured references to the state."""

    def __init__(self, tools: Iterable[Any]) -> None:
        self._tools: List[_ToolSpec] = [_ToolSpec(tool) for tool in tools]

    def __call__(self, state: Any) -> Dict[str, Any]:
        state_payload = _coerce_state_dict(state)
        existing_refs = list(state_payload.get("context_refs", []))
        tool_refs: List[Dict[str, Any]] = []
        tool_results: List[Dict[str, Any]] = []

        for spec in self._tools:
            try:
                result = spec.invoke(state_payload)
            except Exception as exc:
                tool_refs.append(
                    {"kind": "tool", "id": spec.name, "meta": {"status": "error", "error": str(exc)}}
                )
                tool_results.append({"tool": spec.name, "status": "error", "error": str(exc)})
                continue

            payload = _serialise_payload(result)
            tool_refs.append({"kind": "tool", "id": spec.name, "meta": {"status": "ok", "result": payload}})
            tool_results.append({"tool": spec.name, "status": "ok", "result": payload})

        slots = dict(state_payload.get("slots", {}))
        slots["tool_results"] = tool_results

        return {
            "context_refs": existing_refs + tool_refs,
            "slots": slots,
        }


__all__ = ["ToolNode"]

