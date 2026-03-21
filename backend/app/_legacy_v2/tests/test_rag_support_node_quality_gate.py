import os

from langchain_core.messages import HumanMessage

from app._legacy_v2.nodes.nodes_flows import rag_support_node
from app._legacy_v2.state.sealai_state import SealAIState


def test_rag_support_node_skips_on_no_hits(monkeypatch):
    os.environ["MIN_TOP_SCORE"] = "0.20"

    import app._legacy_v2.nodes.nodes_flows as nf

    class FakeSearchTool:
        def invoke(self, _payload):
            return {
                "context": "Gefundene Infos",
                "retrieval_meta": {"k_returned": 0, "top_scores": []},
            }

    monkeypatch.setattr(nf, "search_knowledge_base", FakeSearchTool())

    state = SealAIState(
        conversation={"messages": [HumanMessage(content="Test")], "user_id": "tenant-1"},
        reasoning={"requires_rag": True},
    )
    patch = rag_support_node(state)
    meta = patch.get("reasoning", {}).get("retrieval_meta") or {}
    narrative = meta.get("narrative") or {}
    assert narrative.get("skipped") is True
    assert narrative.get("reason") == "no_hits"
    assert patch.get("reasoning", {}).get("flags", {}).get("rag_low_quality_results") is True
    notes = patch.get("reasoning", {}).get("working_memory").comparison_notes or {}
    assert notes.get("rag_context") == ""


def test_rag_support_node_skips_on_low_score(monkeypatch):
    os.environ["MIN_TOP_SCORE"] = "0.20"

    import app._legacy_v2.nodes.nodes_flows as nf

    class FakeSearchTool:
        def invoke(self, _payload):
            return {
                "context": "Gefundene Infos",
                "retrieval_meta": {"k_returned": 2, "top_scores": [0.1]},
            }

    monkeypatch.setattr(nf, "search_knowledge_base", FakeSearchTool())

    state = SealAIState(
        conversation={"messages": [HumanMessage(content="Test")], "user_id": "tenant-1"},
        reasoning={"requires_rag": True},
    )
    patch = rag_support_node(state)
    meta = patch.get("reasoning", {}).get("retrieval_meta") or {}
    narrative = meta.get("narrative") or {}
    assert narrative.get("skipped") is True
    assert narrative.get("reason") == "low_score"
    assert patch.get("reasoning", {}).get("flags", {}).get("rag_low_quality_results") is True
    notes = patch.get("reasoning", {}).get("working_memory").comparison_notes or {}
    assert notes.get("rag_context") == ""
