import os

from app.langgraph.nodes.supervisor_factory import build_supervisor


def test_handoff_tools_exist(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "1")
    graph = build_supervisor()
    tools = getattr(graph, "handoff_tools", [])

    assert any(tool.startswith("handoff_to_profil") for tool in tools)
    assert any(tool.startswith("handoff_to_validierung") for tool in tools)
    assert any(tool.startswith("handoff_to_material") for tool in tools)
