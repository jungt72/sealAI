from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, List, Tuple

from langchain_core.messages import BaseMessage

from app.langgraph.prompts.prompt_loader import load_jinja_chat_prompt
from app.langgraph.nodes.members import create_domain_agent
from app.langgraph.state import SealAIState


@lru_cache(maxsize=1)
def _planner_graph():
    return create_domain_agent("planner")


PLANNER_PROMPT = load_jinja_chat_prompt("planner_node.de.j2")


def _extract_last_ai(messages: List[Any]) -> str:
    for msg in reversed(messages or []):
        try:
            if getattr(msg, "type", "") == "ai":
                content = getattr(msg, "content", None)
                if isinstance(content, str):
                    return content
                if isinstance(content, dict) and "content" in content:
                    return str(content["content"])
                return str(content)
        except Exception:
            continue
    return ""


def _flatten_history(messages: List[Any]) -> str:
    lines: List[str] = []
    for msg in messages or []:
        role = getattr(msg, "type", getattr(msg, "role", "msg"))
        content = getattr(msg, "content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _serialize_context(value: Any, *, empty_repr: str = "") -> str:
    if value in (None, "", [], {}):
        return empty_repr
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(value)


def _parse_plan_payload(text: str) -> Tuple[Dict[str, Any], List[str]]:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            agents = data.get("empfohlene_agents") or data.get("agents") or data.get("recommended_agents")
            normalized = [str(a).strip().lower() for a in agents or [] if isinstance(a, (str, bytes))]
            return data, normalized
    except Exception:
        return {}, []
    matches: List[str] = []
    lowered = text.lower()
    for token in ("material", "profil", "standards", "validierung"):
        if token in lowered:
            matches.append(token)
    return {}, matches


_SIMPLE_HINTS = ("schreibe", "liste", "format", "nur", "numbers", "zahlen")
_DOMAIN_HINTS = (
    "dichtung",
    "seal",
    "wellendichtung",
    "medium",
    "druck",
    "temperatur",
    "radial",
)


def _determine_mode(user_query: str, recommended: List[str], hint: str | None = None) -> str:
    if hint == "simple_direct_output":
        return "simple_direct_output"
    lowered = user_query.lower()
    if any(keyword in lowered for keyword in _DOMAIN_HINTS):
        return "expert_consulting"
    if any(agent in {"material", "profil", "standards"} for agent in recommended):
        return "expert_consulting"
    if any(hint in lowered for hint in _SIMPLE_HINTS):
        return "simple_direct_output"
    return "expert_consulting"


def planner_node(state: SealAIState) -> Dict[str, Any]:
    if state.get("phase") == "bedarfsanalyse":
        return {}
    messages = list(state.get("messages") or [])
    if not messages:
        return {}

    slots = dict(state.get("slots") or {})
    requirements = state.get("rwd_requirements") or {}
    coverage = float(state.get("requirements_coverage") or 0.0)
    warmup = slots.get("warmup") or {}
    if not warmup and slots.get("rapport_summary"):
        warmup = {"rapport_summary": slots["rapport_summary"]}
    rag_sources = slots.get("rag_sources")
    if not rag_sources:
        refs = state.get("context_refs") or []
        rag_sources = [ref.get("id") for ref in refs if isinstance(ref, dict)]
    style_contract = slots.get("style_contract") or {}

    prompt_messages = [
        msg
        for msg in PLANNER_PROMPT.format_messages(
            user_query=str(slots.get("user_query") or ""),
            history=_flatten_history(messages),
            requirements_json=_serialize_context(requirements, empty_repr="{}"),
            coverage=coverage,
            warmup_json=_serialize_context(warmup, empty_repr="{}"),
            rag_sources_json=_serialize_context(rag_sources, empty_repr="[]"),
            style_contract_json=_serialize_context(style_contract, empty_repr="{}"),
        )
        if isinstance(msg, BaseMessage)
    ]

    planner_graph = _planner_graph()
    planner_payload_messages = messages + prompt_messages
    result = planner_graph.invoke({"messages": planner_payload_messages})
    planner_messages: List[Any] = result.get("messages", [])  # type: ignore[index]
    plan_text = _extract_last_ai(planner_messages)
    if not plan_text:
        return {}

    payload, recommended = _parse_plan_payload(plan_text)
    slots["planner_plan"] = plan_text
    if payload:
        slots["planner_plan_struct"] = payload
    slots["recommended_agents"] = recommended
    slots["planner_mode"] = _determine_mode(
        str(slots.get("user_query") or ""),
        recommended,
        str(slots.get("task_mode_hint") or ""),
    )

    return {"slots": slots}
