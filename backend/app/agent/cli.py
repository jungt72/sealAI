import json
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage
from app.agent.agent.graph import app
from app.agent.agent.state import AgentState, SealingAIState

def create_initial_state() -> SealingAIState:
    """
    Erzeugt einen sauberen, leeren Blueprint-State (Phase E1).
    Entspricht dem 5-Schichten-Modell aus Phase A.
    """
    return {
        "observed": {
            "observed_inputs": [],
            "raw_parameters": {}
        },
        "normalized": {
            "identity_records": {},
            "normalized_parameters": {}
        },
        "asserted": {
            "medium_profile": {},
            "machine_profile": {},
            "installation_profile": {},
            "sealing_requirement_spec": {}
        },
        "governance": {
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "scope_of_validity": [],
            "conflicts": []
        },
        "cycle": {
            "analysis_cycle_id": "session_init_1",
            "snapshot_parent_revision": 0,
            "contract_obsolete": False,
            "state_revision": 1
        }
    }

def run_agent(query: str, use_mock: bool = False):
    """
    Startet den LangGraph-Agenten mit einer Query (Phase E1).
    """
    print(f"--- Starte Agent mit Query: '{query}' ---")
    
    # Initialer State
    sealing_state = create_initial_state()
    agent_state: AgentState = {
        "messages": [HumanMessage(content=query)],
        "sealing_state": sealing_state
    }
    
    # Mocking Setup (optional für Betrieb ohne OpenAI Key)
    if use_mock:
        mock_llm = MagicMock()
        # Simuliere: LLM erkennt Wasser und 10 bar und reicht einen Claim ein
        mock_response = AIMessage(
            content="Ich habe Ihre Anfrage verstanden. Ich werde das Medium 'Wasser' und den Druck '10 bar' im System hinterlegen.",
            tool_calls=[{
                "name": "submit_claim",
                "args": {
                    "claim_type": "fact_observed",
                    "statement": "Medium ist Wasser, Druck ist 10 bar.",
                    "confidence": 1.0,
                    "source_fact_ids": []
                },
                "id": "call_mock_123"
            }]
        )
        # Zweiter Aufruf (nach Tool-Execution) gibt finale Antwort
        final_response = AIMessage(
            content="Die Parameter wurden erfolgreich im technischen State hinterlegt.",
            tool_calls=[]
        )
        
        mock_llm.bind_tools.return_value.invoke.side_effect = [mock_response, final_response]
        
        with patch("src.agent.graph.get_llm", return_value=mock_llm):
            final_output = app.invoke(agent_state)
    else:
        # Echter LLM Aufruf (benötigt OPENAI_API_KEY)
        final_output = app.invoke(agent_state)
        
    # Ergebnisse ausgeben
    res_state = final_output["sealing_state"]
    
    print("\n--- Technischer State (SealingAIState) ---")
    print(f"Revision: {res_state['cycle']['state_revision']}")
    print(f"Release Status: {res_state['governance']['release_status']}")
    
    print("\n--- Konflikte im Governance-Layer ---")
    if res_state['governance']['conflicts']:
        print(json.dumps(res_state['governance']['conflicts'], indent=2))
    else:
        print("Keine Konflikte gefunden.")
        
    print("\n--- Letzte Antwort des Agenten ---")
    print(final_output["messages"][-1].content)
    
    return final_output

if __name__ == "__main__":
    # Beispielaufruf im Mock-Modus
    run_agent("Ich brauche eine Dichtung für 10 bar Wasser", use_mock=True)
