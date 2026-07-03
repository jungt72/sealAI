"""Wiring: sealingAI Memory Architecture V1.0 (Patch 8) flows to the PipelineResult + the chat
serializer ONLY when the flag is on, and is OFF by default (→ None, L1-neutral). Mirrors
test_medium_intel_wiring.py's exact pattern — the REAL MemoryContextService, wired end-to-end
through a real Pipeline.run(), with fake external deps (store/qdrant/embedder)."""

from __future__ import annotations

import asyncio

from sealai_v2.api.serializers import chat_response
from sealai_v2.core.contracts import Answer, Flags, ModelConfig, PipelineResult
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.db.memory_store import InProcessMemoryStore
from sealai_v2.memory.context_assembler import (
    MemoryContextBundle,
    MemoryContextEntry,
    MemoryContextService,
)
from sealai_v2.memory.curated import (
    MemoryItem,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from sealai_v2.memory.policy import MemoryUsage
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient


class _ListLike(list):
    def tolist(self):
        return list(self)


class _FakeEmbedder:
    def embed(self, texts):
        return [_ListLike([0.1, 0.2, 0.3]) for _ in texts]


class _FakePoint:
    def __init__(self, point_id: str) -> None:
        self.id = point_id


class _FakeQueryResult:
    def __init__(self, points) -> None:
        self.points = points


class _FakeQdrantClient:
    def __init__(self, point_ids: list[str]) -> None:
        self._point_ids = point_ids

    def query_points(self, collection, **kwargs):
        return _FakeQueryResult([_FakePoint(pid) for pid in self._point_ids])


class _FailingQdrantClient:
    def query_points(self, collection, **kwargs):
        raise ConnectionError("simulated Qdrant outage")


def _seeded_store(item_id: str = "mem-1") -> InProcessMemoryStore:
    store = InProcessMemoryStore()
    store.create_candidate(
        MemoryItem(
            id=item_id,
            tenant_id="t1",
            scope=MemoryScope.USER,
            scope_id="user-1",
            type=MemoryType.PREFERENCE,
            status=MemoryStatus.CONFIRMED,
            content="prefers metric units",
            semantic_key="pref:units:metric",
            sources=(MemorySource(kind="user_stated"),),
            created_at="2026-07-03T00:00:00Z",
            updated_at="2026-07-03T00:00:00Z",
        )
    )
    return store


def _pipeline(*, enabled: bool, service=None):
    client = FakeLlmClient("Antwort")
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
        memory_context_service=service,
        memory_context_enabled=enabled,
    )


def test_memory_context_flows_to_result_when_enabled():
    service = MemoryContextService(
        store=_seeded_store(),
        qdrant_client=_FakeQdrantClient(point_ids=["mem-1"]),
        embedder=_FakeEmbedder(),
    )
    res = asyncio.run(
        _pipeline(enabled=True, service=service).run(
            "Ich brauche eine Dichtung", tenant=TenantContext("t1")
        )
    )
    assert res.memory_context is not None
    assert res.memory_context.entries[0].item_id == "mem-1"


def test_memory_context_off_by_default_is_none():
    service = MemoryContextService(
        store=_seeded_store(),
        qdrant_client=_FakeQdrantClient(point_ids=["mem-1"]),
        embedder=_FakeEmbedder(),
    )
    res = asyncio.run(
        _pipeline(enabled=False, service=service).run(
            "Ich brauche eine Dichtung", tenant=TenantContext("t1")
        )
    )
    assert res.memory_context is None  # L1-neutral default — service wired but flag off


def test_memory_context_no_service_even_when_enabled_is_none():
    # enabled=True but no service constructed (e.g. database_url/qdrant_url unset at startup) → inert.
    res = asyncio.run(
        _pipeline(enabled=True, service=None).run("q", tenant=TenantContext("t1"))
    )
    assert res.memory_context is None


def test_memory_context_retrieval_failure_does_not_break_the_turn():
    service = MemoryContextService(
        store=_seeded_store(),
        qdrant_client=_FailingQdrantClient(),
        embedder=_FakeEmbedder(),
    )
    res = asyncio.run(
        _pipeline(enabled=True, service=service).run("q", tenant=TenantContext("t1"))
    )
    assert res.answer.text == "Antwort"  # the turn completed normally
    assert res.memory_context is not None
    assert res.memory_context.is_empty  # fail-safe empty bundle, not a raised exception


def test_serializer_surfaces_when_present_and_omits_when_absent():
    base = dict(
        question="x",
        tenant_id="t1",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="…", model="fake"),
    )
    entry = MemoryContextEntry(
        item_id="mem-1",
        content="prefers metric units",
        usage=MemoryUsage.STYLE_ONLY,
        scope="user",
        type="preference",
        estimated_tokens=5,
    )
    bundle = MemoryContextBundle(entries=(entry,), total_estimated_tokens=5)
    out = chat_response(PipelineResult(**base, memory_context=bundle))
    assert out["memory_context"]["context_sources"][0]["item_id"] == "mem-1"
    assert out["memory_context"]["total_estimated_tokens"] == 5
    assert chat_response(PipelineResult(**base))["memory_context"] is None
