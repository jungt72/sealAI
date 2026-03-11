import pytest
from unittest.mock import patch, MagicMock
from app.agent.agent.graph import app
from app.agent.cli import create_initial_state
from langchain_core.messages import HumanMessage, AIMessage

@pytest.mark.asyncio
async def test_heuristic_extraction_only_affects_working_profile():
    """
    Wave 1: Integrationstest über den Graphen.
    Eingabe "5000 rpm" soll working_profile ändern, aber NICHT asserted state.
    """
    initial_sealing_state = create_initial_state()
    if "operating_conditions" not in initial_sealing_state["asserted"]:
        initial_sealing_state["asserted"]["operating_conditions"] = {}
        
    state = {
        "messages": [HumanMessage(content="Meine Anwendung läuft bei 5000 rpm.")],
        "sealing_state": initial_sealing_state,
        "working_profile": {},
        "tenant_id": "test_tenant"
    }
    
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="Ich habe die Drehzahl von 5000 rpm notiert.")
    
    # In dieser Graph-Version gibt es kein hybrid_retrieve Attribut im graph Modul
    with patch("app.agent.agent.graph.get_llm", return_value=mock_llm), \
         patch("app.agent.agent.graph.get_fact_cards", return_value=[]):
        
        final_state = await app.ainvoke(state)
    
    # 1. Working Profile muss den Wert haben (Heuristik via extract_parameters in reasoning_node)
    assert final_state["working_profile"]["speed"] == 5000.0
    
    # 2. Asserted State darf den Wert NICHT haben (Disziplin)
    assert "speed" not in final_state["sealing_state"]["asserted"]["machine_profile"]

def test_governed_claim_affects_asserted_state():
    """
    Wave 1: Integrationstest für den Governed Path.
    Ein expliziter Tool-Call (Claim) muss weiterhin den asserted state ändern.
    """
    from app.agent.agent.graph import evidence_tool_node
    from langchain_core.messages import AIMessage
    
    initial_sealing_state = create_initial_state()
    if "operating_conditions" not in initial_sealing_state["asserted"]:
        initial_sealing_state["asserted"]["operating_conditions"] = {}
    
    ai_msg = AIMessage(
        content="Ich trage 120 Grad ein.",
        tool_calls=[{
            "name": "submit_claim",
            "args": {
                "claim_type": "fact_observed",
                "statement": "Temperatur ist 120 C",
                "confidence": 1.0
            },
            "id": "call_123"
        }]
    )
    
    state = {
        "messages": [ai_msg],
        "sealing_state": initial_sealing_state,
        "working_profile": {},
        "relevant_fact_cards": []
    }
    
    output = evidence_tool_node(state)
    
    assert output["sealing_state"]["asserted"]["operating_conditions"]["temperature"] == 120.0
    assert output["sealing_state"]["cycle"]["state_revision"] == 2
