import pytest
from app.agent.agent.graph import app
from app.agent.agent.state import SealingAIState, AgentState
from app.agent.case_state import build_default_sealing_requirement_spec
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

def create_initial_state_with_ptfe() -> SealingAIState:
    return {
        "observed": {"observed_inputs": [], "raw_parameters": {}},
        "normalized": {"identity_records": {}, "normalized_parameters": {}},
        "asserted": {
            "medium_profile": {"name": "PTFE-Compound"},
            "machine_profile": {},
            "installation_profile": {},
            "operating_conditions": {},
            "sealing_requirement_spec": build_default_sealing_requirement_spec(
                analysis_cycle_id="test_session",
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
            "analysis_cycle_id": "test_session",
            "snapshot_parent_revision": 0,
            "contract_obsolete": False,
            "state_revision": 1
        }
    }

def test_firewall_feedback_loop_limit_violation():
    """
    Test Phase H5:
    Verifiziert, dass der evidence_tool_node bei einem Limit-Verstoß 
    eine detaillierte ToolMessage zurückgibt.
    """
    # 1. State vorbereiten
    sealing_state = create_initial_state_with_ptfe()
    
    # 2. Wir simulieren einen AIMessage mit einem Tool-Call für 300°C
    # (Wir umgehen den reasoning_node und rufen direkt den evidence_tool_node auf)
    from app.agent.agent.graph import evidence_tool_node
    
    mock_tool_call_id = "call_ptfe_300"
    ai_msg = AIMessage(
        content="Ich trage die Temperatur von 300°C für PTFE ein.",
        tool_calls=[{
            "name": "submit_claim",
            "args": {
                "claim_type": "fact_observed",
                "statement": "Die Temperatur beträgt 300 C.",
                "confidence": 1.0
            },
            "id": mock_tool_call_id
        }]
    )
    
    agent_state: AgentState = {
        "messages": [
            HumanMessage(content="Ich habe PTFE und brauche 300°C."),
            ai_msg
        ],
        "sealing_state": sealing_state,
        "relevant_fact_cards": [
            {
                "topic": "PTFE Properties",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                "tags": ["ptfe"]
            }
        ]
    }
    
    # 3. Tool-Node ausführen
    output = evidence_tool_node(agent_state)
    
    # 4. Validierung der ToolMessage
    tool_msgs = [m for m in output["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_call_id == mock_tool_call_id
    assert "DOMAIN_LIMIT_VIOLATION" in tool_msgs[0].content
    assert "260" in tool_msgs[0].content
    assert "300" in tool_msgs[0].content

    # 5. Validierung des States
    new_sealing_state = output["sealing_state"]
    assert new_sealing_state["governance"]["release_status"] == "inadmissible"
    assert len(new_sealing_state["governance"]["conflicts"]) == 1
    assert new_sealing_state["governance"]["conflicts"][0]["type"] == "domain_limit_violation"
