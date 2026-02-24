"""Fan-in merge node for deterministic KB parallel branches."""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.langgraph_v2.state import SealAIState

log = logging.getLogger("app.langgraph_v2.nodes.merge_deterministic")


async def node_merge_deterministic(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Merge parallel factcard + compound outputs and set a deterministic checkpoint."""
    kb_result = state.kb_factcard_result or {}
    compound = state.compound_filter_results or {}
    log.info(
        "merge_deterministic.done",
        extra={
            "deterministic": bool(kb_result.get("deterministic")),
            "factcard_keys": list(kb_result.keys()),
            "compound_candidates": len(compound.get("candidates") or []),
            "run_id": state.run_id,
        },
    )
    return {"last_node": "node_merge_deterministic"}


__all__ = ["node_merge_deterministic"]

