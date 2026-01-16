from functools import lru_cache
import os
from typing import List
from langchain_community.embeddings import FastEmbedEmbeddings

EMBEDDING_MODEL = os.getenv(
    "EMB_MODEL_NAME",
    os.getenv("EMBEDDINGS_MODEL", "intfloat/multilingual-e5-base"),
)

_embedder = None

def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = FastEmbedEmbeddings(
            model_name=EMBEDDING_MODEL,
        )
    return _embedder

def embed_query_cached(texts: List[str]) -> List[List[float]]:
    """Embeds a list of texts using the shared model."""
    embedder = get_embedder()
    return embedder.embed_documents(texts)
