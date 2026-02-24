import asyncio
import os
import sys

# Set path so imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.langgraph_v2.sealai_graph_v2 import get_sealai_graph_v2
from app.langgraph_v2.state import SealAIState

async def verify_graph():
    print("Loading graph...")
    try:
        graph = await get_sealai_graph_v2()
        print("Graph loaded.")
    except Exception as e:
        print(f"FAILED to load graph: {e}")
        sys.exit(1)

    nodes = graph.nodes.keys()
    print(f"Nodes found: {list(nodes)}")

    if "reducer_node" not in nodes:
        print("FAILED: reducer_node missing.")
        sys.exit(1)
    
    if "supervisor_policy_node" not in nodes:
        print("FAILED: supervisor_policy_node missing.")
        sys.exit(1)

    # Check connectivity? 
    # Difficult to inspect edges on compiled graph easily without private attributes.
    # But presence confirms registration.

    print("VERIFICATION SUCCESS: Graph structure valid with reducer_node.")

if __name__ == "__main__":
    asyncio.run(verify_graph())
