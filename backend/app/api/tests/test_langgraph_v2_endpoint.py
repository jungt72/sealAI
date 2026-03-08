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
os.environ.setdefault("nextauth_url", "http://localhost:3000")
os.environ.setdefault("nextauth_secret", "test-secret")
os.environ.setdefault("keycloak_issuer", "http://localhost/realms/test")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_client_id", "test-client")
os.environ.setdefault("keycloak_client_secret", "test-secret")
os.environ.setdefault("keycloak_expected_azp", "test-client")

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.ai import AIMessageChunk

from app.api.v1.endpoints import langgraph_v2 as endpoint  # noqa: E402
from app.api.tests.helpers.langgraph_v2_test_stream_helpers import _event_stream_v2  # noqa: E402
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


class DummyGraphAstreamEventsFinalTextOnly:
    checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot({})

    def astream_events(self, _input: Any, config: Any = None, **_kwargs: Any):
        async def gen():
            yield {
                "event": "on_node_end",
                "name": "response_node",
                "data": {
                    "output": {
                        "final_text": "Kyrolon Antwort",
                        "final_answer": "Kyrolon Antwort",
                        "phase": "final",
                        "last_node": "response_node",
                    }
                },
            }

        return gen()


class DummyGraphStickyLiveCalcTile:
    checkpointer = object()

    async def aget_state(self, _config: Any):
        return _Snapshot(
            {
                "working_profile": {
                    "live_calc_tile": {
                        "status": "warning",
                        "pv_warning": True,
                    }
                },
                "final_text": "done",
                "phase": "final",
                "last_node": "node_p6_generate_pdf",
            }
        )

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
            "reasoning": {
                "phase": "final",
                "last_node": "final_answer_node",
            },
            "system": {
                "governed_output_text": "Resumed",
                "governed_output_ready": True,
                "requires_human_review": False,
                "rfq_admissibility": {
                    "status": "inadmissible",
                    "reason": "rfq_contract_missing",
                    "open_points": [],
                    "blockers": [],
                    "governed_ready": False,
                },
                "governance_metadata": {
                    "scope_of_validity": ["Nur fuer den aktuellen Assertion-Stand."],
                    "assumptions_active": [],
                    "unknowns_release_blocking": [],
                    "unknowns_manufacturer_validation": [],
                    "gate_failures": [],
                    "governance_notes": [],
                },
            },
        }


class DummyGraphFastBrain:
    checkpointer = object()

    def __init__(self):
        self.updates: List[Tuple[Dict[str, Any], Any]] = []
        self.stream_started = False

    async def aget_state(self, _config: Any):
        return _Snapshot(
            {
                "conversation": {"messages": [AIMessage(content="Vorherige Antwort")]},
                "working_profile": {"engineering_profile": {"pressure_bar": 7}},
                "reasoning": {
                    "parameter_provenance": {"pressure_bar": "user"},
                    "parameter_versions": {"pressure_bar": 2},
                    "parameter_updated_at": {"pressure_bar": 1000.0},
                },
            }
        )

    async def aupdate_state(self, _config: Any, updates: Dict[str, Any], as_node: Any = None):
        self.updates.append((updates, as_node))

    def get_graph(self):
        return SimpleNamespace(nodes={endpoint.PARAMETERS_PATCH_AS_NODE: object()})

    def astream_events(self, *_args: Any, **_kwargs: Any):
        self.stream_started = True

        async def gen():
            raise AssertionError("LangGraph stream must not start on fast-brain chat_continue")
            yield  # pragma: no cover

        return gen()


class _DummyFastBrainRouter:
    def __init__(self, result: Dict[str, Any]):
        self.result = result
        self.calls: List[Tuple[str, List[Any]]] = []

    async def chat(self, user_input: str, history: List[Any]):
        self.calls.append((user_input, list(history)))
        return dict(self.result)


class _DummyRawRequest:
    def __init__(self):
        self.headers: Dict[str, str] = {}

    async def is_disconnected(self) -> bool:
        return False


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
    chunks = asyncio.run(_collect(_event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload, _ in events if evt == "token"]
    assert "".join(tokens) == "Hallo Welt"

    done_events = [payload for evt, payload, _ in events if evt == "done"]
    assert len(done_events) == 1
    assert done_events[0]["type"] == "done"


def test_event_multiplexer_emits_token_and_done_for_final_text_only_path() -> None:
    graph = DummyGraphAstreamEventsFinalTextOnly()
    state_input = endpoint.SealAIState(
        conversation={"thread_id": "chat-final-only"},
    )
    frames = asyncio.run(
        _collect(
            endpoint.event_multiplexer(
                graph,
                state_input,
                config={},
                request=_DummyRawRequest(),
            )
        )
    )
    events = _parse_sse_frames(frames)

    token_events = [payload for evt, payload, _ in events if evt == "token"]
    done_events = [payload for evt, payload, _ in events if evt == "done"]

    assert token_events
    assert token_events[0]["text"] == "Kyrolon Antwort"
    assert done_events
    assert done_events[0]["chat_id"] == "chat-final-only"


def test_event_stream_v2_includes_event_ids(monkeypatch):
    async def _dummy_graph():
        return DummyGraphTokens()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test", client_msg_id="msg-1")
    chunks = asyncio.run(_collect(_event_stream_v2(req, user_id="user-test", request_id="req-1")))
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
    chunks = asyncio.run(_collect(_event_stream_v2(req, user_id="user-test", request_id="req-int")))
    events = _parse_sse_frames(chunks)

    interrupt_events = [payload for evt, payload, _ in events if evt == "interrupt"]
    assert len(interrupt_events) == 1
    assert interrupt_events[0]["thread_id"] == "user-test:chat-interrupt"
    assert interrupt_events[0]["checkpoint_id"] == "chk-hitl-1"
    assert interrupt_events[0]["required_action"] == "approve_specification"


def test_event_stream_v2_fallback_chunks_final_text(monkeypatch):
    async def _dummy_graph():
        return DummyGraphNoTokens()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(_event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload, _ in events if evt == "token"]
    assert "".join(tokens) == "Final Antwort"
    assert len([1 for evt, _, _ in events if evt == "done"]) == 1


def test_event_stream_v2_emits_error_then_done(monkeypatch):
    async def _dummy_graph():
        return DummyGraphError()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(_event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    assert [evt for evt, _, _ in events].count("error") == 1
    assert [evt for evt, _, _ in events].count("done") == 1


def test_event_stream_v2_ignores_full_message_after_chunks(monkeypatch):
    async def _dummy_graph():
        return DummyGraphTokensWithFinalMessage()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(_event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload, _ in events if evt == "token"]
    assert "".join(tokens) == "Hallo Welt"


def test_event_stream_v2_filters_structured_payloads_in_astream(monkeypatch):
    async def _dummy_graph():
        return DummyGraphTokensWithStructuredLeak()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(_event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload, _ in events if evt == "token"]
    assert "".join(tokens) == "Hallo Welt"
    assert all("intent_category" not in text for text in tokens)


def test_event_stream_v2_emits_checkpoint_required(monkeypatch):
    async def _dummy_graph():
        return DummyGraphConfirmCheckpoint()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(_event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    assert any(evt == "checkpoint_required" for evt, _, _ in events)


def test_event_stream_v2_astream_events_emits_chat_chunk_tokens_only(monkeypatch):
    async def _dummy_graph():
        return DummyGraphAstreamEventsTokenOnly()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(_event_stream_v2(req, user_id="user-test", request_id="req-1")))
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
    chunks = asyncio.run(_collect(_event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload, _ in events if evt == "token"]
    assert "".join(tokens) == "NEW RFQ TEXT"
    assert all("PREVIOUS RESPONSE" not in text for text in tokens)


def test_event_stream_v2_does_not_duplicate_streamed_tokens_from_snapshot_final_text(monkeypatch):
    async def _dummy_graph():
        return DummyGraphAstreamEventsConversationalSnapshot()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(_event_stream_v2(req, user_id="user-test", request_id="req-1")))
    events = _parse_sse_frames(chunks)

    tokens = [payload["text"] for evt, payload, _ in events if evt == "token"]
    assert tokens == ["Hallo Welt"]


def test_event_stream_v2_emits_terminal_message_from_final_state(monkeypatch):
    async def _dummy_graph():
        return DummyGraphNoTokens()

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-test")
    chunks = asyncio.run(_collect(_event_stream_v2(req, user_id="user-test", request_id="req-1")))
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
    chunks = asyncio.run(_collect(_event_stream_v2(req, user_id="user-test", request_id="req-1")))
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
    assert result["thread_id"] == "user-1:thread-1"
    assert result["checkpoint_id"] == "chk-resume-1"
    assert result["action"] == "approve"
    assert result["governed_output_text"] == "Resumed"
    assert result["governed_output_ready"] is True
    assert result["rfq_admissibility"]["status"] == "inadmissible"


def test_langgraph_chat_v2_endpoint_fast_brain_chat_continue_streams_and_syncs(monkeypatch):
    dummy_graph = DummyGraphFastBrain()
    dummy_router = _DummyFastBrainRouter(
        {
            "status": "chat_continue",
            "content": "Schnelle Antwort",
            "state_patch": {
                "parameters": {
                    "shaft_diameter": 100.0,
                    "speed_rpm": 3000.0,
                    "pressure_bar": 12.0,
                },
                "working_profile": {
                    "live_calc_tile": {
                        "status": "ok",
                        "v_surface_m_s": 15.71,
                        "pv_value_mpa_m_s": 188.52,
                        "parameters": {
                            "shaft_diameter": 100.0,
                            "speed_rpm": 3000.0,
                            "pressure_bar": 12.0,
                        },
                    },
                    "calc_results": {
                        "v_surface_m_s": 15.71,
                        "pv_value_mpa_m_s": 188.52,
                    },
                },
            },
        }
    )
    released: List[str] = []

    async def _dummy_build_graph_config(**_kwargs):
        return dummy_graph, {"configurable": {"thread_id": "user-1:chat-fast"}}

    async def _dummy_claim_thread_lock(*_args: Any, **_kwargs: Any) -> bool:
        return True

    async def _dummy_release_thread_lock(thread_id: str):
        released.append(thread_id)

    monkeypatch.setattr(endpoint, "_build_graph_config", _dummy_build_graph_config)
    monkeypatch.setattr(endpoint, "_get_fast_brain_router", lambda: dummy_router)
    monkeypatch.setattr(endpoint, "_claim_thread_lock", _dummy_claim_thread_lock)
    monkeypatch.setattr(endpoint, "_release_thread_lock", _dummy_release_thread_lock)
    monkeypatch.setattr(endpoint, "event_multiplexer", lambda *_args, **_kwargs: None)

    req = endpoint.LangGraphV2Request(input="100 mm Welle, 3000 rpm, 12 bar", chat_id="chat-fast")
    raw_request = _DummyRawRequest()
    user = RequestUser(user_id="user-1", username="user1", sub=None, roles=[], scopes=[], tenant_id="tenant-1")

    response = asyncio.run(endpoint.langgraph_chat_v2_endpoint(req, raw_request, user=user))
    chunks = asyncio.run(_collect(response.body_iterator))
    events = _parse_sse_frames(chunks)

    assert [evt for evt, _, _ in events] == ["state_update", "turn_complete", "done"]
    done_payload = next(payload for evt, payload, _ in events if evt == "done")
    assert done_payload["final_text"] == "Schnelle Antwort"
    assert done_payload["final_answer"] == "Schnelle Antwort"
    assert dummy_graph.stream_started is False
    assert len(dummy_graph.updates) == 1

    updates, as_node = dummy_graph.updates[0]
    assert as_node == endpoint.PARAMETERS_PATCH_AS_NODE
    assert updates["working_profile"]["extracted_params"]["shaft_diameter"] == 100.0
    assert updates["working_profile"]["extracted_params"]["speed_rpm"] == 3000.0
    assert updates["working_profile"]["extracted_params"]["pressure_bar"] == 12.0
    assert updates["working_profile"]["live_calc_tile"]["v_surface_m_s"] == 15.71
    assert updates["reasoning"]["extracted_parameter_provenance"]["pressure_bar"] == "fast_brain_extracted"
    messages = updates["conversation"]["messages"]
    assert isinstance(messages[0], HumanMessage)
    assert messages[0].content == "100 mm Welle, 3000 rpm, 12 bar"
    assert isinstance(messages[1], AIMessage)
    assert messages[1].content == "Schnelle Antwort"
    assert released == ["user-1:chat-fast"]
    assert dummy_router.calls[0][0] == "100 mm Welle, 3000 rpm, 12 bar"
    assert isinstance(dummy_router.calls[0][1][0], AIMessage)


def test_langgraph_chat_v2_endpoint_handoff_syncs_then_uses_event_multiplexer(monkeypatch):
    dummy_graph = DummyGraphFastBrain()
    dummy_router = _DummyFastBrainRouter(
        {
            "status": "handoff_to_langgraph",
            "content": "IGNORED",
            "state_patch": {
                "parameters": {
                    "shaft_diameter": 80.0,
                    "speed_rpm": 1500.0,
                },
                "working_profile": {
                    "live_calc_tile": {
                        "status": "ok",
                        "v_surface_m_s": 6.28,
                        "parameters": {
                            "shaft_diameter": 80.0,
                            "speed_rpm": 1500.0,
                        },
                    }
                },
            },
        }
    )
    multiplexer_calls: List[str] = []

    async def _dummy_build_graph_config(**_kwargs):
        return dummy_graph, {"configurable": {"thread_id": "user-1:chat-handoff"}}

    async def _dummy_claim_thread_lock(*_args: Any, **_kwargs: Any) -> bool:
        return True

    async def _dummy_event_multiplexer(_graph: Any, _state_input: Any, _config: Any, _request: Any):
        multiplexer_calls.append("called")
        yield endpoint._format_sse_text("text_chunk", {"type": "text_chunk", "text": "LangGraph Antwort"})
        yield endpoint._format_sse_text("turn_complete", {"type": "turn_complete"})

    monkeypatch.setattr(endpoint, "_build_graph_config", _dummy_build_graph_config)
    monkeypatch.setattr(endpoint, "_get_fast_brain_router", lambda: dummy_router)
    monkeypatch.setattr(endpoint, "_claim_thread_lock", _dummy_claim_thread_lock)
    monkeypatch.setattr(endpoint, "event_multiplexer", _dummy_event_multiplexer)

    req = endpoint.LangGraphV2Request(input="Bitte auslegen", chat_id="chat-handoff")
    raw_request = _DummyRawRequest()
    user = RequestUser(user_id="user-1", username="user1", sub=None, roles=[], scopes=[], tenant_id="tenant-1")

    response = asyncio.run(endpoint.langgraph_chat_v2_endpoint(req, raw_request, user=user))
    chunks = asyncio.run(_collect(response.body_iterator))
    events = _parse_sse_frames(chunks)

    assert [evt for evt, _, _ in events] == ["text_chunk", "turn_complete"]
    assert events[0][1]["text"] == "LangGraph Antwort"
    assert multiplexer_calls == ["called"]
    assert len(dummy_graph.updates) == 1
    updates, as_node = dummy_graph.updates[0]
    assert as_node == endpoint.PARAMETERS_PATCH_AS_NODE
    assert updates["working_profile"]["extracted_params"]["shaft_diameter"] == 80.0
    assert updates["working_profile"]["extracted_params"]["speed_rpm"] == 1500.0
    assert "conversation" not in updates
