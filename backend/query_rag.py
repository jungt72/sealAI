
import os
import sys
import asyncio
from dotenv import load_dotenv

# Load env vars from .env file if present
load_dotenv("/home/antigravity/sealai/backend/.env")

# OVERRIDE URL with FOUND IP
os.environ["QDRANT_URL"] = "http://172.18.0.2:6333"

# Add app to path
sys.path.append("/home/antigravity/sealai/backend")

from app.services.rag.rag_orchestrator import hybrid_retrieve

async def main():
    query = "Kyrolon"
    tenant_id = "default" 
    
    print(f"Querying RAG for '{query}'...")
    print(f"URL: {os.environ.get('QDRANT_URL')}")
    
    try:
        # Enable metrics to see errors
        results, metrics = hybrid_retrieve(
            query=query,
            tenant=tenant_id,
            k=5,
            return_metrics=True
        )
        
        print("\n--- Metrics / Error Info ---")
        print(metrics)
        
        if not results:
             print("\nNo results found for tenant 'default'. Trying 'sealai'...")
             results, metrics = hybrid_retrieve(
                 query="Kyrolon", 
                 tenant="sealai", 
                 k=5,
                 # return_metrics=True
             )
             
        if not results:
             print("\nNo results found for 'sealai'. Trying 'public'...")
             results, metrics = hybrid_retrieve(
                 query="Kyrolon", 
                 tenant="public", 
                 k=5
             )

        if not results:
            print("\nFinal: No results found.")
        else:
            print(f"\nFound {len(results)} results:")
            for i, hit in enumerate(results):
                print(f"\n--- Hit {i+1} (Score: {hit.get('fused_score') or hit.get('vector_score'):.4f}) ---")
                print(f"Source: {hit.get('source')}")
                # print(f"Metadata: {hit.get('metadata')}")
                print(f"Content: {hit.get('text')[:400]}...")

    except Exception as e:
        print(f"Fatal Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
