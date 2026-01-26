
import os
import sys
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Env defaults matching backend
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
COLLECTION = os.getenv("QDRANT_COLLECTION", "sealai_knowledge")

DOC_ID = "0b910180-ed08-4c7e-86d4-9a00a9ceeaa3"

def verify_isolation():
    print(f"Connecting to {QDRANT_URL} / {COLLECTION}...")
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    
    # 1. Fetch specific doc
    print(f"\n--- Fetching Doc {DOC_ID} ---")
    points = client.retrieve(
        collection_name=COLLECTION,
        ids=[DOC_ID],
        with_payload=True
    )
    
    if not points:
        print("FAIL: Doc not found by ID. ID might be differnet or collection wrong.")
        return

    pt = points[0]
    print(f"Payload keys: {list(pt.payload.keys())}")
    meta = pt.payload.get("metadata", {})
    print(f"Metadata: {meta}")
    tenant = meta.get("tenant_id")
    print(f"Tenant in metadata: '{tenant}'")
    
    # 2. Try simple Tenant Filter
    print(f"\n--- Testing Filter: metadata.tenant_id = '{tenant}' ---")
    results = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.tenant_id",
                    match=models.MatchValue(value=tenant)
                )
            ]
        ),
        limit=5
    )[0]
    
    found = any(p.id == DOC_ID for p in results)
    if found:
        print("SUCCESS: Found doc via tenant filter.")
    else:
        print("FAILURE: Did not find doc via tenant filter.")
        # Debug: what did we find?
        for p in results:
            print(f"  Found other: {p.id}")

if __name__ == "__main__":
    verify_isolation()
