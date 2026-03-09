import pytest
from unittest.mock import MagicMock, patch
from src.agent.state import AgentState
from src.agent.graph import reasoning_node
from src.agent.knowledge import FactCard
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

def test_reasoning_node_rag_injection():
    """
    Unit Test Phase D1:
    Verifiziert, dass der reasoning_node RAG-Kontext korrekt in den System-Prompt injiziert.
    """
    # 1. Setup Mock Knowledge Base
    mock_cards = [
        FactCard({
            "id": "PTFE-F-001",
            "topic": "PTFE Chemical Resistance",
            "content": "PTFE is resistant to almost all chemicals.",
            "topic_tags": ["PTFE", "Chemicals"]
        })
    ]
    
    # 2. Setup State mit einer spezifischen Query
    state: AgentState = {
        "messages": [HumanMessage(content="Wie ist die chemische Beständigkeit von PTFE?")],
        "sealing_state": {
            "cycle": {"state_revision": 1}
        }
    }
    
    # 3. Setup LLM Mock
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="Test Antwort")
    
    # 4. Mocks für KB und LLM anwenden
    with patch("src.agent.graph.get_fact_cards", return_value=mock_cards), \
         patch("src.agent.graph.get_llm", return_value=mock_llm):
        
        reasoning_node(state)
        
        # 5. Verifikation des LLM-Aufrufs
        # Das gebundene LLM (llm_with_tools) wurde aufgerufen
        call_args = mock_llm.bind_tools.return_value.invoke.call_args[0][0]
        
        # Die erste Nachricht muss eine SystemMessage sein
        assert isinstance(call_args[0], SystemMessage)
        
        # Der Inhalt der SystemMessage muss den FactCard-Content enthalten
        system_content = call_args[0].content
        assert "PTFE is resistant to almost all chemicals" in system_content
        assert "SealAI Prequalification Agent" in system_content
        
        # Die ursprüngliche HumanMessage muss ebenfalls vorhanden sein
        assert isinstance(call_args[1], HumanMessage)
        assert call_args[1].content == "Wie ist die chemische Beständigkeit von PTFE?"

def test_reasoning_node_no_results_fallback():
    """
    Test: Wenn keine FactCards gefunden werden, soll ein Fallback-Text erscheinen.
    """
    state: AgentState = {
        "messages": [HumanMessage(content="Etwas völlig Unbekanntes")],
        "sealing_state": {}
    }
    
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="Keine Ahnung")
    
    with patch("src.agent.graph.get_fact_cards", return_value=[]), \
         patch("src.agent.graph.get_llm", return_value=mock_llm):
        
        reasoning_node(state)
        
        call_args = mock_llm.bind_tools.return_value.invoke.call_args[0][0]
        system_content = call_args[0].content
        assert "Keine relevanten Informationen in der Wissensdatenbank gefunden" in system_content
