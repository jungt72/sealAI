from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import SystemMessage

from app.langgraph.state import SealAIState


def _specialist_graph(_name: str):
    raise RuntimeError("specialist graph not configured")


def specialist_executor(state: SealAIState) -> Dict[str, Any]:
    slots = dict(state.get("slots") or {})
    agents = slots.get("recommended_agents") or ["material"]
    if not isinstance(agents, list) or not agents:
        agents = ["material"]
    agent_name = str(agents[0])
    graph = _specialist_graph(agent_name)

    messages = list(state.get("messages") or [])
    messages.append(SystemMessage(content="Material-Spezialist: Bitte prufe die Anforderungen."))
    payload = {"messages": messages, "state": state}
    result = graph.invoke(payload)

    summary = ""
    if isinstance(result, dict):
        output_messages = result.get("messages") or []
        if output_messages:
            last = output_messages[-1]
            summary = getattr(last, "content", "") or ""

    slots["specialist_summary"] = summary or "Spezialist: Ergebnis"
    slots["candidate_source"] = "specialists"
    if summary and not slots.get("candidate_answer"):
        slots["candidate_answer"] = summary

    return {"slots": slots}


__all__ = ["specialist_executor", "_specialist_graph"]
