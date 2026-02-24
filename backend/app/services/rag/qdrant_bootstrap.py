from __future__ import annotations

import logging
import os
import time
from typing import Optional, Tuple

from app.services.rag.rag_orchestrator import resolve_embedding_config

log = logging.getLogger("app.services.rag.qdrant_bootstrap")


def _collection_name() -> str:
    return (os.getenv("QDRANT_COLLECTION") or "sealai_knowledge").strip()


def _qdrant_client_kwargs() -> dict:
    kwargs: dict = {"url": (os.getenv("QDRANT_URL") or "http://qdrant:6333").rstrip("/")}
    api_key = (os.getenv("QDRANT_API_KEY") or "").strip()
    if api_key:
        kwargs["api_key"] = api_key
    return kwargs


def _vector_name() -> str:
    return "dense"


def _sparse_vector_name() -> str:
    return "sparse"


def _is_dev_env() -> bool:
    env = (os.getenv("APP_ENV") or "development").strip().lower()
    return env in {"dev", "development", "local", "test"}


def _build_vectors_config(*, models: object, dim: int) -> object:
    vector_name = _vector_name()
    vector_params = models.VectorParams(size=dim, distance=models.Distance.COSINE)
    if vector_name:
        return {vector_name: vector_params}
    return vector_params


def _build_sparse_vectors_config(*, models: object) -> dict:
    return {_sparse_vector_name(): models.SparseVectorParams()}


def _expected_embedding() -> Tuple[str, int]:
    model_name = "BAAI/bge-base-en-v1.5"
    try:
        _resolved_model, dim = resolve_embedding_config()
        return model_name, dim
    except Exception as exc:
        log.warning(
            "resolve_embedding_config_failed fallback_dim=768 reason=%s: %s",
            type(exc).__name__,
            exc,
        )
        return model_name, 768


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


def _has_sparse_vector_config(info: object) -> bool:
    try:
        config = getattr(info, "config", None)
        params = getattr(config, "params", None) if config is not None else None
        sparse_vectors = getattr(params, "sparse_vectors", None) if params is not None else None
        if isinstance(sparse_vectors, dict):
            return _sparse_vector_name() in sparse_vectors
        if sparse_vectors is None:
            return False
        return bool(getattr(sparse_vectors, _sparse_vector_name(), None))
    except Exception:
        return False


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

    model_name, dim = expected or _expected_embedding()

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
                has_sparse = _has_sparse_vector_config(info)
                if not has_sparse:
                    log.warning(
                        "qdrant_collection_sparse_missing collection=%s model=%s dim=%s action=upgrade",
                        collection,
                        model_name,
                        dim,
                    )
                    try:
                        client.update_collection(
                            collection_name=collection,
                            sparse_vectors_config=_build_sparse_vectors_config(models=models),
                        )
                    except Exception as exc:
                        if _is_dev_env():
                            log.warning(
                                "qdrant_collection_sparse_upgrade_failed collection=%s reason=%s: %s action=recreate_dev",
                                collection,
                                type(exc).__name__,
                                exc,
                            )
                            client.recreate_collection(
                                collection_name=collection,
                                vectors_config=_build_vectors_config(models=models, dim=dim),
                                sparse_vectors_config=_build_sparse_vectors_config(models=models),
                                hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100),
                                optimizers_config=models.OptimizersConfigDiff(indexing_threshold=10000),
                            )
                            return "recreated"
                        msg = (
                            f"Qdrant collection '{collection}' has no sparse config and automatic "
                            f"upgrade failed: {type(exc).__name__}: {exc}"
                        )
                        raise RuntimeError(msg) from exc

                    upgraded_info = client.get_collection(collection)
                    if _has_sparse_vector_config(upgraded_info):
                        log.info(
                            "qdrant_collection_sparse_upgraded collection=%s model=%s dim=%s",
                            collection,
                            model_name,
                            dim,
                        )
                        return "upgraded"
                    if _is_dev_env():
                        log.warning(
                            "qdrant_collection_sparse_upgrade_not_visible collection=%s action=recreate_dev",
                            collection,
                        )
                        client.recreate_collection(
                            collection_name=collection,
                            vectors_config=_build_vectors_config(models=models, dim=dim),
                            sparse_vectors_config=_build_sparse_vectors_config(models=models),
                            hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100),
                            optimizers_config=models.OptimizersConfigDiff(indexing_threshold=10000),
                        )
                        return "recreated"
                    msg = f"Qdrant collection '{collection}' sparse config still missing after upgrade."
                    raise RuntimeError(msg)
                log.info("qdrant_collection_ok collection=%s model=%s dim=%s", collection, model_name, dim)
                return "ok"
            except UnexpectedResponse as exc:
                last_exc = exc
                if getattr(exc, "status_code", None) == 404:
                    log.info("qdrant_collection_create collection=%s model=%s dim=%s", collection, model_name, dim)
                    client.create_collection(
                        collection_name=collection,
                        vectors_config=_build_vectors_config(models=models, dim=dim),
                        sparse_vectors_config=_build_sparse_vectors_config(models=models),
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
