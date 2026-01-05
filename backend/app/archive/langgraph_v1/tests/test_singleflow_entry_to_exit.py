from __future__ import annotations

import os

import pytest
from langgraph.graph.state import CompiledStateGraph

from app.langgraph.compile import create_main_graph
from app.langgraph.nodes.supervisor_factory import build_supervisor


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Supervisor workflow requires OPENAI_API_KEY for the coordinating LLM.",
)
def test_supervisor_factory_returns_compiled_graph() -> None:
    supervisor = build_supervisor()
    assert isinstance(supervisor, CompiledStateGraph)


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Supervisor workflow requires OPENAI_API_KEY for the coordinating LLM.",
)
def test_main_graph_compiles_with_supervisor() -> None:
    graph = create_main_graph()
    assert isinstance(graph, CompiledStateGraph)
