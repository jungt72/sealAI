from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Sequence

from langchain_core.messages import BaseMessage

from app.common.obs import RoutingMetrics, emit_routing_event
from app.langgraph.nodes.members import create_domain_agent
from app.langgraph.prompts.prompt_loader import load_jinja_chat_prompt, render_prompt
from app.langgraph.state import SealAIState, StyleContract

SPECIALIST_ORDER: Sequence[str] = ("material", "profil", "standards", "validierung")
MAX_SPECIALISTS = int(os.getenv("SPECIALIST_MAX_AGENTS", "2"))
_SPECIALIST_BLOCKED_TEXT = render_prompt("specialist_blocked.de.j2").strip()
_SPECIALIST_PROMPTS = {
    "material": load_jinja_chat_prompt("specialist_material.de.j2"),
    "profil": load_jinja_chat_prompt("specialist_profil.de.j2"),
    "standards": load_jinja_chat_prompt("specialist_standards.de.j2"),
    "validierung": load_jinja_chat_prompt("specialist_validierung.de.j2"),
}


@lru_cache(maxsize=None)
def _specialist_graph(name: str):
    return create_domain_agent(name)


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


def _resolve_agent_sequence(recommended: Sequence[str]) -> List[str]:
    normalized = [a.lower() for a in recommended if isinstance(a, str)]
    order: List[str] = []
    for candidate in normalized + list(SPECIALIST_ORDER):
        if candidate in SPECIALIST_ORDER and candidate not in order:
            order.append(candidate)
        if len(order) >= MAX_SPECIALISTS:
            break
    if not order:
        order = list(SPECIALIST_ORDER[: MAX_SPECIALISTS or 1])
    return order


def _detect_number_range(text: str) -> tuple[int | None, int | None]:
    match = None
    for pattern in (
        r"(\d{1,4})\s*(?:bis|to|-)\s*(\d{1,4})",
        r"von\s*(\d{1,4})\s*(?:bis|to|-)\s*(\d{1,4})",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            break
    if not match:
        return None, None
    start = int(match.group(1))
    end = int(match.group(2))
    if start <= end:
        return start, end
    return end, start


def _format_number_sequence(start: int, end: int, *, ensure_sentence: bool) -> str:
    length = end - start
    if length > 600:
        raise ValueError("number range too large for simple formatter")
    numbers = ", ".join(str(num) for num in range(start, end + 1))
    if ensure_sentence and not numbers.endswith("."):
        return numbers + "."
    return numbers


def _simple_sequence_answer(user_query: str, contract: StyleContract | None) -> str | None:
    start = contract.get("literal_numbers_start") if isinstance(contract, dict) else None
    end = contract.get("literal_numbers_end") if isinstance(contract, dict) else None
    if isinstance(start, int) and isinstance(end, int):
        try:
            return _format_number_sequence(start, end, ensure_sentence=bool(contract.get("single_sentence")))
        except ValueError:
            return None

    parsed_start, parsed_end = _detect_number_range(user_query)
    if parsed_start is not None and parsed_end is not None:
        ensure_sentence = "satz" in user_query.lower()
        try:
            return _format_number_sequence(parsed_start, parsed_end, ensure_sentence=ensure_sentence)
        except ValueError:
            return None
    return None


def _render_simple_answer(slots: Dict[str, Any]) -> str | None:
    user_query = str(slots.get("user_query") or "")
    contract: StyleContract | None = slots.get("style_contract") if isinstance(slots.get("style_contract"), dict) else None
    answer = _simple_sequence_answer(user_query, contract)
    if answer:
        if contract and contract.get("numbers_with_commas") and "," not in answer:
            answer = answer.replace(" ", ", ")
        if contract and contract.get("enforce_plain_answer"):
            return answer.strip()
        return answer
    return None


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


def _build_specialist_context(state: SealAIState) -> Dict[str, Any]:
    slots = dict(state.get("slots") or {})
    messages = list(state.get("messages") or [])
    planner_plan_struct = slots.get("planner_plan_struct") or {}
    planner_plan_text = str(slots.get("planner_plan") or "")
    requirements = state.get("rwd_requirements") or {}
    calc_results = state.get("rwd_calc_results") or {}
    calc_summary = str(slots.get("rwd_calc_summary") or "")
    rag_refs = slots.get("rag_sources")
    if not rag_refs:
        rag_refs = state.get("context_refs") or []
    memory = state.get("memory_injections") or []
    style_contract = slots.get("style_contract") or {}

    return {
        "user_query": str(slots.get("user_query") or ""),
        "history": _flatten_history(messages),
        "phase": state.get("phase") or "",
        "planner_plan_json": _serialize_context(planner_plan_struct, empty_repr="{}"),
        "planner_plan_text": planner_plan_text or "–",
        "requirements_json": _serialize_context(requirements, empty_repr="{}"),
        "calc_results_json": _serialize_context(calc_results, empty_repr="{}"),
        "calc_summary": calc_summary or "Keine Berechnung vorhanden.",
        "rag_refs_json": _serialize_context(rag_refs, empty_repr="[]"),
        "memory_json": _serialize_context(memory, empty_repr="[]"),
        "style_contract_json": _serialize_context(style_contract, empty_repr="{}"),
    }


def specialist_executor(state: SealAIState) -> Dict[str, Any]:
    slots = dict(state.get("slots") or {})
    planner_mode = str(slots.get("planner_mode") or "expert_consulting")
    phase = state.get("phase") or "bedarfsanalyse"
    calc_results = state.get("rwd_calc_results")

    if planner_mode == "simple_direct_output":
        answer = _render_simple_answer(slots)
        if answer:
            slots["specialist_summary"] = answer
            slots["candidate_answer"] = answer
            slots["candidate_source"] = "simple_direct"
            return {"slots": slots, "phase": phase}
        # Fallback auf Expertenmodus, falls keine Heuristik greift
        planner_mode = "expert_consulting"
        slots["planner_mode"] = planner_mode

    if planner_mode != "simple_direct_output" and (phase != "auswahl" or not calc_results):
        slots["candidate_answer"] = _SPECIALIST_BLOCKED_TEXT
        slots["candidate_source"] = "specialist_blocked"
        return {"slots": slots, "phase": phase}
    recommended = slots.get("recommended_agents") or []

    agent_sequence = _resolve_agent_sequence(recommended if isinstance(recommended, list) else [])
    context_payload = _build_specialist_context(state)
    if not agent_sequence:
        return {}

    base_messages = list(state.get("messages") or [])
    aggregated_sections: List[str] = []
    contributors: List[Dict[str, Any]] = []

    for agent_name in agent_sequence:
        try:
            graph = _specialist_graph(agent_name)
        except Exception:
            continue
        prompt = _SPECIALIST_PROMPTS.get(agent_name)
        if prompt is None:
            continue
        prompt_messages = [
            msg
            for msg in prompt.format_messages(**dict(context_payload, specialist=agent_name))
            if isinstance(msg, BaseMessage)
        ]
        specialist_messages = base_messages + prompt_messages
        try:
            result = graph.invoke({"messages": specialist_messages})
        except Exception:
            continue
        agent_messages: List[Any] = result.get("messages", [])  # type: ignore[index]
        answer = _extract_last_ai(agent_messages)
        if not answer:
            continue
        aggregated_sections.append(f"[{agent_name}] {answer}")
        contributors.append({"agent": agent_name, "response": answer})

    if not aggregated_sections:
        return {}

    summary = "\n\n".join(aggregated_sections)
    slots["specialist_summary"] = summary
    slots["specialist_contributors"] = contributors

    metrics = RoutingMetrics(
        route=agent_sequence[0] if agent_sequence else None,
        chosen_agents=agent_sequence,
        rag_sources=slots.get("rag_sources", []),
    )
    meta = state.get("meta") or {}
    emit_routing_event(metrics, extra={"thread_id": meta.get("thread_id")})

    slots["candidate_answer"] = summary
    slots["candidate_source"] = "specialists"
    return {"slots": slots}
