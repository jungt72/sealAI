from __future__ import annotations
# backend/app/services/rag/rag_orchestrator.py
"""
RAG-Orchestrator
----------------
- Laedt Embeddings, Qdrant-Client und VectorStore im Singleton-Pattern
- Erstellt einen Retriever (dense + optional BM25-sparse)
"""
from typing import Optional, List
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import Qdrant
from qdrant_client import QdrantClient
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from app.core.config import settings
import logging
log = logging.getLogger(__name__)
# -------------------------------------------------------------------
# Singletons
# -------------------------------------------------------------------
_dense_embeddings: Optional[HuggingFaceEmbeddings] = None
_qdrant_client: Optional[QdrantClient] = None
_vectorstore: Optional[Qdrant] = None
# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def get_dense_embeddings() -> HuggingFaceEmbeddings:
    global _dense_embeddings
    if _dense_embeddings is None:
        _dense_embeddings = HuggingFaceEmbeddings(model_name=settings.embedding_model)
    return _dense_embeddings
def get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            prefer_grpc=True,
            timeout=0.5,
            grpc_options={
                "grpc.keepalive_time_ms": 20_000,
                "grpc.max_send_message_length": -1,
                "grpc.max_receive_message_length": -1,
            },
        )
    return _qdrant_client
def get_vectorstore() -> Qdrant:
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = Qdrant(
            client=get_qdrant_client(),
            collection_name=settings.qdrant_collection,
            embeddings=get_dense_embeddings(),
        )
    return _vectorstore
# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------
def get_retriever():
    """Erzeugt einen Hybrid-Retriever (dense + optional BM25)."""
    vectorstore = get_vectorstore()
    # Dense-Retriever (MPNet / o. Ä.)
    dense_retriever = vectorstore.as_retriever(
        search_kwargs={"k": getattr(settings, "rag_k", 3)}
    )
    # --- Optionaler BM25-Fallback ------------------------------------
    sparse_retriever: Optional[BM25Retriever] = None
    docs: Optional[List] = getattr(vectorstore, "_documents", None)
    # Manche VectorStore-Wrapper halten die Original-Docs; Qdrant tut das nicht.
    if docs:
        sparse_retriever = BM25Retriever.from_documents(
            docs, k=getattr(settings, "rag_k", 3)
        )
        log.info("BM25 Fallback aktiviert – %s Dokumente", len(docs))
    else:
        log.info("Kein BM25 Fallback (Qdrant hält keine Dokumente im Speicher)")
    # Wenn kein sparse Retriever vorhanden, gib den dichten direkt zurück
    if sparse_retriever is None:
        return dense_retriever
    # Ansonsten beide kombinieren
    return EnsembleRetriever(
        retrievers=[dense_retriever, sparse_retriever],
        weights=[0.7, 0.3],
    )
