"""Supervisor-Fabrik auf Basis der konfigurierten Domains."""

from __future__ import annotations

import contextvars
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from app.langgraph.config.loader import AgentsConfig, DomainCfg, SupervisorCfg
from app.langgraph.nodes.members import (
    _use_offline_mode,
    create_domain_agent,
    create_material_agent,
    create_profil_agent,
    create_standards_agent,
    create_validierung_agent,
)
from app.langgraph.nodes.confidence_gate import confidence_gate_node
from app.langgraph.nodes.planner_node import planner_node
from app.langgraph.nodes.quality_review import run_quality_review
from app.langgraph.nodes.challenger_feedback import challenger_feedback
from app.langgraph.nodes.specialist_executor import specialist_executor
from app.langgraph.nodes.resolver import resolver
from app.langgraph.prompts.prompt_loader import load_jinja_chat_prompt, render_prompt
from app.langgraph.state import SealAIState

logger = logging.getLogger(__name__)

_handoff_counter: contextvars.ContextVar[int] = contextvars.ContextVar("handoff_counter", default=0)
_handoff_trace: contextvars.ContextVar[List[str]] = contextvars.ContextVar("handoff_trace", default=[])
SUPERVISOR_PROMPT = load_jinja_chat_prompt("supervisor_prompt.de.j2")


@dataclass(frozen=True)
class WorkerBinding:
    name: str
    description: str
    graph: CompiledStateGraph
    domain_cfg: DomainCfg


def _build_worker_bindings(config: AgentsConfig, supervisor_cfg: SupervisorCfg) -> List[WorkerBinding]:
    bindings: List[WorkerBinding] = []
    for worker_cfg in supervisor_cfg.workers:
        domain_cfg = config.domain_cfg(worker_cfg.name)
        graph = _create_domain_graph(worker_cfg.name)
        description = worker_cfg.description or domain_cfg.routing_description
        bindings.append(WorkerBinding(name=worker_cfg.name, description=description, graph=graph, domain_cfg=domain_cfg))
    return bindings


def _create_domain_graph(name: str) -> CompiledStateGraph:
    factory_map = {
        "material": create_material_agent,
        "profil": create_profil_agent,
        "validierung": create_validierung_agent,
        "standards": create_standards_agent,
    }
    factory = factory_map.get(name, lambda: create_domain_agent(name))
    return factory()


def _render_supervisor_prompt(cfg: SupervisorCfg, workers: Sequence[WorkerBinding]) -> str:
    worker_entries = [{"name": w.name, "description": w.description} for w in workers]
    extra = str(cfg.prompt or "").strip()
    prompt_value = SUPERVISOR_PROMPT.format_prompt(
        project_name="ACME",
        handoff_tool_prefix=cfg.handoff_tool_prefix,
        output_mode=cfg.output_mode,
        max_handoffs=cfg.max_handoffs,
        workers=worker_entries,
        extra_instructions=extra,
    )
    prompt_text = prompt_value.to_string().strip()
    if not prompt_text:
        raise ValueError("supervisor_prompt Template lieferte einen leeren Text.")
    return prompt_text


# Legacy shim used by prompt snapshot tests.
def _render_prompt(prompt: str, *, prefix: str, output_mode: str) -> str:
    config = AgentsConfig.load()
    base_cfg = config.supervisor_cfg()
    custom_cfg = SupervisorCfg(
        model=base_cfg.model,
        prompt=prompt or base_cfg.prompt,
        output_mode=output_mode,
        allow_forward_message=base_cfg.allow_forward_message,
        handoff_tool_prefix=prefix,
        workers=list(base_cfg.workers),
        max_handoffs=base_cfg.max_handoffs,
    )
    bindings = _build_worker_bindings(config, custom_cfg)
    worker_entries = [{"name": w.name, "description": w.description} for w in bindings]
    body = render_prompt(
        "supervisor_prompt.de.j2",
        project_name="ACME",
        handoff_tool_prefix=custom_cfg.handoff_tool_prefix,
        output_mode=custom_cfg.output_mode,
        max_handoffs=custom_cfg.max_handoffs,
        workers=worker_entries,
        extra_instructions=str(custom_cfg.prompt or "").strip(),
    ).strip()
    header = "# Supervisor (Projekt: ACME)"
    return f"{header}\n{body}"

def _make_handoff_tool(
    prefix: str,
    worker: WorkerBinding,
    *,
    max_handoffs: int,
) -> Any:
    tool_name = f"{prefix}{worker.name}"
    description = worker.description or f"Handoff an {worker.name}"

    @tool(name=tool_name, description=description)
    def _handoff(message: str) -> str:
        count = _handoff_counter.get()
        if count >= max_handoffs:
            logger.warning("Maximale Anzahl an Handoffs (%s) erreicht.", max_handoffs)
            return "Maximale Anzahl an Handoffs erreicht – bitte Antwort formulieren."
        _handoff_counter.set(count + 1)
        trace = _handoff_trace.get()
        trace.append(worker.name)
        return _invoke_worker(worker.graph, message)

    return _handoff


def _make_forward_tool(prefix: str) -> Any:
    @tool(
        name=f"{prefix}forward_message",
        description="Leitet die letzte Worker-Antwort unverändert an den Nutzer weiter.",
    )
    def _forward(message: str) -> str:
        trace = _handoff_trace.get()
        trace.append("forward")
        return message

    return _forward


def _build_supervisor_agent(
    *,
    model: Any,
    prompt: str,
    tools: Sequence[Any],
) -> CompiledStateGraph:
    return create_react_agent(
        model=model,
        tools=tools,
        name="supervisor",
        prompt=prompt,
    )


def _invoke_worker(graph: CompiledStateGraph, message: str) -> str:
    worker_state = {"messages": [HumanMessage(content=message, id="handoff-input")]}
    result = graph.invoke(worker_state)
    messages: Sequence[BaseMessage] = result.get("messages", [])  # type: ignore[index]
    return _extract_last_ai(messages) or ""


def _extract_last_ai(messages: Sequence[BaseMessage]) -> str | None:
    for msg in reversed(messages):
        try:
            if getattr(msg, "type", "") == "ai":
                content = getattr(msg, "content", None)
                if isinstance(content, str):
                    return content
                if isinstance(content, Mapping) and "content" in content:
                    return str(content["content"])
                return str(content)
        except Exception:  # pragma: no cover - defensive
            continue
    return None


def _extract_last_user(messages: Sequence[BaseMessage]) -> str:
    for msg in reversed(messages):
        try:
            if getattr(msg, "type", "") in {"human", "user"}:
                content = getattr(msg, "content", "")
                return content if isinstance(content, str) else str(content)
        except Exception:  # pragma: no cover
            continue
    return ""


def _choose_worker_heuristic(text: str, available: Sequence[str]) -> str:
    lowered = text.lower()
    if "validierung" in available:
        if ("empfiehl" in lowered or "fehl" in lowered or "parameter" in lowered) and not re.search(r"\d", lowered):
            return "validierung"
    if "profil" in available and any(token in lowered for token in ("profil", "persona", "profiling", "steckbrief")):
        return "profil"
    if "material" in available and any(token in lowered for token in ("gewicht", "masse", "material", "platte", "kg", "dichte")):
        return "material"
    if "standards" in available and ("din" in lowered or "iso" in lowered or "norm" in lowered):
        return "standards"
    if "validierung" in available and any(token in lowered for token in ("prüf", "valid", "pass", "fail")):
        return "validierung"
    # Fallback auf Validierung, wenn vorhanden, sonst erster Worker
    if "validierung" in available:
        return "validierung"
    return available[0]


def _offline_supervisor_node(
    workers: Sequence[WorkerBinding],
    *,
    max_handoffs: int,
) -> Any:
    worker_map = {worker.name: worker for worker in workers}
    worker_order = list(worker_map.keys())

    def _node(state: SealAIState) -> Dict[str, Any]:
        messages = list(state.get("messages") or [])
        slots = dict(state.get("slots") or {})
        trace: List[str] = list(slots.get("handoff_history") or [])
        visited = set(trace)

        user_text = _extract_last_user(messages)
        last_response = ""

        for _ in range(max_handoffs):
            target = _choose_worker_heuristic(user_text or last_response, worker_order)
            # Fallback: vermeide Dauerschleifen
            if target in visited and target != "validierung" and len(visited) < len(worker_order):
                for candidate in worker_order:
                    if candidate not in visited:
                        target = candidate
                        break
            visited.add(target)
            trace.append(target)
            response = _invoke_worker(worker_map[target].graph, user_text or last_response or "Bitte übernehmen.")
            messages.append(AIMessage(content=response, name=target))
            last_response = response

            if target == "validierung" and response.lower().startswith("pass"):
                break
            if target == "validierung":
                # Ergebnis zurückgeben und Schleife beenden (keine weiteren Handoffs im Offline-Modus)
                break
            normalized = response.lower()
            if "bitte nenne" in normalized or "benötige ich" in normalized:
                user_text = response
                continue
            break

        slots["handoff_history"] = trace
        return {"messages": messages, "slots": slots}

    return _node


def create_supervisor(
    state_schema: Any,
    workers: Sequence[Any],
    handoff_tool_prefix: str,
    *,
    output_mode: str = "final",
    allow_forward_message: bool = True,
    supervisor_prompt: str | None = None,
    model: Any = None,
    max_handoffs: int = 5,
) -> CompiledStateGraph:
    """Erzeugt einen Supervisor-Graphen basierend auf den Worker-Bindings."""

    normalized_workers: List[WorkerBinding] = []
    for entry in workers:
        if isinstance(entry, WorkerBinding):
            normalized_workers.append(entry)
            continue
        if isinstance(entry, Mapping):
            name = str(entry.get("name") or "").strip()
            graph = entry.get("graph")
            if not name or graph is None:
                raise ValueError("Jeder Worker benötigt mindestens 'name' und 'graph'.")
            description = str(entry.get("description") or "").strip() or f"Handoff an {name}"
            domain_cfg = entry.get("domain_cfg")
            if isinstance(domain_cfg, DomainCfg):
                cfg = domain_cfg
            else:
                cfg = AgentsConfig.load().domain_cfg(name)
            normalized_workers.append(
                WorkerBinding(name=name, description=description, graph=graph, domain_cfg=cfg)
            )
            continue
        raise TypeError("workers-Einträge müssen WorkerBinding oder Mapping sein.")

    workers = normalized_workers

    if model is None:
        offline_node = _offline_supervisor_node(workers, max_handoffs=max_handoffs)
        builder = StateGraph(state_schema)
        builder.add_node("supervisor_offline", offline_node)
        builder.set_entry_point("supervisor_offline")
        builder.add_edge("supervisor_offline", END)
        compiled = builder.compile(name="supervisor_offline")
        setattr(compiled, "handoff_tools", [f"{handoff_tool_prefix}{worker.name}" for worker in workers])
        return compiled

    tools = [_make_handoff_tool(handoff_tool_prefix, worker, max_handoffs=max_handoffs) for worker in workers]
    if allow_forward_message:
        tools.append(_make_forward_tool(handoff_tool_prefix))

    supervisor_agent = _build_supervisor_agent(model=model, prompt=supervisor_prompt or "You are the supervisor.", tools=tools)

    def _run_supervisor(state: SealAIState) -> Dict[str, Any]:
        token_counter = _handoff_counter.set(0)
        token_trace = _handoff_trace.set([])
        try:
            messages = list(state.get("messages") or [])
            agent_state = {"messages": messages}
            result = supervisor_agent.invoke(agent_state)
            new_messages: Sequence[BaseMessage] = result.get("messages", [])  # type: ignore[index]
            slots = dict(state.get("slots") or {})
            slots["handoff_history"] = list(_handoff_trace.get())
            return {"messages": list(new_messages), "slots": slots}
        finally:
            _handoff_counter.reset(token_counter)
            _handoff_trace.reset(token_trace)

    builder = StateGraph(state_schema)
    builder.add_node("supervisor_core", _run_supervisor)
    builder.set_entry_point("supervisor_core")
    builder.add_edge("supervisor_core", END)
    compiled = builder.compile(name="sealai_supervisor")
    setattr(compiled, "handoff_tools", [f"{handoff_tool_prefix}{worker.name}" for worker in workers])
    return compiled


_SUPERVISOR_FLOW: Optional[CompiledStateGraph] = None


def _confidence_route(state: SealAIState) -> str:
    decision = str(state.get("confidence_decision") or "").strip().lower()
    if decision in {"needs_review", "abort"}:
        return decision
    return "ok"


def build_supervisor_subgraph() -> CompiledStateGraph:
    builder = StateGraph(SealAIState)
    builder.add_node("planner", planner_node)
    builder.add_node("specialists", specialist_executor)
    builder.add_node("challenger", challenger_feedback)
    builder.add_node("quality_review", run_quality_review)
    builder.add_node("confidence_gate", confidence_gate_node)
    builder.add_node("arbiter", resolver)

    builder.set_entry_point("planner")
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "specialists")
    builder.add_edge("specialists", "challenger")
    builder.add_edge("challenger", "quality_review")
    builder.add_edge("quality_review", "confidence_gate")
    builder.add_conditional_edges(
        "confidence_gate",
        _confidence_route,
        {
            "ok": "arbiter",
            "abort": "arbiter",
            "needs_review": "challenger",
        },
    )
    builder.add_edge("arbiter", END)
    return builder.compile(name="supervisor_flow")


def _ensure_supervisor_flow() -> CompiledStateGraph:
    global _SUPERVISOR_FLOW
    if _SUPERVISOR_FLOW is None:
        _SUPERVISOR_FLOW = build_supervisor_subgraph()
    return _SUPERVISOR_FLOW


def supervisor_panel_node(state: SealAIState) -> Dict[str, Any]:
    graph = _ensure_supervisor_flow()
    result = graph.invoke(state)
    if not isinstance(result, dict):
        return {}
    updates: Dict[str, Any] = {}
    for key, value in result.items():
        if key == "meta":
            continue
        updates[key] = value
    return updates


def _build_supervisor_model(cfg: SupervisorCfg) -> Any:
    from langchain_openai import ChatOpenAI

    if _use_offline_mode():
        return None

    kwargs: Dict[str, Any] = {"model": cfg.model.name}
    if cfg.model.temperature is not None:
        kwargs["temperature"] = cfg.model.temperature
    if cfg.model.max_output_tokens is not None:
        kwargs["max_tokens"] = cfg.model.max_output_tokens
    return ChatOpenAI(**kwargs)


def build_supervisor() -> CompiledStateGraph:
    """Hauptzugang: Lädt Konfiguration und erstellt den Supervisor-Graphen."""
    config = AgentsConfig.load()
    supervisor_cfg = config.supervisor_cfg()
    workers = _build_worker_bindings(config, supervisor_cfg)
    prompt = _render_supervisor_prompt(supervisor_cfg, workers)

    model = _build_supervisor_model(supervisor_cfg)

    graph = create_supervisor(
        state_schema=SealAIState,
        workers=workers,
        handoff_tool_prefix=supervisor_cfg.handoff_tool_prefix,
        output_mode=supervisor_cfg.output_mode,
        allow_forward_message=supervisor_cfg.allow_forward_message,
        supervisor_prompt=prompt,
        model=model,
        max_handoffs=supervisor_cfg.max_handoffs,
    )
    return graph


__all__ = [
    "build_supervisor",
    "build_supervisor_subgraph",
    "supervisor_panel_node",
]
