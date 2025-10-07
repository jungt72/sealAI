from __future__ import annotations

import logging
from typing import Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from langgraph.constants import END
from langgraph.graph import StateGraph

from app.services.langgraph.config.routing import load_routing_config
from app.services.langgraph.config.runtime import get_runtime_config
from app.services.langgraph.graph.consult import memory_utils as consult_memory
from app.services.langgraph.graph.consult.nodes.ask_missing import ask_missing_node
from app.services.langgraph.graph.consult.nodes.calc_agent import calc_agent_node
from app.services.langgraph.graph.consult.nodes.deterministic_calc import deterministic_calc_node
from app.services.langgraph.graph.consult.nodes.explain import explain_node
from app.services.langgraph.graph.consult.nodes.intake import intake_node
from app.services.langgraph.graph.consult.nodes.lite_router import lite_router_node
from app.services.langgraph.graph.consult.nodes.ltm import ltm_node
from app.services.langgraph.graph.consult.nodes.profile import profile_node
from app.services.langgraph.graph.consult.nodes.rag import run_rag_node
from app.services.langgraph.graph.consult.nodes.recommend import recommend_node
from app.services.langgraph.graph.consult.nodes.smalltalk import smalltalk_node
from app.services.langgraph.graph.consult.nodes.summarize import summarize_node
from app.services.langgraph.graph.consult.nodes.validate import validate_node
from app.services.langgraph.graph.consult.nodes.validate_answer import validate_answer
from app.services.langgraph.graph.consult.build import (
    _compute_node as consult_compute_node,
    _domain_router_node as consult_domain_router_node,
    _extract_node as consult_extract_node,
    _prepare_query_node as consult_prepare_query_node,
    _respond_node as consult_respond_node,
)
from app.services.langgraph.graph.intent_router import classify_intent
from app.services.langgraph.graph.logging_utils import log_branch_decision, wrap_node_with_logging
from app.services.langgraph.graph.types import MaiDxoState
from app.services.langgraph.hybrid_routing import (
    BUTTON_INTENTS,
    IntentMatch,
    find_intent_from_text,
    last_agent_suggestion,
    normalize_intent,
    suggestions_from_alternatives,
)
from app.services.langgraph.llm_factory import get_llm
from app.services.langgraph.telemetry import RoutingEvent, RoutingTimer, emit_routing_event
from app.services.langgraph.tools import long_term_memory as ltm

log = logging.getLogger(__name__)
_GRAPH_NAME = "MaiDxoGraph"


@tool
def ltm_search(query: str) -> str:
    """Durchsucht das Long-Term-Memory (Qdrant) nach relevanten Erinnerungen (MMR, top-k=5) und gibt einen zusammenhängenden Kontext-Text zurück."""
    ctx, _hits = ltm.ltm_query(query, strategy="mmr", top_k=5)
    return ctx or "Keine relevanten Erinnerungen gefunden."


@tool
def ltm_store(user: str, chat_id: str, text: str, kind: str = "note") -> str:
    """Speichert einen Text-Schnipsel im Long-Term-Memory (Qdrant). Parameter: user, chat_id, text, kind."""
    try:
        pid = ltm.upsert_memory(user=user, chat_id=chat_id, text=text, kind=kind)
        return f"Memory gespeichert (ID={pid})"
    except Exception as exc:  # pragma: no cover — reine Telemetrie
        return f"Fehler beim Speichern: {exc}"


TOOLS = [ltm_search, ltm_store]


def create_llm() -> ChatOpenAI:
    """Factory für einen Streaming-LLM entsprechend der Runtime-Konfiguration."""
    return get_llm(streaming=True)


_CLASSIFIER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Du analysierst Anfragen zur Dichtungstechnik und klassifizierst ihre Komplexität.",
        ),
        (
            "user",
            """
Klassifiziere die Query als "simple" oder "complex".

simple ⇒ Allgemeine Vergleiche/Eigenschaften ohne spezifischen Anwendungsfall oder Norm.
complex ⇒ Konkrete Anwendungen, Betriebsbedingungen, Normen, Maß-/Sicherheitsangaben.
Bei Unsicherheit gib "complex" zurück.

Query: {query}

Antwort ausschließlich mit simple oder complex.
""",
        ),
    ]
)


_SIMPLE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
Du bist SealAI, Fachberater für Dichtungstechnik.
Beantworte einfache Wissens- oder Vergleichsfragen präzise, knapp und ohne externe Quellen.
Sprache: Deutsch.
""",
        ),
        ("user", "Query: {query}\n\nAntwort:"),
    ]
)


def _last_user_text(messages: List[BaseMessage] | None) -> str:
    if not messages:
        return ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = (msg.content or "").strip()
            if content:
                return content
        elif isinstance(msg, dict):
            role = str(msg.get("role") or msg.get("type") or "").lower()
            text = str(msg.get("content") or "").strip()
            if role in {"human", "user"} and text:
                return text
    return ""


def _thread_id_from_state(state: MaiDxoState) -> Optional[str]:
    thread_id = state.get("chat_id") or state.get("thread_id")
    if isinstance(thread_id, str) and thread_id.strip():
        return thread_id.strip()
    return None


def _augment_with_last_agent(state: MaiDxoState) -> None:
    thread_id = _thread_id_from_state(state)
    if not thread_id:
        return
    try:
        last_agent = consult_memory.get_last_agent(thread_id)
    except Exception:  # pragma: no cover — defensive Telemetrie
        last_agent = None
    if last_agent:
        state["last_agent"] = last_agent


def _persist_last_agent(state: MaiDxoState, agent: Optional[str]) -> None:
    agent_key = normalize_intent(agent)
    if not agent_key or agent_key not in BUTTON_INTENTS:
        return
    thread_id = _thread_id_from_state(state)
    if not thread_id:
        return
    try:
        consult_memory.set_last_agent(thread_id, agent_key)
    except Exception:  # pragma: no cover — defensive Telemetrie
        pass


def _decide_consult_route(state: MaiDxoState) -> str:
    route = (state.get("consult_route") or state.get("route") or "default").strip().lower() or "default"
    branch = "smalltalk" if route == "smalltalk" else "default"
    log_branch_decision(_GRAPH_NAME, "consult_lite_router", "route", branch, state)
    return branch


def _decide_after_ask(state: MaiDxoState) -> str:
    params = state.get("params") or {}

    def has(value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, (list, dict)) and not value:
            return False
        if isinstance(value, str) and not value.strip():
            return False
        return True

    base_ok = has(params.get("temp_max_c")) and has(params.get("druck_bar"))
    rel_ok = has(params.get("relativgeschwindigkeit_ms") or params.get("geschwindigkeit_m_s")) or (
        has(params.get("wellen_mm")) and has(params.get("drehzahl_u_min"))
    )
    branch = "ask" if not (base_ok and rel_ok) else "ok"
    log_branch_decision(_GRAPH_NAME, "consult_ask_missing", "ask_or_ok", branch, state)
    return branch


def _decide_after_rag(state: MaiDxoState) -> str:
    params = state.get("params") or {}
    docs = state.get("retrieved_docs") or state.get("docs") or []
    context = state.get("context")

    def has(value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, (list, dict)) and not value:
            return False
        if isinstance(value, str) and not value.strip():
            return False
        return True

    base_ok = has(params.get("temp_max_c")) and has(params.get("druck_bar"))
    rel_ok = has(params.get("relativgeschwindigkeit_ms") or params.get("geschwindigkeit_m_s")) or (
        has(params.get("wellen_mm")) and has(params.get("drehzahl_u_min"))
    )
    ctx_ok = bool(docs) or has(context)
    branch = "recommend" if (base_ok and rel_ok and ctx_ok) else "explain"
    log_branch_decision(_GRAPH_NAME, "consult_rag", "after_rag", branch, state)
    return branch


def build_mai_dxo_graph(llm: Optional[ChatOpenAI] = None) -> StateGraph:
    """Erzeugt den vollständigen MAI-DXO-Graphen (Supervisor + Consult in einem StateGraph)."""
    log.info("[mai_dxo] Initialisiere…")
    builder = StateGraph(MaiDxoState)

    base_llm = llm or create_llm()
    llm_chitchat = base_llm.bind_tools(TOOLS)

    classifier_llm = get_llm(streaming=False)
    classifier_chain = _CLASSIFIER_PROMPT | classifier_llm
    simple_chain = _SIMPLE_PROMPT | base_llm

    def legacy_router_node(state: MaiDxoState) -> MaiDxoState:
        label = classify_intent(base_llm, state.get("messages", []))
        intent = "consult" if label == "material_select" else "chitchat"
        next_node = "consult_lite_router" if intent == "consult" else "chitchat"
        return {"intent": intent, "next_node": next_node, "phase": "legacy_router"}

    def complexity_router_node(state: MaiDxoState) -> MaiDxoState:
        query = _last_user_text(state.get("messages", []))
        if not query:
            result: MaiDxoState = {
                "query_type": "complex",
                "phase": "complexity_router",
                "next_node": "consult_lite_router",
            }
            _persist_last_agent(state, state.get("intent_final") or state.get("intent_candidate"))
            return result
        try:
            result_msg = classifier_chain.invoke({"query": query})
            classification = getattr(result_msg, "content", str(result_msg))
        except Exception as exc:  # pragma: no cover — defensive fallback
            log.warning("[mai_dxo] complexity_router_failed", exc=str(exc))
            classification = ""
        classification = (classification or "").strip().lower()
        query_type = "simple" if classification.startswith("simple") else "complex"
        next_node = "simple_response" if query_type == "simple" else "consult_lite_router"
        if next_node == "consult_lite_router":
            _persist_last_agent(state, state.get("intent_final") or state.get("intent_candidate"))
        return {
            "query_type": query_type,
            "phase": "complexity_router",
            "next_node": next_node,
        }

    def simple_response_node(state: MaiDxoState) -> MaiDxoState:
        query = _last_user_text(state.get("messages", []))
        if not query:
            ai_msg = AIMessage(content="Ich habe keine konkrete Frage erkannt.")
            return {"messages": [ai_msg], "query_type": "simple", "phase": "simple_response", "next_node": "END"}
        try:
            resp = simple_chain.invoke({"query": query})
        except Exception as exc:  # pragma: no cover — defensive fallback
            log.warning("[mai_dxo] simple_response_failed", exc=str(exc))
            resp = AIMessage(content="Entschuldigung, ich konnte das gerade nicht beantworten.")
        ai_msg = resp if isinstance(resp, AIMessage) else AIMessage(content=getattr(resp, "content", str(resp)))
        return {
            "messages": [ai_msg],
            "query_type": "simple",
            "phase": "simple_response",
            "next_node": "END",
        }

    def entry_node(state: MaiDxoState) -> MaiDxoState:
        cfg = get_runtime_config()
        next_state: Dict[str, object] = dict(state or {})
        next_state["phase"] = "entry"
        next_state["feature_flag_state"] = cfg.hybrid_routing_enabled

        _augment_with_last_agent(next_state)  # type: ignore[arg-type]

        source = normalize_intent(str(next_state.get("source") or ""))
        intent_seed = normalize_intent(next_state.get("intent_seed"))
        if not source and intent_seed in BUTTON_INTENTS:
            source = "ui_button"
        if not source:
            source = "nlp"
        next_state["source"] = source

        if intent_seed:
            next_state["intent_seed"] = intent_seed

        if not cfg.hybrid_routing_enabled:
            next_state["route"] = "legacy"
            return next_state  # type: ignore[return-value]

        if source == "ui_button" and intent_seed in BUTTON_INTENTS:
            confidence_raw = next_state.get("confidence")
            try:
                confidence_val = float(confidence_raw) if confidence_raw is not None else 0.95
            except (TypeError, ValueError):
                confidence_val = 0.95
            next_state.update(
                {
                    "route": "button",
                    "intent": "consult",
                    "intent_candidate": intent_seed,
                    "intent_final": intent_seed,
                    "query_type": "complex",
                    "confidence": confidence_val,
                    "next_node": "consult_lite_router",
                }
            )
            return next_state  # type: ignore[return-value]

        next_state["route"] = "semantic"
        return next_state  # type: ignore[return-value]

    def button_dispatch_node(state: MaiDxoState) -> MaiDxoState:
        intent = normalize_intent(state.get("intent_final") or state.get("intent_seed"))
        _persist_last_agent(state, intent)

        emit_routing_event(
            RoutingEvent(
                event="ui_button_selected",
                thread_id=_thread_id_from_state(state),
                user_id=state.get("user_id"),
                source=state.get("source"),
                intent_candidate=intent,
                intent_final=intent,
                confidence=state.get("confidence"),
                next_node="consult_lite_router",
            )
        )

        new_state: MaiDxoState = {
            **state,
            "intent": "consult",
            "query_type": "complex",
            "phase": "button_dispatch",
            "next_node": "consult_lite_router",
        }
        return new_state

    def semantic_router_node(state: MaiDxoState) -> MaiDxoState:
        timer = RoutingTimer()
        decision = find_intent_from_text(state.get("messages", []))
        duration_ms = timer.stop()
        candidate = decision.candidate
        cfg = load_routing_config()

        confidence = candidate.score if candidate else 0.0
        intent_key = candidate.intent if candidate else None

        fallback = True
        next_node = "fallback"
        intent_final: Optional[str] = None
        intent = "chitchat"

        if candidate and intent_key in BUTTON_INTENTS and confidence >= cfg.confidence_threshold:
            fallback = False
            next_node = "complexity_router"
            intent_final = intent_key
            intent = "consult"

        alternatives = decision.alternatives
        alt_candidates: List[IntentMatch] = []
        if candidate:
            alt_candidates.append(candidate)
        alt_candidates.extend(alternatives)
        suggestions = suggestions_from_alternatives(alt_candidates)
        last_hint = last_agent_suggestion(state.get("last_agent"))
        if last_hint and last_hint not in suggestions:
            suggestions.append(last_hint)

        emit_routing_event(
            RoutingEvent(
                event="routing_decision",
                thread_id=_thread_id_from_state(state),
                user_id=state.get("user_id"),
                source=state.get("source") or "nlp",
                intent_candidate=intent_key,
                intent_final=intent_final,
                confidence=confidence,
                next_node=next_node,
                fallback=fallback,
                duration_ms=duration_ms,
                extras={
                    "reason": decision.reason,
                    "alternatives": [
                        {"intent": alt.intent, "score": alt.score}
                        for alt in alt_candidates
                    ],
                },
            )
        )

        new_state: MaiDxoState = {
            **state,
            "intent": intent,
            "intent_candidate": intent_key,
            "intent_final": intent_final,
            "confidence": confidence,
            "route": "fallback" if fallback else "semantic",
            "phase": "semantic_router",
            "fallback": fallback,
            "next_node": next_node,
        }
        if fallback:
            new_state["suggestions"] = suggestions
        return new_state

    def fallback_node(state: MaiDxoState) -> MaiDxoState:
        suggestions = state.get("suggestions") or []
        text_lines = [
            "Damit ich zielgerichtet helfen kann, brauche ich noch ein paar Details.",
            "Wähle eine Option oder ergänze deine Beschreibung:" if suggestions else "Beschreibe bitte genauer, wobei du Unterstützung benötigst.",
        ]
        if suggestions:
            for item in suggestions:
                label = item.get("label") or item.get("intent") or "Option"
                text_lines.append(f"- {label}")
        message = "\n".join(text_lines)
        ai_msg = AIMessage(content=message)

        emit_routing_event(
            RoutingEvent(
                event="routing_fallback",
                thread_id=_thread_id_from_state(state),
                user_id=state.get("user_id"),
                source=state.get("source") or "nlp",
                intent_candidate=state.get("intent_candidate"),
                intent_final=None,
                confidence=state.get("confidence"),
                fallback=True,
                next_node="END",
                extras={"suggestions": suggestions},
            )
        )

        ui_event = {
            "type": "routing_suggestions",
            "suggestions": suggestions,
        }

        return {
            "messages": [ai_msg],
            "phase": "fallback",
            "fallback": True,
            "ui_event": ui_event,
            "next_node": "END",
        }

    def consult_lite_router_adapter(state: MaiDxoState) -> MaiDxoState:
        result = lite_router_node(state)
        route_val = (result.get("route") or "default").strip().lower() or "default"
        result["consult_route"] = route_val
        result["phase"] = "consult_lite_router"
        return result

    def consult_respond_adapter(state: MaiDxoState) -> MaiDxoState:
        result = consult_respond_node(state)
        result["phase"] = "consult_respond"
        return result

    chitchat_chain = RunnableLambda(lambda s: s.get("messages", [])) | llm_chitchat | RunnableLambda(
        lambda m: {"messages": [m if isinstance(m, AIMessage) else AIMessage(content=getattr(m, "content", str(m)))]}
    )

    builder.add_node("entry", wrap_node_with_logging(_GRAPH_NAME, "entry", entry_node))
    builder.add_node("legacy_router", wrap_node_with_logging(_GRAPH_NAME, "legacy_router", legacy_router_node))
    builder.add_node("button_dispatch", wrap_node_with_logging(_GRAPH_NAME, "button_dispatch", button_dispatch_node))
    builder.add_node("semantic_router", wrap_node_with_logging(_GRAPH_NAME, "semantic_router", semantic_router_node))
    builder.add_node("fallback", wrap_node_with_logging(_GRAPH_NAME, "fallback", fallback_node))
    builder.add_node("complexity_router", wrap_node_with_logging(_GRAPH_NAME, "complexity_router", complexity_router_node))
    builder.add_node("simple_response", wrap_node_with_logging(_GRAPH_NAME, "simple_response", simple_response_node))
    builder.add_node("chitchat", chitchat_chain)

    builder.add_node("consult_lite_router", wrap_node_with_logging(_GRAPH_NAME, "consult_lite_router", consult_lite_router_adapter))
    builder.add_node("consult_smalltalk", wrap_node_with_logging(_GRAPH_NAME, "consult_smalltalk", smalltalk_node))
    builder.add_node("consult_intake", wrap_node_with_logging(_GRAPH_NAME, "consult_intake", intake_node))
    builder.add_node("consult_profile", wrap_node_with_logging(_GRAPH_NAME, "consult_profile", profile_node))
    builder.add_node("consult_extract", wrap_node_with_logging(_GRAPH_NAME, "consult_extract", consult_extract_node))
    builder.add_node("consult_domain_router", wrap_node_with_logging(_GRAPH_NAME, "consult_domain_router", consult_domain_router_node))
    builder.add_node("consult_compute", wrap_node_with_logging(_GRAPH_NAME, "consult_compute", consult_compute_node))
    builder.add_node("consult_deterministic_calc", wrap_node_with_logging(_GRAPH_NAME, "consult_deterministic_calc", deterministic_calc_node))
    builder.add_node("consult_calc_agent", wrap_node_with_logging(_GRAPH_NAME, "consult_calc_agent", calc_agent_node))
    builder.add_node("consult_ask_missing", wrap_node_with_logging(_GRAPH_NAME, "consult_ask_missing", ask_missing_node))
    builder.add_node("consult_validate", wrap_node_with_logging(_GRAPH_NAME, "consult_validate", validate_node))
    builder.add_node("consult_prepare_query", wrap_node_with_logging(_GRAPH_NAME, "consult_prepare_query", consult_prepare_query_node))
    builder.add_node("consult_ltm", wrap_node_with_logging(_GRAPH_NAME, "consult_ltm", ltm_node))
    builder.add_node("consult_rag", wrap_node_with_logging(_GRAPH_NAME, "consult_rag", run_rag_node))
    builder.add_node("consult_recommend", wrap_node_with_logging(_GRAPH_NAME, "consult_recommend", recommend_node))
    builder.add_node("consult_validate_answer", wrap_node_with_logging(_GRAPH_NAME, "consult_validate_answer", validate_answer))
    builder.add_node("consult_explain", wrap_node_with_logging(_GRAPH_NAME, "consult_explain", explain_node))
    builder.add_node("consult_respond", wrap_node_with_logging(_GRAPH_NAME, "consult_respond", consult_respond_adapter))
    builder.add_node("consult_summarize", wrap_node_with_logging(_GRAPH_NAME, "consult_summarize", summarize_node))

    builder.set_entry_point("entry")

    def decide_entry(state: MaiDxoState) -> str:
        route = str(state.get("route") or "legacy").lower()
        if route not in {"legacy", "button", "semantic"}:
            route = "legacy"
        log_branch_decision(_GRAPH_NAME, "entry", "route", route, state)
        return route

    def decide_after_legacy(state: MaiDxoState) -> str:
        intent = state.get("intent") or "chitchat"
        branch = "consult" if intent == "consult" else "chitchat"
        log_branch_decision(_GRAPH_NAME, "legacy_router", "intent", branch, state)
        return branch

    def decide_after_semantic(state: MaiDxoState) -> str:
        branch = "fallback" if bool(state.get("fallback")) else "continue"
        log_branch_decision(_GRAPH_NAME, "semantic_router", "route", branch, state)
        return branch

    def decide_complexity(state: MaiDxoState) -> str:
        query_type = (state.get("query_type") or "complex").lower()
        branch = "simple" if query_type == "simple" else "complex"
        log_branch_decision(_GRAPH_NAME, "complexity_router", "query_type", branch, state)
        return branch

    builder.add_conditional_edges(
        "entry",
        decide_entry,
        {
            "legacy": "legacy_router",
            "button": "button_dispatch",
            "semantic": "semantic_router",
        },
    )
    builder.add_conditional_edges(
        "legacy_router",
        decide_after_legacy,
        {
            "consult": "consult_lite_router",
            "chitchat": "chitchat",
        },
    )
    builder.add_conditional_edges(
        "semantic_router",
        decide_after_semantic,
        {
            "fallback": "fallback",
            "continue": "complexity_router",
        },
    )
    builder.add_conditional_edges(
        "complexity_router",
        decide_complexity,
        {
            "simple": "simple_response",
            "complex": "consult_lite_router",
        },
    )

    builder.add_edge("button_dispatch", "consult_lite_router")
    builder.add_edge("simple_response", END)
    builder.add_edge("fallback", END)
    builder.add_edge("chitchat", END)

    builder.add_conditional_edges(
        "consult_lite_router",
        _decide_consult_route,
        {
            "smalltalk": "consult_smalltalk",
            "default": "consult_intake",
        },
    )
    builder.add_edge("consult_smalltalk", "consult_respond")
    builder.add_edge("consult_intake", "consult_profile")
    builder.add_edge("consult_profile", "consult_extract")
    builder.add_edge("consult_extract", "consult_domain_router")
    builder.add_edge("consult_domain_router", "consult_compute")
    builder.add_edge("consult_compute", "consult_deterministic_calc")
    builder.add_edge("consult_deterministic_calc", "consult_calc_agent")
    builder.add_edge("consult_calc_agent", "consult_ask_missing")
    builder.add_conditional_edges(
        "consult_ask_missing",
        _decide_after_ask,
        {
            "ask": "consult_respond",
            "ok": "consult_validate",
        },
    )
    builder.add_edge("consult_validate", "consult_prepare_query")
    builder.add_edge("consult_prepare_query", "consult_ltm")
    builder.add_edge("consult_ltm", "consult_rag")
    builder.add_conditional_edges(
        "consult_rag",
        _decide_after_rag,
        {
            "recommend": "consult_recommend",
            "explain": "consult_explain",
        },
    )
    builder.add_edge("consult_recommend", "consult_validate_answer")
    builder.add_edge("consult_validate_answer", "consult_respond")
    builder.add_edge("consult_explain", "consult_respond")
    builder.add_edge("consult_respond", "consult_summarize")
    builder.add_edge("consult_summarize", END)

    log.info("[mai_dxo] Graph bereit (Single-Graph Supervisor+Consult).")
    return builder


def build_supervisor_graph(llm: Optional[ChatOpenAI] = None) -> StateGraph:
    """Kompatibler Alias – historischer Name für den MAI-DXO-Graphen."""
    return build_mai_dxo_graph(llm)


__all__ = ["build_mai_dxo_graph", "build_supervisor_graph"]
