import asyncio
import sys
import os

# Pfade setzen
sys.path.append('/home/thorsten/sealai/backend')

from app.langgraph_v2.state import SealAIState, Parameters
from app.langgraph_v2.nodes.nodes_critic import technical_critic_node

def test_critic():
    print("--- Starte Technical Critic Test ---")
    
    # Szenario: Hoher Druck (150 bar) + Aceton + NBR (falsches Material)
    state = SealAIState(
        parameters=Parameters(
            pressure=150,
            temperature=50,
            medium="Aceton"
        ),
        material_choice={"material": "NBR", "back_up_ring": False},
        calc_results=None
    )
    
    print(f"Test-Input: Druck={state.parameters.pressure} bar, Medium={state.parameters.medium}, Material={state.material_choice['material']}")
    
    # Node ausführen
    result = technical_critic_node(state)
    
    feedback = result.get("critic_feedback", {})
    print(f"Status: {feedback.get('status')}")
    print("Gefundene Probleme:")
    for issue in feedback.get("issues", []):
        print(f" - {issue}")
    
    if feedback.get('status') == 'rejected' and len(feedback.get('issues')) >= 2:
        print("\n✅ TEST ERFOLGREICH: Critic hat die Fehler korrekt erkannt.")
    else:
        print("\n❌ TEST FEHLGESCHLAGEN: Critic hat nicht wie erwartet reagiert.")

if __name__ == "__main__":
    test_critic()
