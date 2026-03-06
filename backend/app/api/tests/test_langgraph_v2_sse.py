from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure backend is on path
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Minimal env defaults for settings to load
os.environ.setdefault("postgres_user", "test")
os.environ.setdefault("postgres_password", "test")
os.environ.setdefault("postgres_host", "localhost")
os.environ.setdefault("postgres_port", "5432")
os.environ.setdefault("postgres_db", "testdb")
os.environ.setdefault("database_url", "postgresql+asyncpg://test:test@localhost:5432/testdb")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/testdb")
os.environ.setdefault("openai_api_key", "sk-test")
os.environ.setdefault("qdrant_url", "http://localhost:6333")
os.environ.setdefault("qdrant_collection", "test")
os.environ.setdefault("redis_url", "redis://localhost:6379/0")
os.environ.setdefault("nextauth_url", "http://localhost:3000")
os.environ.setdefault("nextauth_secret", "test-secret")
os.environ.setdefault("keycloak_issuer", "http://localhost/realms/test")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_client_id", "test-client")
os.environ.setdefault("keycloak_client_secret", "test-secret")
os.environ.setdefault("keycloak_expected_azp", "test-client")

from app.api.v1.endpoints import langgraph_v2 as endpoint  # noqa: E402
from app.langgraph_v2.state import SealAIState  # noqa: E402
from langchain_core.messages.ai import AIMessageChunk  # noqa: E402


class _FakeRequest:
    async def is_disconnected(self) -> bool:
        return False


class _FakeGraph:
    def __init__(self, events):
        self._events = events

    def astream_events(self, _state_input, config=None, version="v2"):
        async def _gen():
            for event in self._events:
                yield event

        return _gen()


def _parse_sse_events(frames: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in frames.split("\n\n"):
        if not block.strip():
            continue
        event_name = ""
        payload: dict[str, Any] | None = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data: "):
                payload = json.loads(line.split(":", 1)[1].strip())
        if event_name and isinstance(payload, dict):
            events.append((event_name, payload))
    return events


def test_format_sse_frame_is_valid():
    frame = endpoint._format_sse("token", {"type": "token", "text": "Hallo"}, event_id="msg-1:1")
    decoded = frame.decode("utf-8")
    assert decoded.startswith("id: msg-1:1\n")
    assert "\nevent: token\n" in decoded
    assert "\ndata: " in decoded
    assert decoded.endswith("\n\n")

    id_line = [line for line in decoded.splitlines() if line.startswith("id:")][0]
    assert id_line == "id: msg-1:1"

    payload_line = [line for line in decoded.splitlines() if line.startswith("data:")][0]
    payload = json.loads(payload_line.split(":", 1)[1].strip())
    assert payload["type"] == "token"
    assert payload["text"] == "Hallo"


def test_format_sse_multiline_payload_stays_single_data_line():
    frame = endpoint._format_sse(
        "token",
        {"type": "token", "text": "Line 1\nLine 2\nLine 3"},
        event_id="msg-1:2",
    )
    decoded = frame.decode("utf-8")
    data_lines = [line for line in decoded.splitlines() if line.startswith("data:")]
    assert len(data_lines) == 1
    payload = json.loads(data_lines[0].split(":", 1)[1].strip())
    assert payload["type"] == "token"
    assert payload["text"] == "Line 1\nLine 2\nLine 3"


def test_event_multiplexer_done_carries_final_text_from_terminal_patch():
    async def _collect():
        initial_state = SealAIState(conversation={"thread_id": "chat-1", "user_id": "user-1", "messages": []})
        events = [
            {
                "event": "on_node_end",
                "name": "node_finalize",
                "metadata": {"run_id": "run-1"},
                "data": {
                    "patch": {
                        "final_text": "Kyrolon ist ein PTFE-Compound.",
                        "final_answer": "Kyrolon ist ein PTFE-Compound.",
                        "messages": [{"role": "assistant", "content": "Kyrolon ist ein PTFE-Compound."}],
                        "reasoning": {"phase": "answer", "last_node": "node_finalize"},
                    }
                },
            }
        ]
        chunks: list[str] = []
        async for chunk in endpoint.event_multiplexer(
            _FakeGraph(events),
            initial_state,
            {"metadata": {"run_id": "run-1"}},
            _FakeRequest(),
        ):
            chunks.append(chunk)
        return "".join(chunks)

    text = __import__("asyncio").run(_collect())
    assert "event: token" in text
    assert "event: done" in text

    done_payload = None
    for block in text.split("\n\n"):
        if "event: done" not in block:
            continue
        for line in block.splitlines():
            if line.startswith("data: "):
                done_payload = json.loads(line.split(":", 1)[1].strip())
                break
    assert done_payload is not None
    assert done_payload["final_text"] == "Kyrolon ist ein PTFE-Compound."
    assert done_payload["final_answer"] == "Kyrolon ist ein PTFE-Compound."


def test_event_multiplexer_does_not_stream_draft_tokens_for_material_research() -> None:
    async def _collect():
        initial_state = SealAIState(
            conversation={"thread_id": "chat-draft", "user_id": "user-1", "messages": []},
            reasoning={"flags": {"frontdoor_intent_category": "MATERIAL_RESEARCH"}},
        )
        events = [
            {
                "event": "on_chat_model_stream",
                "name": "ChatOpenAI",
                "tags": ["langsmith:graph:node:node_draft_answer"],
                "metadata": {"run_id": "run-1", "langgraph_node": "node_draft_answer"},
                "data": {"chunk": AIMessageChunk(content="Kyrolon ")},
            },
            {
                "event": "on_chat_model_stream",
                "name": "ChatOpenAI",
                "tags": ["langsmith:graph:node:node_draft_answer"],
                "metadata": {"run_id": "run-1", "langgraph_node": "node_draft_answer"},
                "data": {"chunk": AIMessageChunk(content="ist ein PTFE-Compound.")},
            },
            {
                "event": "on_node_end",
                "name": "node_finalize",
                "metadata": {"run_id": "run-1"},
                "data": {
                    "patch": {
                        "final_text": "Kyrolon ist ein PTFE-Compound.",
                        "final_answer": "Kyrolon ist ein PTFE-Compound.",
                        "reasoning": {"phase": "answer", "last_node": "node_finalize"},
                    }
                },
            },
        ]
        chunks: list[str] = []
        async for chunk in endpoint.event_multiplexer(
            _FakeGraph(events),
            initial_state,
            {"metadata": {"run_id": "run-1"}},
            _FakeRequest(),
        ):
            chunks.append(chunk)
        return "".join(chunks)

    frames = __import__("asyncio").run(_collect())
    events = _parse_sse_events(frames)
    names = [event_name for event_name, _payload in events]
    token_texts = [payload["text"] for event_name, payload in events if event_name == "token"]

    assert "Kyrolon " not in token_texts
    assert "ist ein PTFE-Compound." not in token_texts
    assert "Kyrolon ist ein PTFE-Compound." in token_texts
    assert names.index("token") < names.index("done")


def test_event_multiplexer_does_not_stream_draft_tokens_for_engineering_path() -> None:
    async def _collect():
        initial_state = SealAIState(
            conversation={"thread_id": "chat-engineering", "user_id": "user-1", "messages": []},
            reasoning={"flags": {"frontdoor_intent_category": "ENGINEERING_CALCULATION"}},
        )
        events = [
            {
                "event": "on_chat_model_stream",
                "name": "ChatOpenAI",
                "tags": ["langsmith:graph:node:node_draft_answer"],
                "metadata": {"run_id": "run-1", "langgraph_node": "node_draft_answer"},
                "data": {"chunk": AIMessageChunk(content="Should stay hidden")},
            },
            {
                "event": "on_node_end",
                "name": "node_finalize",
                "metadata": {"run_id": "run-1"},
                "data": {
                    "patch": {
                        "final_text": "Final engineering answer",
                        "final_answer": "Final engineering answer",
                        "reasoning": {"phase": "answer", "last_node": "node_finalize"},
                    }
                },
            },
        ]
        chunks: list[str] = []
        async for chunk in endpoint.event_multiplexer(
            _FakeGraph(events),
            initial_state,
            {"metadata": {"run_id": "run-1"}},
            _FakeRequest(),
        ):
            chunks.append(chunk)
        return "".join(chunks)

    frames = __import__("asyncio").run(_collect())
    events = _parse_sse_events(frames)
    token_texts = [payload["text"] for event_name, payload in events if event_name == "token"]

    assert "Should stay hidden" not in token_texts
    assert "Final engineering answer" in token_texts
