
import os
import sys
from qdrant_client import QdrantClient, models

# Import Ingest Logic
from app.services.rag.rag_ingest import IngestPipeline, COLLECTION_NAME
from app.services.rag.rag_schema import ChunkMetadata

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

def setup_v2():
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    
    print(f"[SETUP] Resetting collection: {COLLECTION_NAME}")
    client.delete_collection(COLLECTION_NAME)
    
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": models.VectorParams(size=1024, distance=models.Distance.COSINE)
        },
        sparse_vectors_config={
            "sparse": models.SparseVectorParams()
        }
    )
    print(f"[SETUP] Collection created. Starting Ingest...")
    
    # Ingest PTFE.txt
    file_path = "/app/rag_uploads/PTFE_recreated.txt"
    ingest = IngestPipeline()
    
    if os.path.exists(file_path):
        ingest.process_document(file_path, "default", "material")
        print("[SETUP] Ingest complete.")
    else:
        print(f"[ERROR] File not found: {file_path}")

if __name__ == "__main__":
    setup_v2()
