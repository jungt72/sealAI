from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes import nodes_flows
from app.langgraph_v2.state.sealai_state import SealAIState


def test_retry_not_triggered_when_good_score(monkeypatch):
    calls = []

    class FakeSearchTool:
        def invoke(self, payload):
            calls.append(payload)
            return {
                "context": "OK",
                "retrieval_meta": {"k_returned": 1, "top_scores": [0.9]},
            }

    monkeypatch.setenv("RETRIEVAL_RETRY_MIN_TOP_SCORE", "0.20")
    monkeypatch.setattr(nodes_flows, "search_knowledge_base", FakeSearchTool())

    state = SealAIState(
        messages=[HumanMessage(content="Brauche Werkstoffvergleich NBR vs FKM")],
        user_id="user-1",
        tenant_id="tenant-1",
    )
    patch = nodes_flows.rag_support_node(state)

    assert len(calls) == 1
    assert patch.get("retrieval_retry_count") == 0


def test_retry_triggered_on_skipped(monkeypatch):
    calls = []

    class FakeSearchTool:
        def invoke(self, payload):
            calls.append(payload)
            if len(calls) == 1:
                return {
                    "context": "Gefundene Infos",
                    "retrieval_meta": {"skipped": True, "k_returned": 0, "top_scores": []},
                }
            return {
                "context": "OK",
                "retrieval_meta": {"k_returned": 1, "top_scores": [0.5]},
            }

    monkeypatch.setenv("RETRIEVAL_RETRY_MIN_TOP_SCORE", "0.20")
    monkeypatch.setenv("MIN_TOP_SCORE", "0.20")
    monkeypatch.setattr(nodes_flows, "search_knowledge_base", FakeSearchTool())

    state = SealAIState(
        messages=[HumanMessage(content="Bitte prüfe Normen für PTFE Dichtung")],
        user_id="user-1",
        tenant_id="tenant-1",
    )
    patch = nodes_flows.rag_support_node(state)

    assert len(calls) == 2
    assert patch.get("retrieval_retry_count") == 1
    meta = patch.get("retrieval_meta") or {}
    assert meta.get("retry_used") is True
    assert "rewrite_query" not in meta


def test_loop_safety_only_one_retry(monkeypatch):
    calls = []

    class FakeSearchTool:
        def invoke(self, payload):
            calls.append(payload)
            return {
                "context": "Gefundene Infos",
                "retrieval_meta": {"k_returned": 0, "top_scores": []},
            }

    monkeypatch.setenv("RETRIEVAL_RETRY_MIN_TOP_SCORE", "0.20")
    monkeypatch.setattr(nodes_flows, "search_knowledge_base", FakeSearchTool())

    state = SealAIState(
        messages=[HumanMessage(content="Normenvergleich für FKM")],
        user_id="user-1",
        tenant_id="tenant-1",
    )
    patch = nodes_flows.rag_support_node(state)

    assert len(calls) == 2
    assert patch.get("retrieval_retry_count") == 1
