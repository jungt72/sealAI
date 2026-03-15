import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.agent.agent.state import AgentState, SealingAIState
from app.agent.case_state import build_default_sealing_requirement_spec
from app.agent.agent.graph import app, evidence_tool_node, reasoning_node, reasoning_node_sync, final_response_node
from app.agent.evidence.models import ClaimType
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage


async def _astream_once(message):
    yield message


def _stream_once(message):
    yield message


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
    mock_llm.bind_tools.return_value.astream = MagicMock(side_effect=lambda messages: _astream_once(mock_response))
    mock_llm.bind_tools.return_value.ainvoke = AsyncMock(side_effect=AssertionError("ainvoke must not be used"))
    
    state: AgentState = {
        "messages": [HumanMessage(content="Hallo")],
        "sealing_state": {} # Nicht relevant für diesen Node-Test
    }
    
    # Ausführung mit Mock
    with patch("app.agent.agent.graph.get_llm", return_value=mock_llm):
        result = asyncio.run(reasoning_node(state))
        
    # Validierung
    assert "messages" in result
    assert len(result["messages"]) == 1
    msg = result["messages"][0]
    assert isinstance(msg, AIMessage)
    assert msg.tool_calls[0]["name"] == "submit_claim"
    assert msg.tool_calls[0]["args"]["statement"] == "Medium ist Wasser."
    mock_llm.bind_tools.return_value.astream.assert_called_once()


def test_reasoning_node_sync_uses_streaming_model_call_for_active_graph_binding():
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value.stream = MagicMock(
        side_effect=lambda messages, config=None: _stream_once(AIMessage(content="Streaming active", tool_calls=[]))
    )
    mock_llm.bind_tools.return_value.invoke = MagicMock(side_effect=AssertionError("invoke must not be used"))

    state: AgentState = {
        "messages": [HumanMessage(content="Bitte streamen")],
        "sealing_state": {},
    }

    with patch("app.agent.agent.graph.get_llm", return_value=mock_llm):
        result = reasoning_node_sync(state)

    assert result["messages"][0].content == "Streaming active"
    mock_llm.bind_tools.return_value.stream.assert_called_once()

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
            "sealing_requirement_spec": build_default_sealing_requirement_spec(
                analysis_cycle_id="c1",
                state_revision=5,
            ),
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
            "sealing_requirement_spec": build_default_sealing_requirement_spec(
                analysis_cycle_id="c1",
                state_revision=1,
            ),
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
    from app.agent.agent.graph import router
    tool_call = {"name": "submit_claim", "args": {}, "id": "1"}
    state: AgentState = {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "sealing_state": {}
    }
    assert router(state) == "evidence_tool_node"


def test_final_response_node_uses_deterministic_guidance_contract():
    mock_llm = MagicMock()
    mock_llm.stream = MagicMock(side_effect=lambda messages, config=None: _stream_once(AIMessage(content="Bitte bestaetigen Sie noch Druck und Temperatur, dann fuehre ich den Fall weiter.")))

    sealing_state: SealingAIState = {
        "observed": {"observed_inputs": [], "raw_parameters": {}},
        "normalized": {"identity_records": {}, "normalized_parameters": {}},
        "asserted": {
            "medium_profile": {},
            "machine_profile": {},
            "installation_profile": {},
            "operating_conditions": {},
            "sealing_requirement_spec": build_default_sealing_requirement_spec(
                analysis_cycle_id="c1",
                state_revision=1,
            ),
        },
        "governance": {
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "scope_of_validity": [],
            "assumptions_active": [],
            "gate_failures": [],
            "unknowns_release_blocking": ["pressure_bar", "temperature_c"],
            "unknowns_manufacturer_validation": [],
            "conflicts": [],
        },
        "cycle": {
            "analysis_cycle_id": "c1",
            "snapshot_parent_revision": 0,
            "contract_obsolete": False,
            "contract_obsolete_reason": None,
            "state_revision": 1,
        },
        "selection": {
            "selection_status": "blocked_missing_required_inputs",
            "candidates": [],
            "viable_candidate_ids": [],
            "blocked_candidates": [{"candidate_id": "none", "block_reason": "blocked_missing_required_inputs"}],
            "winner_candidate_id": None,
            "recommendation_artifact": {
                "selection_status": "blocked_missing_required_inputs",
                "winner_candidate_id": None,
                "candidate_ids": [],
                "viable_candidate_ids": [],
                "blocked_candidates": [{"candidate_id": "none", "block_reason": "blocked_missing_required_inputs"}],
                "evidence_basis": [],
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "output_blocked": True,
                "trace_provenance_refs": [],
            },
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "output_blocked": True,
        },
    }
    state: AgentState = {
        "messages": [HumanMessage(content="Was fehlt noch fuer den Fall?")],
        "sealing_state": sealing_state,
        "working_profile": {},
    }

    with patch("app.agent.agent.graph.get_llm", return_value=mock_llm):
        result = final_response_node(state)

    assert result["messages"][0].content.startswith("Bitte bestaetigen Sie noch")
    prompt_messages = mock_llm.stream.call_args.args[0]
    assert "Visible Case Narrative Contract" in prompt_messages[1].content
    assert "critical_inputs" in prompt_messages[1].content
    assert "pressure_bar" in prompt_messages[1].content
    assert "temperature_c" in prompt_messages[1].content
    assert "qualification_blocked_by_missing_core_inputs" in prompt_messages[1].content
