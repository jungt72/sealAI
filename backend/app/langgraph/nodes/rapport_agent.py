from __future__ import annotations

from typing import Any, Dict

from app.langgraph.state import SealAIState


def _resolve_llm(_config: Dict[str, Any]):
    raise RuntimeError("rapport llm not configured")


def rapport_agent_node(state: SealAIState, *, config: Dict[str, Any]) -> Dict[str, Any]:
    llm = _resolve_llm(config)
    response = llm.invoke(state.get("messages") or [])
    content = getattr(response, "content", None)
    summary = str(content or "").strip()

    slots = dict(state.get("slots") or {})
    slots["rapport_phase_done"] = True
    slots["rapport_summary"] = summary

    return {
        "slots": slots,
        "message_out": summary,
        "phase": "rapport",
    }


__all__ = ["rapport_agent_node", "_resolve_llm"]
