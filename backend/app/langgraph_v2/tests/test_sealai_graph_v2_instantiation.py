import asyncio
import os

from app.langgraph_v2 import sealai_graph_v2
from app.langgraph_v2.sealai_graph_v2 import get_sealai_graph_v2


def test_sealai_graph_v2_instantiation(monkeypatch):
    # Force in-memory checkpointer to avoid external services
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")
    # Simulate LangSmith env to ensure it does not break graph creation
    monkeypatch.setenv("LANGSMITH_API_KEY", "test")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "http://localhost")
    monkeypatch.setenv("LANGSMITH_PROJECT", "test-project")

    graph = asyncio.run(get_sealai_graph_v2())

    assert graph is not None
    # CompiledStateGraph should expose invoke/ainvoke
    assert hasattr(graph, "invoke")
    assert hasattr(graph, "ainvoke")


def _run_in_loop(loop: asyncio.AbstractEventLoop, coro):
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(None)


def test_sealai_graph_v2_cache_is_per_event_loop(monkeypatch):
    created = []

    async def fake_build_graph(require_async: bool = True):
        graph = object()
        created.append(graph)
        return graph

    monkeypatch.setattr(sealai_graph_v2, "_build_graph", fake_build_graph)

    loop_a = asyncio.new_event_loop()
    try:
        graph_a = _run_in_loop(loop_a, sealai_graph_v2.get_sealai_graph_v2())
        graph_a_second = _run_in_loop(loop_a, sealai_graph_v2.get_sealai_graph_v2())
    finally:
        loop_a.close()

    loop_b = asyncio.new_event_loop()
    try:
        graph_b = _run_in_loop(loop_b, sealai_graph_v2.get_sealai_graph_v2())
    finally:
        loop_b.close()

    assert graph_a is graph_a_second
    assert graph_a is not graph_b
