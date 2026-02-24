from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Ensure `from app...` imports work when run as:
# python backend/app/diagnostic_qdrant.py
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from qdrant_client import QdrantClient

from app.services.rag.qdrant_bootstrap import _collection_name, _qdrant_client_kwargs
from app.services.rag.rag_orchestrator import hybrid_retrieve


def _candidate_urls() -> List[str]:
    configured = (_qdrant_client_kwargs().get("url") or "").strip().rstrip("/")
    env_url = (os.getenv("QDRANT_URL") or "").strip().rstrip("/")
    defaults = [configured, env_url, "http://localhost:6333", "http://qdrant:6333"]
    urls: List[str] = []
    for url in defaults:
        if url and url not in urls:
            urls.append(url)
    return urls


def _connect() -> tuple[QdrantClient, str]:
    api_key = (os.getenv("QDRANT_API_KEY") or "").strip() or None
    errors: List[str] = []
    for url in _candidate_urls():
        try:
            client = QdrantClient(url=url, api_key=api_key)
            _ = client.get_collections()
            return client, url
        except Exception as exc:
            errors.append(f"{url} -> {type(exc).__name__}: {exc}")
    raise RuntimeError("Unable to connect to Qdrant. Tried: " + " | ".join(errors))


def _safe_get(obj: Any, path: Iterable[str], default: Any = None) -> Any:
    cur = obj
    for key in path:
        if cur is None:
            return default
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            cur = getattr(cur, key, None)
    return cur if cur is not None else default


def _collection_vector_count(info: Any) -> Optional[int]:
    # qdrant collection info can expose different counters depending on server version.
    # Use vectors_count when available; otherwise points_count is a better proxy than
    # indexed_vectors_count (which can stay 0 below indexing_threshold).
    vectors_count = getattr(info, "vectors_count", None)
    if isinstance(vectors_count, int):
        return vectors_count
    points_count = getattr(info, "points_count", None)
    if isinstance(points_count, int):
        return points_count
    return None


def _print_results(title: str, hits: List[Dict[str, Any]]) -> None:
    print(f"\n{title}")
    if not hits:
        print("  No hits")
        return
    for idx, hit in enumerate(hits[:2], start=1):
        text = str(hit.get("text") or "").strip()
        metadata = hit.get("metadata") or {}
        print(f"  Hit #{idx}")
        print(f"    page_content: {text[:1200] if text else ''}")
        print("    metadata:", json.dumps(metadata, ensure_ascii=False, indent=2))


def _keyword_scan_kyrolon(client: QdrantClient, collection: str, *, max_points: int = 4000) -> List[Dict[str, Any]]:
    offset: Any = None
    scanned = 0
    results: List[Dict[str, Any]] = []
    while scanned < max_points:
        points, offset = client.scroll(
            collection_name=collection,
            limit=min(256, max_points - scanned),
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        for point in points:
            scanned += 1
            payload = point.payload or {}
            text = str(payload.get("text") or payload.get("chunk") or payload.get("content") or "")
            if "kyrolon" not in text.lower():
                continue
            results.append({"text": text, "metadata": payload, "source": payload.get("source", "payload")})
            if len(results) >= 2:
                return results
        if offset is None:
            break
    return results


def main() -> int:
    print("=== Qdrant Direct Diagnostic ===")
    collection = _collection_name()
    print(f"Configured collection: {collection}")

    client, connected_url = _connect()
    print(f"Connected Qdrant URL: {connected_url}")

    collections = client.get_collections().collections
    names = [c.name for c in collections]
    print(f"Collections ({len(names)}): {names}")

    collection_for_search = collection
    try:
        info = client.get_collection(collection)
        vector_count = _collection_vector_count(info)
        points_count = getattr(info, "points_count", None)
        indexed_vectors_count = getattr(info, "indexed_vectors_count", None)
        status = getattr(info, "status", None)
        print(f"Main collection status: {status}")
        print(f"Main collection vector_count: {vector_count}")
        print(f"Main collection points_count: {points_count}")
        print(f"Main collection indexed_vectors_count: {indexed_vectors_count}")
    except Exception as exc:
        print(f"Failed to read main collection '{collection}': {type(exc).__name__}: {exc}")
        if names:
            collection_for_search = names[0]
            print(f"Fallback collection for search: {collection_for_search}")

    tenant_id = (os.getenv("DIAGNOSTIC_TENANT_ID") or os.getenv("TENANT_ID") or "").strip() or None
    print(f"Semantic search query: 'Kyrolon' (tenant_id={tenant_id})")

    semantic_hits: List[Dict[str, Any]] = []
    try:
        retrieved, metrics = hybrid_retrieve(
            query="Kyrolon",
            tenant=tenant_id,
            k=2,
            metadata_filters=None,
            use_rerank=False,
            return_metrics=True,
        )
        semantic_hits = list(retrieved or [])
        print("Semantic retrieval metrics:", json.dumps(metrics, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"Semantic retrieval failed: {type(exc).__name__}: {exc}")

    _print_results("Top semantic hits for 'Kyrolon':", semantic_hits)
    if not semantic_hits:
        keyword_hits = _keyword_scan_kyrolon(client, collection_for_search)
        _print_results("Keyword fallback hits for 'Kyrolon':", keyword_hits)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
