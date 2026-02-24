import asyncio
import sys
import os
from dotenv import load_dotenv

# Load dummy env BEFORE importing app modules
load_dotenv('backend/.env.test')

from langgraph.store.memory import InMemoryStore
from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2
from langgraph.checkpoint.memory import MemorySaver

async def verify_graph_wiring():
    print("Verifying Graph Wiring with BaseStore...")
    
    # 1. Use InMemoryStore as proxy for AsyncPostgresStore (both are BaseStore)
    store = InMemoryStore()
    checkpointer = MemorySaver()
    
    try:
        # Compile graph
        graph = create_sealai_graph_v2(checkpointer=checkpointer, store=store, require_async=True)
        print("✅ Graph compiled successfully with Store")
        
        # Verify node presence
        if "profile_loader_node" in graph.nodes:
             print("✅ profile_loader_node present in graph")
        else:
             print("❌ profile_loader_node MISSING")
             sys.exit(1)
             
    except Exception as e:
        print(f"❌ Graph compilation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(verify_graph_wiring())
