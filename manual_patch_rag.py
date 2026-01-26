import sys

NODES_FILE = '/home/thorsten/sealai/backend/app/langgraph_v2/nodes/nodes_flows.py'
GRAPH_FILE = '/home/thorsten/sealai/backend/app/langgraph_v2/sealai_graph_v2.py'

def patch_nodes():
    print(f"Reading {NODES_FILE}...")
    with open(NODES_FILE, 'r') as f:
        content = f.read()
    
    # Target block in nodes_flows.py
    target = '"last_node": "rag_support_node",'
    replacement = '"last_node": "rag_support_node",\n        "needs_sources": False,\n        "requires_rag": False,'
    
    if target in content and '"needs_sources": False' not in content:
        print("Injecting flags into rag_support_node return...")
        new_content = content.replace(target, replacement)
        with open(NODES_FILE, 'w') as f:
            f.write(new_content)
        print("Success: nodes_flows.py patched.")
    else:
        print("Skipping nodes_flows.py (pattern not found or already patched).")

def patch_graph():
    print(f"Reading {GRAPH_FILE}...")
    with open(GRAPH_FILE, 'r') as f:
        lines = f.readlines()
        
    target_edge = 'builder.add_edge("rag_support_node", "supervisor_policy_node")'
    new_lines = []
    removed = False
    
    for line in lines:
        if target_edge in line:
            print(f"Removing duplicate edge: {line.strip()}")
            removed = True
            continue
        new_lines.append(line)
        
    if removed:
        with open(GRAPH_FILE, 'w') as f:
            f.writelines(new_lines)
        print("Success: sealai_graph_v2.py patched.")
    else:
        print("Skipping sealai_graph_v2.py (duplicate edge not found).")

if __name__ == "__main__":
    patch_nodes()
    patch_graph()
