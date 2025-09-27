from __future__ import annotations

import inspect
from typing import Any, Callable, Dict


def _supported_kwargs(method: Callable[..., Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Filter kwargs to the subset accepted by the callable.

    Falls back to the original kwargs when signature inspection fails or the
    callable accepts arbitrary keyword arguments.
    """
    try:
        sig = inspect.signature(method)
    except (TypeError, ValueError):
        return kwargs

    params = sig.parameters.values()
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params):
        return kwargs

    allowed: Dict[str, Any] = {}
    for name, value in kwargs.items():
        param = sig.parameters.get(name)
        if param is None:
            continue
        if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
            allowed[name] = value
    return allowed


def call_with_supported_kwargs(
    method: Callable[..., Any], /, *args: Any, **kwargs: Any
) -> Any:
    """Invoke ``method`` with ``args`` and the subset of ``kwargs`` it supports."""
    if method is None:  # pragma: no cover - defensive guard
        raise AttributeError("Callable is None")
    filtered = _supported_kwargs(method, kwargs)
    return method(*args, **filtered)


__all__ = ["call_with_supported_kwargs"]
