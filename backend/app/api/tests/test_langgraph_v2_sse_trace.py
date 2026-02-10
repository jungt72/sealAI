from __future__ import annotations

import asyncio
import ast
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from app.langgraph_v2.utils.threading import resolve_checkpoint_thread_id
from app.services.sse_broadcast import MemoryReplayBackend, SseBroadcastManager

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
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_expected_azp", "test-client")


def _derive_allowed_event_names() -> set[str]:
    import importlib

    endpoint = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    source = inspect.getsource(endpoint._event_stream_v2)
    tree = ast.parse(source)
    allowed: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_emit_event"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            allowed.add(node.args[0].value)
    # `_event_stream_v2` emits retrieval events via a computed `event_name` variable.
    allowed.update({"retrieval.results", "retrieval.skipped"})
    return allowed


ALLOWED_EVENT_NAMES = _derive_allowed_event_names()


class _Snapshot:
    def __init__(self, values=None):
        self.values = values or {}
        self.next = []
        self.config = {}


class DummyGraphTrace:
    checkpointer = object()

    async def aget_state(self, _config):
        return _Snapshot()

    def astream(self, _input, config=None, *, stream_mode=None, **_kwargs):
        async def gen():
            yield ("messages", ("Hi", {"node": "frontdoor_node"}))
            yield ("values", {"phase": "analysis", "last_node": "frontdoor_node"})
            yield ("messages", (" there", {"node": "response_node"}))
            yield ("values", {"phase": "final", "last_node": "response_node"})

        return gen()


class DummyGraphRetrievalResults:
    checkpointer = object()

    async def aget_state(self, _config):
        return _Snapshot()

    def astream(self, _input, config=None, *, stream_mode=None, **_kwargs):
        async def gen():
            yield ("values", {"phase": "analysis", "last_node": "rag_support_node"})
            yield (
                "values",
                {
                    "phase": "rag",
                    "last_node": "rag_support_node",
                    "retrieval_meta": {
                        "k_requested": 3,
                        "k_returned": 2,
                        "top_scores": [0.9, 0.7],
                        "doc_ids": ["doc-1", "doc-2"],
                        "sources": [
                            {
                                "document_id": "doc-1",
                                "sha256": "hash-1",
                                "filename": "specs.pdf",
                                "page": 2,
                                "section": "Werkstoffe",
                                "score": 0.9,
                                "source": "upload",
                            }
                        ],
                        "threshold": None,
                        "fused": False,
                        "reranked": True,
                        "collection": "sealai-docs",
                        "tenant_id": "tenant-1",
                        "category": "norms",
                    },
                },
            )

        return gen()


class DummyGraphRetrievalSkipped:
    checkpointer = object()

    async def aget_state(self, _config):
        return _Snapshot()

    def astream(self, _input, config=None, *, stream_mode=None, **_kwargs):
        async def gen():
            yield (
                "values",
                {
                    "phase": "supervisor",
                    "last_node": "supervisor_policy_node",
                    "retrieval_meta": {
                        "skipped": True,
                        "reason": "requires_rag_false",
                        "tenant_id": "tenant-1",
                    },
                },
            )

        return gen()


class DummyGraphContractHappy:
    checkpointer = object()

    async def aget_state(self, _config):
        return _Snapshot()

    def astream(self, _input, config=None, *, stream_mode=None, **_kwargs):
        async def gen():
            yield ("messages", ("Hallo", {"node": "frontdoor_node"}))
            yield (
                "values",
                {
                    "phase": "knowledge",
                    "last_node": "frontdoor_node",
                    "parameters": {"pressure_bar": 7},
                    "retrieval_meta": {
                        "k_requested": 2,
                        "k_returned": 1,
                        "sources": [{"source": "spec.pdf", "page": 2, "score": 0.9}],
                    },
                },
            )

        return gen()


class DummyGraphContractError:
    checkpointer = object()

    async def aget_state(self, _config):
        return _Snapshot()

    def astream(self, _input, config=None, *, stream_mode=None, **_kwargs):
        async def gen():
            yield ("messages", ("Vorfehler", {"node": "frontdoor_node"}))
            raise RuntimeError("forced_stream_error")

        return gen()


async def _collect(gen) -> str:
    text = ""
    async for chunk in gen:
        text += chunk.decode("utf-8")
    return text


def _checkpoint_thread_id(tenant_id: str, user_id: str, chat_id: str) -> str:
    # Must match your stable scoping {tenant}:{user}:{chat_id}
    return f"{tenant_id}:{user_id}:{chat_id}"


def _parse_sse_events(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event_name: str | None = None
        data_payload: dict | None = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
                if isinstance(payload, dict):
                    data_payload = payload
        if event_name and data_payload is not None:
            events.append((event_name, data_payload))
    return events


def _parse_sse_frames_with_ids(text: str) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event_name: str | None = None
        event_id: str | None = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("id:"):
                event_id = line.split(":", 1)[1].strip()
            elif line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if event_name is None:
            continue
        assert data_lines, f"SSE event frame missing data: {block!r}"
        payload = json.loads("\n".join(data_lines))
        assert isinstance(payload, dict), "SSE data payload must be a JSON object"
        assert event_id is not None and event_id != "", f"SSE event frame missing id: {block!r}"
        frames.append({"id": event_id, "event": event_name, "data": payload})
    return frames


def _id_ordinal(raw_id: str) -> tuple[int, int | str]:
    text = str(raw_id).strip()
    if text.isdigit():
        return (0, int(text))
    if ":" in text:
        suffix = text.rsplit(":", 1)[-1]
        if suffix.isdigit():
            return (0, int(suffix))
    return (1, text)


def _assert_done_once_last(frames: list[dict[str, Any]]) -> None:
    done_positions = [idx for idx, item in enumerate(frames) if item["event"] == "done"]
    assert len(done_positions) == 1, "done must appear exactly once"
    assert done_positions[0] == len(frames) - 1, "done must be the last event"


def _assert_contract_semantics(frames: list[dict[str, Any]]) -> None:
    assert frames, "expected at least one SSE event frame"
    ids = [item["id"] for item in frames]
    assert len(ids) == len(set(ids)), "event ids must be unique within a stream"
    for i in range(1, len(ids)):
        assert _id_ordinal(ids[i]) > _id_ordinal(ids[i - 1]), "event ids must be monotonically increasing"

    for item in frames:
        event_name = item["event"]
        payload = item["data"]
        assert event_name in ALLOWED_EVENT_NAMES

        if event_name == "token":
            assert payload.get("type") == "token"
            assert "text" in payload and isinstance(payload["text"], str) and payload["text"] != ""
        elif event_name == "state_update":
            assert payload.get("type") == "state_update"
            assert ("parameters" in payload) or ("delta" in payload) or ("phase" in payload)
        elif event_name == "retrieval.results":
            assert any(key in payload for key in ("sources", "k_returned", "doc_ids", "tenant_id"))
        elif event_name == "retrieval.skipped":
            assert payload.get("reason")
        elif event_name == "error":
            assert payload.get("type") == "error"
            assert any(key in payload for key in ("message", "detail", "code"))
            assert ("chat_id" in payload) or ("request_id" in payload)
        elif event_name == "done":
            assert payload.get("type") == "done"
            assert "chat_id" in payload

    _assert_done_once_last(frames)


def _assert_ids_monotonic(frames: list[dict[str, Any]]) -> None:
    assert frames, "expected at least one SSE event frame"
    ids = [item["id"] for item in frames]
    assert len(ids) == len(set(ids)), "event ids must be unique within a stream"
    for i in range(1, len(ids)):
        assert _id_ordinal(ids[i]) > _id_ordinal(ids[i - 1]), "event ids must be monotonically increasing"


async def _collect_with_cancel(gen) -> str:
    text = ""
    first = await gen.__anext__()
    text += first.decode("utf-8")
    cancel_frame = await gen.athrow(asyncio.CancelledError())
    text += cancel_frame.decode("utf-8")
    try:
        while True:
            chunk = await gen.__anext__()
            text += chunk.decode("utf-8")
    except StopAsyncIteration:
        return text


def test_chat_v2_sse_contract_e2e_happy_error_cancel_and_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    replay_manager = SseBroadcastManager(
        replay_backend=MemoryReplayBackend(max_buffer=100),
        queue_maxsize=50,
        slow_notice_interval=0.0,
    )
    monkeypatch.setattr(ep, "sse_broadcast", replay_manager)

    checkpoint_thread = _checkpoint_thread_id("tenant-1", "user-1", "default")

    async def _run_happy(last_event_id: str | None = None, *, strict_done: bool = True) -> list[dict[str, Any]]:
        async def _dummy_graph():
            return DummyGraphContractHappy()

        monkeypatch.setattr(ep, "get_sealai_graph_v2", _dummy_graph)
        req = ep.LangGraphV2Request(input="hi", chat_id="default")
        raw = await _collect(
            ep._event_stream_v2(
                req,
                user_id="user-1",
                tenant_id="tenant-1",
                request_id="contract-happy",
                can_read_private=False,
                checkpoint_thread_id=checkpoint_thread,
                last_event_id=last_event_id,
            )
        )
        frames = _parse_sse_frames_with_ids(raw)
        if strict_done:
            _assert_contract_semantics(frames)
        else:
            _assert_ids_monotonic(frames)
            for item in frames:
                assert item["event"] in ALLOWED_EVENT_NAMES
        assert any(item["event"] != "done" for item in frames), "happy path must contain non-done events"
        return frames

    # 1) Happy path (+ replay check)
    happy_frames = asyncio.run(_run_happy())
    if len(happy_frames) >= 2:
        first_event_id = happy_frames[0]["id"]
        replay_frames = asyncio.run(_run_happy(last_event_id=first_event_id, strict_done=False))
        assert replay_frames, "replay stream should return events"
        for frame in replay_frames:
            assert _id_ordinal(frame["id"]) > _id_ordinal(first_event_id)

    # 2) Error path: error before done, done last
    async def _run_error() -> list[dict[str, Any]]:
        async def _dummy_graph():
            return DummyGraphContractError()

        monkeypatch.setattr(ep, "get_sealai_graph_v2", _dummy_graph)
        req = ep.LangGraphV2Request(input="hi", chat_id="default")
        raw = await _collect(
            ep._event_stream_v2(
                req,
                user_id="user-1",
                tenant_id="tenant-1",
                request_id="contract-error",
                can_read_private=False,
                checkpoint_thread_id=checkpoint_thread,
            )
        )
        frames = _parse_sse_frames_with_ids(raw)
        _assert_contract_semantics(frames)
        events = [item["event"] for item in frames]
        assert "error" in events
        assert events.index("error") < events.index("done")
        error_frame = next(item for item in frames if item["event"] == "error")
        assert error_frame["data"].get("chat_id") == req.chat_id
        return frames

    asyncio.run(_run_error())

    # 3) Cancel path: done still emitted and last
    async def _run_cancel() -> list[dict[str, Any]]:
        async def _dummy_graph():
            return DummyGraphContractHappy()

        monkeypatch.setattr(ep, "get_sealai_graph_v2", _dummy_graph)
        req = ep.LangGraphV2Request(input="hi", chat_id="default")
        raw = await _collect_with_cancel(
            ep._event_stream_v2(
                req,
                user_id="user-1",
                tenant_id="tenant-1",
                request_id="contract-cancel",
                can_read_private=False,
                checkpoint_thread_id=checkpoint_thread,
            )
        )
        frames = _parse_sse_frames_with_ids(raw)
        _assert_contract_semantics(frames)
        assert frames[-1]["event"] == "done"
        return frames

    asyncio.run(_run_cancel())


def test_chat_v2_sse_trace_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEALAI_LG_TRACE", "1")

    import importlib

    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")

    async def _dummy_graph():
        return DummyGraphTrace()

    monkeypatch.setattr(ep, "get_sealai_graph_v2", _dummy_graph)

    req = ep.LangGraphV2Request(input="hi", chat_id="default")
    text = asyncio.run(
        _collect(
            ep._event_stream_v2(
                req,
                user_id="user-1",
                tenant_id="tenant-1",
                request_id="trace-1",
                can_read_private=False,
                checkpoint_thread_id=_checkpoint_thread_id("tenant-1", "user-1", "default"),
            )
        )
    )
    assert "event: trace" in text


def test_chat_v2_sse_trace_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEALAI_LG_TRACE", "0")

    import importlib

    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")

    async def _dummy_graph():
        return DummyGraphTrace()

    monkeypatch.setattr(ep, "get_sealai_graph_v2", _dummy_graph)

    req = ep.LangGraphV2Request(input="hi", chat_id="default")
    text = asyncio.run(
        _collect(
            ep._event_stream_v2(
                req,
                user_id="user-1",
                tenant_id="tenant-1",
                request_id="trace-2",
                can_read_private=False,
                checkpoint_thread_id=_checkpoint_thread_id("tenant-1", "user-1", "default"),
            )
        )
    )
    assert "event: trace" not in text


def test_chat_v2_sse_emits_retrieval_results(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")

    async def _dummy_graph():
        return DummyGraphRetrievalResults()

    monkeypatch.setattr(ep, "get_sealai_graph_v2", _dummy_graph)

    req = ep.LangGraphV2Request(input="hi", chat_id="default")
    text = asyncio.run(
        _collect(
            ep._event_stream_v2(
                req,
                user_id="user-1",
                tenant_id="tenant-1",
                request_id="trace-3",
                can_read_private=False,
                checkpoint_thread_id=_checkpoint_thread_id("tenant-1", "user-1", "default"),
            )
        )
    )
    assert "event: retrieval.results" in text
    assert "\"doc_ids\"" in text
    assert "\"sources\"" in text
    assert "\"tenant_id\"" in text


def test_chat_v2_sse_emits_retrieval_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")

    async def _dummy_graph():
        return DummyGraphRetrievalSkipped()

    monkeypatch.setattr(ep, "get_sealai_graph_v2", _dummy_graph)

    req = ep.LangGraphV2Request(input="hi", chat_id="default")
    text = asyncio.run(
        _collect(
            ep._event_stream_v2(
                req,
                user_id="user-1",
                tenant_id="tenant-1",
                request_id="trace-4",
                can_read_private=False,
                checkpoint_thread_id=_checkpoint_thread_id("tenant-1", "user-1", "default"),
            )
        )
    )
    assert "event: retrieval.skipped" in text
    assert "\"reason\"" in text


def test_sse_replay_isolation_by_tenant_user_with_same_chat_id() -> None:
    replay_manager = SseBroadcastManager(
        replay_backend=MemoryReplayBackend(max_buffer=20),
        queue_maxsize=20,
        slow_notice_interval=0.0,
    )

    chat_id = "same"
    thread_a = resolve_checkpoint_thread_id(tenant_id="tenant-1", user_id="user-1", chat_id=chat_id)
    thread_b = resolve_checkpoint_thread_id(tenant_id="tenant-1", user_id="user-2", chat_id=chat_id)
    thread_c = resolve_checkpoint_thread_id(tenant_id="tenant-2", user_id="user-1", chat_id=chat_id)
    assert len({thread_a, thread_b, thread_c}) == 3

    async def _run():
        # Seed replay buffer for scope A only.
        await replay_manager.record_event(
            user_id="user-1",
            chat_id=thread_a,
            event="token",
            data={"type": "token", "text": "A_ONLY", "request_id": "A-only"},
        )
        await replay_manager.record_event(
            user_id="user-1",
            chat_id=thread_a,
            event="token",
            data={"type": "token", "text": "A_ONLY_2", "request_id": "A-only-2"},
        )

        # Baseline: scope A can replay own events.
        replay_a, miss_a = await replay_manager.replay_after(user_id="user-1", chat_id=thread_a, last_seq=1)
        assert miss_a is False
        assert replay_a and replay_a[0].get("data", {}).get("request_id") == "A-only-2"

        # Isolation: same chat_id but different user in same tenant sees nothing from A.
        replay_b, miss_b = await replay_manager.replay_after(user_id="user-2", chat_id=thread_b, last_seq=0)
        assert replay_b == []
        assert miss_b is True

        # Isolation: same chat_id and same user string but different tenant sees nothing from A.
        replay_c, miss_c = await replay_manager.replay_after(user_id="user-1", chat_id=thread_c, last_seq=0)
        assert replay_c == []
        assert miss_c is True

        # Guard: ensure no foreign marker leaked into B/C responses.
        assert all(item.get("data", {}).get("request_id") != "A-only" for item in replay_b)
        assert all(item.get("data", {}).get("request_id") != "A-only" for item in replay_c)

    asyncio.run(_run())

    # Evidence:
    # - backend/app/services/sse_broadcast.py:59-64, 82-89, 94-102 (memory key=(user_id, chat_id))
    # - backend/app/api/v1/endpoints/langgraph_v2.py:1245-1249 (checkpoint key resolution)
    # - backend/app/api/v1/endpoints/langgraph_v2.py:693-699 (replay_after keyed by scoped_user_id + checkpoint_thread_id)


def test_chat_v2_sse_contract_allowed_events_and_required_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEALAI_LG_TRACE", "1")

    import importlib

    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")

    async def _dummy_graph():
        return DummyGraphTrace()

    monkeypatch.setattr(ep, "get_sealai_graph_v2", _dummy_graph)

    req = ep.LangGraphV2Request(input="hi", chat_id="default")
    text = asyncio.run(
        _collect(
            ep._event_stream_v2(
                req,
                user_id="user-1",
                tenant_id="tenant-1",
                request_id="trace-contract-1",
                can_read_private=False,
                checkpoint_thread_id=_checkpoint_thread_id("tenant-1", "user-1", "default"),
            )
        )
    )

    frames = _parse_sse_frames_with_ids(text)
    _assert_contract_semantics(frames)
    for item in frames:
        assert item["event"] in ALLOWED_EVENT_NAMES
        # Contract guard: payloads must remain JSON serializable for SSE.
        json.dumps(item["data"])
