from __future__ import annotations

from typing import Any

from langgraph.types import Command

from app.langgraph_v2.nodes.nodes_supervisor import supervisor_policy_node
from app.langgraph_v2.state import SealAIState


def orchestrator_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Command:
    """
    v3.1 compatibility orchestrator.

    The active orchestration logic lives in `supervisor_policy_node` and uses
    `Send("material_agent", ...)` for material-datasheet routes.
    """
    cmd = supervisor_policy_node(state, *_args, **_kwargs)
    if isinstance(getattr(cmd, "update", None), dict):
        cmd.update["last_node"] = "orchestrator_node"
    return cmd


__all__ = ["orchestrator_node"]
