from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

import pytest
from langchain_core.messages.ai import AIMessageChunk
from langchain_core.messages import HumanMessage

from app.api.v1.endpoints import langgraph_v2 as endpoint_v2
from app.langgraph_v2.state import SealAIState

class FakeGraph:
    def __init__(self, events: List[Dict[str, Any]]) -> None:
        self._events = events

    async def astream_events(self, *_, **__) -> Any:
        for event in self._events:
            yield event

async def _collect_sse_payloads(req: endpoint_v2.LangGraphV2Request, **kwargs: Any) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    async for frame in endpoint_v2._event_stream_v2(req, **kwargs):
        if not frame:
            continue
        # frame is ALREADY a string (decrypted by _event_stream_v2 internally)
        # It can be bytes or str, but _event_stream_v2 yields str usually
        decoded_frame = frame.decode("utf-8") if isinstance(frame, bytes) else frame
        for line in decoded_frame.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                try:
                    data_json = line[5:].strip()
                    payloads.append(json.loads(data_json))
                except Exception:
                    pass
    return payloads

@pytest.mark.asyncio
async def test_streaming_flow_v2_payloads(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Setup mock events
    events = [
        {"event": "on_chat_model_stream", "name": "response_node", "data": {"chunk": AIMessageChunk(content="Hallo ")}},
        {"event": "on_chat_model_stream", "name": "response_node", "data": {"chunk": AIMessageChunk(content="Welt")}},
        {
            "event": "on_graph_end",
            "data": {"output": SealAIState(final_text="Hallo Welt")},
        },
    ]
    
    fake_graph = FakeGraph(events)
    
    # 2. Mock graph getter in endpoint module
    async def _mock_get_graph(*args, **kwargs):
        return fake_graph
    
    monkeypatch.setattr(endpoint_v2, "get_sealai_graph_v2", _mock_get_graph)
    
    # 3. Create request
    req = endpoint_v2.LangGraphV2Request(
        input="Hi",
        chat_id="ws-test-123",
    )
    
    # 4. Invoke the stream helper
    payloads = await _collect_sse_payloads(req, user_id="user-1")
    
    # 5. Verify results
    token_events = [p for p in payloads if p.get("type") == "token"]
    assert len(token_events) == 2
    assert [p.get("text") for p in token_events] == ["Hallo ", "Welt"]
    
    # Check for done event
    assert any(p.get("type") == "done" for p in payloads)
