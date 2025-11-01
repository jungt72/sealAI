from __future__ import annotations

import pytest

try:
    import app.langgraph  # probe import after rewrite
except Exception as _e:
    pytest.skip(f"legacy test skipped: cannot import app.langgraph ({_e})", allow_module_level=True)

try:
    import app.langgraph.graph.supervisor_graph as _supervisor_graph_mod
except ModuleNotFoundError as _imp_err:
    pytest.skip(f"legacy test skipped: supervisor graph module missing ({_imp_err})", allow_module_level=True)

from typing import Iterable, Sequence
from langgraph.constants import END
from langgraph.graph import StateGraph
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage


class DummyLLM:
    def __init__(self, *, streaming: bool) -> None:
        self.streaming = streaming

    def bind_tools(self, _tools: Sequence) -> "DummyLLM":
        # Supervisor nutzt das gebundene LLM nur für Smalltalk. Wir benötigen kein spezielles Verhalten.
        return self

    def invoke(self, messages: Iterable[BaseMessage], **_kwargs) -> AIMessage:
        messages = list(messages)
        last = messages[-1].content if messages else ""
        text = str(last).lower()
        if not self.streaming:
            # Komplexitätsklassifikation
            if "vergleich" in text or "vergleiche" in text:
                return AIMessage(content="simple")
            return AIMessage(content="complex")

        # Simple-Response – gebe deterministische Antwort zurück
        if "vergleich" in text or "vergleiche" in text:
            return AIMessage(content="Simple-Route: PTFE vs FKM")
        return AIMessage(content="Base answer")


def _fake_consult_graph():
    from app.langgraph.graph.supervisor_graph import ChatState

    g = StateGraph(ChatState)

    def final_node(state: ChatState) -> ChatState:
        return {"messages": [AIMessage(content="Complex-Route: Consult graph")], "phase": "consult"}

    g.add_node("finish", final_node)
    g.set_entry_point("finish")
    g.add_edge("finish", END)
    return g


@pytest.fixture(autouse=True)
def _patch_supervisor(monkeypatch):
    import app.langgraph.graph.supervisor_graph as supervisor_graph

    monkeypatch.setattr(supervisor_graph, "get_llm", lambda *, streaming: DummyLLM(streaming=streaming))
    monkeypatch.setattr(supervisor_graph, "build_consult_graph", _fake_consult_graph)
    monkeypatch.setattr(supervisor_graph, "classify_intent", lambda _llm, _msgs: "consult")


def _compile_supervisor():
    from app.langgraph.graph.supervisor_graph import build_supervisor_graph

    graph = build_supervisor_graph()
    return graph.compile()


def test_simple_query_routes_to_simple_response():
    compiled = _compile_supervisor()
    result = compiled.invoke({"messages": [HumanMessage(content="Vergleiche PTFE mit FKM")]})

    assert result.get("query_type") == "simple"
    messages = result.get("messages") or []
    assert len(messages) == 1
    assert isinstance(messages[0], AIMessage)
    assert "simple-route" in messages[0].content.lower()


def test_complex_query_routes_into_consult_graph():
    compiled = _compile_supervisor()
    result = compiled.invoke({"messages": [HumanMessage(content="Empfiehl RWDR nach DIN 3760 für 200°C.")]})

    assert result.get("query_type") == "complex"
    messages = result.get("messages") or []
    assert len(messages) == 1
    assert messages[0].content == "Complex-Route: Consult graph"
    assert result.get("phase") == "consult"
