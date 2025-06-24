# backend/app/services/rag/rag_orchestrator.py

"""
RAG-Orchestrator: Erstellt einen Qdrant-Vectorstore für RAG-Workflows.
Alle Parameter (Modell, Collection, API-Key, K) kommen aus der zentralen Config.
Lädt HuggingFaceEmbeddings und QdrantClient nur einmal (Singleton Pattern)!
"""

from langchain_community.vectorstores import Qdrant
from langchain_community.embeddings import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from app.core.config import settings

# --- Singleton-Pattern: Modell und Client werden EINMAL geladen ---
_embeddings = None
_qdrant_client = None
_vectorstore = None

def get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
        )
    return _embeddings

def get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            api_key=getattr(settings, "qdrant_api_key", None),
        )
    return _qdrant_client

def get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = Qdrant(
            client=get_qdrant_client(),
            collection_name=settings.qdrant_collection,
            embeddings=get_embeddings(),   # Singleton!
        )
    return _vectorstore
