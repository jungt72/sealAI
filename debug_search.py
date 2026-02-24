import asyncio
from qdrant_client import QdrantClient
from fastembed import TextEmbedding
from app.core.config import settings

async def main():
    print(f"Lade Embedding-Modell: {settings.embedding_model}...")
    model = TextEmbedding(model_name=settings.embedding_model)
    query_vector = list(model.embed(["Was kannst du mir über Kyrolon sagen?"]))[0].tolist()

    client = QdrantClient(url=settings.qdrant_url)
    
    # Wir testen beide Collections!
    collections_to_test = [settings.qdrant_collection, "sealai_knowledge"]
    
    for coll in set(collections_to_test):
        print(f"\n--- Prüfe Collection: '{coll}' ---")
        try:
            # query_points statt search (neue Qdrant API)
            response = client.query_points(
                collection_name=coll,
                query=query_vector,
                limit=3,
                with_payload=True
            )
            
            # API Kompatibilität (manche Versionen geben direkt eine Liste zurück, andere ein Objekt)
            hits = response.points if hasattr(response, 'points') else response
            
            if not hits:
                print(f"Ergebnis: 0 Treffer. Die Collection ist leer oder hat keine passenden Vektoren.")
            else:
                for i, hit in enumerate(hits):
                    print(f"Treffer {i+1} (Score: {hit.score}) | Tenant: {hit.payload.get('tenant_id', 'N/A')}")
                    text = hit.payload.get('text', hit.payload.get('page_content', 'Kein Text'))
                    print(f"Snippet: {str(text)[:150]}...\n")
                    
        except Exception as e:
            print(f"Fehler bei dieser Collection: {e}")

if __name__ == "__main__":
    asyncio.run(main())
