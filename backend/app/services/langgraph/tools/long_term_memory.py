# backend/app/services/langgraph/tools/long_term_memory.py
from __future__ import annotations

import os
import time
import uuid
import logging
import threading
from typing import Optional, Dict, Any, List, Tuple

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# -------------------- ENV & Defaults --------------------

_QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333").strip() or "http://qdrant:6333"
_COLLECTION = os.getenv("LTM_COLLECTION", "sealai_ltm").strip() or "sealai_ltm"
_EMB_MODEL = os.getenv("LTM_EMBED_MODEL", "intfloat/multilingual-e5-base").strip() or "intfloat/multilingual-e5-base"
_DISABLE_PREWARM = os.getenv("LTM_DISABLE_PREWARM", "0").strip() in ("1", "true", "yes", "on")

# -------------------- Singletons --------------------

_client = None            # QdrantClient
_embeddings = None        # HuggingFaceEmbeddings
_ready = False
_init_err: Optional[str] = None
_lock = threading.RLock()

# -------------------- Init helpers --------------------

def _init_hf_embeddings():
    """Create CPU-safe HuggingFaceEmbeddings."""
    from langchain_huggingface import HuggingFaceEmbeddings
    log.info("LTM: using HuggingFaceEmbeddings model=%s", _EMB_MODEL)
    return HuggingFaceEmbeddings(
        model_name=_EMB_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

def _ensure_collection(client, dim: int):
    from qdrant_client.http.models import Distance, VectorParams
    try:
        info = client.get_collection(_COLLECTION)
        if info and getattr(info, "vectors_count", 0) > 0:
            return
    except Exception:
        pass
    client.recreate_collection(
        collection_name=_COLLECTION,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )

def _do_init_once():
    global _client, _embeddings, _ready, _init_err
    from qdrant_client import QdrantClient

    log.info("LTM: Connecting Qdrant at %s", _QDRANT_URL)
    client = QdrantClient(url=_QDRANT_URL, prefer_grpc=False, timeout=5.0)

    embeddings = _init_hf_embeddings()
    # probe to get dimension
    probe_vec = embeddings.embed_query("ltm-probe")
    dim = len(probe_vec)
    _ensure_collection(client, dim)

    _client = client
    _embeddings = embeddings
    _ready = True
    _init_err = None

def _do_init(retries: int = 2, backoff_ms: int = 400):
    global _ready, _init_err
    if _ready:
        return
    with _lock:
        if _ready:
            return
        for i in range(retries + 1):
            try:
                _do_init_once()
                log.info("LTM init ok")
                return
            except Exception as e:
                _init_err = f"{e}"
                if i < retries:
                    log.warning("LTM init attempt %s failed: %s – retrying in %dms", i + 1, _init_err, backoff_ms)
                    time.sleep(backoff_ms / 1000.0)
                else:
                    log.error("LTM init failed: %s", _init_err)

# -------------------- Public API --------------------

def prewarm_ltm():
    """Optional prewarm – no-op if disabled by ENV."""
    if _DISABLE_PREWARM:
        return
    _do_init()

def upsert_memory(*, user: str, chat_id: str, text: str, kind: str = "note") -> bool:
    """
    Store a short memory snippet. Returns True if stored, False otherwise.
    Works even if init failed (returns False, no exception).
    """
    try:
        if not _ready:
            _do_init()
        if not (_ready and _client and _embeddings):
            return False

        vec = _embeddings.embed_query(text or "")
        if not isinstance(vec, list):
            vec = list(vec)

        payload: Dict[str, Any] = {
            "user": user,
            "chat_id": chat_id,
            "kind": kind,
            "text": text,
        }

        point_id = str(uuid.uuid4())
        from qdrant_client.http.models import PointStruct
        _client.upsert(
            collection_name=_COLLECTION,
            points=[PointStruct(id=point_id, vector=vec, payload=payload)],
            wait=True,
        )
        return True
    except Exception as e:
        log.warning("LTM upsert failed: %s", e)
        return False


def _qdrant_filter(*, user: Optional[str], chat_id: Optional[str]):
    """Build Qdrant payload filter for user/chat_id if provided."""
    try:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        must: List[Any] = []
        if user:
            must.append(FieldCondition(key="user", match=MatchValue(value=user)))
        if chat_id:
            must.append(FieldCondition(key="chat_id", match=MatchValue(value=chat_id)))
        return Filter(must=must) if must else None
    except Exception:
        return None


def ltm_query(
    query: str,
    *,
    user: Optional[str] = None,
    chat_id: Optional[str] = None,
    top_k: int = 5,
    strategy: str = "mmr",
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Query Long-Term-Memory (Qdrant) using embeddings.
    Returns (context_text, hits)

    - Filters by user/chat_id when provided
    - Concatenates top hits' payload['text'] into a compact context
    """
    try:
        if not _ready:
            _do_init()
        if not (_ready and _client and _embeddings):
            return "", []

        qvec = _embeddings.embed_query(query or "")
        if not isinstance(qvec, list):
            qvec = list(qvec)

        flt = _qdrant_filter(user=user, chat_id=chat_id)

        # Qdrant search
        from qdrant_client.http.models import SearchParams
        params = SearchParams(hnsw_ef=128)
        points = _client.search(
            collection_name=_COLLECTION,
            query_vector=qvec,
            limit=max(1, int(top_k or 5)),
            query_filter=flt,
            with_payload=True,
            with_vectors=False,
            search_params=params,
        )
        hits: List[Dict[str, Any]] = []
        parts: List[str] = []
        for p in points or []:
            payload = dict(getattr(p, "payload", {}) or {})
            txt = (payload.get("text") or "").strip()
            if txt:
                parts.append(txt)
            hits.append({
                "id": str(getattr(p, "id", "")),
                "score": float(getattr(p, "score", 0.0) or 0.0),
                "payload": payload,
            })

        # Simple diversity: if strategy == mmr, drop near-duplicates by text prefix
        if strategy.lower().startswith("mmr") and len(parts) > 1:
            seen: set[str] = set()
            dedup_parts: List[str] = []
            for t in parts:
                key = t[:64]
                if key in seen:
                    continue
                seen.add(key)
                dedup_parts.append(t)
            parts = dedup_parts

        ctx_max = 800
        ctx = "\n\n".join(parts)[:ctx_max]
        return ctx, hits
    except Exception as e:
        log.warning("LTM query failed: %s", e)
        return "", []
