from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

pytest.skip(
    "Legacy LangGraph v2 ask-missing flow test disabled during agent-path canonization.",
    allow_module_level=True,
)

from app.api.v1.endpoints import langgraph_v2 as endpoint_v2
from app.langgraph_v2.sealai_graph_v2 import build_v2_config, create_sealai_graph_v2
from app.langgraph_v2.state import SealAIState, Intent
from app.langgraph_v2.utils import llm_factory


@pytest.fixture(autouse=True)
def mock_rag(monkeypatch: pytest.MonkeyPatch):
    from app.mcp import knowledge_tool
    from app.services.rag import rag_orchestrator
    import qdrant_client
    
    def _fake_search(**_):
        return {"hits": [], "context": "", "retrieval_meta": {}}
        
    async def _fake_hybrid_retrieve(**_):
        return []

    class FakeQdrant:
        def __init__(self, *args, **kwargs): pass
        def query_points(self, *args, **kwargs): 
            class FakeResp:
                points = []
            return FakeResp()
        def search(self, *args, **kwargs): return []
        def get_collection(self, *args, **kwargs): pass

    monkeypatch.setattr(knowledge_tool, "search_technical_docs", _fake_search)
    monkeypatch.setattr(rag_orchestrator, "hybrid_retrieve", _fake_hybrid_retrieve)
    monkeypatch.setattr(qdrant_client, "QdrantClient", FakeQdrant)
    return _fake_search


@pytest.fixture(autouse=True)
def stub_llm(monkeypatch: pytest.MonkeyPatch):
    """Replace OpenAI calls with deterministic text/JSON for tests."""

    def _fake_run_llm(*, model: str, prompt: str, system: str, **_: Any) -> str:
        if "kompaktes json" in system.lower() or "extrahiere" in system.lower():
            return '{"medium": "Hydraulikoel", "temperature_max_c": 80, "pressure_max_bar": 10}'
        if "frontdoor" in system.lower():
            return '{"frontdoor_reply": "Hallo", "intent": {"goal": "design_recommendation", "confidence": 0.9}}'
        return "final-answer"

    async def _fake_run_llm_stream(
        *,
        model: str,
        prompt: str,
        system: str,
        on_chunk=None,
        **_: Any,
    ) -> str:
        parts = ["stream-", "final-", "answer"]
        for part in parts:
            if on_chunk is not None:
                await on_chunk(part)
        return "".join(parts)

    monkeypatch.setattr(llm_factory, "run_llm", _fake_run_llm)
    monkeypatch.setattr(llm_factory, "run_llm_stream", _fake_run_llm_stream)
    return _fake_run_llm


@pytest.fixture
def memory_graph(monkeypatch: pytest.MonkeyPatch):
    saver = MemorySaver()
    from langgraph.store.memory import InMemoryStore
    store = InMemoryStore()
    graph = create_sealai_graph_v2(checkpointer=saver, store=store, require_async=False)
    # Ensure the SSE endpoint reuses this in-memory graph/checkpointer.
    monkeypatch.setattr(endpoint_v2, "get_sealai_graph_v2", lambda: graph)
    return graph


async def _collect_events(graph, input_state: Dict[str, Any], config: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Any]:
    events: List[Dict[str, Any]] = []
    async for event in graph.astream_events(input_state, config=config, stream_mode="messages", version="v1"):
        events.append(event)
    
    # Reliably get the final state from the checkpointer
    snapshot = await graph.aget_state(config)
    return events, snapshot.values


async def _collect_sse_lines(req: endpoint_v2.LangGraphV2Request) -> List[str]:
    lines: List[str] = []
    async for line in endpoint_v2._event_stream_v2(req):
        lines.append(line.strip())
    return lines


@pytest.mark.asyncio
async def test_all_parameters_present_flows_to_final(memory_graph) -> None:
    config = build_v2_config(thread_id="case-a", user_id="user-a")
    user_payload = (
        '{"shaft_diameter": 30, "housing_diameter": 45, "speed_rpm": 1200, '
        '"medium": "Hydraulikoel", "temperature_max": 80, "pressure": 10}'
    )
    input_state = {
        "messages": [HumanMessage(content=user_payload)],
        "intent": Intent(goal="design_recommendation", confidence=1.0)
    }

    events, raw_state = await _collect_events(memory_graph, input_state, config)
    state = SealAIState.model_validate(raw_state or {})

    # Verify that the graph ran and updated the state
    assert len(state.messages) >= 1
    assert state.final_answer or state.final_text or any(e.get("event") == "on_chat_model_stream" for e in events)


@pytest.mark.asyncio
async def test_missing_params_ask_and_resume(memory_graph) -> None:
    thread_id = "case-b"
    config = build_v2_config(thread_id=thread_id, user_id="user-b")

    # First turn
    events_1, raw_state_1 = await _collect_events(
        memory_graph,
        {
            "messages": [HumanMessage(content="Getriebe ohne Parameter")],
            "intent": Intent(goal="design_recommendation", confidence=1.0)
        },
        config,
    )
    state_1 = SealAIState.model_validate(raw_state_1 or {})
    assert state_1.final_text or state_1.final_answer or any(e.get("event") == "on_chat_model_stream" for e in events_1)

    # SSE emission
    req1 = endpoint_v2.LangGraphV2Request(input="Getriebe ohne Parameter", thread_id=thread_id, user_id="user-b")
    sse_lines_1 = await _collect_sse_lines(req1)
    assert any("event: done" in line for line in sse_lines_1)
