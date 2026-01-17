from __future__ import annotations

import os
import time
import math
import logging
import random
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
QDRANT_COLLECTION_DEFAULT  = os.getenv("QDRANT_COLLECTION", "sealai_knowledge").strip()

# Embeddings / Rerank
EMB_MODEL_NAME             = os.getenv("EMB_MODEL_NAME", os.getenv("EMBEDDINGS_MODEL", "intfloat/multilingual-e5-base"))
RERANK_MODEL_NAME          = os.getenv("RERANK_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# Retrieval knobs
HYBRID_K                   = int(os.getenv("RAG_HYBRID_K", os.getenv("RAG_TOP_K", "12")))
FINAL_K                    = int(os.getenv("RAG_FINAL_K", "6"))
RRF_K                      = int(os.getenv("RAG_RRF_K", "60"))
SCORE_THRESHOLD            = float(os.getenv("RAG_SCORE_THRESHOLD", "0.0"))
QDRANT_TIMEOUT_S           = float(os.getenv("QDRANT_TIMEOUT_S", "5.0"))
QDRANT_RETRY_ATTEMPTS      = 3
QDRANT_RETRY_BASE_MS       = 150
QDRANT_RETRY_JITTER_MS     = 100
QDRANT_RETRY_STATUS        = {429, 500, 502, 503, 504}

# Optional BM25 over Redis (gated)
USE_BM25                   = _truthy(os.getenv("RAG_BM25_ENABLED", "0"))
REDIS_URL                  = os.getenv("REDIS_URL")
REDIS_BM25_INDEX           = os.getenv("REDIS_BM25_INDEX") or os.getenv("RAG_BM25_INDEX")

# ─────────────────────────────────────────────────────────────────────────────
# Module globals (lazy)
# ─────────────────────────────────────────────────────────────────────────────
_embedder = None
_reranker = None
_embedding_dim: Optional[int] = None

def resolve_embedding_config() -> Tuple[str, int]:
    """Resolve embedding model name and vector dimension from the active embedder."""
    global _embedder, _embedding_dim
    model_name = EMB_MODEL_NAME
    if _embedding_dim is not None:
        return model_name, _embedding_dim

    if _embedder is not None:
        for attr in (
            "get_sentence_embedding_dimension",
            "embedding_dimension",
            "dimension",
            "dim",
            "vector_size",
        ):
            value = getattr(_embedder, attr, None)
            if callable(value):
                try:
                    dim_value = int(value())
                    _embedding_dim = dim_value
                    return model_name, dim_value
                except Exception:
                    continue
            if isinstance(value, (int, float)):
                dim_value = int(value)
                _embedding_dim = dim_value
                return model_name, dim_value

    # Controlled fallback: embed a probe string and read vector length.
    vector = _embed(["_dim_probe_"])[0]
    dim_value = int(len(vector))
    _embedding_dim = dim_value
    return model_name, dim_value

def _event(event: str, **data: Any) -> None:
    payload = {**data, "event": event, "timestamp": _iso_utc(), "level": "info"}
    log.info(f"{payload}")

def _iso_utc() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()

def _truncate_str(value: Any, limit: int = 160) -> Optional[str]:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if len(trimmed) > limit:
        return trimmed[:limit] + "..."
    return trimmed

def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def _build_sources(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    for hit in hits:
        metadata = hit.get("metadata") or {}
        doc_id = metadata.get("document_id") or metadata.get("doc_id") or metadata.get("id")
        sha256 = metadata.get("sha256")
        filename = (
            metadata.get("filename")
            or metadata.get("file_name")
            or metadata.get("name")
        )
        page = metadata.get("page")
        if page is None:
            page = metadata.get("page_number")
        section = (
            metadata.get("section")
            or metadata.get("section_title")
            or metadata.get("chunk_title")
        )
        source = metadata.get("source") or hit.get("source") or metadata.get("url") or metadata.get("file")
        score_value = hit.get("fused_score") or hit.get("vector_score")
        try:
            score = float(score_value) if score_value is not None else None
        except (TypeError, ValueError):
            score = None
        sources.append(
            {
                "document_id": str(doc_id) if doc_id is not None else None,
                "sha256": str(sha256) if sha256 is not None else None,
                "filename": _truncate_str(filename, 160),
                "page": _coerce_int(page),
                "section": _truncate_str(section, 160),
                "score": score,
                "source": _truncate_str(source, 200),
            }
        )
    return sources

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
def _collection_name() -> str:
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
    return candidates

def _hit_key(hit: Dict[str, Any]) -> str:
    metadata = hit.get("metadata") or {}
    chunk_id = metadata.get("chunk_id") or metadata.get("point_id") or metadata.get("id")
    if isinstance(chunk_id, str) and chunk_id.strip():
        return chunk_id
    doc_id = metadata.get("document_id") or metadata.get("doc_id")
    chunk_index = metadata.get("chunk_index")
    if doc_id is not None and chunk_index is not None:
        return f"{doc_id}#{chunk_index}"
    if doc_id is not None:
        return str(doc_id)
    text = (hit.get("text") or "")
    return f"text:{text[:80]}"

def _rrf_fuse(vector_hits: List[Dict[str, Any]], bm25_hits: List[Dict[str, Any]], k0: int = RRF_K) -> List[Dict[str, Any]]:
    scores: Dict[str, float] = {}
    winners: Dict[str, Dict[str, Any]] = {}

    for idx, hit in enumerate(vector_hits):
        key = _hit_key(hit)
        scores[key] = scores.get(key, 0.0) + 1.0 / (k0 + idx + 1)
        winners.setdefault(key, hit)

    for idx, hit in enumerate(bm25_hits):
        key = _hit_key(hit)
        scores[key] = scores.get(key, 0.0) + 1.0 / (k0 + idx + 1)
        winners.setdefault(key, hit)

    fused: List[Dict[str, Any]] = []
    for key, hit in winners.items():
        hit = dict(hit)
        hit["fused_score"] = float(scores.get(key, 0.0))
        fused.append(hit)
    return sorted(fused, key=lambda h: float(h.get("fused_score") or 0.0), reverse=True)

def _bm25_search(
    query: str,
    collection: str,
    top_k: int,
    metadata_filters: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    try:
        from app.services.rag.bm25_store import bm25_repo
    except Exception as exc:
        return [], _qdrant_error("bm25_unavailable", None, f"{type(exc).__name__}: {exc}")
    try:
        return bm25_repo.search(collection, query, top_k=top_k, metadata_filters=metadata_filters), None
    except Exception as exc:
        return [], _qdrant_error("bm25_error", None, f"{type(exc).__name__}: {exc}")

def _qdrant_backoff_ms(attempt_index: int) -> int:
    base = QDRANT_RETRY_BASE_MS * (2 ** attempt_index)
    jitter = int(random.random() * QDRANT_RETRY_JITTER_MS)
    return base + jitter

def _qdrant_error(kind: str, status: int | None, message: str) -> Dict[str, Any]:
    return {
        "kind": kind,
        "status": status,
        "message": _truncate_str(message, 200) or "qdrant_error",
    }

def _should_retry_status(status: int) -> bool:
    return status in QDRANT_RETRY_STATUS

def _qdrant_search_with_retry(
    query_vec: List[float],
    collection: str,
    top_k: int = HYBRID_K,
    metadata_filters: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
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

    attempts = 0
    backoffs: List[int] = []
    last_error: Dict[str, Any] | None = None
    started = time.perf_counter()

    for attempt in range(QDRANT_RETRY_ATTEMPTS):
        attempts += 1
        try:
            with httpx.Client(timeout=QDRANT_TIMEOUT_S) as client:
                r = client.post(url, json=body)
            status = int(getattr(r, "status_code", 0) or 0)
            if status >= 400:
                last_error = _qdrant_error("http_error", status, f"HTTP {status}")
                if _should_retry_status(status) and attempt < QDRANT_RETRY_ATTEMPTS - 1:
                    delay_ms = _qdrant_backoff_ms(attempt)
                    backoffs.append(delay_ms)
                    log.warning("qdrant_retry_http_error", extra={"status": status, "attempt": attempts})
                    time.sleep(delay_ms / 1000.0)
                    continue
                break
            try:
                data = r.json()
            except Exception as exc:
                last_error = _qdrant_error("decode", None, f"{type(exc).__name__}: {exc}")
                break
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
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return out, {
                "attempts": attempts,
                "timeout_s": QDRANT_TIMEOUT_S,
                "elapsed_ms": elapsed_ms,
                "retry_backoff_ms": backoffs or None,
                "error": None,
            }
        except httpx.TimeoutException as exc:
            last_error = _qdrant_error("timeout", None, f"{type(exc).__name__}: {exc}")
        except httpx.TransportError as exc:
            last_error = _qdrant_error("network", None, f"{type(exc).__name__}: {exc}")
        except Exception as exc:
            last_error = _qdrant_error("unknown", None, f"{type(exc).__name__}: {exc}")

        if attempt < QDRANT_RETRY_ATTEMPTS - 1:
            delay_ms = _qdrant_backoff_ms(attempt)
            backoffs.append(delay_ms)
            log.warning("qdrant_retry_exception", extra={"attempt": attempts, "kind": last_error.get("kind")})
            time.sleep(delay_ms / 1000.0)
            continue
        break

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if last_error:
        _event("qdrant_search_failed", reason=last_error.get("message", "error"), collection=collection)
    return [], {
        "attempts": attempts,
        "timeout_s": QDRANT_TIMEOUT_S,
        "elapsed_ms": elapsed_ms,
        "retry_backoff_ms": backoffs or None,
        "error": last_error or _qdrant_error("unknown", None, "qdrant_error"),
    }


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
                    use_rerank: bool = True,
                    return_metrics: bool = False) -> List[Dict[str, Any]] | Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Vector-first retrieval from Qdrant (+ optional BM25 fusion in future).
    Returns list of {text, source, vector_score, fused_score?, metadata}.
    """
    q = (query or "").strip()
    if not q:
        return []

    # Embed query
    vec = _embed([q])[0]

    # Single-collection setup (tenant scoped via payload filter)
    collection = _collection_name()

    # Vector search
    vector_k = max(HYBRID_K, k)
    vec_hits, qdrant_meta = _qdrant_search_with_retry(
        vec, collection, top_k=vector_k, metadata_filters=metadata_filters
    )

    bm25_hits: List[Dict[str, Any]] = []
    bm25_error: Optional[Dict[str, Any]] = None
    bm25_k = max(HYBRID_K, k)
    if USE_BM25:
        bm25_hits, bm25_error = _bm25_search(
            q, collection, top_k=bm25_k, metadata_filters=metadata_filters
        )

    # Placeholder: BM25 could be merged here when enabled
    merged: List[Dict[str, Any]]
    if USE_BM25 and bm25_hits:
        merged = _rrf_fuse(vec_hits, bm25_hits, k0=RRF_K)
    else:
        merged = list(vec_hits)

    # Optional rerank
    merged = _rerank_if_enabled(q, merged, use_rerank)

    # Threshold + top-k
    merged = _apply_threshold(merged, SCORE_THRESHOLD)[:k]

    # Externer Fallback (Microservice), wenn keine Treffer
    if not merged:
        ext = _fallback_external_search(q, tenant=tenant, limit=k)
        merged = ext[:k]

    reranked = any("rerank_score" in hit for hit in merged)
    metrics: Dict[str, Any] = {
        "k_requested": k,
        "k_returned": len(merged),
        "top_scores": [
            float(hit.get("fused_score") or hit.get("vector_score") or 0.0)
            for hit in merged
        ][:5],
        "threshold": SCORE_THRESHOLD if SCORE_THRESHOLD > 0 else None,
        "fused": False,
        "reranked": reranked,
        "collection": collection,
    }
    if qdrant_meta:
        metrics["qdrant"] = qdrant_meta
    if USE_BM25:
        vector_keys = {_hit_key(hit) for hit in vec_hits}
        bm25_keys = {_hit_key(hit) for hit in bm25_hits}
        overlap = len(vector_keys & bm25_keys) if bm25_hits else 0
        hybrid_meta: Dict[str, Any] = {
            "enabled": bool(bm25_hits),
            "vector_k": vector_k,
            "bm25_k": bm25_k,
            "fusion": "rrf",
            "k0": RRF_K,
            "counts": {
                "vector": len(vec_hits),
                "bm25": len(bm25_hits),
                "fused": len(merged),
            },
            "overlap": overlap,
        }
        if bm25_error:
            hybrid_meta["degraded"] = bm25_error.get("kind")
        metrics["hybrid"] = hybrid_meta
    doc_ids: list[str] = []
    for hit in merged:
        metadata = hit.get("metadata") or {}
        doc_id = metadata.get("document_id") or metadata.get("doc_id") or metadata.get("id")
        if doc_id:
            doc_ids.append(str(doc_id))
    if doc_ids:
        metrics["doc_ids"] = doc_ids
    sources = _build_sources(merged)
    if sources:
        metrics["sources"] = sources

    try:
        _event("hybrid_retrieve", n=len(merged), tenant=tenant or "-", collection=collection, k=k)
    except Exception:
        pass

    if return_metrics:
        return merged, metrics
    return merged

__all__ = [
    "startup_warmup",
    "init_bm25",
    "prewarm_embeddings",
    "resolve_embedding_config",
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
def _fallback_external_search(query: str, *, tenant: Optional[str] = None, limit: int = FINAL_K) -> List[Dict[str, Any]]:
    """Optionaler externer Fallback über Microservices (z.B. Normen-/Material-Agent).

    Env:
      AGENT_NORMEN_URL    → /v1/search endpoint returning [{text, source, score?, metadata?}]
      AGENT_MATERIAL_URL  → /v1/search endpoint returning [{text, source, score?, metadata?}]
    """
    import itertools
    bases = []
    n_url = (os.getenv("AGENT_NORMEN_URL") or "").strip().rstrip("/")
    m_url = (os.getenv("AGENT_MATERIAL_URL") or "").strip().rstrip("/")
    if n_url:
        bases.append((n_url, "normen"))
    if m_url:
        bases.append((m_url, "material"))
    if not bases:
        return []

    results: List[Dict[str, Any]] = []
    errors: List[str] = []
    try:
        import httpx
        payload: Dict[str, Any] = {"query": query, "k": limit}
        if tenant:
            payload["tenant"] = tenant
        with httpx.Client(timeout=5.0) as client:
            for base, tag in bases:
                try:
                    r = client.post(f"{base}/v1/search", json=payload)
                    r.raise_for_status()
                    data = r.json()
                    items = data if isinstance(data, list) else (data.get("items") or [])
                    for it in items[:limit]:
                        t = (it.get("text") or it.get("content") or "").strip()
                        if not t:
                            continue
                        results.append({
                            "text": t,
                            "source": it.get("source") or f"{tag}_agent",
                            "vector_score": float(it.get("score") or 0.0),
                            "metadata": it.get("metadata") or {},
                        })
                    _event("fallback_search", n=len(items), tenant=tenant or "-", agent=tag)
                except Exception as e:
                    errors.append(f"{tag}:{type(e).__name__}:{e}")
    except Exception as e:
        errors.append(f"client:{type(e).__name__}:{e}")

    # Dedup by text prefix to reduce repetitions
    seen = set()
    dedup: List[Dict[str, Any]] = []
    for it in results:
        key = (it.get("text") or "")[:80]
        if key in seen:
            continue
        seen.add(key)
        dedup.append(it)

    return dedup[:limit]
