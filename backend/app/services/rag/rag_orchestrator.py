from __future__ import annotations

import os
import time
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
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333").rstrip("/")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION_DEFAULT = os.getenv("QDRANT_COLLECTION", "sealai_knowledge").strip()

# Shared knowledge (read-only fallback)
# NOTE: default OFF to keep fail-closed behavior unless explicitly enabled via env.
RAG_SHARED_TENANT_ENABLED = _truthy(os.getenv("RAG_SHARED_TENANT_ENABLED", "0"))
RAG_SHARED_TENANT_ID = (os.getenv("RAG_SHARED_TENANT_ID", "default") or "default").strip()

# Embeddings / Rerank
RERANK_MODEL_NAME = os.getenv("RERANK_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# Retrieval knobs
HYBRID_K = int(os.getenv("RAG_HYBRID_K", os.getenv("RAG_TOP_K", "12")))
FINAL_K = int(os.getenv("RAG_FINAL_K", "6"))
RRF_K = int(os.getenv("RAG_RRF_K", "60"))
SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.0"))
QDRANT_TIMEOUT_S = float(os.getenv("QDRANT_TIMEOUT_S", "5.0"))
QDRANT_RETRY_ATTEMPTS = 3
QDRANT_RETRY_BASE_MS = 150
QDRANT_RETRY_JITTER_MS = 100
QDRANT_RETRY_STATUS = {429, 500, 502, 503, 504}

# Optional BM25 over Redis (gated)
USE_BM25 = _truthy(os.getenv("RAG_BM25_ENABLED", "0"))
REDIS_URL = os.getenv("REDIS_URL")
REDIS_BM25_INDEX = os.getenv("REDIS_BM25_INDEX") or os.getenv("RAG_BM25_INDEX")

# ─────────────────────────────────────────────────────────────────────────────
# Module globals (lazy)
# ─────────────────────────────────────────────────────────────────────────────
_embedder = None
_embedding_dim: Optional[int] = None


def ensure_fastembed_cache_dir() -> None:
    if os.getenv("FASTEMBED_CACHE_DIR"):
        return
    cache_dir = "/app/data/fastembed"
    os.environ.setdefault("FASTEMBED_CACHE_DIR", cache_dir)
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except OSError:
        pass


def resolve_embedding_model_name() -> str:
    return (
        os.getenv("RAG_EMBEDDING_MODEL")
        or os.getenv("EMB_MODEL_NAME")
        or os.getenv("EMBEDDINGS_MODEL")
        or "intfloat/multilingual-e5-base"
    )


def resolve_embeddings_provider() -> str:
    provider = os.getenv("EMBEDDINGS_PROVIDER", "fastembed").strip().lower()
    return provider or "fastembed"


def _get_embedder() -> Any:
    global _embedder
    if _embedder is None:
        provider = resolve_embeddings_provider()
        model_name = resolve_embedding_model_name()

        if provider == "fastembed":
            try:
                from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
            except ImportError as exc:
                raise ImportError(
                    "EMBEDDINGS_PROVIDER=fastembed requires 'fastembed'. "
                    "Install fastembed or set EMBEDDINGS_PROVIDER=sentence_transformers."
                ) from exc
            ensure_fastembed_cache_dir()
            _embedder = FastEmbedEmbeddings(model_name=model_name)

        elif provider == "sentence_transformers":
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImportError(
                    "EMBEDDINGS_PROVIDER=sentence_transformers requires 'sentence-transformers'. "
                    "Install with `pip install sentence-transformers`."
                ) from exc

            class _SentenceTransformerEmbeddings:
                def __init__(self, model: str):
                    self._model = SentenceTransformer(model)
                    self.embedding_dimension = self._model.get_sentence_embedding_dimension()

                def embed_documents(self, texts: List[str]) -> List[List[float]]:
                    vectors = self._model.encode(texts, show_progress_bar=False)
                    return [vec.tolist() for vec in vectors]

                def embed_query(self, text: str) -> List[float]:
                    return self._model.encode([text], show_progress_bar=False)[0].tolist()

            _embedder = _SentenceTransformerEmbeddings(model_name)

        else:
            raise ValueError(f"Unknown EMBEDDINGS_PROVIDER: {provider}")

    return _embedder


def get_embedder() -> Any:
    return _get_embedder()


def resolve_embedding_config() -> Tuple[str, int]:
    global _embedder, _embedding_dim
    model_name = resolve_embedding_model_name()
    if _embedding_dim is not None:
        return model_name, _embedding_dim

    if _embedder is not None:
        for attr in ("embedding_dimension", "dimension", "dim", "vector_size"):
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

    env_dim = os.getenv("RAG_EMBEDDING_DIM")
    if env_dim is None:
        raise ValueError(
            "RAG_EMBEDDING_DIM must be set to a positive integer when embedder dimension is unavailable."
        )
    try:
        dim_value = int(env_dim)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "RAG_EMBEDDING_DIM must be set to a positive integer when embedder dimension is unavailable."
        ) from exc
    if dim_value <= 0:
        raise ValueError(
            "RAG_EMBEDDING_DIM must be set to a positive integer when embedder dimension is unavailable."
        )
    _embedding_dim = dim_value
    return model_name, dim_value


def resolve_embedding_model() -> Tuple[str, int]:
    return resolve_embedding_config()


def _iso_utc() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _event(event: str, **data: Any) -> None:
    payload = {**data, "event": event, "timestamp": _iso_utc(), "level": "info"}
    log.info(f"{payload}")


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
        filename = metadata.get("filename") or metadata.get("file_name") or metadata.get("name")
        page = metadata.get("page")
        if page is None:
            page = metadata.get("page_number")
        section = metadata.get("section") or metadata.get("section_title") or metadata.get("chunk_title")
        source = metadata.get("source") or hit.get("source") or metadata.get("url") or metadata.get("file")
        score_value = hit.get("fused_score") or hit.get("vector_score")
        try:
            score = float(score_value) if score_value is not None else None
        except (TypeError, ValueError):
            score = None

        filename_value = _truncate_str(filename, 160)
        source_value = _truncate_str(source, 200)
        if not filename_value and isinstance(source, str):
            source_str = source.strip()
            if source_str and ("/" in source_str or "\\" in source_str):
                derived = os.path.basename(source_str)
                if derived:
                    filename_value = _truncate_str(derived, 160)

        sources.append(
            {
                "document_id": str(doc_id) if doc_id is not None else None,
                "sha256": str(sha256) if sha256 is not None else None,
                "filename": filename_value,
                "page": _coerce_int(page),
                "section": _truncate_str(section, 160),
                "score": score,
                "source": source_value,
            }
        )
    return sources


def init_bm25(redis_url: Optional[str] = None, index_name: Optional[str] = None) -> Optional[Any]:
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
    global _embedder
    try:
        t0 = time.perf_counter()
        _embedder = _get_embedder()
        _event("embeddings_loaded", model=resolve_embedding_model_name(), ms=int((time.perf_counter() - t0) * 1000))
    except Exception as e:
        _event("embeddings_failed", model=resolve_embedding_model_name(), error=f"{type(e).__name__}: {e}")
    log.info("RAG prewarm completed.")


def startup_warmup() -> None:
    _ = init_bm25()
    prewarm_embeddings()


def _collection_name() -> str:
    return QDRANT_COLLECTION_DEFAULT


def _embed(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    embedder = _get_embedder()
    return embedder.embed_documents(texts)


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
    qdrant_filter: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    import httpx

    url = f"{QDRANT_URL}/collections/{collection}/points/search"
    body: Dict[str, Any] = {
        "vector": query_vec,
        "limit": top_k,
        "with_payload": True,
        "with_vector": False,
    }
    headers: Dict[str, str] | None = None
    if QDRANT_API_KEY:
        headers = {"api-key": QDRANT_API_KEY}

    if qdrant_filter:
        body["filter"] = qdrant_filter
    elif metadata_filters:
        body["filter"] = {
            "must": [{"key": k, "match": {"value": v}} for k, v in metadata_filters.items()]
        }

    attempts = 0
    backoffs: List[int] = []
    last_error: Dict[str, Any] | None = None
    started = time.perf_counter()

    for attempt in range(QDRANT_RETRY_ATTEMPTS):
        attempts += 1
        try:
            with httpx.Client(timeout=QDRANT_TIMEOUT_S) as client:
                r = client.post(url, json=body, headers=headers)

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
                raw_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None
                txt = (
                    payload.get("page_content")
                    or (raw_metadata or {}).get("page_content")
                    or payload.get("text")
                    or payload.get("chunk")
                    or payload.get("content")
                    or ""
                )
                src = (
                    payload.get("source")
                    or (raw_metadata or {}).get("source")
                    or payload.get("file")
                    or ""
                )
                if raw_metadata is not None:
                    metadata = dict(raw_metadata)
                    metadata.pop("page_content", None)
                else:
                    metadata = {
                        key: value
                        for key, value in payload.items()
                        if key not in {"page_content", "text", "chunk", "content", "metadata"}
                    }
                out.append(
                    {
                        "text": txt,
                        "source": src,
                        "vector_score": float(item.get("score") or 0.0),
                        "metadata": metadata,
                    }
                )

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


def delete_qdrant_points(*, tenant_id: str, document_id: str) -> Dict[str, Any]:
    if not tenant_id or not document_id:
        raise ValueError("tenant_id and document_id required for qdrant delete")
    collection = _collection_name().strip()
    if not collection:
        raise ValueError("missing qdrant collection")

    import httpx

    url = f"{QDRANT_URL}/collections/{collection}/points/delete"
    payload = {
        "filter": {
            "must": [
                {"key": "metadata.tenant_id", "match": {"value": tenant_id}},
                {"key": "metadata.document_id", "match": {"value": document_id}},
            ]
        },
        "wait": True,
    }
    headers: Dict[str, str] | None = None
    if QDRANT_API_KEY:
        headers = {"api-key": QDRANT_API_KEY}

    with httpx.Client(timeout=QDRANT_TIMEOUT_S) as client:
        resp = client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            raise RuntimeError(f"qdrant_delete_failed status={resp.status_code}")
        try:
            return resp.json()
        except Exception:
            return {}


def _apply_threshold(hits: List[Dict[str, Any]], thr: float) -> List[Dict[str, Any]]:
    if thr <= 0:
        return hits
    out: List[Dict[str, Any]] = []
    for h in hits:
        s = float(h.get("fused_score") or h.get("vector_score") or 0.0)
        if s >= thr:
            out.append(h)
    return out


def _rerank_if_enabled(query: str, hits: List[Dict[str, Any]], use_rerank: bool) -> List[Dict[str, Any]]:
    if not use_rerank or not hits:
        return hits
    return hits


def _normalize_metadata_filters(tenant: str, metadata_filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    filters: Dict[str, Any] = dict(metadata_filters or {})

    legacy_tenant = filters.pop("tenant_id", None)
    explicit_tenant = filters.pop("metadata.tenant_id", None)
    if legacy_tenant is not None and explicit_tenant is not None and legacy_tenant != explicit_tenant:
        raise ValueError(f"tenant_id filter mismatch: {explicit_tenant} != {legacy_tenant}")
    specified_tenant = explicit_tenant if explicit_tenant is not None else legacy_tenant
    if specified_tenant is not None and specified_tenant != tenant:
        raise ValueError(f"tenant_id filter mismatch: {specified_tenant} != {tenant}")

    legacy_document = filters.pop("document_id", None)
    explicit_document = filters.get("metadata.document_id")
    if legacy_document is not None:
        if explicit_document is not None and explicit_document != legacy_document:
            raise ValueError(f"document_id filter mismatch: {explicit_document} != {legacy_document}")
        filters["metadata.document_id"] = legacy_document

    return filters


def _build_qdrant_filter(
    *,
    tenant: str,
    metadata_filters: Dict[str, Any],
    include_shared: bool,
) -> Dict[str, Any]:
    must_filters = [{"key": k, "match": {"value": v}} for k, v in metadata_filters.items()]
    tenant_clause = {"must": [{"key": "metadata.tenant_id", "match": {"value": tenant}}]}

    if not include_shared:
        return {"must": must_filters + tenant_clause["must"]}

    shared_clause = {
        "must": [
            {"key": "metadata.tenant_id", "match": {"value": RAG_SHARED_TENANT_ID}},
            {"key": "metadata.visibility", "match": {"value": "public"}},
        ]
    }
    return {
        "must": must_filters,
        "min_should": {"conditions": [tenant_clause, shared_clause], "min_count": 1},
    }


def _bm25_filters_from_metadata(filters: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(filters)
    tenant = out.pop("metadata.tenant_id", None)
    if tenant is not None:
        out.setdefault("tenant_id", tenant)
    document = out.pop("metadata.document_id", None)
    if document is not None:
        out.setdefault("document_id", document)
    return out


def _fallback_external_search(query: str, tenant: str, limit: int) -> List[Dict[str, Any]]:
    return []


def _allow_shared_fallback(*, tenant: str, metadata_filters: Optional[Dict[str, Any]]) -> bool:
    if not RAG_SHARED_TENANT_ENABLED:
        return False
    if not tenant or tenant == RAG_SHARED_TENANT_ID:
        return False

    mf = dict(metadata_filters or {})
    if mf.get("metadata.tenant_id") is not None:
        return False
    if mf.get("tenant_id") is not None:
        return False

    return True


def hybrid_retrieve(
    *,
    query: str,
    tenant: Optional[str],
    k: int = FINAL_K,
    metadata_filters: Optional[Dict[str, Any]] = None,
    use_rerank: bool = True,
    return_metrics: bool = False,
) -> List[Dict[str, Any]] | Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return [] if not return_metrics else ([], {"k_requested": k, "k_returned": 0})

    if not tenant:
        raise ValueError("tenant_id required for retrieval")

    collection = _collection_name()
    filters = _normalize_metadata_filters(tenant, metadata_filters)
    include_shared = bool(
        RAG_SHARED_TENANT_ENABLED and tenant and tenant != RAG_SHARED_TENANT_ID
    )
    qdrant_filter = _build_qdrant_filter(
        tenant=tenant,
        metadata_filters=filters,
        include_shared=include_shared,
    )

    vec = _embed([q])[0]

    vector_k = max(HYBRID_K, k)
    vec_hits, qdrant_meta = _qdrant_search_with_retry(
        vec,
        collection,
        top_k=vector_k,
        qdrant_filter=qdrant_filter,
    )

    shared_used = False
    shared_qdrant_meta: Optional[Dict[str, Any]] = None

    bm25_hits: List[Dict[str, Any]] = []
    bm25_error: Optional[Dict[str, Any]] = None
    bm25_k = max(HYBRID_K, k)
    if USE_BM25:
        bm25_filters = _bm25_filters_from_metadata(filters)
        bm25_hits, bm25_error = _bm25_search(q, collection, top_k=bm25_k, metadata_filters=bm25_filters)

        if shared_used and not bm25_hits:
            shared_bm25_filters = _bm25_filters_from_metadata(
                {"metadata.tenant_id": RAG_SHARED_TENANT_ID, **filters}
            )
            bm25_hits, bm25_error = _bm25_search(
                q, collection, top_k=bm25_k, metadata_filters=shared_bm25_filters
            )

    merged: List[Dict[str, Any]]
    fused = False
    if USE_BM25 and bm25_hits:
        merged = _rrf_fuse(vec_hits, bm25_hits, k0=RRF_K)
        fused = True
    else:
        merged = list(vec_hits)

    merged = _rerank_if_enabled(q, merged, use_rerank)
    merged = _apply_threshold(merged, SCORE_THRESHOLD)[:k]

    if not merged:
        ext = _fallback_external_search(q, tenant=tenant, limit=k)
        merged = ext[:k]

    sources = _build_sources(merged)
    shared_used = bool(
        include_shared
        and any((hit.get("metadata") or {}).get("tenant_id") == RAG_SHARED_TENANT_ID for hit in merged)
    )

    if include_shared:
        filter_should = [tenant, RAG_SHARED_TENANT_ID]
    else:
        filter_should = None
    log.info(
        "rag_retrieval_summary",
        extra={
            "tenant_id": tenant,
            "shared_enabled": bool(RAG_SHARED_TENANT_ENABLED),
            "shared_tenant_id": RAG_SHARED_TENANT_ID,
            "shared_used": shared_used,
            "collection": collection,
            "hits_count": len(merged),
            "top_filenames": [s.get("filename") for s in sources if s.get("filename")][:3],
            "top_doc_ids": [s.get("document_id") for s in sources if s.get("document_id")][:3],
            "score_threshold": SCORE_THRESHOLD,
            "top_k": k,
            "filters": {
                "must_keys": list(filters.keys()),
                "should_tenants": filter_should,
                "min_should": {"min_count": 1} if include_shared else None,
            },
        },
    )

    if return_metrics:
        reranked = any("rerank_score" in hit for hit in merged)
        metrics: Dict[str, Any] = {
            "k_requested": k,
            "k_returned": len(merged),
            "top_scores": [float(hit.get("fused_score") or hit.get("vector_score") or 0.0) for hit in merged][:5],
            "threshold": SCORE_THRESHOLD if SCORE_THRESHOLD > 0 else None,
            "fused": fused,
            "reranked": reranked,
            "collection": collection,
            "qdrant": qdrant_meta,
            "qdrant_shared": shared_qdrant_meta,
            "shared_fallback": {
                "enabled": bool(RAG_SHARED_TENANT_ENABLED),
                "shared_tenant_id": RAG_SHARED_TENANT_ID,
                "used": bool(shared_used),
            },
            "sources": sources,
        }

        overlap_count = 0
        if USE_BM25 and bm25_hits:
            vec_ids = {_hit_key(h) for h in vec_hits}
            bm_ids = {_hit_key(h) for h in bm25_hits}
            overlap_count = len(vec_ids.intersection(bm_ids))

        metrics["hybrid"] = {"enabled": fused, "overlap": overlap_count}

        if USE_BM25 and bm25_error:
            metrics["bm25_error"] = bm25_error
        return merged, metrics

    return merged


__all__ = [
    "hybrid_retrieve",
    "delete_qdrant_points",
    "startup_warmup",
    "prewarm_embeddings",
    "get_embedder",
    "resolve_embedding_model",
    "resolve_embedding_config",
]
