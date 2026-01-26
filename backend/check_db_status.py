
import asyncio
import asyncpg
import sys

PG_HOST = "172.18.0.3"
PG_PORT = 5432
PG_USER = "sealai"
PG_PASS = "sealAI_dev_2025"
PG_DB = "sealai"

DOC_ID = "480b3ffb51664ecf99433318decc1b98" 

async def main():
    print(f"Checking Document {DOC_ID}...")
    try:
        conn = await asyncpg.connect(user=PG_USER, password=PG_PASS,
                                     database=PG_DB, host=PG_HOST, port=PG_PORT)
        
        row = await conn.fetchrow("SELECT status, error, ingest_stats FROM rag_documents WHERE document_id = $1", DOC_ID)
        await conn.close()
        
        if row:
            print(f"Status: {row['status']}")
            print(f"Error: {row['error']}")
            print(f"Stats: {row['ingest_stats']}")
        else:
            print("Document not found!")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
