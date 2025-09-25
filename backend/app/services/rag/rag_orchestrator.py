from __future__ import annotations

import os
import time
import math
import logging
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("app.services.rag.rag_orchestrator")

# ─────────────────────────────────────────────────────────────────────────────
# Env & Flags
# ─────────────────────────────────────────────────────────────────────────────
def _truthy(x: Optional[str]) -> bool:
    if x is None:
        return False
    v = str(x).strip().lower()
    return v in {"1", "true", "yes", "on"}

# RAG core
QDRANT_URL                 = os.getenv("QDRANT_URL", "http://qdrant:6333").rstrip("/")
QDRANT_COLLECTION_PREFIX   = os.getenv("QDRANT_COLLECTION_PREFIX", "").strip()
QDRANT_COLLECTION_DEFAULT  = os.getenv("QDRANT_COLLECTION", "sealai-docs").strip()

# Embeddings / Rerank
EMB_MODEL_NAME             = os.getenv("EMB_MODEL_NAME", os.getenv("EMBEDDINGS_MODEL", "intfloat/multilingual-e5-base"))
RERANK_MODEL_NAME          = os.getenv("RERANK_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# Retrieval knobs
HYBRID_K                   = int(os.getenv("RAG_HYBRID_K", os.getenv("RAG_TOP_K", "12")))
FINAL_K                    = int(os.getenv("RAG_FINAL_K", "6"))
RRF_K                      = int(os.getenv("RAG_RRF_K", "60"))
SCORE_THRESHOLD            = float(os.getenv("RAG_SCORE_THRESHOLD", "0.0"))

# Optional BM25 over Redis (gated)
USE_BM25                   = _truthy(os.getenv("RAG_BM25_ENABLED", "0"))
REDIS_URL                  = os.getenv("REDIS_URL")
REDIS_BM25_INDEX           = os.getenv("REDIS_BM25_INDEX") or os.getenv("RAG_BM25_INDEX")

# ─────────────────────────────────────────────────────────────────────────────
# Module globals (lazy)
# ─────────────────────────────────────────────────────────────────────────────
_embedder = None
_reranker = None

def _event(event: str, **data: Any) -> None:
    payload = {**data, "event": event, "timestamp": _iso_utc(), "level": "info"}
    log.info(f"{payload}")

def _iso_utc() -> str:
    import datetime as _dt
    return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat()

# ─────────────────────────────────────────────────────────────────────────────
# Init / warmup
# ─────────────────────────────────────────────────────────────────────────────
def init_bm25(redis_url: Optional[str] = None, index_name: Optional[str] = None) -> Optional[Any]:
    """BM25 optional. Wenn deaktiviert, komplett still."""
    if not USE_BM25:
        return None
    url = redis_url or REDIS_URL
    idx = index_name or REDIS_BM25_INDEX
    if not url or not idx:
        _event("redis_bm25_unavailable", reason="missing_url_or_index")
        return None
    try:
        import redis
        r = redis.Redis.from_url(url)
        _ = r.ping()
        _event("redis_bm25_ready", index=idx)
        return {"client": r, "index": idx}
    except Exception as e:
        _event("redis_bm25_unavailable", reason=f"{type(e).__name__}: {e}")
        return None

def prewarm_embeddings() -> None:
    """Lädt Embeddings + Reranker und meldet Zeiten."""
    global _embedder, _reranker
    try:
        t0 = time.perf_counter()
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(EMB_MODEL_NAME)
        _event("embeddings_loaded", model=EMB_MODEL_NAME, ms=int((time.perf_counter() - t0) * 1000))
    except Exception as e:
        _event("embeddings_failed", model=EMB_MODEL_NAME, error=f"{type(e).__name__}: {e}")

    try:
        t0 = time.perf_counter()
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder(RERANK_MODEL_NAME)
        _event("reranker_loaded", model=RERANK_MODEL_NAME, ms=int((time.perf_counter() - t0) * 1000))
    except Exception as e:
        _event("reranker_failed", model=RERANK_MODEL_NAME, error=f"{type(e).__name__}: {e}")

    log.info("RAG prewarm completed.")

def startup_warmup() -> None:
    _ = init_bm25()
    prewarm_embeddings()

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────
def _collection_for_tenant(tenant: Optional[str]) -> str:
    t = (tenant or "").strip()
    if QDRANT_COLLECTION_PREFIX and t:
        return f"{QDRANT_COLLECTION_PREFIX}:{t}"
    return QDRANT_COLLECTION_DEFAULT

def _embed(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(EMB_MODEL_NAME)
    return _embedder.encode(texts, normalize_embeddings=True).tolist()

def _rrf_merge(candidates: List[Tuple[Dict[str, Any], float]], k: int = RRF_K) -> List[Tuple[Dict[str, Any], float]]:
    """Reciprocal Rank Fusion on already ranked hits (doc, score)."""
    # candidates are already from a single source; RRF is trivial passthrough here.
    # Hook left in for future BM25+Vector fusion.
    return candidates

def _qdrant_search(query_vec: List[float], collection: str, top_k: int = HYBRID_K,
                   metadata_filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    import httpx
    url = f"{QDRANT_URL}/collections/{collection}/points/search"
    body: Dict[str, Any] = {
        "vector": query_vec,
        "limit": top_k,
        "with_payload": True,
        "with_vector": False,
    }
    if metadata_filters:
        body["filter"] = {"must": [{"key": k, "match": {"value": v}} for k, v in metadata_filters.items()]}
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
            res = data.get("result") or []
            out: List[Dict[str, Any]] = []
            for item in res:
                payload = item.get("payload") or {}
                txt = payload.get("text") or payload.get("chunk") or payload.get("content") or ""
                src = payload.get("source") or (payload.get("metadata") or {}).get("source") or payload.get("file") or ""
                out.append({
                    "text": txt,
                    "source": src,
                    "vector_score": float(item.get("score") or 0.0),
                    "metadata": payload,
                })
            return out
    except Exception as e:
        _event("qdrant_search_failed", reason=f"{type(e).__name__}: {e}", collection=collection)
        return []

def _apply_threshold(hits: List[Dict[str, Any]], thr: float) -> List[Dict[str, Any]]:
    if thr <= 0:
        return hits
    out = []
    for h in hits:
        s = float(h.get("fused_score") or h.get("vector_score") or 0.0)
        if s >= thr:
            out.append(h)
    return out

def _rerank_if_enabled(query: str, hits: List[Dict[str, Any]], use_rerank: bool) -> List[Dict[str, Any]]:
    if not use_rerank or not hits:
        return hits
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            _reranker = CrossEncoder(RERANK_MODEL_NAME)
        except Exception:
            return hits
    pairs = [(query, h.get("text") or "") for h in hits]
    try:
        scores = _reranker.predict(pairs)
    except Exception:
        return hits
    # attach and sort
    for h, s in zip(hits, scores):
        h["rerank_score"] = float(s)
        # normalize a bit into 0..1 via sigmoid
        try:
            h["fused_score"] = 1.0 / (1.0 + math.exp(-float(s)))
        except Exception:
            h["fused_score"] = float(h.get("vector_score") or 0.0)
    return sorted(hits, key=lambda d: float(d.get("fused_score") or 0.0), reverse=True)

# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def hybrid_retrieve(*, query: str, tenant: Optional[str], k: int = FINAL_K,
                    metadata_filters: Optional[Dict[str, Any]] = None,
                    use_rerank: bool = True) -> List[Dict[str, Any]]:
    """
    Vector-first retrieval from Qdrant (+ optional BM25 fusion in future).
    Returns list of {text, source, vector_score, fused_score?, metadata}.
    """
    q = (query or "").strip()
    if not q:
        return []

    # Embed query
    vec = _embed([q])[0]

    # Pick collection by tenant
    collection = _collection_for_tenant(tenant)

    # Vector search
    vec_hits = _qdrant_search(vec, collection, top_k=max(HYBRID_K, k), metadata_filters=metadata_filters)

    # Placeholder: BM25 could be merged here when enabled
    fused = _rrf_merge([(h, float(h.get("vector_score") or 0.0)) for h in vec_hits], k=RRF_K)
    merged = [h for (h, _s) in fused]

    # Optional rerank
    merged = _rerank_if_enabled(q, merged, use_rerank)

    # Threshold + top-k
    merged = _apply_threshold(merged, SCORE_THRESHOLD)[:k]

    try:
        _event("hybrid_retrieve", n=len(merged), tenant=tenant or "-", collection=collection, k=k)
    except Exception:
        pass

    return merged

__all__ = [
    "startup_warmup",
    "init_bm25",
    "prewarm_embeddings",
    "hybrid_retrieve",
    "FINAL_K",
    "prewarm",
]
# ---- Backward-compat shim for startup ----
def prewarm() -> None:
    """Backward-compat: Startup expects ro.prewarm()."""
    try:
        startup_warmup()
    except Exception:
        # Beim Boot nie eskalieren
        pass
