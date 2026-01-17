from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes import nodes_flows
from app.langgraph_v2.state.sealai_state import SealAIState


def test_rag_support_node_uses_tenant_id(monkeypatch):
    captured = {}

    class FakeSearchTool:
        def invoke(self, payload):
            captured.update(payload)
            return {
                "context": "Gefundene Infos",
                "retrieval_meta": {"k_returned": 0, "top_scores": []},
            }

    monkeypatch.setattr(nodes_flows, "search_knowledge_base", FakeSearchTool())

    state = SealAIState(
        messages=[HumanMessage(content="Test")],
        user_id="user-1",
        tenant_id="tenant-1",
    )
    _ = nodes_flows.rag_support_node(state)

    assert captured.get("tenant") == "tenant-1"
    assert captured.get("tenant") != state.user_id
