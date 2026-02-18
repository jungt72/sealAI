from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes.nodes_frontdoor import frontdoor_discovery_node
from app.langgraph_v2.nodes.nodes_knowledge import generic_sealing_qa_node, knowledge_material_node
from app.langgraph_v2.state.sealai_state import SealAIState, Source


def test_knowledge_node_populates_sources(monkeypatch):
    mock_rets = {
        "context": "Sample RAG text",
        "retrieval_meta": {
            "skipped": False,
            "k_returned": 2,
            "top_scores": [0.95, 0.85],
            "sources": [
                {"source": "doc1.pdf", "metadata": {"title": "Document 1"}},
                {"url": "https://example.com/item", "metadata": {"title": "External source"}},
            ],
        },
    }

    mock_tool = MagicMock()
    mock_tool.invoke.return_value = mock_rets

    monkeypatch.setattr("app.langgraph_v2.nodes.nodes_knowledge.search_knowledge_base", mock_tool)
    monkeypatch.setattr("app.langgraph_v2.nodes.nodes_knowledge.run_llm", lambda **kwargs: "Mocked response")

    state = SealAIState(messages=[HumanMessage(content="Tell me about NBR")], tenant_id="tenant-1")

    patch = knowledge_material_node(state)

    assert patch.get("needs_sources") is True
    assert patch.get("sources_status") == "ok"
    assert len(patch.get("sources")) == 2
    assert isinstance(patch.get("sources")[0], Source)
    assert patch.get("sources")[0].source == "doc1.pdf"
    assert patch.get("sources")[1].source == "https://example.com/item"


def test_knowledge_node_missing_sources(monkeypatch):
    mock_rets = {
        "context": "No info found",
        "retrieval_meta": {"skipped": True, "k_returned": 0},
    }

    mock_tool = MagicMock()
    mock_tool.invoke.return_value = mock_rets

    monkeypatch.setattr("app.langgraph_v2.nodes.nodes_knowledge.search_knowledge_base", mock_tool)
    monkeypatch.setattr("app.langgraph_v2.nodes.nodes_knowledge.run_llm", lambda **kwargs: "Mocked response")

    state = SealAIState(messages=[HumanMessage(content="Unknown item")], tenant_id="tenant-1")

    patch = generic_sealing_qa_node(state)

    assert patch.get("needs_sources") is False
    assert patch.get("sources_status") == "missing"
    assert patch.get("sources") == []


def test_frontdoor_triggers_rag_for_knowledge(monkeypatch):
    mock_run_llm = MagicMock(
        return_value='{"intent": {"goal": "explanation_or_comparison", "key": "knowledge_material"}, "frontdoor_reply": "Ok"}'
    )
    monkeypatch.setattr("app.langgraph_v2.nodes.nodes_frontdoor.run_llm", mock_run_llm)
    monkeypatch.setattr("app.langgraph_v2.nodes.nodes_frontdoor.extract_parameters_from_text", lambda x: {})

    state = SealAIState(messages=[HumanMessage(content="Kyrolon 79X")])

    patch = frontdoor_discovery_node(state)

    assert patch["intent"].goal == "design_recommendation"
    assert patch.get("prompt_id_used") == "discovery/analysis"
    assert patch.get("last_node") == "frontdoor_discovery_node"


def test_frontdoor_triggers_rag_for_generic_qa(monkeypatch):
    monkeypatch.setattr(
        "app.langgraph_v2.nodes.nodes_frontdoor.run_llm",
        lambda **kwargs: '{"intent": {"goal": "explanation_or_comparison", "key": "generic_sealing_qa"}, "frontdoor_reply": "Ok"}',
    )
    monkeypatch.setattr("app.langgraph_v2.nodes.nodes_frontdoor.extract_parameters_from_text", lambda x: {})

    state = SealAIState(messages=[HumanMessage(content="How does it work?")])

    patch = frontdoor_discovery_node(state)

    assert patch["intent"].goal == "design_recommendation"
    assert patch.get("prompt_id_used") == "discovery/analysis"
    assert patch.get("last_node") == "frontdoor_discovery_node"


def test_frontdoor_sources_request_forces_rag(monkeypatch):
    monkeypatch.setattr(
        "app.langgraph_v2.nodes.nodes_frontdoor.run_llm",
        lambda **kwargs: '{"intent": {"goal": "design_recommendation"}, "frontdoor_reply": "Ok"}',
    )
    monkeypatch.setattr("app.langgraph_v2.nodes.nodes_frontdoor.extract_parameters_from_text", lambda x: {})

    state = SealAIState(messages=[HumanMessage(content="Kyrolon 79X - Quellen (filename, sha256) bitte.")])

    patch = frontdoor_discovery_node(state)

    assert patch["intent"].goal == "design_recommendation"
    assert patch.get("prompt_id_used") == "discovery/analysis"
    assert patch.get("last_node") == "frontdoor_discovery_node"
