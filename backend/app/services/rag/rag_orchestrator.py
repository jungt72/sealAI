# backend/app/services/rag/rag_orchestrator.py
from __future__ import annotations

import math
import os
import time
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import structlog
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter as QFilter,
    MatchValue,
    VectorParams,
)
from sentence_transformers import SentenceTransformer
from sentence_transformers.cross_encoder import CrossEncoder

log = structlog.get_logger(__name__)

# ---- Konfiguration ----
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None

COLL_PREFIX = os.getenv("QDRANT_COLLECTION_PREFIX", "sealai-docs")
DEFAULT_COLL = os.getenv("QDRANT_DEFAULT_COLLECTION", COLL_PREFIX)

EMB_MODEL_NAME = os.getenv("EMB_MODEL_NAME", "intfloat/multilingual-e5-base")
RERANK_MODEL_NAME = os.getenv("RERANK_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")

HYBRID_K = int(os.getenv("RAG_HYBRID_K", "12"))
FINAL_K = int(os.getenv("RAG_FINAL_K", "6"))
RRF_K = int(os.getenv("RAG_RRF_K", "60"))
VEC_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.0"))

TENANT_FIELD = os.getenv("RAG_TENANT_FIELD", "tenant")
REDIS_BM25_INDEX = os.getenv("REDIS_BM25_INDEX", "sealai:docs")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# ---- Lazy Singletons ----
_qdrant: Optional[QdrantClient] = None
_emb: Optional[SentenceTransformer] = None
_reranker: Optional[CrossEncoder] = None
_redis_search: Optional[Dict[str, Any]] = None  # {"mode":"raw"/"redisvl", ...}

@dataclass
class RetrievedDoc:
    id: str
    text: str
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    fused_score: Optional[float] = None
    def to_payload(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.metadata and len(str(self.metadata)) > 5000:
            d["metadata"] = {"_truncated": True}
        return d

# ---------------- Qdrant / Embeddings ----------------
def _get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY, timeout=30.0)
    return _qdrant

def _get_emb() -> SentenceTransformer:
    global _emb
    if _emb is None:
        t0 = time.time()
        _emb = SentenceTransformer(EMB_MODEL_NAME, device="cpu")
        log.info("embeddings_loaded", model=EMB_MODEL_NAME, ms=round((time.time() - t0) * 1000))
    return _emb

def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        t0 = time.time()
        _reranker = CrossEncoder(RERANK_MODEL_NAME)
        log.info("reranker_loaded", model=RERANK_MODEL_NAME, ms=round((time.time() - t0) * 1000))
    return _reranker

def _collection_for(tenant: Optional[str]) -> str:
    return f"{COLL_PREFIX}-{tenant}" if tenant else DEFAULT_COLL

def _embed(texts: List[str]) -> List[List[float]]:
    emb = _get_emb()
    prepped = [f"query: {t}" for t in texts]
    return emb.encode(prepped, normalize_embeddings=True).tolist()

def _ensure_collection(coll: str) -> None:
    client = _get_qdrant()
    try:
        names = {c.name for c in (client.get_collections().collections or [])}
        if coll in names:
            return
    except Exception:
        pass
    dim = len(_embed(["ping"])[0])
    log.info("qdrant_create_collection", collection=coll, dim=dim)
    client.create_collection(collection_name=coll, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
    for field in (TENANT_FIELD, "material", "profile", "domain", "norm", "lang", "source", "doc_sha1"):
        try:
            client.create_payload_index(collection_name=coll, field_name=field, field_schema="keyword")
        except Exception:
            pass

def _qdrant_vector_search(query: str, tenant: Optional[str], k: int, metadata_filters: Optional[Dict[str, Any]]) -> List[RetrievedDoc]:
    client = _get_qdrant()
    coll = _collection_for(tenant)
    _ensure_collection(coll)
    vec = _embed([query])[0]
    conditions: List[FieldCondition] = []
    if tenant:
        conditions.append(FieldCondition(key=TENANT_FIELD, match=MatchValue(value=tenant)))
    if metadata_filters:
        for kf, val in metadata_filters.items():
            conditions.append(FieldCondition(key=kf, match=MatchValue(value=val)))
    qfilter: Optional[QFilter] = QFilter(must=conditions) if conditions else None
    try:
        hits = client.search(
            collection_name=coll,
            query_vector=vec,
            limit=k,
            with_payload=True,
            with_vectors=False,
            score_threshold=VEC_SCORE_THRESHOLD if VEC_SCORE_THRESHOLD > 0 else None,
            query_filter=qfilter,
        )
    except Exception as e:
        log.warning("qdrant_search_failed", collection=coll, error=str(e))
        return []
    out: List[RetrievedDoc] = []
    for h in hits:
        payload = h.payload or {}
        text = payload.get("text") or payload.get("content") or ""
        src = payload.get("source") or payload.get("doc_uri") or payload.get("path")
        out.append(
            RetrievedDoc(
                id=str(h.id),
                text=text,
                source=src,
                metadata=payload,
                vector_score=float(h.score) if h.score is not None else None,
            )
        )
    return out

# ---------------- Redis BM25 ----------------
def _maybe_bind_redis_index() -> None:
    global _redis_search
    if _redis_search is not None:
        return
    index_name = (os.getenv("REDIS_BM25_INDEX") or REDIS_BM25_INDEX or "").strip()
    if not index_name:
        _redis_search = None
        return
    redis_url = os.getenv("REDIS_URL", REDIS_URL)
    try:
        from redisvl.index import SearchIndex  # type: ignore
        try:
            idx = SearchIndex.from_existing(index_name, redis_url=redis_url)
        except Exception:
            idx = SearchIndex.from_existing(index_name)
            idx.connect(redis_url)
        _redis_search = {"mode": "redisvl", "index": idx}
        log.info("redis_bm25_bound", mode="redisvl", index=index_name, url=redis_url)
        return
    except Exception as e:
        log.info("redis_bm25_unavailable", reason=str(e))
    try:
        import redis  # type: ignore
        r = redis.Redis.from_url(redis_url)
        r.execute_command("FT.INFO", index_name)
        _redis_search = {"mode": "raw", "client": r, "name": index_name}
        log.info("redis_bm25_bound", mode="raw", index=index_name, url=redis_url)
    except Exception as e:
        log.info("redis_bm25_unavailable", reason=str(e))
        _redis_search = None

def _normalize_redisvl_result(res: Any) -> List[Dict[str, Any]]:
    docs: List[Any] = []
    if isinstance(res, dict):
        for key in ("documents", "docs", "results", "data"):
            if key in res and isinstance(res[key], (list, tuple)):
                docs = list(res[key]); break
        else:
            for v in res.values():
                if isinstance(v, (list, tuple)) and v and isinstance(v[0], (dict, object)):
                    docs = list(v); break
    elif isinstance(res, (list, tuple)):
        docs = list(res)
    else:
        for attr in ("documents", "docs", "results", "data"):
            if hasattr(res, attr):
                maybe = getattr(res, attr)
                if isinstance(maybe, (list, tuple)):
                    docs = list(maybe); break
    out: List[Dict[str, Any]] = []
    for d in docs:
        if isinstance(d, dict):
            out.append(d); continue
        tmp: Dict[str, Any] = {}
        for k in ("id", "pk", "text", "source", "__score", TENANT_FIELD):
            if hasattr(d, k):
                tmp[k] = getattr(d, k)
        if hasattr(d, "payload") and isinstance(getattr(d, "payload"), dict):
            tmp.update(getattr(d, "payload"))
        if not tmp and hasattr(d, "__dict__"):
            tmp.update({k: v for k, v in d.__dict__.items() if not k.startswith("_")})
        out.append(tmp)
    return out

def _redisvl_search(idx, q: str, k: int, return_fields: List[str]) -> List[Dict[str, Any]]:
    variants = [
        {"num_results": k, "return_fields": return_fields},
        {"top_k": k, "return_fields": return_fields},
        {"k": k, "return_fields": return_fields},
        {"paging": {"offset": 0, "limit": k}, "return_fields": return_fields},
        {"return_fields": return_fields},
    ]
    last_err: Optional[Exception] = None
    for kwargs in variants:
        try:
            res = idx.search(query=q, **kwargs)  # type: ignore
            docs = _normalize_redisvl_result(res)
            return docs[:k]
        except TypeError as e:
            last_err = e; continue
        except Exception as e:
            last_err = e; continue
    try:
        res = idx.search(q)  # type: ignore
        docs = _normalize_redisvl_result(res)
        return docs[:k]
    except Exception as e:
        raise RuntimeError(f"Unexpected error while searching: {e}") from last_err

# NEW: defensives Quoten/Escapen – RediSearch-Sonderzeichen
_RS_SPECIAL = re.compile(r'([\-@{}\[\]:"|><()~*?+^$\\])')
def _sanitize_redis_query(q: str) -> str:
    q = q.replace('"', r"\"")
    q = _RS_SPECIAL.sub(r"\\\1", q)
    return f"\"{q}\""  # als Phrase

def _redis_bm25_search(query: str, k: int, tenant: Optional[str]) -> List[RetrievedDoc]:
    _maybe_bind_redis_index()
    if _redis_search is None:
        return []
    user_q = _sanitize_redis_query(query)
    q = f'@{TENANT_FIELD}:{{{tenant}}} {user_q}' if tenant else user_q
    rf = ["id", "text", "source", TENANT_FIELD]
    try:
        if _redis_search.get("mode") == "redisvl":
            idx = _redis_search["index"]
            rows = _redisvl_search(idx, q, k, rf)
            docs: List[RetrievedDoc] = []
            for r in rows:
                docs.append(
                    RetrievedDoc(
                        id=str(r.get("id") or r.get("pk") or ""),
                        text=r.get("text") or "",
                        source=r.get("source"),
                        keyword_score=float(r.get("__score", 0.0)) if "__score" in r else None,
                        metadata={kk: vv for kk, vv in r.items() if kk not in {"id", "text", "source"}},
                    )
                )
            return docs
        r = _redis_search["client"]
        name = _redis_search["name"]
        res = r.execute_command("FT.SEARCH", name, q, "RETURN", 3, "text", "source", TENANT_FIELD, "LIMIT", 0, k)
        if not res or len(res) < 2:
            return []
        items = res[1:]; docs: List[RetrievedDoc] = []
        def _dec(x): return x.decode("utf-8") if isinstance(x, (bytes, bytearray)) else str(x)
        for i in range(0, len(items), 2):
            doc_id = _dec(items[i])
            fields = items[i + 1]
            data = {_dec(fields[j]): _dec(fields[j + 1]) for j in range(0, len(fields), 2)}
            docs.append(RetrievedDoc(id=doc_id, text=data.get("text", ""), source=data.get("source"), keyword_score=None, metadata=data))
        return docs
    except Exception as e:
        log.info("redis_search_failed", reason=str(e))
        return []

# ---------------- Fusion & Reranking ----------------
def _rrf_fuse(vector_docs: List[RetrievedDoc], keyword_docs: List[RetrievedDoc], rrf_k: int, final_k: int) -> List[RetrievedDoc]:
    by_id: Dict[str, RetrievedDoc] = {}
    ranks: Dict[str, float] = {}
    def add_rank(items: List[RetrievedDoc], weight: float = 1.0):
        for idx, d in enumerate(items):
            rid = d.id or f"{hash(d.text)}"
            if rid not in by_id:
                by_id[rid] = d
            ranks[rid] = ranks.get(rid, 0.0) + weight * (1.0 / (rrf_k + (idx + 1)))
    add_rank(vector_docs, 1.0); add_rank(keyword_docs, 1.0)
    fused: List[RetrievedDoc] = []
    for rid, score in sorted(ranks.items(), key=lambda x: x[1], reverse=True):
        doc = by_id[rid]; doc.fused_score = score; fused.append(doc)
    return fused[:final_k]

def _logistic(x: float) -> float: return 1.0 / (1.0 + math.exp(-x))

def _rerank(query: str, docs: List[RetrievedDoc]) -> List[RetrievedDoc]:
    if not docs: return docs
    try:
        rer = _get_reranker()
        pairs = [(query, d.text) for d in docs]
        scores = rer.predict(pairs).tolist()
        for d, s in zip(docs, scores):
            d.fused_score = _logistic(float(s))
        docs.sort(key=lambda d: d.fused_score or 0.0, reverse=True)
    except Exception as e:
        log.info("rerank_failed", reason=str(e))
    return docs

# ---------------- Public API ----------------
def hybrid_retrieve(query: str, tenant: Optional[str], k: int = FINAL_K, metadata_filters: Optional[Dict[str, Any]] = None, use_rerank: bool = True) -> List[Dict[str, Any]]:
    t0 = time.time()
    vec_docs = _qdrant_vector_search(query, tenant=tenant, k=HYBRID_K, metadata_filters=metadata_filters)
    kw_docs = _redis_bm25_search(query, k=HYBRID_K, tenant=tenant)
    fused = _rrf_fuse(vec_docs, kw_docs, rrf_k=RRF_K, final_k=k)
    if use_rerank:
        fused = _rerank(query, fused)
    ms = round((time.time() - t0) * 1000)
    log.info("hybrid_retrieve", tenant=tenant, q=query[:120], vec=len(vec_docs), kw=len(kw_docs), fused=len(fused), ms=ms)
    return [d.to_payload() for d in fused]

# --------- Warmup (beim App-Start aufrufen) ---------
def prewarm() -> None:
    """Lädt Redis/Qdrant/Embedding/Reranker einmalig in den Speicher."""
    try: _maybe_bind_redis_index()
    except Exception: pass
    try: _get_qdrant()
    except Exception: pass
    try: _get_emb()
    except Exception: pass
    try: _get_reranker()
    except Exception: pass
