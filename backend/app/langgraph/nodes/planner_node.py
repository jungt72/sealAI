from __future__ import annotations

import json
from typing import Any, Dict

from langchain_core.messages import SystemMessage

from app.langgraph.state import SealAIState


def _planner_graph():
    raise RuntimeError("planner graph not configured")


def planner_node(state: SealAIState) -> Dict[str, Any]:
    graph = _planner_graph()
    messages = list(state.get("messages") or [])
    messages.append(SystemMessage(content="Dr. Planner: Erstelle einen Plan basierend auf den Eingaben."))
    payload = {"messages": messages, "state": state}
    result = graph.invoke(payload)

    planner_plan = ""
    if isinstance(result, dict):
        output_messages = result.get("messages") or []
        if output_messages:
            last = output_messages[-1]
            planner_plan = getattr(last, "content", "") or ""
    plan_struct = {}
    if planner_plan:
        try:
            plan_struct = json.loads(planner_plan)
        except Exception:
            plan_struct = {}

    slots = dict(state.get("slots") or {})
    if planner_plan:
        slots["planner_plan"] = planner_plan
    if plan_struct:
        slots["planner_plan_struct"] = plan_struct
    agents = plan_struct.get("empfohlene_agents") if isinstance(plan_struct, dict) else None
    if agents:
        slots["recommended_agents"] = agents

    return {"slots": slots}


__all__ = ["planner_node", "_planner_graph"]
