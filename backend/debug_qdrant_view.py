#!/usr/bin/env python3
"""Direct Qdrant probe for debugging 'zero hit' issues."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx

QDRANT_URL = "http://qdrant:6333"
COLLECTION = "sealai_knowledge_v3"
TIMEOUT_S = 20.0


def _print_json(title: str, payload: Any) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def _safe_get(client: httpx.Client, path: str) -> Dict[str, Any]:
    r = client.get(f"{QDRANT_URL}{path}")
    r.raise_for_status()
    return r.json()


def _safe_post(client: httpx.Client, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    r = client.post(f"{QDRANT_URL}{path}", json=body)
    r.raise_for_status()
    return r.json()


def list_collections(client: httpx.Client) -> List[str]:
    data = _safe_get(client, "/collections")
    cols = [c.get("name") for c in (data.get("result", {}).get("collections") or []) if c.get("name")]
    _print_json("Task 1: All collections", cols)
    return cols


def count_points(client: httpx.Client, collection: str) -> int:
    data = _safe_post(client, f"/collections/{collection}/points/count", {"exact": True})
    count = int((data.get("result") or {}).get("count") or 0)
    _print_json(f"Task 2: Total points in '{collection}'", {"collection": collection, "count": count})
    return count


def first_five_tenants(client: httpx.Client, collection: str) -> List[Dict[str, Any]]:
    body = {
        "limit": 5,
        "with_payload": True,
        "with_vector": False,
    }
    data = _safe_post(client, f"/collections/{collection}/points/scroll", body)
    points = (data.get("result") or {}).get("points") or []

    view: List[Dict[str, Any]] = []
    for p in points:
        payload = p.get("payload") or {}
        metadata = payload.get("metadata") or {}
        tenant_id = payload.get("tenant_id") or metadata.get("tenant_id")
        view.append({"id": p.get("id"), "tenant_id": tenant_id})

    _print_json("Task 3: First 5 points tenant_id (raw scroll, no filter)", view)
    return view


def kyrolon_scroll_filter(client: httpx.Client, collection: str) -> List[Dict[str, Any]]:
    # Raw scroll with payload filter to find likely Kyrolon fields.
    body = {
        "limit": 20,
        "with_payload": True,
        "with_vector": False,
        "filter": {
            "should": [
                {"key": "text", "match": {"text": "Kyrolon"}},
                {"key": "chunk", "match": {"text": "Kyrolon"}},
                {"key": "content", "match": {"text": "Kyrolon"}},
                {"key": "trade_name", "match": {"text": "Kyrolon"}},
                {"key": "metadata.trade_name", "match": {"text": "Kyrolon"}},
                {"key": "metadata.text", "match": {"text": "Kyrolon"}},
                {"key": "metadata.content", "match": {"text": "Kyrolon"}},
                {"key": "text", "match": {"value": "Kyrolon"}},
                {"key": "trade_name", "match": {"value": "Kyrolon"}},
                {"key": "metadata.trade_name", "match": {"value": "Kyrolon"}},
            ]
        },
    }
    data = _safe_post(client, f"/collections/{collection}/points/scroll", body)
    points = (data.get("result") or {}).get("points") or []

    view: List[Dict[str, Any]] = []
    for p in points:
        payload = p.get("payload") or {}
        metadata = payload.get("metadata") or {}
        text = payload.get("text") or payload.get("chunk") or payload.get("content") or ""
        view.append(
            {
                "id": p.get("id"),
                "tenant_id": payload.get("tenant_id") or metadata.get("tenant_id"),
                "source": payload.get("source") or metadata.get("source") or payload.get("filename"),
                "text_preview": str(text)[:220],
            }
        )

    _print_json('Task 4: Raw scroll filter search for "Kyrolon"', {"hits": len(view), "results": view})
    return view


def main() -> None:
    print(f"Using Qdrant URL: {QDRANT_URL}")
    print(f"Target collection: {COLLECTION}")

    with httpx.Client(timeout=TIMEOUT_S) as client:
        cols = list_collections(client)
        if COLLECTION not in cols:
            print(f"\nWARNING: Collection '{COLLECTION}' is not present in Qdrant.")
            return

        count_points(client, COLLECTION)
        first_five_tenants(client, COLLECTION)
        kyrolon_scroll_filter(client, COLLECTION)


if __name__ == "__main__":
    main()
