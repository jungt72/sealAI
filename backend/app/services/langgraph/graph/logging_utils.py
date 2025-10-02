from __future__ import annotations

import logging
from collections.abc import Mapping
from functools import wraps
from typing import Any, Callable, Iterable

_LOG = logging.getLogger("uvicorn.error")

# Keys we care about for a compact snapshot of the state
_DEFAULT_STATE_KEYS: tuple[str, ...] = (
    "route",
    "phase",
    "domain",
    "intent",
    "query_type",
    "next_action",
)


def _format_scalar(value: Any) -> str:
    if value in (None, "", [], {}, ()):  # treat empty values uniformly
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{value}"
    text = str(value)
    text = text.strip()
    if len(text) > 48:
        return f"{text[:45]}…"
    return text or "-"


def _active_param_keys(params: Mapping[str, Any] | None) -> str | None:
    if not isinstance(params, Mapping):
        return None

    active_keys: list[str] = []
    for key, value in params.items():
        if value in (None, "", [], {}, ()):  # skip empty/falsey domain-specific defaults
            continue
        active_keys.append(str(key))
    if not active_keys:
        return None
    active_keys.sort()
    if len(active_keys) > 6:
        return ",".join(active_keys[:6]) + ",…"
    return ",".join(active_keys)


def summarize_state(state: Any, extra_keys: Iterable[str] | None = None) -> str:
    """Render a concise textual description of a LangGraph state for logging."""
    data: Mapping[str, Any] | None = None

    if isinstance(state, Mapping):
        data = state
    else:
        try:
            data = dict(state or {})  # type: ignore[arg-type]
        except Exception:
            data = None

    if data is None:
        return f"state={type(state).__name__}"

    parts: list[str] = []

    keys = list(_DEFAULT_STATE_KEYS)
    if extra_keys:
        keys.extend(extra_keys)

    seen = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        if key not in data:
            continue
        parts.append(f"{key}={_format_scalar(data.get(key))}")

    params_descr = _active_param_keys(data.get("params"))
    if params_descr:
        parts.append(f"params={params_descr}")

    messages = data.get("messages")
    if isinstance(messages, (list, tuple)):
        parts.append(f"messages={len(messages)}")

    retrieved = data.get("retrieved_docs") or data.get("docs")
    if isinstance(retrieved, (list, tuple)):
        parts.append(f"docs={len(retrieved)}")

    if not parts:
        return "state=empty"

    return "; ".join(parts)


def wrap_node_with_logging(
    graph_name: str,
    node_name: str,
    fn: Callable[..., Any],
    *,
    extra_keys: Iterable[str] | None = None,
) -> Callable[..., Any]:
    """Wrap a node callable so that entering/exiting the node is logged consistently."""

    @wraps(fn)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        state = args[0] if args else kwargs.get("state")
        snapshot = summarize_state(state, extra_keys=extra_keys)
        _LOG.info("[%s] ▶ node=%s %s", graph_name, node_name, snapshot)
        try:
            result = fn(*args, **kwargs)
        except Exception:
            _LOG.exception("[%s] ✖ node=%s %s", graph_name, node_name, snapshot)
            raise
        result_snapshot = summarize_state(result, extra_keys=extra_keys)
        _LOG.info("[%s] ◀ node=%s %s", graph_name, node_name, result_snapshot)
        return result

    return _wrapper


def log_branch_decision(
    graph_name: str,
    node_name: str,
    decision: str,
    branch: str,
    state: Any,
    *,
    extra_keys: Iterable[str] | None = None,
) -> None:
    """Emit a standardized log entry for conditional routing decisions."""
    snapshot = summarize_state(state, extra_keys=extra_keys)
    _LOG.info(
        "[%s] ➜ %s.%s -> %s %s",
        graph_name,
        node_name,
        decision,
        branch,
        snapshot,
    )

__all__ = ["summarize_state", "wrap_node_with_logging", "log_branch_decision"]
