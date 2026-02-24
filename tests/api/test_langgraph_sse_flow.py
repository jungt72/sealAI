from __future__ import annotations

import json
from typing import List, Tuple, Dict, Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.messages.ai import AIMessageChunk

from app.api.v1.endpoints import langgraph_v2 as endpoint_v2
from app.langgraph_v2.state import SealAIState

# Endpoint path
ENDPOINT = "/api/v1/langgraph/chat/v2"

class FakeGraph:
    def __init__(self, events: List[Dict[str, Any]]) -> None:
        self._events = events

    async def astream_events(self, *_, **__) -> Any:
        for event in self._events:
            yield event

def parse_sse_events(response_text: str) -> List[Tuple[str, dict]]:
    events: List[Tuple[str, dict]] = []
    current_event = None
    for line in response_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = json.loads(line.split(":", 1)[1].strip())
            events.append((current_event, payload))
    return events

def test_sse_flow_v2_mocked_graph(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from app.services.auth.dependencies import get_current_request_user, RequestUser
    
    mock_user = RequestUser(user_id="user-123", username="testuser", sub="user-123", roles=[])
    client.app.dependency_overrides[get_current_request_user] = lambda: mock_user
    
    try:
        # Prepare mocked graph events
        events = [
            {"event": "on_chat_model_stream", "name": "response_node", "data": {"chunk": AIMessageChunk(content="Hallo ")}},
            {"event": "on_chat_model_stream", "name": "response_node", "data": {"chunk": AIMessageChunk(content="Welt")}},
            {
                "event": "on_node_end",
                "name": "response_node",
                "data": {"output": SealAIState(final_text="Hallo Welt")},
            },
        ]
        
        fake_graph = FakeGraph(events)
        
        # Mock the graph getter in the endpoint module
        async def _mock_get_graph():
            return fake_graph
        
        monkeypatch.setattr(endpoint_v2, "get_sealai_graph_v2", _mock_get_graph)
        
        # Request body
        payload = {
            "input": "Hi",
            "chat_id": "thread-123",
        }
        
        # Call the endpoint
        response = client.post(ENDPOINT, json=payload, headers={"X-Request-Id": "req-123"})
        
        assert response.status_code == 200
        
        parsed_events = parse_sse_events(response.text)
        
        # Verify events
        tokens = [payload.get("text") for event, payload in parsed_events if event == "token"]
        assert tokens == ["Hallo ", "Welt"]
        
        # Verify tracing or other v2 events if they are emitted
        event_names = [event for event, payload in parsed_events]
        assert "token" in event_names
        assert "done" in event_names
    finally:
        client.app.dependency_overrides.clear()
