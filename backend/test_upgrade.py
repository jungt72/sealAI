
import sys
import asyncio
from app.langgraph_v2.nodes.nodes_intent import intent_projector_node
from app.langgraph_v2.nodes.nodes_consulting import consulting_supervisor_node
from app.langgraph_v2.state import SealAIState
from langchain_core.messages import HumanMessage

def test_intent():
    print("--- Testing Intent Router ---")
    # Test 1: Consulting
    state = SealAIState(messages=[HumanMessage(content="Mein Getriebe ist undicht.")])
    result = intent_projector_node(state)
    print(f"Input: 'Mein Getriebe ist undicht.' -> Intent: {result['intent'].key} (Conf: {result['intent'].confidence})")
    
    # Test 2: Smalltalk
    print("DEBUG: Calling intent_projector_node for Smalltalk...")
    state = SealAIState(messages=[HumanMessage(content="Hallo, wer bist du?")])
    result = intent_projector_node(state)
    print(f"Input: 'Hallo, wer bist du?' -> Intent: {result['intent'].key} (Conf: {result['intent'].confidence})")

def test_supervisor():
    print("\n--- Testing Supervisor ---")
    # Test 1: Happy Path
    print("DEBUG: Calling consulting_supervisor_node...")
    state = SealAIState(
        parameters={"medium": "Öl", "temperature_max": 80, "pressure": 10},
        working_memory={}
    )
    result = consulting_supervisor_node(state)
    print(f"DEBUG: Result keys: {result.keys()}")
    decision = result['working_memory'].get('supervisor_decision')
    print(f"State: Params present -> Decision: {decision}")

if __name__ == "__main__":
    try:
        test_intent()
        test_supervisor()
        print("\nVerification Successful!")
    except Exception as e:
        print(f"\nVerification Failed: {e}")
        sys.exit(1)
