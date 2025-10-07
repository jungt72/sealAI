"""Unified LangGraph chat pipeline wiring the new IO nodes."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from typing_extensions import Annotated

try:  # langchain optional at import time for tests
    from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
except Exception:  # pragma: no cover - test environments without langchain
    AnyMessage = Dict[str, str]  # type: ignore[assignment]
    HumanMessage = SystemMessage = Dict[str, str]  # type: ignore[assignment]

try:  # langgraph import (only required at runtime)
    from langgraph.constants import END
    from langgraph.graph import StateGraph, add_messages
except Exception as exc:  # pragma: no cover - fails fast if dependency missing at runtime
    raise RuntimeError("langgraph package required for chat graph") from exc

from app.langgraph.agents import adapt_agent_input
from app.langgraph.io.schema import Intent, SCHEMA_VERSION
from app.langgraph.io.validation import (
    ensure_agent_output,
    ensure_handoff,
    ensure_intent,
    ensure_parameter_bag,
)
from app.langgraph.nodes import (
    ConfirmGateNode,
    DiscoveryIntakeNode,
    DiscoverySummarizeNode,
    IntentClassifierNode,
    RouterNode,
    SyntheseNode,
    SafetyGateNode,
)


def _model_dump(model: Any) -> Dict[str, Any]:
    """Support both pydantic v1/v2 model dump APIs."""
    exporter = getattr(model, "model_dump", None)
    if callable(exporter):  # pydantic v2
        return exporter()
    to_dict = getattr(model, "dict", None)
    if callable(to_dict):  # pydantic v1
        return to_dict()
    if isinstance(model, dict):
        return dict(model)
    raise TypeError(f"Cannot dump model of type {type(model)!r}")


class ChatState(TypedDict, total=False):
    messages: Annotated[List[AnyMessage], add_messages]
    parameter_bag: Dict[str, Any]
    discovery: Dict[str, Any]
    classification: Dict[str, Any]
    handoff: Dict[str, Any]
    agent_queue: List[str]
    executed_agents: List[str]
    current_agent: Optional[str]
    agent_outputs: List[Dict[str, Any]]
    synthesis: Dict[str, Any]
    safety: Dict[str, Any]
    final: Dict[str, Any]
    thread_id: str
    user_id: str


_DISCOVERY = DiscoveryIntakeNode()
_SUMMARY = DiscoverySummarizeNode()
_GATE = ConfirmGateNode()
_CLASSIFIER = IntentClassifierNode()
_ROUTER = RouterNode()
_SYNTH = SyntheseNode()
_SAFETY = SafetyGateNode()


def _discovery_step(state: ChatState) -> Dict[str, Any]:
    discovery = _DISCOVERY.run(dict(state))
    return {"discovery": discovery}


def _summary_step(state: ChatState) -> Dict[str, Any]:
    discovery = dict(state.get("discovery") or {})
    summarized = _SUMMARY.run(discovery)
    return {"discovery": summarized}


def _gate_step(state: ChatState) -> Dict[str, Any]:
    discovery = dict(state.get("discovery") or {})
    gated = _GATE.run({**discovery, "force_ready": discovery.get("ready_to_route")})
    return {"discovery": gated}


def _intent_step(state: ChatState) -> Dict[str, Any]:
    discovery = dict(state.get("discovery") or {})
    classification = _CLASSIFIER.run(discovery)
    return {"classification": classification}


def _router_step(state: ChatState) -> Dict[str, Any]:
    classification = dict(state.get("classification") or {})
    parameter_bag = state.get("parameter_bag") or {"items": []}
    ensured_bag = ensure_parameter_bag(parameter_bag)
    bag_payload = _model_dump(ensured_bag)

    discovery = state.get("discovery") or {}
    auftrag = discovery.get("ziel") or "Beratung"

    handoff = _ROUTER.run(
        {
            "classification": classification,
            "parameter": bag_payload,
            "auftrag": auftrag,
            "restriktionen": [],
            "max_tokens_hint": 512,
        }
    )

    classification_model = ensure_intent(classification)
    queue: List[str] = []
    primary = str(handoff.get("agent") or classification_model.intent.value)
    queue.append(primary)
    if classification_model.routing_modus in {"parallel", "sequenziell"}:
        for agent in classification_model.empfohlene_agenten:
            queue.append(agent.value if isinstance(agent, Intent) else str(agent))
    fallback = classification_model.intent.value
    if fallback not in queue:
        queue.append(fallback)
    if "safety" not in queue and classification_model.intent is Intent.safety:
        queue.append("safety")

    seen: set[str] = set()
    dedup_queue: List[str] = []
    for agent in queue:
        if not agent:
            continue
        if agent not in seen:
            dedup_queue.append(agent)
            seen.add(agent)

    return {
        "handoff": handoff,
        "agent_queue": dedup_queue,
        "executed_agents": [],
        "agent_outputs": [],
        "current_agent": None,
    }


def _dispatch_step(state: ChatState) -> Dict[str, Any]:
    queue = list(state.get("agent_queue") or [])
    executed = set(state.get("executed_agents") or [])
    next_agent: Optional[str] = None
    for candidate in queue:
        if candidate not in executed:
            next_agent = candidate
            break
    return {"current_agent": next_agent}


def _summarise_params(agent_input_dict: Dict[str, Any]) -> str:
    items = agent_input_dict.get("parameter", {}).get("items", []) if isinstance(agent_input_dict, dict) else []
    parts: List[str] = []
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or "param"
        value = item.get("value")
        unit = item.get("unit")
        unit_suffix = f" {unit}" if unit and unit not in {"none", ""} else ""
        parts.append(f"{name}={value}{unit_suffix}".strip())
    return ", ".join(parts) if parts else "keine Parameter angegeben"


def _agent_step(state: ChatState) -> Dict[str, Any]:
    handoff_dict = dict(state.get("handoff") or {})
    ensured_handoff = ensure_handoff(handoff_dict)
    agent_name = (state.get("current_agent") or ensured_handoff.agent.value).lower()

    agent_input = adapt_agent_input(
        {
            "schema_version": ensured_handoff.schema_version,
            "ziel": ensured_handoff.auftrag,
            "parameter": _model_dump(ensured_handoff.eingaben),
            "constraints": [_model_dump(c) for c in ensured_handoff.restriktionen],
        }
    )

    param_summary = _summarise_params(_model_dump(agent_input))
    discovery = state.get("discovery") or {}
    missing = discovery.get("fehlende_parameter") or []
    uncertainties = [f"Fehlender Parameter: {item}" for item in missing]

    raw_output = {
        "schema_version": SCHEMA_VERSION,
        "empfehlung": f"[{agent_name}] {ensured_handoff.auftrag}",
        "begruendung": f"Analyse basiert auf {param_summary}.",
        "annahmen": [],
        "unsicherheiten": uncertainties,
        "evidenz": [],
    }
    agent_output = ensure_agent_output(raw_output)
    dumped_output = _model_dump(agent_output)

    existing = list(state.get("agent_outputs") or [])
    existing.append(dumped_output)
    executed = list(state.get("executed_agents") or [])
    executed.append(agent_name)

    return {
        "agent_outputs": existing,
        "executed_agents": executed,
        "current_agent": None,
    }


def _synth_step(state: ChatState) -> Dict[str, Any]:
    outputs = list(state.get("agent_outputs") or [])
    synthesis = _SYNTH.run({"agent_outputs": outputs})
    return {"synthesis": synthesis}


def _safety_step(state: ChatState) -> Dict[str, Any]:
    payload = {
        "risk": (state.get("classification") or {}).get("risk"),
        "classification": state.get("classification"),
        "agent_outputs": state.get("agent_outputs"),
        "synthesis": state.get("synthesis"),
    }
    verdict = _SAFETY.run(payload)
    return {"safety": verdict}


def _final_step(state: ChatState) -> Dict[str, Any]:
    final = {
        "discovery": state.get("discovery"),
        "classification": state.get("classification"),
        "handoff": state.get("handoff"),
        "agent_outputs": state.get("agent_outputs"),
        "executed_agents": state.get("executed_agents"),
        "synthesis": state.get("synthesis"),
        "safety": state.get("safety"),
    }
    return {"final": final}


def _dispatch_branch(state: ChatState) -> str:
    return "run" if state.get("current_agent") else "done"


def build_chat_graph() -> StateGraph:
    builder = StateGraph(ChatState)

    builder.add_node("discovery", _discovery_step)
    builder.add_node("summarize", _summary_step)
    builder.add_node("gate", _gate_step)
    builder.add_node("intent", _intent_step)
    builder.add_node("router", _router_step)
    builder.add_node("dispatch", _dispatch_step)
    builder.add_node("agent", _agent_step)
    builder.add_node("synthese", _synth_step)
    builder.add_node("safety", _safety_step)
    builder.add_node("final", _final_step)

    builder.set_entry_point("discovery")

    builder.add_edge("discovery", "summarize")
    builder.add_edge("summarize", "gate")
    builder.add_edge("gate", "intent")
    builder.add_edge("intent", "router")
    builder.add_edge("router", "dispatch")
    builder.add_conditional_edges("dispatch", _dispatch_branch, {"run": "agent", "done": "synthese"})
    builder.add_edge("agent", "dispatch")
    builder.add_edge("synthese", "safety")
    builder.add_edge("safety", "final")
    builder.add_edge("final", END)

    return builder


def compile_chat_graph(*, checkpointer: Any | None = None):
    """Compile the chat graph with optional Redis checkpointer."""
    builder = build_chat_graph()
    compile_kwargs: Dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
    try:
        compile_kwargs["stream_mode"] = "messages"
        return builder.compile(**compile_kwargs)
    except TypeError:  # pragma: no cover - older langgraph versions
        compile_kwargs.pop("stream_mode", None)
        return builder.compile(**compile_kwargs)


__all__ = ["ChatState", "build_chat_graph", "compile_chat_graph"]
