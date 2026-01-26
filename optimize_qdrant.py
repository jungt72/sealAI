
import os
import sys
import time
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Config
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "sealai_knowledge")

def wait_for_qdrant(client: QdrantClient, timeout: int = 30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            client.get_collections()
            return True
        except Exception:
            time.sleep(1)
    return False

def optimize_collection():
    print(f"[OPTIMIZE] Connecting to {QDRANT_URL}...")
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    
    if not wait_for_qdrant(client):
        print("[ERROR] Could not connect to Qdrant.")
        sys.exit(1)

    # Check if collection exists
    exists = client.collection_exists(collection_name=COLLECTION_NAME)
    if not exists:
        print(f"[WARN] Collection '{COLLECTION_NAME}' does not exist yet. Please ingest data first.")
        # Optional: create it? Better to let ingest handle dimension logic.
        return

    print(f"[OPTIMIZE] Optimizing collection '{COLLECTION_NAME}'...")

    # Define indexes to create
    # metadata.tenant_id is CRITICAL for isolation filtering
    indexes = [
        ("metadata.tenant_id", models.PayloadSchemaType.KEYWORD),
        ("metadata.document_id", models.PayloadSchemaType.KEYWORD),
        ("metadata.category", models.PayloadSchemaType.KEYWORD),
        ("metadata.visibility", models.PayloadSchemaType.KEYWORD),
        ("metadata.source", models.PayloadSchemaType.KEYWORD),
        ("metadata.chunk_index", models.PayloadSchemaType.INTEGER),
    ]

    for field_name, schema_type in indexes:
        print(f"  -> Creating index for '{field_name}' ({schema_type})...")
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field_name,
                field_schema=schema_type,
            )
        except Exception as e:
            # Often fails if index already exists or is building, which is fine
            print(f"     (Note: {e})")

    print("[SUCCESS] Optimization commands sent. Indexes are building in background.")

if __name__ == "__main__":
    optimize_collection()
