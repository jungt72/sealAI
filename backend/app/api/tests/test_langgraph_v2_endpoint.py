"""
Contract tests for the LangGraph v2 SSE endpoint internals.

Expected contract:
- `event: token` streams partial assistant text (`data.text`)
- `event: done` ends the stream (metadata in `data`)
- `event: error` is terminal and is followed by `done`
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure backend is on path (tests run from repo root in some setups).
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Minimal env defaults for settings to load (avoid import-time config failures).
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
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_expected_azp", "test-client")

from langchain_core.messages import AIMessage

from app.api.v1.endpoints import langgraph_v2 as endpoint  # noqa: E402


def _parse_sse_frames(frames: List[bytes]) -> List[Tuple[str, Dict[str, Any]]]:
    parsed: List[Tuple[str, Dict[str, Any]]] = []
    for chunk in frames:
        text = chunk.decode("utf-8").strip()
        if not text or text.startswith(":"):
            continue
        event_name = ""
        data_payload: Dict[str, Any] = {}
        for line in text.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_payload = json.loads(line.split(":", 1)[1].strip())
        if event_name:
            parsed.append((event_name, data_payload))
    return parsed


async def _collect(gen) -> List[bytes]:
    out: List[bytes] = []
    async for chunk in gen:
        out.append(chunk)
    return out


class DummyGraphTokens:
    checkpointer = object()

    def astream(self, _input: Any, config: Any = None, *, stream_mode: Any = None, **_kwargs: Any):
        async def gen():
            yield ("messages", ("Hallo", {"node": "final_answer_node"}))
            yield ("messages", (" Welt", {"node": "final_answer_node"}))
            yield ("values", {"final_text": "Hallo Welt", "phase": "final", "last_node": "final_answer_node"})

        return gen()


class DummyGraphNoTokens:
    checkpointer = object()

    def astream(self, _input: Any, config: Any = None, *, stream_mode: Any = None, **_kwargs: Any):
        async def gen():
            yield ("values", {"final_text": "Final Antwort", "phase": "final", "last_node": "response_node"})

        return gen()


class DummyGraphTokensWithFinalMessage:
    checkpointer = object()

    def astream(self, _input: Any, config: Any = None, *, stream_mode: Any = None, **_kwargs: Any):
        async def gen():
            yield ("messages", ("Hallo", {"node": "final_answer_node"}))
            yield ("messages", (" Welt", {"node": "final_answer_node"}))
            yield ("messages", (AIMessage(content="Hallo Welt"), {"node": "final_answer_node"}))
            yield ("values", {"final_text": "Hallo Welt", "phase": "final", "last_node": "final_answer_node"})

        return gen()


class DummyGraphError:
    checkpointer = object()

    def astream(self, _input: Any, config: Any = None, *, stream_mode: Any = None, **_kwargs: Any):
        async def gen():
            raise RuntimeError("dummy graph error")
            yield  # pragma: no cover

        return gen()


def test_event_stream_v2_streams_tokens_and_done(monkeypatch):
    async def _dummy_graph():
        return DummyGraphTokens()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload in events if evt == "token"]
    assert "".join(tokens) == "Hallo Welt"

    done_events = [payload for evt, payload in events if evt == "done"]
    assert len(done_events) == 1
    assert done_events[0]["type"] == "done"


def test_event_stream_v2_fallback_chunks_final_text(monkeypatch):
    async def _dummy_graph():
        return DummyGraphNoTokens()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload in events if evt == "token"]
    assert "".join(tokens) == "Final Antwort"
    assert len([1 for evt, _ in events if evt == "done"]) == 1


def test_event_stream_v2_emits_error_then_done(monkeypatch):
    async def _dummy_graph():
        return DummyGraphError()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    assert [evt for evt, _ in events].count("error") == 1
    assert [evt for evt, _ in events].count("done") == 1


def test_event_stream_v2_ignores_full_message_after_chunks(monkeypatch):
    async def _dummy_graph():
        return DummyGraphTokensWithFinalMessage()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload in events if evt == "token"]
    assert "".join(tokens) == "Hallo Welt"
