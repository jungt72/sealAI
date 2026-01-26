
import asyncio
import json
import uuid
import datetime
import os
from redis.asyncio import Redis
import asyncpg
from dotenv import load_dotenv

# Load env to get any defaults, but we use discovered IPs
load_dotenv("/home/antigravity/sealai/backend/.env")

# Discovered Services
PG_HOST = "172.18.0.3"
PG_PORT = 5432
PG_USER = "sealai"
PG_PASS = "sealAI_dev_2025" # Found in .env
PG_DB = "sealai"

REDIS_HOST = "172.18.0.4"
REDIS_PORT = 6379
REDIS_PASS = "sealai_dev_redis_2025"

# File details
FILENAME = "PTFE_Kyrolon.txt"
FILEPATH_CONTAINER = "/app/backend/PTFE_Kyrolon.txt" # Mounted volume
TENANT_ID = "default" 
DOC_ID = uuid.uuid4().hex

async def main():
    print(f"--- Injecting Job for {FILENAME} ---")
    
    # 1. Insert into Postgres
    print(f"Connecting to Postgres {PG_HOST}...")
    try:
        conn = await asyncpg.connect(user=PG_USER, password=PG_PASS,
                                     database=PG_DB, host=PG_HOST, port=PG_PORT)
        
        # Check if doc exists (optional, simply insert new for now)
        print("Inserting document record...")
        
        # Calculate size/sha dummy
        file_size = 1234 
        sha256 = "dummy_sha_" + DOC_ID
        
        await conn.execute("""
            INSERT INTO rag_documents (
                document_id, tenant_id, status, visibility, filename, 
                content_type, size_bytes, sha256, path, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
        """, DOC_ID, TENANT_ID, "queued", "private", FILENAME, 
             "text/plain", file_size, sha256, FILEPATH_CONTAINER)
        
        await conn.close()
        print(f"DB Record created: {DOC_ID}")
        
    except Exception as e:
        print(f"Postgres Error: {e}")
        return

    # 2. Push to Redis
    print(f"Connecting to Redis {REDIS_HOST}...")
    try:
        redis = Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASS)
        
        payload = {
            "document_id": DOC_ID,
            "tenant_id": TENANT_ID,
            "path": FILEPATH_CONTAINER,
            "filepath": FILEPATH_CONTAINER,
            "original_filename": FILENAME,
            "uploader_id": "manual_injection",
            "category": "manual",
            "tags": ["manual", "kyrolon"],
            "visibility": "private",
            "sha256": sha256
        }
        
        data = json.dumps(payload)
        await redis.rpush("rag_ingest", data)
        await redis.aclose()
        print("Job enqueued to 'rag_ingest'.")
        
    except Exception as e:
        print(f"Redis Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
