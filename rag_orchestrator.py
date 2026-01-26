
from __future__ import annotations
import os
import logging
from typing import List, Optional, Dict, Any, Tuple
from qdrant_client import QdrantClient, models
from .rag_schema import ChunkMetadata 

log = logging.getLogger("app.services.rag.rag_orchestrator")

# Config
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = "sealai_knowledge_v2" # Canonical collection

# Lazy singletons
_client: Optional[QdrantClient] = None
_dense_embedder = None
_sparse_embedder = None

def get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    return _client

def _lazy_load_embedders():
    global _dense_embedder, _sparse_embedder
    if not _dense_embedder:
        from fastembed import TextEmbedding
        model = "intfloat/multilingual-e5-large"
        log.info(f"Loading Dense: {model}")
        _dense_embedder = TextEmbedding(model_name=model)
        
    if not _sparse_embedder:
        from fastembed import SparseTextEmbedding
        model = "prithivida/Splade_PP_en_v1"
        log.info(f"Loading Sparse: {model}")
        _sparse_embedder = SparseTextEmbedding(model_name=model)

def hybrid_retrieve(
    *,
    query: str,
    tenant: str,
    k: int = 5,
    metadata_filters: Optional[Dict[str, Any]] = None,
    use_rerank: bool = True,
    return_metrics: bool = False,
) -> List[Dict[str, Any]] | Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Hybrid Search (Dense + Sparse/Splade) with strict isolation.
    Returns: List[Dict] compatible with legacy nodes_knowledge.
    """
    import sys
    print(f"[ORCH_DEBUG] hybrid_retrieve start. Query='{query}'", file=sys.stderr, flush=True)

    if not query.strip():
        return []

    try:
        print("[ORCH_DEBUG] lazy loading embedders...", file=sys.stderr, flush=True)
        _lazy_load_embedders()
        print("[ORCH_DEBUG] embedders loaded. Embedding query...", file=sys.stderr, flush=True)
        
        # 1. Embed
        dense_vec = list(_dense_embedder.embed([query]))[0]
        sparse_vec = list(_sparse_embedder.embed([query]))[0]
        print("[ORCH_DEBUG] Embedding complete.", file=sys.stderr, flush=True)
        
        # 2. Prefetch (Dense + Sparse)
        # Policy: shared 'default' tenant is readable by all
        filter_cond = [
            models.FieldCondition(
                key="tenant_id", 
                match=models.MatchAny(any=[tenant, "default"])
            )
        ]
        q_filter = models.Filter(must=filter_cond)

        prefetch = [
            models.Prefetch(
                query=dense_vec.tolist(),
                using="dense",
                limit=k * 2,
                filter=q_filter
            ),
            models.Prefetch(
                query=sparse_vec.as_object(),
                using="sparse",
                limit=k * 2,
                filter=q_filter
            )
        ]
        
        # 3. RRF Fusion
        client = get_qdrant_client()
        print(f"[ORCH_DEBUG] Querying Qdrant... Collection={QDRANT_COLLECTION}", file=sys.stderr, flush=True)
        results = client.query_points(
            collection_name=QDRANT_COLLECTION,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=k,
            with_payload=True
        )
        print(f"[ORCH_DEBUG] Qdrant returned {len(results.points)} points.", file=sys.stderr, flush=True)
        
        # 4. Map to Standard Output (Dict)
        out = []
        hits_meta = []
        for point in results.points:
            try:
                # Validation
                meta_obj = ChunkMetadata(**point.payload)
                
                # Convert back to flat dict for compatibility
                # Flatten the 'eng' nested object for consumers if needed, 
                # but currently we just dump the model.
                # Note: consumers expecting 'text' and 'source' at top level
                row = meta_obj.model_dump()
                
                # Ensure 'metadata' key exists if consumers expect nested metadata 
                # (Common RAG pattern: {'text':..., 'metadata': {...}})
                # Our schema has text/source at top level. 
                # We replicate common access patterns.
                
                item = {
                    "text": meta_obj.text,
                    "source": str(meta_obj.source_uri),
                    "score": point.score,
                    "metadata": row # Include full strict metadata
                }
                out.append(item)
                hits_meta.append(meta_obj)
            except Exception as e:
                log.warning(f"Schema violation in {point.id}: {e}")

        if return_metrics:
            metrics = {
                "k": k, 
                "hits": len(out),
                "mode": "hybrid_rrf",
                "schema": "v2"
            }
            return out, metrics
            
        print(f"[ORCH_DEBUG] returning {len(out)} hits.", file=sys.stderr, flush=True)
        return out

    except Exception as e:
        import traceback
        traceback.print_exc()
        log.error(f"hybrid_retrieve failed: {e}")
        print(f"[ORCH_DEBUG] ERROR: {e}", file=sys.stderr, flush=True)
        if return_metrics: return [], {"error": str(e)}
        return []

# Compatibility Constants
FINAL_K = 6
HYBRID_K = 12

# Public exports
def delete_qdrant_points(*args, **kwargs):
    raise NotImplementedError("Use V2 Ingest for deletions")

def get_embedder():
    _lazy_load_embedders()
    return _dense_embedder

def resolve_embedding_model():
    return "intfloat/multilingual-e5-large", 1024

# Compatibility for qdrant_bootstrap.py
def resolve_embedding_config():
    return resolve_embedding_model()

def resolve_embeddings_provider():
    return "fastembed"

def startup_warmup():
    _lazy_load_embedders()

__all__ = [
    "hybrid_retrieve", 
    "startup_warmup", 
    "delete_qdrant_points", 
    "get_embedder",
    "resolve_embedding_model",
    "resolve_embedding_config",
    "resolve_embeddings_provider",
    "FINAL_K",
    "HYBRID_K"
]
