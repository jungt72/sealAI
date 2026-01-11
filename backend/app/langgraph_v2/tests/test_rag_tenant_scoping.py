from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes import nodes_flows
from app.langgraph_v2.state import SealAIState


def test_rag_support_node_uses_tenant_id(monkeypatch) -> None:
    captured = {}

    class FakeTool:
        def invoke(self, payload):
            captured.update(payload)
            return {
                "context": "Kontext\nQuelle: http://example.test",
                "retrieval_meta": {"k_returned": 1, "top_scores": [0.9]},
            }

    monkeypatch.setattr(nodes_flows, "search_knowledge_base", FakeTool())

    state = SealAIState(
        messages=[HumanMessage(content="hi")],
        user_id="user-1",
        tenant_id="tenant-1",
    )

    nodes_flows.rag_support_node(state)
    assert captured.get("tenant") == "tenant-1"


def test_rag_support_node_falls_back_to_user_id(monkeypatch) -> None:
    captured = {}

    class FakeTool:
        def invoke(self, payload):
            captured.update(payload)
            return {
                "context": "Kontext\nQuelle: http://example.test",
                "retrieval_meta": {"k_returned": 1, "top_scores": [0.9]},
            }

    monkeypatch.setattr(nodes_flows, "search_knowledge_base", FakeTool())

    state = SealAIState(messages=[HumanMessage(content="hi")], user_id="user-1")

    nodes_flows.rag_support_node(state)
    assert captured.get("tenant") == "user-1"
