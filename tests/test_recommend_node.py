import pytest
from unittest.mock import patch, MagicMock
from app.services.langgraph.graph.consult.nodes.recommend import recommend_node

def test_recommend_node_with_retrieved_docs():
    # Mock-State mit retrieved_docs
    state = {
        "messages": [],
        "missing": [],
        "params": {},
        "domain": "test",
        "derived": {},
        "retrieved_docs": [
            {"text": "Empfehlung 1", "source": "doc1"},
            {"text": "Empfehlung 2", "source": "doc2"}
        ],
        "context": None
    }

    # Mock config und events
    config = None
    events = None

    # Mock LLM und andere Abhängigkeiten
    with patch('app.services.langgraph.graph.consult.nodes.recommend.create_llm') as mock_create_llm, \
         patch('app.services.langgraph.graph.consult.nodes.recommend.render_template') as mock_render, \
         patch('app.services.langgraph.graph.consult.nodes.recommend.get_agent_prompt') as mock_get_prompt, \
         patch('app.services.langgraph.graph.consult.nodes.recommend.build_system_prompt_from_parts') as mock_build:

        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_llm.bind.return_value = mock_llm
        mock_render.return_value = "Mock prompt"
        mock_get_prompt.return_value = "Mock domain prompt"
        mock_build.return_value = "Mock system prompt"

        # Mock LLM Response
        mock_response = MagicMock()
        mock_response.content = '{"empfehlungen": [{"name": "Test Empfehlung"}], "text": "Mock answer"}'
        mock_llm.stream.return_value = [mock_response]

        result = recommend_node(state, config, events=events)

        # Assertions
        assert result["phase"] == "recommend"
        assert "empfehlungen" in result
        assert result["context"] == "Empfehlung 1\n[source: doc1]\n\nEmpfehlung 2\n[source: doc2]"  # Aus _context_from_docs
        assert len(result["empfehlungen"]) > 0

def test_recommend_node_empty_docs():
    state = {
        "messages": [],
        "missing": [],
        "params": {},
        "domain": "test",
        "derived": {},
        "retrieved_docs": [],
        "context": None
    }

    with patch('app.services.langgraph.graph.consult.nodes.recommend.create_llm') as mock_create_llm:
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_llm.bind.return_value = mock_llm
        mock_llm.stream.return_value = []

        result = recommend_node(state, config=None, events=None)

        assert result["context"] == ""  # Leere docs -> leerer context