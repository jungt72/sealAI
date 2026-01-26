
import os
import sys
from qdrant_client import QdrantClient

# Env defaults matching backend
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
COLLECTION = os.getenv("QDRANT_COLLECTION", "sealai_knowledge")

def check_kyrolon():
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    
    print(f"Checking Qdrant at {QDRANT_URL} / {COLLECTION}...")
    
    # 1. Search generally for Kyrolon
    results = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=None,
        limit=10,
        with_payload=True,
        with_vectors=False
    )[0]
    
    found = False
    for pt in results:
        txt = (pt.payload.get("page_content") or "").lower()
        if "kyrolon" in txt:
            print(f"[MATCH] Found Kyrolon in doc {pt.id}")
            print(f"  Tenant: {pt.payload.get('metadata', {}).get('tenant_id')}")
            print(f"  Snippet: {txt[:100]}...")
            found = True
            
    if not found:
        print("[FAIL] Kyrolon NOT found in first 10 docs (scroll). trying text search...")
        # Text search not strictly via scroll, but let's trust scroll for now or try filter
        
        # Try filter for specific tenant if we knew it, but here we scan all
        from qdrant_client.http import models
        results = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="page_content",
                        match=models.MatchText(text="kyrolon")
                    )
                ]
            ),
            limit=5
        )[0]
        
        for pt in results:
            print(f"[MATCH-FILTER] Found Kyrolon in doc {pt.id}")
            print(f"  Tenant: {pt.payload.get('metadata', {}).get('tenant_id')}")
            found = True
            
    if not found:
        print("[CRITICAL] Kyrolon missing from Qdrant completely.")

if __name__ == "__main__":
    check_kyrolon()
