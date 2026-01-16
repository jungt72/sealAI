from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

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
                        "tenant_id": "user-1",
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
                        "tenant_id": "user-1",
                    },
                },
            )

        return gen()


async def _collect(gen) -> str:
    text = ""
    async for chunk in gen:
        text += chunk.decode("utf-8")
    return text


def test_chat_v2_sse_trace_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEALAI_LG_TRACE", "1")

    import importlib

    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")

    async def _dummy_graph():
        return DummyGraphTrace()

    monkeypatch.setattr(ep, "get_sealai_graph_v2", _dummy_graph)

    req = ep.LangGraphV2Request(input="hi", chat_id="de9c6623-8a9d-4889-84e8-73d68b3ec287")
    text = asyncio.run(_collect(ep._event_stream_v2(req, user_id="user-1", request_id="trace-1")))
    assert "event: trace" in text


def test_chat_v2_sse_trace_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEALAI_LG_TRACE", "0")

    import importlib

    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")

    async def _dummy_graph():
        return DummyGraphTrace()

    monkeypatch.setattr(ep, "get_sealai_graph_v2", _dummy_graph)

    req = ep.LangGraphV2Request(input="hi", chat_id="de9c6623-8a9d-4889-84e8-73d68b3ec287")
    text = asyncio.run(_collect(ep._event_stream_v2(req, user_id="user-1", request_id="trace-2")))
    assert "event: trace" not in text


def test_chat_v2_sse_emits_retrieval_results(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")

    async def _dummy_graph():
        return DummyGraphRetrievalResults()

    monkeypatch.setattr(ep, "get_sealai_graph_v2", _dummy_graph)

    req = ep.LangGraphV2Request(input="hi", chat_id="de9c6623-8a9d-4889-84e8-73d68b3ec287")
    text = asyncio.run(_collect(ep._event_stream_v2(req, user_id="user-1", request_id="trace-3")))
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

    req = ep.LangGraphV2Request(input="hi", chat_id="de9c6623-8a9d-4889-84e8-73d68b3ec287")
    text = asyncio.run(_collect(ep._event_stream_v2(req, user_id="user-1", request_id="trace-4")))
    assert "event: retrieval.skipped" in text
    assert "\"reason\"" in text
