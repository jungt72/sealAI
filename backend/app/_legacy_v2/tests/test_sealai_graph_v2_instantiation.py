import os

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app._legacy_v2.sealai_graph_v2 import create_sealai_graph_v2


def test_sealai_graph_v2_instantiation(monkeypatch):
    # Force in-memory checkpointer to avoid external services
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")
    # Simulate LangSmith env to ensure it does not break graph creation
    monkeypatch.setenv("LANGSMITH_API_KEY", "test")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "http://localhost")
    monkeypatch.setenv("LANGSMITH_PROJECT", "test-project")

    graph = create_sealai_graph_v2(checkpointer=MemorySaver(), store=InMemoryStore())

    assert graph is not None
    # CompiledStateGraph should expose invoke/ainvoke
    assert hasattr(graph, "invoke")
    assert hasattr(graph, "ainvoke")
