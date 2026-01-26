import asyncio
from app.langgraph_v2.nodes.nodes_supervisor import supervisor_policy_node, ACTION_RUN_PANEL_NORMS_RAG
from app.langgraph_v2.state import SealAIState, Intent, WorkingMemory
from app.langgraph_v2.phase import PHASE
from langchain_core.messages import HumanMessage

async def repro():
    # Simulate state after Frontdoor has identified a knowledge intent
    state = SealAIState(
        messages=[HumanMessage(content="Suche nach Normen f??r NBR.", id="msg-1")],
        intent=Intent(
            category="knowledge", 
            key="knowledge_norms", 
            confidence=0.9, 
            knowledge_type="norms"
        ),
        working_memory=WorkingMemory(),
        phase=PHASE.SUPERVISOR,
        requires_rag=True, # Frontdoor should have set this
        user_id="user-1",
        thread_id="chat-1",
        tenant_id="tenant-1"
    )

    print("--- INPUT STATE ---")
    print(f"Intent: {state.intent}")
    print(f"Requires RAG: {state.requires_rag}")
    
    # Run Supervisor Node Logic
    # We want to know if it selects ACTION_RUN_PANEL_NORMS_RAG
    
    try:
        result = supervisor_policy_node(state)
        print("\n--- OUTPUT RESULT ---")
        print(result)
        
        action = result.get("next_action")
        print(f"\nSelected Action: {action}")
        
        if action == ACTION_RUN_PANEL_NORMS_RAG:
            print("SUCCESS: Supervisor routed to Panel Norms RAG.")
        else:
            print(f"FAILURE: Supervisor routed to {action} instead of {ACTION_RUN_PANEL_NORMS_RAG}.")
            
    except Exception as e:
        print(f"CRASH: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(repro())
