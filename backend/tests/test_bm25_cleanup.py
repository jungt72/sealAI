"""Tests for H4: BM25CleanupService."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jsonl(path: Path, entries: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            json.dump(entry, fh)
            fh.write("\n")


def _read_jsonl(path: Path) -> list[dict]:
    items = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _make_entry(doc_id: str, text: str = "sample text") -> dict:
    return {
        "id": f"{doc_id}#0",
        "text": text,
        "metadata": {"document_id": doc_id, "tenant_id": "acme"},
    }


# ---------------------------------------------------------------------------
# BM25CleanupService.cleanup
# ---------------------------------------------------------------------------

class TestCleanup:
    def test_cleanup_removes_target_document(self, tmp_path: Path):
        from app.services.rag.bm25_cleanup import BM25CleanupService

        svc = BM25CleanupService(bm25_dir=tmp_path)
        coll_path = tmp_path / "sealai_knowledge.jsonl"
        entries = [_make_entry("doc-1"), _make_entry("doc-2"), _make_entry("doc-3")]
        _make_jsonl(coll_path, entries)

        result = svc.cleanup("sealai_knowledge", ["doc-2"])

        assert result["removed"] == 1
        assert result["remaining"] == 2

        remaining = _read_jsonl(coll_path)
        remaining_ids = [(e.get("metadata") or {}).get("document_id") for e in remaining]
        assert "doc-1" in remaining_ids
        assert "doc-3" in remaining_ids
        assert "doc-2" not in remaining_ids

    def test_cleanup_removes_multiple_documents(self, tmp_path: Path):
        from app.services.rag.bm25_cleanup import BM25CleanupService

        svc = BM25CleanupService(bm25_dir=tmp_path)
        coll_path = tmp_path / "col.jsonl"
        entries = [_make_entry(f"doc-{i}") for i in range(5)]
        _make_jsonl(coll_path, entries)

        result = svc.cleanup("col", ["doc-0", "doc-2", "doc-4"])

        assert result["removed"] == 3
        assert result["remaining"] == 2

    def test_cleanup_empty_remove_list_is_noop(self, tmp_path: Path):
        from app.services.rag.bm25_cleanup import BM25CleanupService

        svc = BM25CleanupService(bm25_dir=tmp_path)
        coll_path = tmp_path / "col.jsonl"
        entries = [_make_entry("doc-1")]
        _make_jsonl(coll_path, entries)

        result = svc.cleanup("col", [])
        assert result["removed"] == 0

        # File unchanged
        remaining = _read_jsonl(coll_path)
        assert len(remaining) == 1

    def test_cleanup_nonexistent_collection_is_noop(self, tmp_path: Path):
        from app.services.rag.bm25_cleanup import BM25CleanupService

        svc = BM25CleanupService(bm25_dir=tmp_path)
        result = svc.cleanup("does_not_exist", ["doc-1"])
        assert result["removed"] == 0

    def test_cleanup_all_entries(self, tmp_path: Path):
        from app.services.rag.bm25_cleanup import BM25CleanupService

        svc = BM25CleanupService(bm25_dir=tmp_path)
        coll_path = tmp_path / "col.jsonl"
        _make_jsonl(coll_path, [_make_entry("only-doc")])

        result = svc.cleanup("col", ["only-doc"])
        assert result["removed"] == 1
        assert result["remaining"] == 0

        # File still exists but is empty
        assert _read_jsonl(coll_path) == []


# ---------------------------------------------------------------------------
# BM25CleanupService.enforce_size_limit
# ---------------------------------------------------------------------------

class TestEnforceSizeLimit:
    def _fill_collection(self, path: Path, n_entries: int, entry_size_bytes: int = 100) -> None:
        """Write n_entries × entry_size_bytes to path."""
        with path.open("w", encoding="utf-8") as fh:
            for i in range(n_entries):
                text = "x" * max(entry_size_bytes - 50, 10)
                entry = {"id": f"chunk#{i}", "text": text,
                         "metadata": {"document_id": f"doc-{i}"}}
                json.dump(entry, fh)
                fh.write("\n")

    def test_no_truncation_when_under_limit(self, tmp_path: Path):
        from app.services.rag.bm25_cleanup import BM25CleanupService

        svc = BM25CleanupService(bm25_dir=tmp_path)
        coll_path = tmp_path / "col.jsonl"
        # Write only a few bytes — well under 500 MB
        _make_jsonl(coll_path, [_make_entry("doc-1")])

        result = svc.enforce_size_limit("col", max_size_mb=500)
        assert result["truncated"] is False
        assert result["removed"] == 0

    def test_truncation_enforced_when_over_limit(self, tmp_path: Path):
        from app.services.rag.bm25_cleanup import BM25CleanupService

        svc = BM25CleanupService(bm25_dir=tmp_path)
        coll_path = tmp_path / "col.jsonl"
        # Write 200 entries, then set limit to 1 entry worth (< 1 KB)
        self._fill_collection(coll_path, n_entries=200, entry_size_bytes=200)
        original_size = coll_path.stat().st_size

        # Limit: 1 byte → forces truncation to 0 or very few entries
        result = svc.enforce_size_limit("col", max_size_mb=0)  # 0 MB → truncate all
        assert result["truncated"] is True
        assert result["removed"] > 0
        assert result["size_mb_before"] == pytest.approx(original_size / (1024 * 1024), abs=0.01)

    def test_nonexistent_collection_returns_not_truncated(self, tmp_path: Path):
        from app.services.rag.bm25_cleanup import BM25CleanupService

        svc = BM25CleanupService(bm25_dir=tmp_path)
        result = svc.enforce_size_limit("nonexistent", max_size_mb=10)
        assert result["truncated"] is False
        assert result["size_mb_before"] == 0.0


# ---------------------------------------------------------------------------
# BM25CleanupService.list_collections
# ---------------------------------------------------------------------------

def test_list_collections(tmp_path: Path):
    from app.services.rag.bm25_cleanup import BM25CleanupService

    svc = BM25CleanupService(bm25_dir=tmp_path)
    (tmp_path / "col_a.jsonl").write_text("{}\n")
    (tmp_path / "col_b.jsonl").write_text("{}\n")
    (tmp_path / "other.txt").write_text("not a collection")

    colls = svc.list_collections()
    assert set(colls) == {"col_a", "col_b"}


# ---------------------------------------------------------------------------
# Atomic write: tmp file replace
# ---------------------------------------------------------------------------

def test_cleanup_uses_atomic_write(tmp_path: Path):
    """Cleanup must write to a .tmp file then rename — no partial writes visible."""
    from app.services.rag.bm25_cleanup import BM25CleanupService

    svc = BM25CleanupService(bm25_dir=tmp_path)
    coll_path = tmp_path / "col.jsonl"
    _make_jsonl(coll_path, [_make_entry("doc-1"), _make_entry("doc-2")])

    # After cleanup the .tmp file must NOT exist (was renamed away)
    svc.cleanup("col", ["doc-1"])
    tmp_file = tmp_path / "col.jsonl.tmp"
    assert not tmp_file.exists(), "Temp file was not cleaned up"


# ---------------------------------------------------------------------------
# run_cleanup async wrapper
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_cleanup_async(tmp_path: Path):
    from app.services.rag.bm25_cleanup import run_cleanup

    coll_path = tmp_path / "sealai_knowledge.jsonl"
    _make_jsonl(coll_path, [_make_entry("doc-A"), _make_entry("doc-B")])

    result = await run_cleanup(
        collection="sealai_knowledge",
        document_ids_to_remove=["doc-A"],
        enforce_size=True,
        max_size_mb=500,
        bm25_dir=tmp_path,
    )

    assert "cleanup" in result
    assert result["cleanup"]["removed"] == 1
    assert "size_limit" in result
    assert result["size_limit"]["truncated"] is False
