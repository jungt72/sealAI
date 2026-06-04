#!/usr/bin/env python3
"""C5 (P2-1 TEIL A) — backfill the cross-cutting-vs-pack marker on the live corpus.

Sets `metadata.pack_affinity` on every chunk of a Qdrant collection using the same
deterministic classifier the ingest path uses (`classify_pack_affinity`), so ingest
and backfill agree. "rwdr" = radial-shaft-seal pack-specific; None = cross-cutting.

Dry-run by default (prints the exact accounting); pass --apply to persist. Idempotent:
a point whose marker already equals the desired value is skipped, so a second run
writes nothing. The marker is retrieval-inert (no filter consumes it), so the backfill
causes no result-diff on today's corpus.

Usage:
    python scripts/backfill_pack_affinity_qdrant.py --collection sealai_knowledge
    python scripts/backfill_pack_affinity_qdrant.py --collection sealai_knowledge --apply
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.services.rag.rag_schema import classify_pack_affinity


def classify_point_payload(payload: dict[str, Any]) -> str | None:
    """Desired pack_affinity for a stored point payload (metadata sub-key + top text)."""
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    tags = metadata.get("tags")
    return classify_pack_affinity(
        domain=metadata.get("domain"),
        entity=metadata.get("entity"),
        route_key=metadata.get("route_key"),
        category=metadata.get("category"),
        tags=tags if isinstance(tags, list) else None,
        text=payload.get("text") or metadata.get("text"),
    )


@dataclass
class BackfillPlan:
    total: int = 0
    already_correct: int = 0
    to_set_rwdr: int = 0
    to_set_cross_cutting: int = 0
    writes: list[tuple[Any, dict[str, Any]]] = field(default_factory=list)

    @property
    def write_count(self) -> int:
        return len(self.writes)

    @property
    def conserved(self) -> bool:
        # Every point is accounted for exactly once.
        return (
            self.total
            == self.already_correct + self.to_set_rwdr + self.to_set_cross_cutting
        )

    def summary(self, *, apply: bool) -> str:
        return (
            f"total={self.total} already_correct={self.already_correct} "
            f"to_set_rwdr={self.to_set_rwdr} "
            f"to_set_cross_cutting={self.to_set_cross_cutting} "
            f"writes={self.write_count} apply={apply} conserved={self.conserved}"
        )


def plan_backfill(points: Iterable[Any]) -> BackfillPlan:
    """Pure accounting over scrolled points — no I/O. Each point gets exactly one bucket."""
    plan = BackfillPlan()
    for point in points:
        plan.total += 1
        payload = dict(getattr(point, "payload", None) or {})
        metadata = dict(payload.get("metadata") or {})
        desired = classify_point_payload(payload)
        if "pack_affinity" in metadata and metadata["pack_affinity"] == desired:
            plan.already_correct += 1
            continue
        metadata["pack_affinity"] = desired
        payload["metadata"] = metadata
        plan.writes.append((point.id, payload))
        if desired == "rwdr":
            plan.to_set_rwdr += 1
        else:
            plan.to_set_cross_cutting += 1
    return plan


def _scroll_all(client: Any, collection: str, limit: int = 256) -> Iterable[Any]:
    offset: Any = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        yield from points
        if offset is None:
            break


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill pack_affinity (cross-cutting vs RWDR-pack) in Qdrant."
    )
    # The live collection is driven by QDRANT_COLLECTION (sealai_knowledge_v3 in
    # prod); the literal fallback matches that so a host-run without env hits the
    # real corpus, not an empty/legacy name.
    parser.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", "sealai_knowledge_v3"))
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--qdrant-api-key", default=os.getenv("QDRANT_API_KEY") or None)
    parser.add_argument("--apply", action="store_true", help="Persist updates to Qdrant.")
    args = parser.parse_args()

    from qdrant_client import QdrantClient

    client = QdrantClient(url=args.qdrant_url, api_key=args.qdrant_api_key)
    plan = plan_backfill(_scroll_all(client, args.collection))

    print(plan.summary(apply=args.apply))
    if not plan.conserved:
        print("ERROR: accounting not conserved — refusing to apply.")
        return 2

    if args.apply:
        for point_id, payload in plan.writes:
            client.overwrite_payload(
                collection_name=args.collection,
                points=[point_id],
                payload=payload,
            )
        # Post-check: every point now carries a defined pack_affinity.
        missing = sum(
            1
            for point in _scroll_all(client, args.collection)
            if "pack_affinity" not in (dict((point.payload or {}).get("metadata") or {}))
        )
        print(f"applied_writes={plan.write_count} post_check_missing_marker={missing}")
    else:
        print(">>> DRY-RUN (no writes). Re-run with --apply to persist.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
