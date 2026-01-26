
import sys
from app.services.rag.rag_orchestrator import hybrid_retrieve
from pprint import pprint

# Manual setup for standalone test (if env vars are handled by container)
import os
# os.environ["QDRANT_API_KEY"] = "..."

def run():
    print("[CHECK] Testing Canonical Orchestrator...")
    results = hybrid_retrieve(query="PTFE", tenant="default")
    
    if not results:
        print("[FAIL] No results.")
        sys.exit(1)
        
    first = results[0]
    pprint(first)
    
    if not isinstance(first, dict):
        print(f"[FAIL] Expected dict, got {type(first)}")
        sys.exit(1)
        
    if "metadata" not in first:
         print("[FAIL] Missing 'metadata' key in result")
         sys.exit(1)
         
    eng = first["metadata"].get("eng")
    if eng:
         print(f"[SUCCESS] Engineering metadata found: {eng.get('material_family')}")
    else:
         print("[WARN] Engineering metadata empty/missing.")
         
    print("[VERIFIED] Canonical integration functional.")

if __name__ == "__main__":
    run()
