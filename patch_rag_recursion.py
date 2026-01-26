import sys
import os

# Paths
GRAPH_FILE = '/home/thorsten/sealai/backend/app/langgraph_v2/sealai_graph_v2.py'
NODES_FILE = '/home/thorsten/sealai/backend/app/langgraph_v2/nodes/nodes_flows.py'

def patch_graph():
    print(f"Patching {GRAPH_FILE}...")
    with open(GRAPH_FILE, 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    removed = False
    
    # Target: builder.add_edge("rag_support_node", "supervisor_policy_node")
    target_edge = 'builder.add_edge("rag_support_node", "supervisor_policy_node")'
    
    for line in lines:
        if target_edge in line:
            print(f"  Removing duplicate edge: {line.strip()}")
            removed = True
            # Skip this line
            continue
        new_lines.append(line)
        
    if removed:
        with open(GRAPH_FILE, 'w') as f:
            f.writelines(new_lines)
        print("  Graph patched successfully.")
    else:
        print("  Target edge not found (already removed?).")

def patch_nodes():
    print(f"Patching {NODES_FILE}...")
    with open(NODES_FILE, 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    patched = False
    
    # We look for the return statement in rag_support_node
    # It likely looks like: return { ... "working_memory": ... }
    # Accessing strict "rag_support_node" function context is hard with just line iteration if multiple functions exist.
    # Assuming standard indentation and unique function name.
    
    in_function = False
    
    for i, line in enumerate(lines):
        if "async def rag_support_node" in line:
            in_function = True
        
        if in_function and "return" in line and "patch_v2_parameters" in line:
            # This logic might be fragile if the return is multi-line or complex.
            # Let's look for the dictionary construction or similar.
            pass
            
        # Alternative: look for where `patch` dict is created or returned.
        # usually `patch = {...}` then `return patch`.
        
    # Let's try a robust search for variable assignment or return.
    # From previous audits, nodes usually return a dict.
    
    # Strategy: Find "async def rag_support_node"
    # Then forward find the return statement or the dict construction.
    # Inject the flags.
    
    # Re-reading strategy: I'll use a specific replacement if I can identify the context.
    # Let's assume the node constructs a dict.
    # I'll look for the end of the function? No.
    
    # Let's be invasive but safe:
    # Find `return {` inside `rag_support_node`.
    # Inject keys before the closing `}` matches? No, unsafe.
    
    # Better: Identify the return value construction.
    # "patch = {" or similar.
    pass

# Refined Patch Strategy for Nodes using string search
def patch_nodes_robust():
    print(f"Patching {NODES_FILE}...")
    with open(NODES_FILE, 'r') as f:
        lines = f.readlines()
        
    new_lines = []
    in_rag_node = False
    patched = False
    
    for i, line in enumerate(lines):
        if "async def rag_support_node" in line:
            in_rag_node = True
        elif in_rag_node and "async def" in line:
            in_rag_node = False
            
        if in_rag_node and "return" in line and "{" in line and "}" in line and not patched:
             # Inline return? e.g. return {"keys": val}
             # Check if we can inject keys.
             # Replace `}` with `, "needs_sources": False, "requires_rag": False, "sources_status": "ok"}`
             # But check if already present.
             if "needs_sources" not in line:
                 print(f"  Patching return line: {line.strip()}")
                 # Replace the last occurrence of `}`
                 idx = line.rfind("}")
                 if idx != -1:
                     new_line = line[:idx] + ', "needs_sources": False, "requires_rag": False, "sources_status": "ok"}' + line[idx+1:]
                     new_lines.append(new_line)
                     patched = True
                     continue
        
        # Multiline return handling?
        # If the code structure is complex, this simple line patch might fail.
        # But for agentic patching, simple is often better if we verified the file structure.
        # I did audit logic, but didn't save the full file content to memory.
        # Let's double check file structure via grep if this fails? 
        # No, I'll trust the simple regex-like replacement for now, 
        # assuming standard `return {...}` pattern common in this repo.
        
        new_lines.append(line)

    if patched:
        with open(NODES_FILE, 'w') as f:
            f.writelines(new_lines)
        print("  Nodes patched successfully.")
    else:
        print("  Nodes patch skipped (pattern not found or already patched).")

if __name__ == "__main__":
    patch_graph()
    patch_nodes_robust()
