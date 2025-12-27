from __future__ import annotations

import logging
import os
import time
from typing import Optional, Tuple

from app.services.rag.rag_orchestrator import resolve_embedding_model

log = logging.getLogger("app.services.rag.qdrant_bootstrap")


def _collection_name() -> str:
    return (os.getenv("QDRANT_COLLECTION") or "sealai-docs").strip()


def _qdrant_client_kwargs() -> dict:
    kwargs: dict = {"url": (os.getenv("QDRANT_URL") or "http://qdrant:6333").rstrip("/")}
    api_key = (os.getenv("QDRANT_API_KEY") or "").strip()
    if api_key:
        kwargs["api_key"] = api_key
    return kwargs


def _extract_vector_size(info: object) -> Optional[int]:
    try:
        # qdrant-client models: info.config.params.vectors.size
        config = getattr(info, "config", None)
        params = getattr(config, "params", None) if config is not None else None
        vectors = getattr(params, "vectors", None) if params is not None else None
        if vectors is None:
            return None
        size = getattr(vectors, "size", None)
        if size is not None:
            return int(size)
        # Named vectors: vectors is a dict-like
        if isinstance(vectors, dict):
            for v in vectors.values():
                if isinstance(v, dict) and "size" in v:
                    return int(v["size"])
                size = getattr(v, "size", None)
                if size is not None:
                    return int(size)
    except Exception:
        return None
    return None


def bootstrap_rag_collection(*, expected: Optional[Tuple[str, int]] = None) -> str:
    """
    Ensure the main RAG collection exists with the configured embedding dim.

    - Creates the collection if missing.
    - Never touches any collection name ending with `-ltm`.
    - If Qdrant is down: warn and return "skipped".
    - If collection exists but dim mismatches: raise RuntimeError (fail-fast, explicit).
    """
    collection = _collection_name()
    if not collection:
        log.warning("qdrant_bootstrap_skipped reason=empty_collection_name")
        return "skipped"
    if collection.endswith("-ltm"):
        log.warning("qdrant_bootstrap_skipped reason=ltm_collection_guard collection=%s", collection)
        return "skipped"

    model_name, dim = expected or resolve_embedding_model()

    try:
        from qdrant_client import QdrantClient, models
        from qdrant_client.http.exceptions import UnexpectedResponse
    except Exception as exc:
        log.warning("qdrant_client_unavailable error=%s: %s", type(exc).__name__, exc)
        return "skipped"

    try:
        client = QdrantClient(**_qdrant_client_kwargs())

        last_exc: Exception | None = None
        for attempt in range(1, 6):
            try:
                info = client.get_collection(collection)
                actual = _extract_vector_size(info)
                if actual is not None and actual != dim:
                    msg = (
                        f"FATAL mismatch: Qdrant collection '{collection}' vector size={actual} "
                        f"!= expected={dim} for embedding model '{model_name}'."
                    )
                    log.critical(msg)
                    raise RuntimeError(msg)
                log.info("qdrant_collection_ok collection=%s model=%s dim=%s", collection, model_name, dim)
                return "ok"
            except UnexpectedResponse as exc:
                last_exc = exc
                if getattr(exc, "status_code", None) == 404:
                    log.info("qdrant_collection_create collection=%s model=%s dim=%s", collection, model_name, dim)
                    client.create_collection(
                        collection_name=collection,
                        vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
                        hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100),
                        optimizers_config=models.OptimizersConfigDiff(indexing_threshold=10000),
                    )
                    return "created"
                raise
            except RuntimeError:
                raise
            except Exception as exc:
                last_exc = exc
                # Qdrant may not be ready yet during startup; retry a few times.
                if attempt < 5:
                    time.sleep(0.6)
                    continue
                raise

        raise last_exc or RuntimeError("unknown bootstrap failure")
    except RuntimeError:
        raise
    except Exception as exc:
        log.warning("qdrant_bootstrap_skipped reason=%s: %s collection=%s", type(exc).__name__, exc, collection)
        return "skipped"


__all__ = ["bootstrap_rag_collection"]
