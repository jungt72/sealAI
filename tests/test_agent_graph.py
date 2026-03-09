import pytest
from unittest.mock import MagicMock, patch
from src.agent.state import AgentState, SealingAIState
from src.agent.graph import app, evidence_tool_node, reasoning_node
from src.evidence.models import ClaimType
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

def test_graph_compilation():
    """Test: Der Graph muss korrekt kompiliert sein und alle Nodes enthalten."""
    assert app is not None
    nodes = app.nodes
    assert "reasoning_node" in nodes
    assert "evidence_tool_node" in nodes

def test_reasoning_node_generates_tool_call():
    """
    Test Phase C5:
    Simuliert einen LLM-Aufruf im reasoning_node.
    Mockt das LLM, sodass es ein AIMessage mit einem tool_call auf submit_claim zurückgibt.
    """
    # Setup
    mock_llm = MagicMock()
    mock_response = AIMessage(
        content="Ich erkenne eine Medium-Änderung.",
        tool_calls=[{
            "name": "submit_claim",
            "args": {
                "claim_type": "fact_observed",
                "statement": "Medium ist Wasser.",
                "confidence": 1.0,
                "source_fact_ids": []
            },
            "id": "call_abc_123"
        }]
    )
    mock_llm.bind_tools.return_value.invoke.return_value = mock_response
    
    state: AgentState = {
        "messages": [HumanMessage(content="Hallo")],
        "sealing_state": {} # Nicht relevant für diesen Node-Test
    }
    
    # Ausführung mit Mock
    with patch("src.agent.graph.get_llm", return_value=mock_llm):
        result = reasoning_node(state)
        
    # Validierung
    assert "messages" in result
    assert len(result["messages"]) == 1
    msg = result["messages"][0]
    assert isinstance(msg, AIMessage)
    assert msg.tool_calls[0]["name"] == "submit_claim"
    assert msg.tool_calls[0]["args"]["statement"] == "Medium ist Wasser."

def test_evidence_tool_node_integration_conflict():
    """
    Integrationstest Phase C4:
    Simuliert, dass das LLM einen Claim einreicht, der einem assertierten Wert widerspricht.
    """
    sealing_state: SealingAIState = {
        "observed": {"observed_inputs": [], "raw_parameters": {}},
        "normalized": {"identity_records": {}, "normalized_parameters": {}},
        "asserted": {
            "medium_profile": {"name": "Wasser"},
            "machine_profile": {},
            "installation_profile": {},
            "sealing_requirement_spec": {}
        },
        "governance": {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "scope_of_validity": [],
            "conflicts": []
        },
        "cycle": {
            "analysis_cycle_id": "c1",
            "snapshot_parent_revision": 0,
            "contract_obsolete": False,
            "state_revision": 5
        }
    }
    
    tool_call = {
        "name": "submit_claim",
        "args": {
            "claim_type": ClaimType.FACT_OBSERVED,
            "statement": "Der Kunde sagt, das Medium ist Öl.",
            "confidence": 1.0,
            "source_fact_ids": ["input_2"]
        },
        "id": "call_999"
    }
    
    state: AgentState = {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "sealing_state": sealing_state
    }
    
    result = evidence_tool_node(state)
    new_sealing_state = result["sealing_state"]
    
    assert new_sealing_state["cycle"]["state_revision"] == 6
    conflicts = new_sealing_state["governance"]["conflicts"]
    assert len(conflicts) == 1
    assert conflicts[0]["severity"] == "CRITICAL"
    assert new_sealing_state["governance"]["release_status"] == "inadmissible"

def test_agent_state_schema():
    """Test: Der AgentState muss das 5-Schichten-Modell korrekt aufnehmen können."""
    sealing_state: SealingAIState = {
        "observed": {"observed_inputs": [], "raw_parameters": {}},
        "normalized": {"identity_records": {}, "normalized_parameters": {}},
        "asserted": {
            "medium_profile": {"name": "water"},
            "machine_profile": {},
            "installation_profile": {},
            "sealing_requirement_spec": {}
        },
        "governance": {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "scope_of_validity": [],
            "conflicts": []
        },
        "cycle": {
            "analysis_cycle_id": "c1",
            "snapshot_parent_revision": 0,
            "contract_obsolete": False,
            "state_revision": 1
        }
    }
    messages = [HumanMessage(content="Test")]
    agent_state: AgentState = {"messages": messages, "sealing_state": sealing_state}
    assert len(agent_state["messages"]) == 1
    assert agent_state["sealing_state"]["cycle"]["state_revision"] == 1

def test_graph_router_to_tools():
    """Test: Der Router soll 'evidence_tool_node' zurückgeben, wenn Tool-Calls vorhanden sind."""
    from src.agent.graph import router
    tool_call = {"name": "submit_claim", "args": {}, "id": "1"}
    state: AgentState = {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "sealing_state": {}
    }
    assert router(state) == "evidence_tool_node"
