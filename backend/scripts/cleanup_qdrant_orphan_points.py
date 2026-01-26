from __future__ import annotations

import argparse
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from qdrant_client import QdrantClient, models


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete Qdrant points missing metadata.tenant_id (or payload.tenant_id).",
    )
    parser.add_argument(
        "--collection",
        default=os.getenv("QDRANT_COLLECTION", "sealai_knowledge"),
        help="Qdrant collection name (default: env QDRANT_COLLECTION)",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("QDRANT_URL", "http://qdrant:6333").rstrip("/"),
        help="Qdrant URL (default: env QDRANT_URL)",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("QDRANT_API_KEY"),
        help="Qdrant API key (default: env QDRANT_API_KEY)",
    )
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--dry-run", action="store_true", help="Only report matches; do not delete")
    return parser.parse_args()


def _resolve_tenant_id(payload: Dict[str, Any]) -> Optional[str]:
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        tenant_id = metadata.get("tenant_id")
        if tenant_id is not None:
            s = str(tenant_id).strip()
            return s if s else None

    tenant_id = payload.get("tenant_id")
    if tenant_id is None:
        return None
    s = str(tenant_id).strip()
    return s if s else None


def _scroll_points(
    client: QdrantClient,
    collection: str,
    batch_size: int,
) -> Iterable[Tuple[List[Any], Optional[Any]]]:
    """
    Yield (points, next_offset) batches from Qdrant.

    Note: We intentionally avoid depending on qdrant_client.models.Record / PointId
    because these names differ across qdrant-client versions.
    """
    offset: Optional[Any] = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        yield points, offset
        if offset is None:
            break


def main() -> int:
    args = _parse_args()
    client = QdrantClient(url=args.url, api_key=args.api_key)

    total_orphans = 0
    total_deleted = 0

    for points, _offset in _scroll_points(client, args.collection, args.batch_size):
        orphan_ids: List[Any] = []

        for point in points:
            # Qdrant returns Record-like objects with .payload and .id
            payload = getattr(point, "payload", None) or {}
            tenant_id = _resolve_tenant_id(payload)
            if not tenant_id:
                orphan_ids.append(getattr(point, "id", None))

        # filter out any unexpected Nones (defensive)
        orphan_ids = [pid for pid in orphan_ids if pid is not None]

        if not orphan_ids:
            continue

        total_orphans += len(orphan_ids)

        if args.dry_run:
            print(f"[DRY-RUN] Would delete {len(orphan_ids)} orphan points")
            continue

        client.delete(
            collection_name=args.collection,
            points_selector=models.PointIdsList(points=orphan_ids),
        )
        total_deleted += len(orphan_ids)
        print(f"Deleted {len(orphan_ids)} orphan points")

    if args.dry_run:
        print(f"[DRY-RUN] Orphan points found: {total_orphans}")
    else:
        print(f"Deleted {total_deleted} orphan points (found {total_orphans})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
