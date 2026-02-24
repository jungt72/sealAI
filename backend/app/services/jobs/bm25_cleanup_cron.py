"""BM25 cleanup cron job.

Run periodically (e.g. daily via Docker cron or Kubernetes CronJob) to:
  1. Remove BM25 entries for documents that have been deleted from Postgres.
  2. Enforce the per-collection JSONL size limit (default: 500 MB).

Usage::

    # From project root (inside backend container):
    python -m app.services.jobs.bm25_cleanup_cron

Environment variables:
  RAG_BM25_MAX_SIZE_MB   Max JSONL size in MB per collection (default: 500)
  DATABASE_URL           Postgres URL for fetching active document IDs
  QDRANT_COLLECTION      Collection name (default: sealai_knowledge)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

log = logging.getLogger("bm25_cleanup_cron")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


async def _fetch_active_document_ids(database_url: str) -> set[str]:
    """Return all document_ids that still exist (non-deleted) in Postgres."""
    try:
        import asyncpg  # type: ignore

        dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch("SELECT document_id FROM rag_documents")
            return {str(r["document_id"]) for r in rows}
        finally:
            await conn.close()
    except Exception as exc:
        log.warning("Could not fetch active document IDs from DB: %s", exc)
        return set()


async def main() -> None:
    t0 = time.perf_counter()

    from app.services.rag.bm25_cleanup import BM25CleanupService, DEFAULT_MAX_SIZE_MB

    collection = os.getenv("QDRANT_COLLECTION", "sealai_knowledge")
    max_size_mb = int(os.getenv("RAG_BM25_MAX_SIZE_MB", str(DEFAULT_MAX_SIZE_MB)))

    svc = BM25CleanupService()
    collections = svc.list_collections()
    if not collections:
        log.info("No BM25 JSONL files found — nothing to clean.")
        return

    log.info("Found %d BM25 collection(s): %s", len(collections), collections)

    # Fetch active document IDs from Postgres (to find orphans).
    database_url = os.getenv("DATABASE_URL", "")
    active_ids: set[str] = set()
    if database_url:
        active_ids = await _fetch_active_document_ids(database_url)
        log.info("Active document IDs in Postgres: %d", len(active_ids))
    else:
        log.warning("DATABASE_URL not set — skipping orphan removal, only enforcing size limit.")

    for coll in collections:
        log.info("Processing collection: %s", coll)

        # Identify orphaned IDs (in BM25 but not in Postgres).
        if active_ids:
            all_entries = svc._load_jsonl(svc._dir / f"{coll}.jsonl")
            bm25_doc_ids: set[str] = set()
            for entry in all_entries:
                doc_id = (
                    entry.get("document_id")
                    or (entry.get("metadata") or {}).get("document_id")
                    or (entry.get("metadata") or {}).get("doc_id")
                )
                if doc_id:
                    bm25_doc_ids.add(str(doc_id))

            orphaned = bm25_doc_ids - active_ids
            if orphaned:
                log.info("Removing %d orphaned document(s) from BM25 '%s'", len(orphaned), coll)
                result = svc.cleanup(coll, orphaned)
                log.info("Cleanup result: %s", result)
            else:
                log.info("No orphans found in '%s'", coll)

        # Enforce size limit.
        size_result = svc.enforce_size_limit(coll, max_size_mb)
        if size_result.get("truncated"):
            log.warning(
                "Size limit enforced for '%s': removed %d entries (was %.1f MB)",
                coll,
                size_result.get("removed", 0),
                size_result.get("size_mb_before", 0.0),
            )

    elapsed = time.perf_counter() - t0
    log.info("BM25 cleanup finished in %.2fs", elapsed)


if __name__ == "__main__":
    asyncio.run(main())
