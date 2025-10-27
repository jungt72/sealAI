from __future__ import annotations

"""Simplified StateGraph implementation for local testing."""

import asyncio
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from functools import partial
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Tuple, Type

from .constants import END

try:  # Pydantic v2
    from pydantic import BaseModel  # type: ignore

    _PYDANTIC_BASE = BaseModel
except Exception:  # pragma: no cover
    _PYDANTIC_BASE = None  # type: ignore

StateCallable = Callable[[Dict[str, Any]], Dict[str, Any]]


class CheckpointerProtocol(Protocol):
    """Minimal protocol that LangGraph checkpointers are expected to satisfy."""

    def put(self, key: str, value: Dict[str, Any]) -> None:
        ...

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        ...


def _serialise_payload(value: Any) -> Any:
    """Convert nested state objects into JSON-serialisable structures."""

    if value is None:
        return None
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _serialise_payload(value.model_dump())
    if is_dataclass(value):
        return _serialise_payload(asdict(value))
    if isinstance(value, dict):
        return {key: _serialise_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialise_payload(item) for item in value]
    return value


def _derive_checkpoint_id(state: Dict[str, Any], config: Dict[str, Any]) -> Optional[str]:
    """Pick a checkpoint identifier from config or fall back to state meta."""

    explicit = config.get("checkpoint_id")
    if explicit:
        return str(explicit)
    meta = state.get("meta") if isinstance(state, dict) else None
    if isinstance(meta, dict):
        trace_id = meta.get("trace_id")
        if trace_id:
            return str(trace_id)
    return None


def _merge_resume_state(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow merge overlay data into the persisted base state for resume flows."""

    if not overlay:
        return base

    merged: Dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if value is None:
            continue
        if key == "slots" and isinstance(value, dict):
            existing = dict(merged.get("slots", {}))
            existing.update(value)
            merged["slots"] = existing
        elif key == "messages" and isinstance(value, list):
            existing_messages = list(merged.get("messages", []))
            existing_messages.extend(value)
            merged["messages"] = existing_messages
        elif key == "context_refs" and isinstance(value, list):
            existing_refs = list(merged.get("context_refs", []))
            existing_refs.extend(value)
            merged["context_refs"] = existing_refs
        else:
            merged[key] = value
    return merged


def add_messages(existing: Iterable[Any] | None, new_messages: Iterable[Any] | None) -> List[Any]:
    messages: List[Any] = list(existing or [])
    if new_messages:
        messages.extend(list(new_messages))
    return messages


def _coerce_to_payload(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return value.model_dump()
    if hasattr(value, "dict") and callable(value.dict):
        return value.dict()
    if isinstance(value, dict):
        return dict(value)
    raise TypeError(f"Unsupported state payload type: {type(value)!r}")


def _normalise_patch(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return value.model_dump()
    if hasattr(value, "dict") and callable(value.dict):
        return value.dict()
    if isinstance(value, dict):
        return dict(value)
    raise TypeError(f"Unsupported node return type: {type(value)!r}")


def _make_state_builder(example: Any) -> Callable[[Dict[str, Any]], Any]:
    if example is None:
        return lambda payload: payload

    example_type: Type[Any] | None = type(example)

    if _PYDANTIC_BASE and isinstance(example, _PYDANTIC_BASE):  # type: ignore[arg-type]
        cls: Any = example_type
        if hasattr(cls, "model_validate"):
            return lambda payload: cls.model_validate(payload)
        if hasattr(cls, "parse_obj"):
            return lambda payload: cls.parse_obj(payload)
    if hasattr(example, "__class__") and hasattr(example.__class__, "model_validate"):
        cls = example.__class__
        return lambda payload: cls.model_validate(payload)
    if callable(getattr(example_type, "parse_obj", None)):
        return lambda payload: example_type.parse_obj(payload)
    return lambda payload: dict(payload)


def _apply_patch(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    if not patch:
        return base

    merged: Dict[str, Any] = dict(base)
    for key, value in patch.items():
        if value is None:
            continue
        if key == "slots" and isinstance(value, dict):
            existing = dict(merged.get("slots", {}))
            existing.update(value)
            merged["slots"] = existing
        elif key == "messages" and isinstance(value, list):
            merged["messages"] = list(value)
        elif key == "context_refs" and isinstance(value, list):
            merged["context_refs"] = list(value)
        elif key == "routing":
            if isinstance(value, dict):
                existing_routing = dict(merged.get("routing", {}))
                existing_routing.update(value)
                merged["routing"] = existing_routing
            else:
                merged["routing"] = value
        elif key == "meta":
            if isinstance(value, dict):
                existing_meta = dict(merged.get("meta", {}))
                existing_meta.update(value)
                merged["meta"] = existing_meta
            else:
                merged["meta"] = value
        else:
            merged[key] = value
    return merged


class CompiledGraph:
    def __init__(
        self,
        entry_point: str,
        nodes: Dict[str, Any],
        edges: Dict[str, List[str]],
        conditional: Dict[str, List[tuple[Callable[[Dict[str, Any]], str], Dict[str, str]]]],
        checkpointer: CheckpointerProtocol | None = None,
    ) -> None:
        self._entry_point = entry_point
        self._nodes = nodes
        self._edges = edges
        self._conditional = conditional
        self._checkpointer = checkpointer  # MIGRATION: Phase 1 - retain optional checkpointer

    def _next_node(self, current: str, state: Dict[str, Any]) -> Optional[str]:
        for condition_fn, mapping in self._conditional.get(current, []):
            key = condition_fn(state)
            if key in mapping:
                return mapping[key]
        targets = self._edges.get(current) or []
        return targets[0] if targets else END

    def _call_node(self, node: Any, state: Dict[str, Any]) -> Dict[str, Any]:
        if hasattr(node, "invoke"):
            return node.invoke(state)
        if callable(node):
            return node(state)
        raise TypeError(f"Unsupported node type: {type(node)!r}")

    def _prepare_state(self, state: Any) -> Tuple[Dict[str, Any], Callable[[Dict[str, Any]], Any]]:
        state_payload = _coerce_to_payload(state)
        builder = _make_state_builder(state)
        return state_payload, builder

    def _run(
        self,
        state: Any,
        *,
        config: Optional[Dict[str, Any]] = None,
        emit: Optional[Callable[[str, Any], None]] = None,
    ) -> Any:
        config = config or {}
        current = self._entry_point
        state_payload, builder = self._prepare_state(state)
        state_obj = builder(state_payload)
        checkpoint_key: Optional[str] = None

        if self._checkpointer:
            checkpoint_key = _derive_checkpoint_id(state, config)
            if checkpoint_key and config.get("resume"):
                stored = self._checkpointer.get(checkpoint_key)
                if stored:
                    stored_state = stored.get("state", state) or state
                    state_payload = _merge_resume_state(stored_state, state_payload)
                    current = stored.get("current", current) or current
                    state_obj = builder(state_payload)

        iterations = 0
        while current and current != END:
            if current not in self._nodes:
                raise KeyError(f"Unknown node '{current}'")
            node = self._nodes[current]
            try:
                patch = self._call_node(node, state_obj)
            except Exception:
                if checkpoint_key and self._checkpointer:
                    self._checkpointer.put(
                        checkpoint_key,
                        {"state": _serialise_payload(state_payload), "current": current, "error": True},
                    )
                raise
            patch_payload = _normalise_patch(patch)
            state_payload = _apply_patch(state_payload, patch_payload)
            state_obj = builder(state_payload)

            if emit:
                emit(current, state_obj)

            next_node = self._next_node(current, state_payload)
            if checkpoint_key and self._checkpointer:
                payload = {
                    "state": _serialise_payload(state_payload),
                    "current": next_node,
                }
                self._checkpointer.put(checkpoint_key, payload)
            current = next_node
            iterations += 1
            if iterations > 10_000:
                raise RuntimeError("Graph execution exceeded iteration limit")

        if emit:
            emit(END, builder(state_payload))

        if checkpoint_key and self._checkpointer:
            self._checkpointer.put(
                checkpoint_key,
                {"state": _serialise_payload(state_payload), "current": END, "completed": True},
            )

        return builder(state_payload)

    def invoke(self, state: Any, *, config: Optional[Dict[str, Any]] = None, **_: Any) -> Any:
        return self._run(state, config=config)

    async def ainvoke(self, state: Dict[str, Any], *, config: Optional[Dict[str, Any]] = None, **_: Any) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        runner = partial(self.invoke, state, config=config)
        return await loop.run_in_executor(None, runner)

    async def astream(self, state: Any, *, config: Optional[Dict[str, Any]] = None, **_: Any):
        loop = asyncio.get_running_loop()
        events: List[Tuple[str, Any]] = []

        def _emit(node: str, node_state: Any) -> None:
            events.append((node, node_state))

        def _runner() -> None:
            self._run(state, config=config, emit=_emit)

        await loop.run_in_executor(None, _runner)
        for node, node_state in events:
            yield {node: node_state}


class StateGraph:
    def __init__(self, _state_type: Any) -> None:
        self._nodes: Dict[str, Any] = {}
        self._edges: Dict[str, List[str]] = defaultdict(list)
        self._conditional: Dict[
            str, List[tuple[Callable[[Dict[str, Any]], str], Dict[str, str]]]
        ] = defaultdict(list)
        self._entry_point: Optional[str] = None

    def add_node(self, name: str, node: Any) -> None:
        self._nodes[name] = node

    def set_entry_point(self, name: str) -> None:
        self._entry_point = name

    def add_edge(self, source: str, target: str) -> None:
        self._edges[source].append(target)

    def add_conditional_edges(
        self,
        source: str,
        condition_fn: Callable[[Dict[str, Any]], str],
        mapping: Dict[str, str],
    ) -> None:
        self._conditional[source].append((condition_fn, mapping))

    def compile(self, checkpointer: Any = None) -> CompiledGraph:  # noqa: D401
        if not self._entry_point:
            raise ValueError("Entry point not set")
        return CompiledGraph(self._entry_point, self._nodes, self._edges, self._conditional, checkpointer)


__all__ = ["StateGraph", "add_messages", "CompiledGraph"]
