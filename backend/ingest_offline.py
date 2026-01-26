
import os
import sys
import asyncio
import uuid
from datetime import datetime
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer

# Load env vars
load_dotenv("/home/antigravity/sealai/backend/.env")

# Config matches production
QDRANT_URL = "http://172.18.0.2:6333" # IP found by scanner
COLLECTION_NAME = "sealai-docs" # From .env
MODEL_NAME = "jinaai/jina-embeddings-v2-base-de" # From .env

def ingest_file(filepath: str, tenant_id: str = "default"):
    print(f"--- Ingesting {filepath} for tenant '{tenant_id}' ---")
    
    # 1. Read Content
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    
    # 2. Chunking (Simple split for now)
    chunks = [text[i:i+800] for i in range(0, len(text), 800)]
    print(f"Created {len(chunks)} chunks.")

    # 3. Embedding
    print(f"Loading model {MODEL_NAME}...")
    # Trust remote code needed for jina models
    encoder = SentenceTransformer(MODEL_NAME, trust_remote_code=True)
    embeddings = encoder.encode(chunks, normalize_embeddings=True)
    print("Embedding complete.")

    # 4. Upload to Qdrant
    client = QdrantClient(url=QDRANT_URL)
    
    points = []
    doc_id = str(uuid.uuid4())
    
    for i, (chunk, vec) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid4())
        payload = {
            "text": chunk,
            "source": "manual_upload",
            "filename": os.path.basename(filepath),
            "page": 1,
            "metadata": {
                "tenant_id": tenant_id, # CRITICAL
                "document_id": doc_id,
                "chunk_index": i,
                "visibility": "public",
            }
        }
        points.append(models.PointStruct(
            id=point_id,
            vector=vec.tolist(),
            payload=payload
        ))

    print(f"Uploading {len(points)} points to collection '{COLLECTION_NAME}'...")
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )
    print("Success!")

if __name__ == "__main__":
    # Ingest for both 'default' and 'sealai' tenants to be sure
    ingest_file("PTFE_Kyrolon.txt", tenant_id="default")
    ingest_file("PTFE_Kyrolon.txt", tenant_id="sealai")
