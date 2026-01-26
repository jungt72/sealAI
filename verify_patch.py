
import sys
import os
sys.path.append("/app")

# Mock environment if needed (though backend container has it)
if not os.getenv("QDRANT_URL"):
    os.environ["QDRANT_URL"] = "http://qdrant:6333"

try:
    from app.services.rag.rag_orchestrator import hybrid_retrieve
except ImportError as e:
    print(f"ImportError: {e}")
    # Fallback to local import if structure differs, but /app should work
    sys.exit(1)

def test_shared_access():
    print("Testing hybrid_retrieve with tenant='user-123' looking for 'Kyrolon'...")
    try:
        results = hybrid_retrieve(
            query="Kyrolon",
            tenant="user-123", # Acting as a different tenant
            k=5
        )
        
        # hybrid_retrieve returns (results, metrics) if return_metrics=True, but default is False -> results list
        if isinstance(results, tuple):
             results = results[0]

        if not results:
            print("FAIL: No results found.")
            sys.exit(1)
            
        print(f"SUCCESS: Found {len(results)} docs.")
        found_strict = False
        found_default = False
        
        for hit in results:
            tid = hit['metadata'].get('tenant_id')
            fname = hit['metadata'].get('filename')
            print(f"  - {fname} (Tenant: {tid})")
            
            if tid == 'default':
                found_default = True
            elif tid == 'user-123':
                found_strict = True
            
        if found_default:
            print("CONFIRMED: Retrieved 'default' tenant doc.")
        else:
            print("WARNING: Retrieved docs but not from default. Is Kyrolon copied?")

    except Exception as e:
        print(f"CRASH: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_shared_access()
