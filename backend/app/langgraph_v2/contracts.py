from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping, Set

from fastapi import HTTPException

logger = logging.getLogger(__name__)


STABLE_V2_NODE_CONTRACT: frozenset[str] = frozenset(
    {
        # Nodes referenced outside the graph (API / state updates).
        "supervisor_policy_node",
        "confirm_recommendation_node",
        "confirm_checkpoint_node",
    }
)


def error_detail(code: str, *, request_id: str | None = None, message: str | None = None, **extra: Any) -> dict:
    detail: dict[str, Any] = {"code": code}
    if request_id:
        detail["request_id"] = request_id
    if message:
        detail["message"] = message
    if extra:
        detail.update(extra)
    return detail


def get_compiled_graph_node_names(graph: Any) -> Set[str]:
    """
    Best-effort extraction of node names from a LangGraph compiled graph.

    Observed in this repo:
      - `graph.get_graph().nodes` is a dict mapping node_name -> node_callable/metadata.
    """
    get_graph = getattr(graph, "get_graph", None)
    if callable(get_graph):
        try:
            g = get_graph()
            nodes = getattr(g, "nodes", None)
            if isinstance(nodes, Mapping):
                return set(nodes.keys())
            if nodes is not None:
                try:
                    return set(nodes)  # networkx-like NodeView
                except TypeError:
                    pass
        except Exception:
            logger.debug("langgraph_v2_get_nodes_failed", exc_info=True)
            return set()
    return set()


def assert_node_exists(
    graph: Any,
    node_name: str,
    *,
    request_id: str | None = None,
    status_code: int = 400,
    code: str = "invalid_as_node",
) -> None:
    nodes = get_compiled_graph_node_names(graph)
    if node_name in nodes:
        return
    raise HTTPException(
        status_code=status_code,
        detail=error_detail(
            code,
            request_id=request_id,
            as_node=node_name,
            known_nodes_count=len(nodes),
        ),
    )


def pick_existing_node(
    graph: Any,
    node_name: str | None,
    *,
    fallback: str,
) -> str:
    """
    Return `node_name` if it exists in the compiled graph; otherwise return `fallback`.
    """
    candidate = (node_name or "").strip()
    if not candidate:
        return fallback
    nodes = get_compiled_graph_node_names(graph)
    return candidate if candidate in nodes else fallback


def is_dependency_unavailable_error(exc: BaseException) -> bool:
    """
    Heuristic: map Redis/Qdrant connectivity/timeouts to 503.

    We avoid importing optional deps unconditionally; we only check types if available.
    """
    try:
        import redis.exceptions  # type: ignore

        if isinstance(
            exc,
            (
                redis.exceptions.ConnectionError,
                redis.exceptions.TimeoutError,
            ),
        ):
            return True
    except Exception:
        pass

    # Common stdlib / http clients
    if isinstance(exc, TimeoutError):
        return True

    mod = (type(exc).__module__ or "").lower()
    name = (type(exc).__name__ or "").lower()
    if "httpx" in mod and name in {"connecterror", "readtimeout", "connecttimeout", "remotepotentialerror"}:
        return True
    if "qdrant" in mod and "timeout" in name:
        return True

    return False


__all__ = [
    "STABLE_V2_NODE_CONTRACT",
    "assert_node_exists",
    "error_detail",
    "get_compiled_graph_node_names",
    "is_dependency_unavailable_error",
    "pick_existing_node",
]
