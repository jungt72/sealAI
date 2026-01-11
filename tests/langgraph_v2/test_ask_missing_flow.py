from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

pytest.skip(
    "ask-missing flow is covered by the legacy graph which is no longer wired into the v2 frontdoor/supervisor topology",
    allow_module_level=True,
)

from app.api.v1.endpoints import langgraph_v2 as endpoint_v2
from app.langgraph_v2.sealai_graph_v2 import build_v2_config, create_sealai_graph_v2
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils import llm_factory


@pytest.fixture(autouse=True)
def stub_llm(monkeypatch: pytest.MonkeyPatch):
    """Replace OpenAI calls with deterministic text/JSON for tests."""

    def _fake_run_llm(*, model: str, prompt: str, system: str, **_: Any) -> str:
        if "kompaktes json" in system.lower():
            return '{"summary": "stub", "coverage": 0.92, "missing": []}'
        return "final-answer"

    async def _fake_run_llm_stream(
        *,
        model: str,
        prompt: str,
        system: str,
        on_chunk=None,
        **_: Any,
    ) -> str:
        text = _fake_run_llm(model=model, prompt=prompt, system=system)
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
    graph = create_sealai_graph_v2(checkpointer=saver, require_async=False)
    # Ensure the SSE endpoint reuses this in-memory graph/checkpointer.
    monkeypatch.setattr(endpoint_v2, "get_sealai_graph_v2", lambda: graph)
    return graph


async def _collect_events(graph, input_state: Dict[str, Any], config: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Any]:
    events: List[Dict[str, Any]] = []
    final_state: Any = None
    async for event in graph.astream_events(input_state, config=config, stream_mode="messages", version="v1"):
        events.append(event)
        if event.get("event") == "on_graph_end":
            data = event.get("data") or {}
            final_state = data.get("output") or data.get("state") or final_state
    return events, final_state


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
    input_state = {"messages": [HumanMessage(content=user_payload)]}

    events, raw_state = await _collect_events(memory_graph, input_state, config)
    state = SealAIState.model_validate(raw_state or {})

    assert not state.awaiting_user_input
    assert state.ask_missing_request is None
    assert state.coverage_analysis is not None
    assert state.coverage_analysis.coverage_score >= 0.85
    assert state.final_prompt
    # on_graph_end should have been emitted exactly once
    assert sum(1 for e in events if e.get("event") == "on_graph_end") == 1


@pytest.mark.asyncio
async def test_missing_params_ask_and_resume(memory_graph) -> None:
    thread_id = "case-b"
    config = build_v2_config(thread_id=thread_id, user_id="user-b")

    # First turn: missing required technical parameters -> ask_missing
    events_1, raw_state_1 = await _collect_events(
        memory_graph,
        {"messages": [HumanMessage(content="Getriebe ohne Parameter")]},
        config,
    )
    state_1 = SealAIState.model_validate(raw_state_1 or {})
    assert state_1.awaiting_user_input is True
    assert state_1.ask_missing_request is not None
    assert state_1.ask_missing_scope == "technical"
    assert sum(1 for e in events_1 if e.get("event") == "on_graph_end") == 1

    # SSE emission: exactly one ask_missing + done
    req1 = endpoint_v2.LangGraphV2Request(input="Getriebe ohne Parameter", thread_id=thread_id, user_id="user-b")
    sse_lines_1 = await _collect_sse_lines(req1)
    assert any("event: ask_missing" in line for line in sse_lines_1)
    assert sse_lines_1[-1].startswith("event: done")

    # Second turn: provide the missing parameters on the same thread -> resume, complete
    answer_payload = (
        '{"shaft_diameter": 35, "housing_diameter": 50, "speed_rpm": 900, '
        '"medium": "Hydraulikoel", "temperature_max": 95, "pressure": 12}'
    )
    events_2, raw_state_2 = await _collect_events(
        memory_graph,
        {"messages": [HumanMessage(content=answer_payload)]},
        config,
    )
    state_2 = SealAIState.model_validate(raw_state_2 or {})
    assert state_2.awaiting_user_input is False
    assert state_2.coverage_analysis is not None
    assert state_2.coverage_analysis.coverage_score >= 0.85
    assert state_2.parameters.get("pressure") == 12
    assert state_2.final_prompt

    # SSE for the resume run: no ask_missing, ends with message/done
    req2 = endpoint_v2.LangGraphV2Request(input=answer_payload, thread_id=thread_id, user_id="user-b")
    sse_lines_2 = await _collect_sse_lines(req2)
    assert not any("event: ask_missing" in line for line in sse_lines_2)
    message_events = [line for line in sse_lines_2 if "event: message" in line]
    assert len(message_events) >= 1
    assert sse_lines_2[-1].startswith("event: done")
