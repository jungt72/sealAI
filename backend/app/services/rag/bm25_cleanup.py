"""BM25 JSONL cleanup utilities.

Provides:
  - ``BM25CleanupService``: removes stale document entries from the BM25 JSONL
    store and enforces a per-tenant (and global) file-size limit.
  - ``run_cleanup``: convenience coroutine for use in background tasks / cron.

Usage (cron / background task)::

    from app.services.rag.bm25_cleanup import run_cleanup
    await run_cleanup(tenant_id="acme", document_ids_to_remove=deleted_ids)
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from threading import RLock
from typing import Iterable, Optional

log = logging.getLogger("app.services.rag.bm25_cleanup")

_DEFAULT_BM25_SUBDIR = "bm25"
_DEFAULT_UPLOAD_ROOT = "/app/data/uploads"
_DEFAULT_MODELS_ROOT = "/app/data/models"

# 500 MB per-tenant JSONL size cap (configurable via env).
DEFAULT_MAX_SIZE_MB: int = int(os.getenv("RAG_BM25_MAX_SIZE_MB", "500"))


# ---------------------------------------------------------------------------
# Path helpers (mirrored from bm25_store.py to avoid circular imports)
# ---------------------------------------------------------------------------

def _resolve_bm25_dir() -> Path:
    upload_root_raw = (os.getenv("RAG_UPLOAD_DIR") or _DEFAULT_UPLOAD_ROOT).strip()
    upload_root = Path(upload_root_raw).resolve()
    models_root = Path(_DEFAULT_MODELS_ROOT).resolve()
    default_dir = (upload_root / "tmp" / _DEFAULT_BM25_SUBDIR).resolve()
    configured = (os.getenv("RAG_BM25_DIR") or "").strip()

    def _is_within(base: Path, target: Path) -> bool:
        try:
            target.relative_to(base)
            return True
        except ValueError:
            return False

    if configured:
        raw = Path(configured)
        if raw.is_absolute():
            candidate = raw.resolve()
            if _is_within(upload_root, candidate) or _is_within(models_root, candidate):
                return candidate

    candidates = [default_dir, (models_root / _DEFAULT_BM25_SUBDIR).resolve()]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except PermissionError:
            continue
    return default_dir


def _collection_path(bm25_dir: Path, collection: str) -> Path:
    safe = collection.replace("/", "_")
    return bm25_dir / f"{safe}.jsonl"


# ---------------------------------------------------------------------------
# Core service
# ---------------------------------------------------------------------------

class BM25CleanupService:
    """Removes stale entries from the BM25 JSONL store.

    Thread-safe (uses an :class:`~threading.RLock`).  Designed to run in a
    background task — it never raises; errors are logged and the store is left
    intact.
    """

    def __init__(self, bm25_dir: Optional[Path] = None) -> None:
        self._dir: Path = bm25_dir or _resolve_bm25_dir()
        self._lock = RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def cleanup(
        self,
        collection: str,
        document_ids_to_remove: Iterable[str],
    ) -> dict:
        """Remove all BM25 entries belonging to the given document IDs.

        Parameters
        ----------
        collection:
            Qdrant collection name (== JSONL file stem).
        document_ids_to_remove:
            Iterable of ``document_id`` strings to evict from the index.

        Returns
        -------
        dict
            ``{"removed": int, "remaining": int, "collection": str}``
        """
        remove_set = {str(d) for d in document_ids_to_remove if d}
        if not remove_set:
            return {"removed": 0, "remaining": 0, "collection": collection}

        path = _collection_path(self._dir, collection)
        if not path.exists():
            return {"removed": 0, "remaining": 0, "collection": collection}

        with self._lock:
            try:
                kept, removed = self._filter_jsonl(path, remove_set)
                self._write_jsonl(path, kept)
                log.info(
                    "bm25.cleanup.done",
                    extra={
                        "collection": collection,
                        "removed": removed,
                        "remaining": len(kept),
                    },
                )
                return {"removed": removed, "remaining": len(kept), "collection": collection}
            except Exception as exc:
                log.error(
                    "bm25.cleanup.failed",
                    extra={"collection": collection, "error": f"{type(exc).__name__}: {exc}"},
                )
                return {"removed": 0, "remaining": -1, "collection": collection}

    def enforce_size_limit(
        self,
        collection: str,
        max_size_mb: Optional[int] = None,
    ) -> dict:
        """Truncate the JSONL file if it exceeds *max_size_mb* megabytes.

        Oldest entries (appearing earliest in the file) are dropped first.

        Returns
        -------
        dict
            ``{"truncated": bool, "removed": int, "size_mb_before": float, "collection": str}``
        """
        limit_bytes = (DEFAULT_MAX_SIZE_MB if max_size_mb is None else max_size_mb) * 1024 * 1024
        path = _collection_path(self._dir, collection)
        if not path.exists():
            return {"truncated": False, "removed": 0, "size_mb_before": 0.0, "collection": collection}

        size_bytes = path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)

        if size_bytes <= limit_bytes:
            return {
                "truncated": False,
                "removed": 0,
                "size_mb_before": round(size_mb, 2),
                "collection": collection,
            }

        with self._lock:
            try:
                all_entries = self._load_jsonl(path)
                total = len(all_entries)

                # Drop oldest entries until size estimate is within limit.
                # Estimate: average bytes per entry from current file size.
                avg_entry_bytes = max(size_bytes / max(total, 1), 1)
                entries_to_keep = max(int(limit_bytes / avg_entry_bytes), 0)
                kept = all_entries[-entries_to_keep:] if entries_to_keep > 0 else []
                removed = total - len(kept)

                self._write_jsonl(path, kept)
                log.warning(
                    "bm25.size_limit_enforced",
                    extra={
                        "collection": collection,
                        "size_mb_before": round(size_mb, 2),
                        "max_size_mb": max_size_mb or DEFAULT_MAX_SIZE_MB,
                        "removed": removed,
                        "remaining": len(kept),
                    },
                )
                return {
                    "truncated": True,
                    "removed": removed,
                    "size_mb_before": round(size_mb, 2),
                    "collection": collection,
                }
            except Exception as exc:
                log.error(
                    "bm25.size_limit_failed",
                    extra={"collection": collection, "error": f"{type(exc).__name__}: {exc}"},
                )
                return {
                    "truncated": False,
                    "removed": 0,
                    "size_mb_before": round(size_mb, 2),
                    "collection": collection,
                }

    def list_collections(self) -> list[str]:
        """Return all collection names (JSONL file stems) in the BM25 dir."""
        if not self._dir.exists():
            return []
        return [p.stem for p in self._dir.glob("*.jsonl")]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_jsonl(path: Path) -> list[dict]:
        entries: list[dict] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        entries.append(obj)
                except json.JSONDecodeError:
                    continue
        return entries

    @staticmethod
    def _filter_jsonl(
        path: Path,
        remove_doc_ids: set[str],
    ) -> tuple[list[dict], int]:
        """Return (kept_entries, removed_count)."""
        kept: list[dict] = []
        removed = 0
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                # Check both direct "document_id" and nested metadata.document_id
                doc_id = (
                    obj.get("document_id")
                    or (obj.get("metadata") or {}).get("document_id")
                    or (obj.get("metadata") or {}).get("doc_id")
                )
                if str(doc_id or "") in remove_doc_ids:
                    removed += 1
                else:
                    kept.append(obj)
        return kept, removed

    @staticmethod
    def _write_jsonl(path: Path, entries: list[dict]) -> None:
        tmp_path = path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            for entry in entries:
                json.dump(entry, fh, ensure_ascii=False)
                fh.write("\n")
        tmp_path.replace(path)


# ---------------------------------------------------------------------------
# Convenience async wrapper for background tasks
# ---------------------------------------------------------------------------

async def run_cleanup(
    collection: str = "sealai_knowledge",
    document_ids_to_remove: Optional[Iterable[str]] = None,
    enforce_size: bool = True,
    max_size_mb: Optional[int] = None,
    bm25_dir: Optional[Path] = None,
) -> dict:
    """Async-friendly wrapper — runs sync cleanup in the current thread.

    Suitable for use in FastAPI background tasks or a scheduled cron job.
    """
    import asyncio

    svc = BM25CleanupService(bm25_dir=bm25_dir)
    loop = asyncio.get_event_loop()

    results: dict = {"collection": collection, "timestamp": time.time()}

    if document_ids_to_remove is not None:
        remove_list = list(document_ids_to_remove)
        cleanup_result = await loop.run_in_executor(
            None, svc.cleanup, collection, remove_list
        )
        results["cleanup"] = cleanup_result

    if enforce_size:
        size_result = await loop.run_in_executor(
            None, svc.enforce_size_limit, collection, max_size_mb
        )
        results["size_limit"] = size_result

    return results
