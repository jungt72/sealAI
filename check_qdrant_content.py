#!/usr/bin/env python3
from __future__ import annotations

from qdrant_client import QdrantClient


QDRANT_URL = "http://localhost:6333"
COLLECTION = "sealai_knowledge_v3"


def _get_payload_value(payload: dict, *keys: str):
    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def main() -> None:
    client = QdrantClient(url=QDRANT_URL)

    info = client.get_collection(COLLECTION)
    vector_config = getattr(getattr(info, "config", None), "params", None)
    vector_config = getattr(vector_config, "vectors", None)
    print(f"Collection: {COLLECTION}")
    print(f"vector_config: {vector_config}")
    print("-" * 80)

    points, _ = client.scroll(
        collection_name=COLLECTION,
        limit=10,
        with_payload=True,
        with_vectors=False,
    )

    if not points:
        print("No points found.")
        return

    for i, point in enumerate(points, start=1):
        payload = point.payload or {}
        tenant_id = _get_payload_value(payload, "tenant_id")
        source = _get_payload_value(payload, "metadata", "source")
        text = _get_payload_value(payload, "text")
        if not isinstance(text, str):
            text = _get_payload_value(payload, "metadata", "text")
        preview = (text or "")[:50].replace("\n", " ")

        print(f"[{i}] id={point.id}")
        print(f"    payload['tenant_id']={tenant_id}")
        print(f"    payload['metadata']['source']={source}")
        print(f"    text[:50]={preview!r}")


if __name__ == "__main__":
    main()
