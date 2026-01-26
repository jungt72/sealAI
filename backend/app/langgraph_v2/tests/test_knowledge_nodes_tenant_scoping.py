import sys
from types import ModuleType

from langchain_core.messages import HumanMessage

if "app.core.llm_client" not in sys.modules:
    stub = ModuleType("app.core.llm_client")
    stub.run_llm = lambda *args, **kwargs: "ok"
    stub.get_model_tier = lambda *args, **kwargs: "mini"
    sys.modules["app.core.llm_client"] = stub

if "app.utils.message_helpers" not in sys.modules:
    stub = ModuleType("app.utils.message_helpers")
    stub.latest_user_text = lambda messages: messages[-1].content if messages else ""
    sys.modules["app.utils.message_helpers"] = stub

from app.langgraph_v2.nodes import nodes_knowledge
from app.langgraph_v2.state.sealai_state import SealAIState


def test_knowledge_nodes_use_tenant_id(monkeypatch):
    captured = []

    class FakeSearchTool:
        def invoke(self, payload):
            captured.append(payload)
            return {
                "context": "Gefundene Infos",
                "retrieval_meta": {"k_returned": 1, "top_scores": [0.5]},
            }

    monkeypatch.setattr(nodes_knowledge, "search_knowledge_base", FakeSearchTool())
    monkeypatch.setattr(nodes_knowledge, "run_llm", lambda **_kwargs: "ok")
    monkeypatch.setattr(nodes_knowledge, "get_model_tier", lambda *_args, **_kwargs: "mini")

    state = SealAIState(
        messages=[HumanMessage(content="Test")],
        user_id="user-1",
        tenant_id="tenant-1",
    )

    _ = nodes_knowledge.knowledge_material_node(state)
    _ = nodes_knowledge.knowledge_lifetime_node(state)
    _ = nodes_knowledge.generic_sealing_qa_node(state)

    assert len(captured) == 3
    assert all(item.get("tenant") == "tenant-1" for item in captured)
    assert all(item.get("tenant") != state.user_id for item in captured)
