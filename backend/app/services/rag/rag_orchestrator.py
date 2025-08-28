import os
from qdrant_client import QdrantClient
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore

def get_settings():
    return {
        "embedding_model": os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
        "qdrant_url": os.getenv("QDRANT_URL", "http://qdrant:6333"),
        "qdrant_api_key": os.getenv("QDRANT_API_KEY"),
        "qdrant_collection": os.getenv("QDRANT_COLLECTION", "sealai-docs-bge-m3"),
        "rag_k": int(os.getenv("RAG_TOP_K", "3")),
        "normalize": os.getenv("EMBED_NORMALIZE", "true").lower() == "true",
    }

def get_embeddings() -> HuggingFaceEmbeddings:
    s = get_settings()
    return HuggingFaceEmbeddings(
        model_name=s["embedding_model"],
        encode_kwargs={"normalize_embeddings": s["normalize"]},
    )

def get_qdrant_client() -> QdrantClient:
    s = get_settings()
    return QdrantClient(url=s["qdrant_url"], api_key=s["qdrant_api_key"], prefer_grpc=True)

def get_vectorstore() -> QdrantVectorStore:
    s = get_settings()
    client = get_qdrant_client()
    embeddings = get_embeddings()
    return QdrantVectorStore(
        client=client,
        collection_name=s["qdrant_collection"],
        embedding=embeddings,
    )

def get_retriever():
    s = get_settings()
    vs = get_vectorstore()
    return vs.as_retriever(search_kwargs={"k": s["rag_k"]})
