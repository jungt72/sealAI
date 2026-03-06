from __future__ import annotations

import os
import time
import math
import logging
import random
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

log = logging.getLogger("app.services.rag.rag_orchestrator")

from app.core.config import settings

# ─────────────────────────────────────────────────────────────────────────────
# Env & Flags
# ─────────────────────────────────────────────────────────────────────────────
def _truthy(x: Optional[str]) -> bool:
    if x is None:
        return False
    v = str(x).strip().lower()
    return v in {"1", "true", "yes", "on"}


def _running_in_docker() -> bool:
    if _truthy(os.getenv("IN_DOCKER")) or _truthy(os.getenv("RUNNING_IN_DOCKER")):
        return True
    return os.path.exists("/.dockerenv")


def _resolve_qdrant_url() -> str:
    configured = (os.getenv("QDRANT_URL") or os.getenv("qdrant_url") or "").strip()
    default_url = "http://qdrant:6333"
    if not configured:
        return default_url

    parsed = urlparse(configured)
    if parsed.scheme and parsed.hostname and _running_in_docker() and parsed.hostname in {"localhost", "127.0.0.1"}:
        replacement_host = "qdrant"
        auth = ""
        if parsed.username:
            auth = parsed.username
            if parsed.password:
                auth += f":{parsed.password}"
            auth += "@"
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"{auth}{replacement_host}{port}"
        rewritten = urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
        log.warning(
            "qdrant_url_rewritten_for_docker",
            extra={"original": configured, "rewritten": rewritten},
        )
        return rewritten.rstrip("/")

    return configured.rstrip("/")

# RAG core
QDRANT_URL                 = _resolve_qdrant_url()
QDRANT_COLLECTION_PREFIX   = os.getenv("QDRANT_COLLECTION_PREFIX", "").strip()
QDRANT_COLLECTION_DEFAULT  = settings.qdrant_collection
QDRANT_VECTOR_NAME         = "dense"
QDRANT_SPARSE_VECTOR_NAME  = "sparse"

# Embeddings / Rerank
EMB_MODEL_NAME             = (
    os.getenv("RAG_DENSE_MODEL")
    or os.getenv("embedding_model")
    or "BAAI/bge-base-en-v1.5"
).strip()
SPARSE_MODEL_NAME          = os.getenv("RAG_SPARSE_MODEL", "prithivida/Splade_PP_en_v1").strip()
RERANK_MODEL_NAME          = os.getenv("RERANK_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")
EMBEDDINGS_CACHE_FOLDER    = os.getenv("EMBEDDINGS_CACHE_FOLDER", "/app/data/models").strip()
EMBEDDINGS_CACHE_FALLBACK  = os.getenv("EMBEDDINGS_CACHE_FALLBACK", "/tmp/sealai-models").strip()

# Retrieval knobs
HYBRID_K                   = int(os.getenv("RAG_HYBRID_K", os.getenv("RAG_TOP_K", "12")))
FINAL_K                    = int(os.getenv("RAG_FINAL_K", "6"))
RRF_K                      = int(os.getenv("RAG_RRF_K", "60"))
SCORE_THRESHOLD            = float(os.getenv("RAG_SCORE_THRESHOLD", "0.05"))
ZERO_SCORE_EPS             = 1e-9
QDRANT_TIMEOUT_S           = float(os.getenv("QDRANT_TIMEOUT_S", "5.0"))
QDRANT_RETRY_ATTEMPTS      = 3
QDRANT_RETRY_BASE_MS       = 150
QDRANT_RETRY_JITTER_MS     = 100
QDRANT_RETRY_STATUS        = {429, 500, 502, 503, 504}

# Optional BM25 over Redis (gated)
# v3.1 blueprint default: hybrid retrieval enabled unless explicitly disabled.
USE_BM25                   = _truthy(os.getenv("RAG_BM25_ENABLED", "1"))
USE_SPARSE_RETRIEVAL       = _truthy(os.getenv("RAG_SPARSE_ENABLED", "1"))
REDIS_URL                  = os.getenv("REDIS_URL")
REDIS_BM25_INDEX           = os.getenv("REDIS_BM25_INDEX") or os.getenv("RAG_BM25_INDEX")

# ─────────────────────────────────────────────────────────────────────────────
# Module globals (lazy)
# ─────────────────────────────────────────────────────────────────────────────
_embedder = None
_sparse_embedder = None
_reranker = None
_embedding_dim: Optional[int] = None
_resolved_cache_folder: Optional[str] = EMBEDDINGS_CACHE_FOLDER or None

def resolve_embedding_model() -> Tuple[str, int]:
    _, resolved_dim = resolve_embedding_config()
    return EMB_MODEL_NAME, resolved_dim

def resolve_embedding_config() -> Tuple[str, int]:
    """Resolve embedding model name and vector dimension from the active embedder."""
    global _embedder, _embedding_dim
    model_name = EMB_MODEL_NAME
    if _embedding_dim is not None:
        return model_name, _embedding_dim

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
                "source_id": str(metadata.get("source_id") or ""),
                "version": str(metadata.get("version") or "1.0"),
                "sha256": str(sha256) if sha256 is not None else None,
                "filename": _truncate_str(filename, 160),
                "page": _coerce_int(page),
                "section": _truncate_str(section, 160),
                "score": score,
                "source": _truncate_str(source, 200),
            }
        )
    return sources

def _embedding_cache_folder() -> Optional[str]:
    global _resolved_cache_folder
    candidate = (_resolved_cache_folder or "").strip()
    if not candidate:
        return None
    try:
        os.makedirs(candidate, exist_ok=True)
        return candidate
    except PermissionError:
        fallback = (EMBEDDINGS_CACHE_FALLBACK or "").strip()
        if not fallback:
            _event("embeddings_cache_unavailable", preferred=candidate, error="permission_denied")
            _resolved_cache_folder = None
            return None
        try:
            os.makedirs(fallback, exist_ok=True)
            _event("embeddings_cache_fallback", preferred=candidate, fallback=fallback)
            _resolved_cache_folder = fallback
            return fallback
        except Exception as exc:
            _event(
                "embeddings_cache_unavailable",
                preferred=candidate,
                fallback=fallback,
                error=f"{type(exc).__name__}: {exc}",
            )
            _resolved_cache_folder = None
            return None
    except Exception as exc:
        _event(
            "embeddings_cache_unavailable",
            preferred=candidate,
            error=f"{type(exc).__name__}: {exc}",
        )
        _resolved_cache_folder = None
        return None

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
    global _embedder, _reranker, _embedding_dim
    try:
        t0 = time.perf_counter()
        from fastembed import TextEmbedding  # type: ignore

        cache_folder = _embedding_cache_folder()
        embedder_kwargs: Dict[str, Any] = {"model_name": EMB_MODEL_NAME}
        if cache_folder:
            embedder_kwargs["cache_dir"] = cache_folder
        _embedder = TextEmbedding(**embedder_kwargs)
        _embedding_dim = len(next(_embedder.embed(["_warmup_"])).tolist())
        _event(
            "embeddings_loaded",
            model=EMB_MODEL_NAME,
            backend="fastembed",
            dim=_embedding_dim,
            ms=int((time.perf_counter() - t0) * 1000),
        )
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
    return QDRANT_COLLECTION_DEFAULT

def _embed(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding  # type: ignore

        cache_folder = _embedding_cache_folder()
        embedder_kwargs: Dict[str, Any] = {"model_name": EMB_MODEL_NAME}
        if cache_folder:
            embedder_kwargs["cache_dir"] = cache_folder
        _embedder = TextEmbedding(**embedder_kwargs)
    return [vec.tolist() for vec in _embedder.embed(texts)]


def _embed_sparse_query(text: str) -> Optional[Dict[str, Any]]:
    if not USE_SPARSE_RETRIEVAL:
        return None
    q = (text or "").strip()
    if not q:
        return None
    global _sparse_embedder
    try:
        if _sparse_embedder is None:
            from fastembed import SparseTextEmbedding  # type: ignore

            _sparse_embedder = SparseTextEmbedding(model_name=SPARSE_MODEL_NAME)
        sparse_vec = next(_sparse_embedder.embed([q]))
        if hasattr(sparse_vec, "as_object"):
            payload = sparse_vec.as_object()
        elif isinstance(sparse_vec, dict):
            payload = sparse_vec
        else:
            payload = {
                "indices": list(getattr(sparse_vec, "indices", []) or []),
                "values": list(getattr(sparse_vec, "values", []) or []),
            }
        indices = payload.get("indices") if isinstance(payload, dict) else None
        values = payload.get("values") if isinstance(payload, dict) else None
        if not isinstance(indices, list) or not isinstance(values, list):
            return None
        if not indices or not values:
            return None
        return {"indices": [int(i) for i in indices], "values": [float(v) for v in values]}
    except Exception as exc:
        _event("sparse_query_embed_failed", model=SPARSE_MODEL_NAME, error=f"{type(exc).__name__}: {exc}")
        return None

def _to_qdrant_sparse_vector(models_module: Any, sparse_query: Any) -> Optional[Any]:
    if sparse_query is None:
        return None

    # FastEmbed commonly returns SparseEmbedding with ndarray fields; Qdrant expects plain lists.
    raw_indices: Any = None
    raw_values: Any = None
    if isinstance(sparse_query, dict):
        raw_indices = sparse_query.get("indices")
        raw_values = sparse_query.get("values")
    else:
        raw_indices = getattr(sparse_query, "indices", None)
        raw_values = getattr(sparse_query, "values", None)

    if raw_indices is None or raw_values is None:
        return None

    if hasattr(raw_indices, "tolist"):
        raw_indices = raw_indices.tolist()
    if hasattr(raw_values, "tolist"):
        raw_values = raw_values.tolist()

    try:
        indices = [int(i) for i in (raw_indices or [])]
        values = [float(v) for v in (raw_values or [])]
    except (TypeError, ValueError):
        return None

    if not indices or not values or len(indices) != len(values):
        return None

    return models_module.SparseVector(indices=indices, values=values)

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
        "error_msg": _truncate_str(message, 200) or "qdrant_error",
    }

def _should_retry_status(status: int) -> bool:
    return status in QDRANT_RETRY_STATUS

def _as_str_list(value: Any) -> List[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]
    out: List[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip() if item is not None else ""
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out

def _build_qdrant_filter(metadata_filters: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Build a Qdrant filter dict from metadata_filters.

    Special key ``_visibility_user_id``: when present, adds a ``should`` clause
    that enforces visibility rules — the requesting user can see:
      (1) all documents where ``tenant_id == user_id`` (own docs, any visibility), or
      (2) documents where ``visibility == "public"`` (shared/public docs from any
          allowed tenant, e.g. "sealai").
    This prevents private docs from other tenants leaking through the filter.
    """
    if not metadata_filters:
        return None

    # Extract special visibility key — not a Qdrant payload field.
    visibility_user_id: Optional[str] = metadata_filters.get("_visibility_user_id") or None

    tenant_values: List[str] = []
    if "tenant_id" in metadata_filters:
        tenant_values.extend(_as_str_list(metadata_filters.get("tenant_id")))
    if "metadata.tenant_id" in metadata_filters:
        tenant_values.extend(_as_str_list(metadata_filters.get("metadata.tenant_id")))

    if not tenant_values:
        return None

    deduped: List[str] = []
    seen: set[str] = set()
    for tenant in tenant_values:
        if not tenant or tenant in seen:
            continue
        seen.add(tenant)
        deduped.append(tenant)

    if not deduped:
        return None

    # Build the tenant must-condition.
    if len(deduped) == 1:
        tenant_condition: Dict[str, Any] = {"key": "tenant_id", "match": {"value": deduped[0]}}
    else:
        tenant_condition = {"key": "tenant_id", "match": {"any": deduped}}

    result: Dict[str, Any] = {"must": [tenant_condition]}

    # Visibility gate: enforce public-only for docs the user does not own.
    # A point passes if EITHER:
    #   • its tenant_id equals the requesting user_id (own document), OR
    #   • its visibility field is "public"
    # Qdrant semantics: when both `must` and `should` are present, a point must
    # satisfy ALL must-conditions AND AT LEAST ONE should-condition.
    if visibility_user_id:
        result["should"] = [
            {"key": "visibility", "match": {"value": "public"}},
            {"key": "tenant_id", "match": {"value": visibility_user_id}},
        ]

    return result


def _qdrant_client_kwargs() -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {"url": QDRANT_URL}
    api_key = (os.getenv("QDRANT_API_KEY") or "").strip()
    if api_key:
        kwargs["api_key"] = api_key
    return kwargs


def _make_qdrant_client() -> Any:
    from qdrant_client import QdrantClient

    return QdrantClient(**_qdrant_client_kwargs())

def _qdrant_search_with_retry(
    query_vec: List[float],
    sparse_query: Optional[Dict[str, Any]],
    collection: str,
    top_k: int = HYBRID_K,
    metadata_filters: Optional[Dict[str, Any]] = None,
    timeout_s: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    effective_timeout_s = float(timeout_s) if timeout_s is not None else QDRANT_TIMEOUT_S
    qdrant_timeout = int(float(effective_timeout_s))

    attempts = 0
    backoffs: List[int] = []
    last_error: Dict[str, Any] | None = None
    started = time.perf_counter()

    for attempt in range(QDRANT_RETRY_ATTEMPTS):
        attempts += 1
        try:
            from qdrant_client import models

            qdrant_filter = _build_qdrant_filter(metadata_filters)
            filter_model = models.Filter(**qdrant_filter) if qdrant_filter else None
            client = _make_qdrant_client()

            sparse_vector = _to_qdrant_sparse_vector(models, sparse_query)
            
            if sparse_vector is not None:
                # Hybrid Search: Use prefetch + FusionQuery
                prefetch = [
                    models.Prefetch(query=query_vec, using=QDRANT_VECTOR_NAME, limit=top_k),
                    models.Prefetch(query=sparse_vector, using=QDRANT_SPARSE_VECTOR_NAME, limit=top_k),
                ]
                query = models.FusionQuery(fusion=models.Fusion.RRF)
                using = None
            else:
                # Single Vector Search: No prefetch allowed if only one query source
                prefetch = None
                query = query_vec
                using = QDRANT_VECTOR_NAME

            response = client.query_points(
                collection_name=collection,
                prefetch=prefetch,
                query=query,
                using=using,
                query_filter=filter_model,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
                timeout=qdrant_timeout,
            )
            res = getattr(response, "points", None)
            if res is None and isinstance(response, dict):
                res = response.get("points") or response.get("result") or []
            if res is None:
                res = []

            out: List[Dict[str, Any]] = []
            for item in res:
                payload = getattr(item, "payload", None)
                if payload is None and isinstance(item, dict):
                    payload = item.get("payload")
                payload = payload or {}
                txt = payload.get("text") or payload.get("chunk") or payload.get("content") or ""
                src = payload.get("source") or (payload.get("metadata") or {}).get("source") or payload.get("file") or ""
                raw_score = getattr(item, "score", None)
                if raw_score is None and isinstance(item, dict):
                    raw_score = item.get("score")
                out.append({
                    "text": txt,
                    "source": src,
                    "vector_score": float(raw_score or 0.0),
                    "metadata": payload,
                })
            hits = out
            top_score = (
                hits[0].score if hits and hasattr(hits[0], "score")
                else (hits[0].get("vector_score") if hits and isinstance(hits[0], dict) else "N/A")
            )
            log.debug(
                "rag.raw_hits",
                extra={"count": len(hits), "top_score": top_score, "collection": collection},
            )
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return out, {
                "attempts": attempts,
                "timeout_s": effective_timeout_s,
                "elapsed_ms": elapsed_ms,
                "retry_backoff_ms": backoffs or None,
                "error": None,
            }
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status is not None:
                try:
                    status = int(status)
                except Exception:
                    status = None
            kind = "unknown"
            if type(exc).__name__ in {"ResponseHandlingException"}:
                kind = "decode"
            elif type(exc).__name__ in {"UnexpectedResponse"}:
                kind = "http_error"
            elif "Timeout" in type(exc).__name__:
                kind = "timeout"
            elif "Transport" in type(exc).__name__ or "Connect" in type(exc).__name__:
                kind = "network"
            last_error = _qdrant_error(kind, status, f"{type(exc).__name__}: {exc}")
            log.exception(
                "Qdrant Query Failed",
                extra={
                    "attempt": attempts,
                    "max_attempts": QDRANT_RETRY_ATTEMPTS,
                    "collection": collection,
                    "kind": kind,
                    "status": status,
                    "top_k": top_k,
                },
            )
            if kind == "http_error" and status is not None and not _should_retry_status(status):
                break

        if attempt < QDRANT_RETRY_ATTEMPTS - 1:
            delay_ms = _qdrant_backoff_ms(attempt)
            backoffs.append(delay_ms)
            log.warning(
                "qdrant_retry_exception",
                extra={
                    "attempt": attempts,
                    "max_attempts": QDRANT_RETRY_ATTEMPTS,
                    "kind": (last_error or {}).get("kind"),
                    "status": (last_error or {}).get("status"),
                    "error_msg": (last_error or {}).get("message"),
                    "retry_in_ms": delay_ms,
                },
            )
            time.sleep(delay_ms / 1000.0)
            continue
        break

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if last_error:
        _event("qdrant_search_failed", reason=last_error.get("message", "error"), collection=collection)
    return [], {
        "attempts": attempts,
        "timeout_s": effective_timeout_s,
        "elapsed_ms": elapsed_ms,
        "retry_backoff_ms": backoffs or None,
        "error": last_error or _qdrant_error("unknown", None, "qdrant_error"),
    }


def _apply_threshold(hits: List[Dict[str, Any]], thr: float) -> List[Dict[str, Any]]:
    out = []
    for h in hits:
        s = _score_value(h)
        # Keep sparse/hybrid low-score hits; only hard-block true zero-score entries.
        if s <= ZERO_SCORE_EPS:
            continue
        out.append(h)
    return out


def _score_value(hit: Dict[str, Any]) -> float:
    has_retrieval_score = ("vector_score" in hit) or ("sparse_score" in hit)
    vector_score = float(hit.get("vector_score") or 0.0)
    sparse_score = float(hit.get("sparse_score") or 0.0)
    if has_retrieval_score:
        return float(max(vector_score, sparse_score))
    return float(hit.get("fused_score") or 0.0)


def _sanitize_hits(hits: List[Dict[str, Any]], thr: float) -> List[Dict[str, Any]]:
    out = _apply_threshold(hits, thr)
    if not out:
        return []
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
                    user_id: Optional[str] = None,
                    use_rerank: bool = True,
                    qdrant_timeout_s: Optional[float] = None,
                    return_metrics: bool = False) -> List[Dict[str, Any]] | Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Vector-first retrieval from Qdrant (+ optional BM25 fusion in future).
    Returns list of {text, source, vector_score, fused_score?, metadata}.
    """
    q = (query or "").strip()
    if not q:
        return []
    effective_k = k
    effective_threshold = 0.0

    # Embed query
    log.warning(
        "rag_search_embedding_model model=%s backend=fastembed vector_name=dense",
        EMB_MODEL_NAME,
    )
    vec = _embed([q])[0]
    sparse_query = _embed_sparse_query(q)

    # Pick collection by tenant
    collection = _collection_for_tenant(tenant)

    # Enforce tenant scoping via payload filters (single collection strategy).
    # Restrict payload filtering to tenant scope only.
    raw_filters: Dict[str, Any] = dict(metadata_filters or {})
    filters: Dict[str, Any] = {}
    tenant_values: List[str] = []

    if "tenant_id" in raw_filters:
        tenant_values.extend(_as_str_list(raw_filters.get("tenant_id")))
    if "metadata.tenant_id" in raw_filters:
        tenant_values.extend(_as_str_list(raw_filters.get("metadata.tenant_id")))
    if tenant:
        tenant_values.extend(_as_str_list(tenant))
        if tenant != "sealai":
            tenant_values.append("sealai")

    if tenant_values:
        deduped: List[str] = []
        seen: set[str] = set()
        for item in tenant_values:
            if not item or item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        filters["tenant_id"] = deduped if len(deduped) > 1 else deduped[0]

    # Visibility enforcement: pass user_id so _build_qdrant_filter can add
    # a should-clause that blocks private docs from other tenants.
    effective_user_id = user_id or (tenant if tenant and tenant != "sealai" else None)
    if effective_user_id:
        filters["_visibility_user_id"] = effective_user_id

    qdrant_filter = _build_qdrant_filter(filters)
    log.debug(
        "rag.qdrant_filter",
        extra={"filter": str(qdrant_filter)[:300] if qdrant_filter else None, "tenant": tenant},
    )

    # Vector search
    vector_k = max(HYBRID_K, effective_k)
    vec_hits, qdrant_meta = _qdrant_search_with_retry(
        vec,
        sparse_query,
        collection,
        top_k=vector_k,
        metadata_filters=filters,
        timeout_s=qdrant_timeout_s,
    )

    bm25_hits: List[Dict[str, Any]] = []
    bm25_error: Optional[Dict[str, Any]] = None
    bm25_k = max(HYBRID_K, effective_k)
    bm25_filters: Dict[str, Any] = dict(filters)
    bm25_tenant_value = bm25_filters.get("tenant_id")
    if isinstance(bm25_tenant_value, (list, tuple, set)):
        bm25_tenant_candidates = _as_str_list(bm25_tenant_value)
        preferred_tenant = next((v for v in bm25_tenant_candidates if v != "sealai"), None)
        if preferred_tenant:
            bm25_filters["tenant_id"] = preferred_tenant
        elif bm25_tenant_candidates:
            bm25_filters["tenant_id"] = bm25_tenant_candidates[0]
        else:
            bm25_filters.pop("tenant_id", None)
    if USE_BM25:
        bm25_hits, bm25_error = _bm25_search(
            q, collection, top_k=bm25_k, metadata_filters=bm25_filters
        )

    # Placeholder: BM25 could be merged here when enabled
    merged: List[Dict[str, Any]]
    used_fusion = False
    if USE_BM25 and bm25_hits:
        merged = _rrf_fuse(vec_hits, bm25_hits, k0=RRF_K)
        used_fusion = True
    else:
        merged = list(vec_hits)

    # Optional rerank
    merged = _rerank_if_enabled(q, merged, use_rerank)

    # Threshold + top-k
    merged = _sanitize_hits(merged, effective_threshold)[:effective_k]

    # Externer Fallback (Microservice), wenn keine Treffer
    if not merged:
        ext = _fallback_external_search(q, tenant=tenant, limit=effective_k)
        merged = _sanitize_hits(ext, effective_threshold)[:effective_k]

    reranked = any("rerank_score" in hit for hit in merged)
    metrics: Dict[str, Any] = {
        "k_requested": effective_k,
        "k_returned": len(merged),
        "top_scores": [
            _score_value(hit)
            for hit in merged
        ][:5],
        "threshold": effective_threshold,
        "configured_threshold": SCORE_THRESHOLD if SCORE_THRESHOLD > 0 else None,
        "fused": used_fusion,
        "reranked": reranked,
        "collection": collection,
        "vector_name": QDRANT_VECTOR_NAME or None,
        "sparse_vector_name": QDRANT_SPARSE_VECTOR_NAME if sparse_query else None,
        "sparse_query_enabled": bool(sparse_query),
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

    # [MONITORING] Score Quality Check (Blueprint v4.1)
    if merged and float(merged[0].get("fused_score") or merged[0].get("vector_score") or 0.0) < 0.1:
        log.warning(
            "rag_low_quality_results",
            extra={
                "query": q[:100],
                "top_score": merged[0].get("fused_score") or merged[0].get("vector_score"),
                "tenant": tenant,
            }
        )

    if return_metrics:
        return merged, metrics
    return merged

__all__ = [
    "startup_warmup",
    "init_bm25",
    "prewarm_embeddings",
    "resolve_embedding_model",
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
