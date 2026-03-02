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
from types import SimpleNamespace
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
from langchain_core.messages.ai import AIMessageChunk

from app.api.v1.endpoints import langgraph_v2 as endpoint  # noqa: E402
from app.services.auth.dependencies import RequestUser  # noqa: E402


def _parse_sse_frames(frames: List[Any]) -> List[Tuple[str, Dict[str, Any], str | None]]:
    parsed: List[Tuple[str, Dict[str, Any], str | None]] = []
    for chunk in frames:
        text = chunk.decode("utf-8").strip() if isinstance(chunk, (bytes, bytearray)) else str(chunk).strip()
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


async def _collect(gen) -> List[Any]:
    out: List[Any] = []
    async for chunk in gen:
        out.append(chunk)
    return out


class _Snapshot:
    def __init__(
        self,
        values: Dict[str, Any] | None = None,
        *,
        next_nodes: List[Any] | None = None,
        config: Dict[str, Any] | None = None,
    ):
        self.values = values or {}
        self.next: List[Any] = list(next_nodes or [])
        self.config: Dict[str, Any] = config or {}


class DummyGraphTokens:
    checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot()

    def astream(self, _input: Any, config: Any = None, *, stream_mode: Any = None, **_kwargs: Any):
        async def gen():
            yield ("messages", ("Hallo", {"node": "final_answer_node"}))
            yield ("messages", (" Welt", {"node": "final_answer_node"}))
            yield ("values", {"final_text": "Hallo Welt", "phase": "final", "last_node": "final_answer_node"})

        return gen()


class DummyGraphNoTokens:
    checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot()

    def astream(self, _input: Any, config: Any = None, *, stream_mode: Any = None, **_kwargs: Any):
        async def gen():
            yield ("values", {"final_text": "Final Antwort", "phase": "final", "last_node": "response_node"})

        return gen()


class DummyGraphTokensWithFinalMessage:
    checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot()

    def astream(self, _input: Any, config: Any = None, *, stream_mode: Any = None, **_kwargs: Any):
        async def gen():
            yield ("messages", ("Hallo", {"node": "final_answer_node"}))
            yield ("messages", (" Welt", {"node": "final_answer_node"}))
            yield ("messages", (AIMessage(content="Hallo Welt"), {"node": "final_answer_node"}))
            yield ("values", {"final_text": "Hallo Welt", "phase": "final", "last_node": "final_answer_node"})

        return gen()


class DummyGraphTokensWithStructuredLeak:
    checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot()

    def astream(self, _input: Any, config: Any = None, *, stream_mode: Any = None, **_kwargs: Any):
        async def gen():
            yield ("messages", ('{"intent_category":"MATERIAL_RESEARCH"}', {"node": "frontdoor_discovery_node"}))
            yield ("messages", ({"intent_category": "MATERIAL_RESEARCH"}, {"node": "response_node"}))
            yield ("messages", ("Hallo", {"node": "final_answer_node"}))
            yield ("messages", (" Welt", {"node": "final_answer_node"}))
            yield ("values", {"final_text": "Hallo Welt", "phase": "final", "last_node": "final_answer_node"})

        return gen()


class DummyGraphError:
    checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot()

    def astream(self, _input: Any, config: Any = None, *, stream_mode: Any = None, **_kwargs: Any):
        async def gen():
            raise RuntimeError("dummy graph error")
            yield  # pragma: no cover

        return gen()


class DummyGraphConfirmCheckpoint:
    checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot()

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


class DummyGraphAstreamEventsTokenOnly:
    checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot(
            {
                "final_text": "Hallo Welt",
                "phase": "final",
                "last_node": "final_answer_node",
            }
        )

    def astream_events(self, _input: Any, config: Any = None, **_kwargs: Any):
        async def gen():
            yield {
                "event": "on_chat_model_stream",
                "name": "frontdoor_discovery_node",
                "data": {"chunk": AIMessageChunk(content='{"intent_category":"MATERIAL_RESEARCH"}')},
            }
            yield {
                "event": "on_chat_model_stream",
                "name": "final_answer_node",
                "data": {"chunk": AIMessageChunk(content="Hallo")},
            }
            yield {
                "event": "on_chain_stream",
                "name": "final_answer_node",
                "data": {
                    "output": {
                        "final_text": "SHOULD_NOT_STREAM",
                        "phase": "final",
                        "last_node": "final_answer_node",
                    }
                },
            }
            yield {
                "event": "on_chat_model_stream",
                "name": "final_answer_node",
                "data": {"chunk": AIMessageChunk(content=" Welt")},
            }
            yield {
                "event": "on_node_end",
                "name": "final_answer_node",
                "data": {
                    "output": {
                        "final_text": "Hallo Welt",
                        "phase": "final",
                        "last_node": "final_answer_node",
                    }
                },
            }

        return gen()


class DummyGraphAstreamEventsPatchFinalText:
    checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot(
            {
                "messages": [AIMessage(content="PREVIOUS RESPONSE")],
                "phase": "final",
                "last_node": "answer_subgraph_node",
            }
        )

    def astream_events(self, _input: Any, config: Any = None, **_kwargs: Any):
        async def gen():
            yield {
                "event": "on_chain_stream",
                "name": "answer_subgraph_node",
                "data": {
                    "chunk": {
                        "chunk_type": "final_answer",
                        "final_text": "NEW RFQ TEXT",
                    }
                },
            }
            yield {
                "event": "on_node_end",
                "name": "answer_subgraph_node",
                "data": {"output": {"last_node": "answer_subgraph_node", "phase": "final"}},
            }

        return gen()


class DummyGraphAstreamEventsConversationalSnapshot:
    checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot(
            {
                "final_text": "Hallo Welt",
                "phase": "final",
                "last_node": "conversational_rag_node",
            }
        )

    def astream_events(self, _input: Any, config: Any = None, **_kwargs: Any):
        async def gen():
            yield {
                "event": "on_chat_model_stream",
                "name": "conversational_rag_node",
                "data": {"chunk": AIMessageChunk(content="Hallo")},
            }
            yield {
                "event": "on_chat_model_stream",
                "name": "conversational_rag_node",
                "data": {"chunk": AIMessageChunk(content=" Welt")},
            }
            yield {
                "event": "on_node_end",
                "name": "conversational_rag_node",
                "data": {
                    "output": {
                        "final_text": "Hallo Welt",
                        "phase": "final",
                        "last_node": "conversational_rag_node",
                    }
                },
            }

        return gen()


class DummyGraphStickyLiveCalcTile:
    checkpointer = object()

    async def get_state(self, _config: Any):
        return _Snapshot(
            {
                "live_calc_tile": {
                    "status": "warning",
                    "pv_warning": True,
                }
            }
        )

    async def aget_state(self, _config: Any):
        return _Snapshot({"final_text": "done", "phase": "final", "last_node": "node_p6_generate_pdf"})

    def astream_events(self, _input: Any, config: Any = None, **_kwargs: Any):
        async def gen():
            yield {
                "event": "on_node_end",
                "name": "calculator_node",
                "data": {
                    "output": {
                        "parameters": {"temperature_C": 80},
                        "phase": "aggregation",
                        "last_node": "calculator_node",
                    }
                },
            }
            yield {
                "event": "on_node_end",
                "name": "node_p6_generate_pdf",
                "data": {
                    "output": {
                        "rfq_ready": True,
                        "phase": "final",
                        "last_node": "node_p6_generate_pdf",
                    }
                },
            }

        return gen()


class DummyGraphInterrupted:
    checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot(
            {
                "phase": "aggregation",
                "last_node": "reducer_node",
                "requires_human_review": True,
            },
            next_nodes=["human_review_node"],
            config={"configurable": {"checkpoint_id": "chk-hitl-1"}},
        )

    def astream(self, _input: Any, config: Any = None, *, stream_mode: Any = None, **_kwargs: Any):
        async def gen():
            yield ("values", {"phase": "aggregation", "last_node": "reducer_node"})

        return gen()


class DummyGraphResume:
    checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot({"confirm_checkpoint_id": "chk-resume-1"})

    async def ainvoke(self, _input: Any, config: Any = None):
        return {
            "phase": "final",
            "last_node": "final_answer_node",
            "final_text": "Resumed",
            "requires_human_review": False,
        }


def test_langgraph_v2_request_coerces_nullable_and_mapping_fields():
    req = endpoint.LangGraphV2Request(
        input=None,  # type: ignore[arg-type]
        chat_id=None,  # type: ignore[arg-type]
        client_msg_id="   ",
        metadata=None,  # type: ignore[arg-type]
        client_context=[],  # type: ignore[arg-type]
    )
    assert req.input == ""
    assert req.chat_id != "default"
    assert len(req.chat_id) == 32
    assert req.client_msg_id is None
    assert req.metadata == {}
    assert req.client_context == {}


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


def test_event_stream_v2_emits_interrupt_event(monkeypatch):
    async def _dummy_graph():
        return DummyGraphInterrupted()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-interrupt")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-int")))
    events = _parse_sse_frames(chunks)

    interrupt_events = [payload for evt, payload, _ in events if evt == "interrupt"]
    assert len(interrupt_events) == 1
    assert interrupt_events[0]["thread_id"] == "chat-interrupt"
    assert interrupt_events[0]["checkpoint_id"] == "chk-hitl-1"
    assert interrupt_events[0]["required_action"] == "approve_specification"


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


def test_event_stream_v2_filters_structured_payloads_in_astream(monkeypatch):
    async def _dummy_graph():
        return DummyGraphTokensWithStructuredLeak()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload, _ in events if evt == "token"]
    assert "".join(tokens) == "Hallo Welt"
    assert all("intent_category" not in text for text in tokens)


def test_event_stream_v2_emits_checkpoint_required(monkeypatch):
    async def _dummy_graph():
        return DummyGraphConfirmCheckpoint()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    assert any(evt == "checkpoint_required" for evt, _, _ in events)


def test_event_stream_v2_astream_events_emits_chat_chunk_tokens_only(monkeypatch):
    async def _dummy_graph():
        return DummyGraphAstreamEventsTokenOnly()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload, _ in events if evt == "token"]
    assert "".join(tokens) == "Hallo Welt"
    assert all("SHOULD_NOT_STREAM" not in text for text in tokens)
    assert all("intent_category" not in text for text in tokens)


def test_event_stream_v2_prefers_patch_final_text_over_stale_messages(monkeypatch):
    async def _dummy_graph():
        return DummyGraphAstreamEventsPatchFinalText()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload, _ in events if evt == "token"]
    assert "".join(tokens) == "NEW RFQ TEXT"
    assert all("PREVIOUS RESPONSE" not in text for text in tokens)


def test_event_stream_v2_does_not_duplicate_streamed_tokens_from_snapshot_final_text(monkeypatch):
    async def _dummy_graph():
        return DummyGraphAstreamEventsConversationalSnapshot()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload, _ in events if evt == "token"]
    assert tokens == ["Hallo", " Welt"]
    assert "".join(tokens) == "Hallo Welt"


def test_event_stream_v2_emits_terminal_message_from_final_state(monkeypatch):
    async def _dummy_graph():
        return DummyGraphNoTokens()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    messages = [payload for evt, payload, _ in events if evt == "message"]
    assert len(messages) == 1
    assert messages[0]["type"] == "message"
    assert messages[0]["text"] == "Final Antwort"
    assert messages[0]["replace"] is True


def test_event_stream_v2_injects_sticky_live_calc_tile_into_state_updates(monkeypatch):
    async def _dummy_graph():
        return DummyGraphStickyLiveCalcTile()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(endpoint._event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    state_updates = [payload for evt, payload, _ in events if evt == "state_update"]
    assert state_updates
    for payload in state_updates:
        data = payload.get("data", {})
        tile = data.get("live_calc_tile")
        assert isinstance(tile, dict)
        assert tile
        assert tile.get("status") == "warning"


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


def test_resume_run_endpoint_uses_command_resume(monkeypatch):
    async def _dummy_build_graph_config(**_kwargs):
        return DummyGraphResume(), {}

    monkeypatch.setattr(endpoint, "_build_graph_config", _dummy_build_graph_config)

    body = endpoint.HITLResumeRequest(
        checkpoint_id="chk-resume-1",
        command={"action": "approve"},
    )
    user = RequestUser(
        user_id="user-1",
        username="user1",
        sub="user-1",
        roles=[],
        scopes=[],
    )
    raw_request = SimpleNamespace(headers={})

    result = asyncio.run(
        endpoint.resume_run(
            thread_id="thread-1",
            body=body,
            raw_request=raw_request,
            user=user,
        )
    )
    assert result["ok"] is True
    assert result["thread_id"] == "thread-1"
    assert result["checkpoint_id"] == "chk-resume-1"
    assert result["action"] == "approve"
