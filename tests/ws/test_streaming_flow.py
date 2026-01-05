from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from starlette.websockets import WebSocketState

from langchain_core.messages.ai import AIMessageChunk

from app.langgraph.compile import build_initial_state, build_stream_config, iter_langgraph_payloads


class DummyWebSocket:
    def __init__(self) -> None:
        self.sent: List[Dict[str, Any]] = []
        self.application_state = WebSocketState.CONNECTED

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


class FakeGraph:
    def __init__(self, events: List[Dict[str, Any]]) -> None:
        self._events = events

    async def astream_events(self, *_, **__) -> Any:
        for event in self._events:
            yield event


def test_streaming_flow_emits_multiple_tokens() -> None:
    payload = {
        "input": "Testprompt",
        "chat_id": "ws-test",
        "consent": True,
        "user_id": "user-1",
    }
    state = build_initial_state(payload, chat_id="ws-test", user_id="user-1", user_input="Testprompt")
    config = build_stream_config(thread_id="ws-test", user_id="user-1")

    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content="Hallo ")}},
        {"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content="Welt")}},
        {
            "event": "on_graph_end",
            "data": {"output": {"slots": {"final_answer": "Hallo Welt"}}},
        },
        {"event": "end"},
    ]

    graph = FakeGraph(events)

    async def _collect() -> list[Dict[str, Any]]:
        collected: list[Dict[str, Any]] = []
        async for payload in iter_langgraph_payloads(graph, state, config):
            collected.append(payload)
        return collected

    payloads = asyncio.run(_collect())

    token_events = [frame for frame in payloads if frame.get("type") == "token"]
    assert len(token_events) >= 2
    assert [frame.get("text") for frame in token_events[:2]] == ["Hallo ", "Welt"]
    assert any(frame.get("type") == "done" for frame in payloads)
