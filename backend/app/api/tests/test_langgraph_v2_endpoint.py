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


def _parse_sse_frames(frames: List[bytes]) -> List[Tuple[str, Dict[str, Any], str | None]]:
    parsed: List[Tuple[str, Dict[str, Any], str | None]] = []
    for chunk in frames:
        text = chunk.decode("utf-8").strip()
        if not text or text.startswith(":"):
            continue
        event_name = ""
        event_id = None
        data_payload: Dict[str, Any] = {}
        for line in text.splitlines():
            if line.startswith("id:"):
                event_id = line.split(":", 1)[1].strip()
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_payload = json.loads(line.split(":", 1)[1].strip())
        if event_name:
            parsed.append((event_name, data_payload, event_id))
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


class DummyGraphConfirmCheckpoint:
    checkpointer = object()

    def astream(self, _input: Any, config: Any = None, *, stream_mode: Any = None, **_kwargs: Any):
        async def gen():
            yield (
                "values",
                {
                    "phase": "confirm",
                    "last_node": "confirm_checkpoint_node",
                    "pending_action": "RUN_PANEL_NORMS_RAG",
                    "awaiting_user_confirmation": True,
                    "user_id": "user-1",
                    "thread_id": "chat-1",
                },
            )

        return gen()


def test_event_stream_v2_streams_tokens_and_done(monkeypatch):
    async def _dummy_graph():
        return DummyGraphTokens()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload, _ in events if evt == "token"]
    assert "".join(tokens) == "Hallo Welt"

    done_events = [payload for evt, payload, _ in events if evt == "done"]
    assert len(done_events) == 1
    assert done_events[0]["type"] == "done"


def test_event_stream_v2_includes_event_ids(monkeypatch):
    async def _dummy_graph():
        return DummyGraphTokens()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test", client_msg_id="msg-1")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    token_ids = [event_id for evt, _, event_id in events if evt == "token"]
    done_ids = [event_id for evt, _, event_id in events if evt == "done"]
    assert token_ids
    assert all(event_id for event_id in token_ids)
    assert done_ids
    assert all(event_id for event_id in done_ids)


def test_event_stream_v2_fallback_chunks_final_text(monkeypatch):
    async def _dummy_graph():
        return DummyGraphNoTokens()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload, _ in events if evt == "token"]
    assert "".join(tokens) == "Final Antwort"
    assert len([1 for evt, _, _ in events if evt == "done"]) == 1


def test_event_stream_v2_emits_error_then_done(monkeypatch):
    async def _dummy_graph():
        return DummyGraphError()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    assert [evt for evt, _, _ in events].count("error") == 1
    assert [evt for evt, _, _ in events].count("done") == 1


def test_event_stream_v2_ignores_full_message_after_chunks(monkeypatch):
    async def _dummy_graph():
        return DummyGraphTokensWithFinalMessage()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload, _ in events if evt == "token"]
    assert "".join(tokens) == "Hallo Welt"


def test_event_stream_v2_emits_checkpoint_required(monkeypatch):
    async def _dummy_graph():
        return DummyGraphConfirmCheckpoint()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    assert any(evt == "checkpoint_required" for evt, _, _ in events)


def test_claim_client_msg_id_deduplicates(monkeypatch):
    class DummyRedis:
        def __init__(self):
            self.seen = set()

        async def set(self, key, value, nx=True, ex=None):
            if key in self.seen:
                return None
            self.seen.add(key)
            return True

    client = DummyRedis()

    async def _dummy_client():
        return client

    monkeypatch.setattr(endpoint, "_get_dedup_redis", _dummy_client)

    first = asyncio.run(
        endpoint._claim_client_msg_id(
            user_id="user-1",
            chat_id="chat-1",
            client_msg_id="msg-1",
        )
    )
    second = asyncio.run(
        endpoint._claim_client_msg_id(
            user_id="user-1",
            chat_id="chat-1",
            client_msg_id="msg-1",
        )
    )
    assert first is True
    assert second is False
