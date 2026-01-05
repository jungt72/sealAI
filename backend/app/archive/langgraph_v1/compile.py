from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .utils.checkpointer import make_checkpointer
from .constants import CHECKPOINTER_NAMESPACE_MAIN
from .nodes.discovery_intake import discovery_intake
from .nodes.general_answer import general_answer_node
from .nodes.entry_frontend import entry_frontend
from .nodes.exit_response import exit_response
from .nodes.intent_classifier import intent_classifier_node
from .nodes.context_retrieval import context_retrieval
from .nodes.rwd_confirm import rwd_confirm_node
from .nodes.rwd_calculation import rwd_calculation_node
from .nodes.memory_bridge import memory_bridge_node
from .nodes.bedarfsanalyse_agent import bedarfsanalyse_node
from .nodes.supervisor_factory import supervisor_panel_node
from .nodes.nano_triage_node import nano_triage_node
from .nodes.intent_clarify import intent_clarify_node
from .nodes.smalltalk_agent import smalltalk_agent_node
from .nodes.human_escalation import human_escalation_node
from .nodes.product_recommender import product_recommender_node
from .nodes.error_handler import error_handler_node
from .nodes.memory_commit_node import memory_commit_node
from .nodes.quality_review import run_quality_review
from .state import IntentPrediction, MetaInfo, Routing, SealAIState
from app.services.context_state_store import get_context_state, merge_context_state

_CHECKPOINTER = make_checkpointer()
_ASYNC_CHECKPOINTER = make_checkpointer(require_async=True)
logger = logging.getLogger(__name__)

_TECHNICAL_DOMAINS: Set[str] = {"sealing", "dichtungstechnik"}
_NON_TECHNICAL_KINDS: Set[str] = {"smalltalk", "greeting", "meta", "other"}
_TECHNICAL_CONFIDENCE_THRESHOLD = 0.7  # Technical intents must be high-confidence.


def _ensure_async_ready(checkpointer: object) -> object:
    if hasattr(checkpointer, "aget_tuple") and callable(getattr(checkpointer, "aget_tuple")):
        return checkpointer
    return _ASYNC_CHECKPOINTER


def _is_technical_consulting(intent: Optional[IntentPrediction]) -> bool:
    """
    Returns True only for high-confidence technical intents.

    - Domain must explicitly be part of _TECHNICAL_DOMAINS (e.g. sealing/dichtungstechnik)
    - Kind must not describe smalltalk/greeting/meta intents
    - Confidence must reach the configured threshold (default: 0.7)
    """
    if not isinstance(intent, dict):
        return False

    domain = str(intent.get("domain") or "").strip().lower()
    if domain not in _TECHNICAL_DOMAINS:
        return False

    kind = str(intent.get("kind") or "").strip().lower()
    if kind in _NON_TECHNICAL_KINDS:
        return False

    try:
        confidence = float(intent.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return confidence >= _TECHNICAL_CONFIDENCE_THRESHOLD


def _warmup_ready(state: SealAIState) -> bool:
    warmup = state.get("warmup")
    if not isinstance(warmup, dict):
        slots = state.get("slots") if isinstance(state.get("slots"), dict) else {}
        warmup = slots.get("warmup") if isinstance(slots.get("warmup"), dict) else None
    if not isinstance(warmup, dict):
        return False
    return bool(warmup.get("ready_for_analysis"))


def _route_after_intent(state: SealAIState) -> str:
    slots = state.get("slots") or {}
    if str(slots.get("task_mode_hint") or "") == "simple_direct_output":
        return "context_retrieval"

    intent = state.get("intent")
    if _is_technical_consulting(intent):
        if slots.get("rapport_phase_done"):
            return "warmup_agent"
        return "rapport_agent"
    return "context_retrieval"


def _route_after_warmup(state: SealAIState) -> str:
    if _warmup_ready(state):
        return "memory_bridge"
    logger.debug("warmup_agent: ready flag fehlt – route erneut durch warmup.")
    return "warmup"


def _route_after_intent_classifier(state: SealAIState) -> str:
    if state.get("pending_intent_choice"):
        return "intent_clarify"
    intent = state.get("intent")
    if isinstance(intent, dict):
        intent_type = str(intent.get("type") or "").strip().lower()
        if intent_type in {"general", "general_answer"}:
            return "general"
        if intent_type in {"consulting", "consultation"}:
            return "consulting"
    return "consulting"


def _route_after_rwd_confirm(state: SealAIState) -> str:
    """
    Steuert den Pfad abhängig vom Coverage-/Phase-Ergebnis des rwd_confirm Nodes.

    - Phase "berechnung" → weiter zu rwd_calculation
    - sonst: Antwort aus rwd_confirm (Missing-Prompt) direkt an den Nutzer (exit_response)
    """
    phase = state.get("phase")
    if phase == "berechnung":
        return "rwd_calculation"
    return "exit_response"


def _route_after_rwd_calculation(state: SealAIState) -> str:
    """
    Nach der Berechnung nur weiter zum Supervisor, wenn wir in die Auswahl-Phase gelangt sind.
    Andernfalls den aktuellen Stand (z.B. fehlende Daten) an den Nutzer ausgeben.
    """
    phase = state.get("phase")
    if phase == "auswahl":
        return "supervisor_panel"
    return "exit_response"


def create_main_graph(*, checkpointer: Optional[object] = None, require_async: bool = False) -> CompiledStateGraph:
    """
    Refactored supervisor flow with 3-path architecture:
    - Fast-Track: nano_triage → smalltalk/general
    - Engineering: intent → entry → discovery → bedarfsanalyse → calculation → supervisor
    - Governance: quality_review → human_escalation → product_recommender
    """
    builder = StateGraph(SealAIState)

    # === Nodes ===
    # Fast-Track & Triage
    builder.add_node("nano_triage", nano_triage_node)
    builder.add_node("smalltalk_agent", smalltalk_agent_node)
    builder.add_node("intent_classifier", intent_classifier_node)
    builder.add_node("intent_clarify", intent_clarify_node)
    builder.add_node("general_answer", general_answer_node)
    
    # Engineering Flow
    builder.add_node("entry_frontend", entry_frontend)
    builder.add_node("discovery_intake", discovery_intake)
    builder.add_node("memory_bridge", memory_bridge_node)
    builder.add_node("bedarfsanalyse", bedarfsanalyse_node)
    builder.add_node("context_retrieval", context_retrieval)
    builder.add_node("rwd_confirm", rwd_confirm_node)
    builder.add_node("rwd_calculation", rwd_calculation_node)
    builder.add_node("supervisor_panel", supervisor_panel_node)
    
    # Governance & Output
    builder.add_node("quality_review", run_quality_review)
    builder.add_node("human_escalation", human_escalation_node)
    builder.add_node("product_recommender", product_recommender_node)
    builder.add_node("memory_commit", memory_commit_node)
    builder.add_node("exit_response", exit_response)
    builder.add_node("error_handler", error_handler_node)

    # === Edges ===
    # Fast-Track Path
    builder.add_edge(START, "nano_triage")
    builder.add_conditional_edges(
        "nano_triage",
        lambda s: s.get("routing", {}).get("nano_classification", "needs_llm"),
        {
            "smalltalk": "smalltalk_agent",
            "needs_llm": "intent_classifier"
        }
    )
    builder.add_edge("smalltalk_agent", "exit_response")
    
    # Intent Routing
    builder.add_conditional_edges(
        "intent_classifier",
        _route_after_intent_classifier,
        {
            "intent_clarify": "intent_clarify",
            "general": "general_answer",
            "consulting": "entry_frontend"
        }
    )
    # Klarifizierungsfrage → zurück zum Intent-Classifier (nutzt pending_intent_choice)
    builder.add_edge("intent_clarify", "intent_classifier")
    builder.add_edge("general_answer", "exit_response")
    
    # Engineering Loop (simplified - no rapport/warmup)
    builder.add_edge("entry_frontend", "discovery_intake")
    builder.add_edge("discovery_intake", "memory_bridge")
    builder.add_edge("memory_bridge", "bedarfsanalyse")
    builder.add_edge("bedarfsanalyse", "context_retrieval")
    builder.add_edge("context_retrieval", "rwd_confirm")
    builder.add_conditional_edges(
        "rwd_confirm",
        _route_after_rwd_confirm,
        {
            "rwd_calculation": "rwd_calculation",
            "exit_response": "exit_response",
        },
    )
    builder.add_conditional_edges(
        "rwd_calculation",
        _route_after_rwd_calculation,
        {
            "supervisor_panel": "supervisor_panel",
            "exit_response": "exit_response",
        },
    )
    
    # Governance Path
    builder.add_edge("supervisor_panel", "quality_review")
    builder.add_conditional_edges(
        "quality_review",
        lambda s: "supervisor_panel" if s.get("review_status") == "REJECTED" else "human_escalation",
        {
            "supervisor_panel": "supervisor_panel",  # self-correction loop
            "human_escalation": "human_escalation"
        }
    )
    builder.add_edge("human_escalation", "product_recommender")
    builder.add_edge("product_recommender", "memory_commit")
    builder.add_edge("memory_commit", "exit_response")
    builder.add_edge("exit_response", END)

    # Checkpointer
    if checkpointer is None:
        checkpointer = _ASYNC_CHECKPOINTER if require_async else _CHECKPOINTER
    elif require_async:
        checkpointer = _ensure_async_ready(checkpointer)

    return builder.compile(checkpointer=checkpointer)


_GRAPH_CACHE: Optional[CompiledStateGraph] = None


def _ensure_main_graph() -> CompiledStateGraph:
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None:
        _GRAPH_CACHE = create_main_graph(require_async=True)
    return _GRAPH_CACHE


def ensure_main_graph() -> CompiledStateGraph:
    """Return the cached main supervisor graph (async checkpointer ready)."""
    return _ensure_main_graph()


def _derive_graph_inputs(
    payload: Dict[str, Any],
    *,
    chat_override: str | None = None,
    user_override: str | None = None,
) -> Tuple[str, str, str]:
    """Extract the normalized user_input, chat_id and user_id from payload data."""
    user_input = str(
        payload.get("input")
        or payload.get("input_text")
        or payload.get("text")
        or payload.get("query")
        or payload.get("message")
        or ""
    ).strip()

    chat_id = chat_override
    if not chat_id:
        chat_id = str(
            payload.get("chat_id")
            or payload.get("thread_id")
            or payload.get("chatId")
            or "default"
        ).strip() or "default"

    user_id = user_override
    if not user_id:
        user_id = str(payload.get("user_id") or "api_user") or "api_user"
    return user_input, chat_id, user_id


def _resolve_graph_inputs(payload: Dict[str, Any], request: Request) -> Tuple[str, str, str]:
    """Return the normalized input text, chat_id, and user_id for a request."""
    chat_override = str(
        payload.get("chat_id")
        or payload.get("thread_id")
        or payload.get("chatId")
        or request.path_params.get("chat_id")
        or "default"
    ).strip() or "default"
    user_override = str(
        payload.get("user_id")
        or getattr(getattr(request.state, "user", None), "id", None)
        or request.headers.get("x-user-id")
        or "api_user"
    )
    return _derive_graph_inputs(payload, chat_override=chat_override, user_override=user_override)


def _chunk_text(text: str, *, size: int = 80) -> List[str]:
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + size)
        chunks.append(text[start:end])
        start = end
    return chunks


def _coerce_message_text(source: Any) -> Optional[str]:
    """Extract a readable text fragment from LC/LG objects, dicts, or primitives."""
    from langchain_core.messages import BaseMessage as _BaseMsg  # local import to avoid cycles

    if source is None:
        return None

    if isinstance(source, _BaseMsg):
        direct = _coerce_message_text(getattr(source, "content", None))
        if direct:
            return direct
        for attr in ("additional_kwargs", "response_metadata"):
            direct = _coerce_message_text(getattr(source, attr, None))
            if direct:
                return direct
        return None

    if isinstance(source, str):
        return source

    if isinstance(source, (int, float)):
        return str(source)

    if isinstance(source, dict):
        for key in ("text", "content", "answer", "value", "output", "delta"):
            if key not in source:
                continue
            candidate = _coerce_message_text(source[key])
            if candidate:
                return candidate
        return None

    if isinstance(source, (list, tuple)):
        parts: List[str] = []
        for item in source:
            piece = _coerce_message_text(item)
            if piece:
                parts.append(piece)
        return "".join(parts) if parts else None

    for attr in ("content", "text", "value", "delta"):
        attr_value = getattr(source, attr, None)
        if attr_value is None:
            continue
        candidate = _coerce_message_text(attr_value)
        if candidate:
            return candidate

    return None


def _extract_text_from_message(message: Any) -> Optional[str]:
    """Bevorzugt 'answer' aus JSON-ähnlichem Content, sonst rohen Text."""
    content = _coerce_message_text(message)
    if not isinstance(content, str) or not content:
        return None

    s = content.strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            obj = json.loads(s)
            ans = obj.get("answer")
            if isinstance(ans, str) and ans.strip():
                return ans
        except Exception:
            pass
    return content


def _map_event_payloads(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize LangGraph events into transport-neutral payload dictionaries."""
    if not isinstance(event, dict):
        return []

    kind = str(event.get("event") or "").strip()
    data = event.get("data")
    data_dict: Optional[Dict[str, Any]] = data if isinstance(data, dict) else None
    outputs: List[Dict[str, Any]] = []

    def _token_payload(text: str, role: str | None = None) -> Dict[str, Any]:
        base: Dict[str, Any] = {"type": "token", "event": "token", "text": text}
        if role:
            base["role"] = role
        return base

    if kind == "messages":
        messages: List[Any] = []
        if isinstance(data, list):
            messages = data
        elif isinstance(data_dict, dict):
            for key in ("messages", "data", "output"):
                candidate = data_dict.get(key)
                if isinstance(candidate, list):
                    messages = candidate
                    break
        elif data is not None:
            messages = [data]

        for message in messages or []:
            text = _extract_text_from_message(message)
            if not text:
                continue
            role = getattr(message, "role", None) or getattr(message, "type", None)
            role_text = str(role).strip() if isinstance(role, str) and role.strip() else None
            outputs.append(_token_payload(text, role_text))

    elif kind in {"on_chat_model_stream", "on_llm_stream"}:
        chunk_sources: List[Any] = []
        if isinstance(data_dict, dict):
            for key in ("chunk", "delta", "message", "content", "text"):
                candidate = data_dict.get(key)
                if candidate is not None:
                    chunk_sources.append(candidate)
        elif data is not None:
            chunk_sources.append(data)

        for chunk in chunk_sources:
            token = _extract_text_from_message(chunk)
            if token:
                role = getattr(chunk, "role", None) or getattr(chunk, "type", None)
                role_text = str(role).strip() if isinstance(role, str) and role else None
                outputs.append(_token_payload(token, role_text))
                break

    elif kind == "on_tool_end":
        tool_output = data_dict.get("output") if isinstance(data_dict, dict) else None
        if tool_output:
            outputs.append({"type": "tool", "event": "tool", "output": tool_output})

    elif kind == "error":
        if isinstance(data, dict):
            outputs.append({"type": "error", "event": "error", "message": data.get("message")})
        else:
            outputs.append({"type": "error", "event": "error", "message": str(data)})

    return outputs


async def iter_langgraph_payloads(
    graph: CompiledStateGraph,
    state: SealAIState,
    config: Dict[str, Any],
) -> AsyncIterator[Dict[str, Any]]:
    """Yield typed JSON payloads for each LangGraph event stream chunk."""
    final_state: Dict[str, Any] | None = None
    try:
        async for event in graph.astream_events(state, config=config, stream_mode="messages", version="v1"):
            if event.get("event") == "on_graph_end":
                data = event.get("data") or {}
                final_state = data.get("output") or data.get("state") or final_state
            for payload in _map_event_payloads(event):
                yield payload
            if event.get("event") == "on_graph_end":
                break
    except Exception as exc:  # pragma: no cover - bubbled to caller
        yield {"type": "error", "event": "error", "message": f"{type(exc).__name__}: {exc}"}
        return

    final_text = _resolve_final_answer(final_state or {})
    if final_text:
        for chunk in _chunk_text(final_text):
            yield {"type": "message", "event": "message", "text": chunk}
    else:
        yield {"type": "message", "event": "message", "text": ""}

    if final_state:
        meta_payload = {
            "type": "meta",
            "event": "meta",
            "slots": final_state.get("slots"),
            "routing": final_state.get("routing"),
            "meta": final_state.get("meta"),
        }
        yield meta_payload

    yield {"type": "done", "event": "done"}


def _parse_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(text, str):
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start : end + 1]
    try:
        obj = json.loads(snippet)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _looks_like_intent_signal(payload: Dict[str, Any]) -> bool:
    keys = {str(k).lower() for k in payload.keys()}
    if not keys:
        return False
    if not {"type", "confidence"}.issubset(keys):
        return False
    if "reason" not in keys and "task" not in keys:
        return False
    if keys & {"answer", "message", "text"}:
        return False
    return True


def _build_intent_meta_payload(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Internal meta, not user-facing."""
    sanitized = {str(k): v for k, v in signal.items()}
    return {
        "type": "meta",
        "event": "meta",
        "subtype": "intent_signal",
        "intent_signal": sanitized,
        "meta": {"intent_signal": sanitized},
        "internal": True,
    }


def _classify_internal_meta_from_message(message: Any) -> Optional[Dict[str, Any]]:
    text = _coerce_message_text(message)
    if not text:
        return None
    obj = _parse_json_from_text(text)
    if not obj or not _looks_like_intent_signal(obj):
        return None
    return _build_intent_meta_payload(obj)


def _classify_internal_meta_from_error(data: Any) -> Optional[Dict[str, Any]]:
    if isinstance(data, dict):
        candidates = []
        message = data.get("message")
        if message:
            candidates.append(str(message))
        error_payload = data.get("payload")
        if isinstance(error_payload, dict):
            candidates.append(json.dumps(error_payload))
        elif error_payload:
            candidates.append(str(error_payload))
    else:
        candidates = [str(data)]
    for candidate in candidates:
        obj = _parse_json_from_text(candidate)
        if obj and _looks_like_intent_signal(obj):
            return _build_intent_meta_payload(obj)
    return None


async def _request_payload(request: Request) -> Dict[str, Any]:
    cached = getattr(request.state, "langgraph_payload", None)
    if isinstance(cached, dict):
        return dict(cached)
    if request.method in {"POST", "PUT", "PATCH"}:
        try:
            data = await request.json()
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return dict(request.query_params)


def build_initial_state(payload: Dict[str, Any], *, chat_id: str, user_id: str, user_input: str) -> SealAIState:
    payload_context = payload.get("context_state")
    merged_context = get_context_state(user_id)
    if isinstance(payload_context, dict):
        merged_context.update(payload_context)
    merged_context = merge_context_state(user_id, merged_context)

    slots = {
        "user_query": user_input,
        "user_consent": bool(payload.get("consent")),
        "planner_mode": "expert_consulting",
        "context_state": merged_context,
    }
    return SealAIState(
        messages=[],
        slots=slots,
        context_state=merged_context,
        message_in=user_input,
        routing=Routing(),
        context_refs=[],
        meta=MetaInfo(thread_id=chat_id, user_id=user_id, trace_id=str(uuid4())),
    )


def _resolve_final_answer(state_like: Dict[str, Any]) -> str:
    slots = state_like.get("slots") if isinstance(state_like, dict) else None
    if isinstance(slots, dict):
        direct = slots.get("final_answer") or slots.get("candidate_answer")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
    messages = state_like.get("messages") if isinstance(state_like, dict) else None
    if isinstance(messages, list):
        for message in reversed(messages):
            text = _extract_text_from_message(message)
            if text:
                return text
    return ""


def _format_sse(event: Optional[str], data: Dict[str, Any]) -> bytes:
    buf = []
    if event:
        buf.append(f"event: {event}")
    buf.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    buf.append("")
    return ("\n".join(buf) + "\n").encode("utf-8")


async def stream_langgraph_events(
    graph: CompiledStateGraph,
    state: SealAIState,
    config: Dict[str, Any],
) -> AsyncIterator[bytes]:
    """Stream events from the graph as SSE tokens/tools/done events."""
    async for payload in iter_langgraph_payloads(graph, state, config):
        event_type = payload.get("event")
        data = {k: v for k, v in payload.items() if k != "event"}
        yield _format_sse(event_type, data)


async def run_langgraph_stream(request: Request):
    """
    POST/GET-kompatibler Stream-Endpunkt (ohne direkten FastAPI-Router-Decorator),
    nutzbar z.B. für /chat/stream.
    """
    payload = await _request_payload(request)
    user_input, chat_id, user_id = _resolve_graph_inputs(payload, request)
    if not user_input:
        raise HTTPException(status_code=400, detail="input empty")

    graph = ensure_main_graph()
    initial_state = build_initial_state(payload, chat_id=chat_id, user_id=user_id, user_input=user_input)
    config = build_stream_config(thread_id=chat_id, user_id=user_id)

    accepts = request.headers.get("accept", "")
    if request.url.path.endswith("/chat/stream") or "text/event-stream" in accepts:
        return StreamingResponse(stream_langgraph_events(graph, initial_state, config), media_type="text/event-stream")

    try:
        result = await graph.ainvoke(initial_state, config=config)
    except Exception as exc:  # pragma: no cover - defensive guardrail
        logger.exception("run_langgraph_stream: graph execution failed")
        return {
            "text": "Entschuldigung, es gab ein technisches Problem bei der Verarbeitung Ihrer Anfrage.",
            "error": f"{type(exc).__name__}: {exc}",
            "chat_id": chat_id,
        }

    final_text = ""
    if isinstance(result, dict):
        final_text = _resolve_final_answer(result)

    return {"text": final_text or "", "chat_id": chat_id}


def build_stream_config(*, thread_id: str, user_id: str, checkpoint_ns: str = CHECKPOINTER_NAMESPACE_MAIN) -> Dict[str, Any]:
    """Common LangGraph config for both streaming and blocking runs."""
    return {"configurable": {"thread_id": thread_id, "user_id": user_id, "checkpoint_ns": checkpoint_ns}}


__all__ = [
    "create_main_graph",
    "run_langgraph_stream",
    "ensure_main_graph",
    "build_initial_state",
    "stream_langgraph_events",
    "build_stream_config",
    "iter_langgraph_payloads",
]
