import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agent.agent.state import AgentState, SealingAIState
from app.agent.case_state import build_default_sealing_requirement_spec
from app.agent.agent.graph import app
from app.agent.evidence.models import ClaimType
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage


def _stream_once(message):
    yield message


def test_e2e_agent_conflict_injection():
    """
    E2E Test Phase C6:
    Beweist, dass der kompilierte LangGraph den LLM-Output sicher in den 
    SealingAIState übersetzt und die Engineering Firewall auslöst.
    
    Ablauf:
    1. Initial State: Wasser (Revision 1)
    2. Input: "Kunde will nun Öl einsetzen"
    3. LLM (Mock): Generiert submit_claim("Medium ist Öl")
    4. Graph: reasoning_node -> router -> evidence_tool_node -> reasoning_node -> router -> END
    5. Validierung: Konflikt erkannt, Revision 2.
    """
    
    # 1. Initialer SealingAIState (Assertiert: Wasser)
    initial_sealing_state: SealingAIState = {
        "observed": {"observed_inputs": [], "raw_parameters": {}},
        "normalized": {"identity_records": {}, "normalized_parameters": {}},
        "asserted": {
            "medium_profile": {"name": "Wasser"},
            "machine_profile": {},
            "installation_profile": {},
            "sealing_requirement_spec": build_default_sealing_requirement_spec(
                analysis_cycle_id="session_e2e_1",
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
            "analysis_cycle_id": "session_e2e_1",
            "snapshot_parent_revision": 0,
            "contract_obsolete": False,
            "state_revision": 1
        }
    }
    
    # 2. AgentState vorbereiten
    initial_messages = [HumanMessage(content="Kunde will nun Öl einsetzen")]
    agent_state: AgentState = {
        "messages": initial_messages,
        "sealing_state": initial_sealing_state
    }
    
    # 3. LLM Mock konfigurieren
    # Erster Aufruf: Tool Call (Öl)
    # Zweiter Aufruf: Finale Antwort (keine Tools)
    mock_llm = MagicMock()
    
    tool_call_response = AIMessage(
        content="Ich muss das Medium auf Öl ändern.",
        tool_calls=[{
            "name": "submit_claim",
            "args": {
                "claim_type": "fact_observed",
                "statement": "Medium ist Öl.",
                "confidence": 1.0,
                "source_fact_ids": []
            },
            "id": "call_e2e_999"
        }]
    )
    
    final_response = AIMessage(
        content="Der Konflikt wurde im System vermerkt. Eine Freigabe ist aktuell nicht möglich.",
        tool_calls=[]
    )
    
    mock_llm.bind_tools.return_value.stream = MagicMock(
        side_effect=[
            _stream_once(tool_call_response),
            _stream_once(final_response),
        ]
    )
    mock_llm.stream = MagicMock(
        side_effect=lambda messages, config=None: _stream_once(
            AIMessage(
                content="Ich habe den Konflikt dokumentiert. Fuer eine Freigabe brauche ich erst einen konsistenten, neu bestaetigten Fallstand.",
                tool_calls=[],
            )
        )
    )
    
    # 4. Graphen ausführen
    with patch("app.agent.agent.graph.retrieve_rag_context", new=AsyncMock(return_value=[])), \
         patch("app.agent.agent.graph.get_fact_cards", return_value=[]), \
         patch("app.agent.agent.graph.get_llm", return_value=mock_llm):
        final_output = app.invoke(agent_state)
        
    # 5. Verifiziere Nachrichten-Historie
    # Human -> AI (ToolCall) -> ToolMessage -> AI (LLM Final) -> AI (Governed Final Reply)
    messages = final_output["messages"]
    assert len(messages) == 5
    assert isinstance(messages[0], HumanMessage)
    assert isinstance(messages[1], AIMessage) and messages[1].tool_calls
    assert isinstance(messages[2], ToolMessage)
    assert isinstance(messages[3], AIMessage) and not messages[3].tool_calls
    assert isinstance(messages[4], AIMessage) and not messages[4].tool_calls
    assert "Konflikt" in messages[4].content
    
    # 6. Verifiziere Engineering Firewall (sealing_state)
    final_sealing_state = final_output["sealing_state"]
    
    # Revision muss gestiegen sein
    assert final_sealing_state["cycle"]["state_revision"] == 2
    assert final_sealing_state["cycle"]["snapshot_parent_revision"] == 1
    
    # Kritischer Konflikt muss existieren
    conflicts = final_sealing_state["governance"]["conflicts"]
    assert len(conflicts) == 1
    assert conflicts[0]["severity"] == "CRITICAL"
    assert conflicts[0]["field"] == "medium"
    assert "Wasser" in conflicts[0]["message"]
    assert "öl" in conflicts[0]["message"].lower()
    
    # Release Status blockiert
    assert final_sealing_state["governance"]["release_status"] == "inadmissible"
