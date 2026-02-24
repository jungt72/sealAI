from __future__ import annotations

import importlib
from pathlib import Path


def test_bm25_store_ignores_relative_dir_and_uses_upload_tmp(monkeypatch) -> None:
    upload_root = Path("/tmp/sealai-test-uploads").resolve()
    monkeypatch.setenv("RAG_UPLOAD_DIR", str(upload_root))
    monkeypatch.setenv("RAG_BM25_DIR", "backend/data/rag/bm25")

    import app.services.rag.bm25_store as bm25_store

    module = importlib.reload(bm25_store)
    repo = module.BM25Repository()

    resolved = repo.data_dir.resolve()
    expected_root = (upload_root / "tmp").resolve()

    assert str(resolved).startswith(str(expected_root))
    assert "backend/data/rag/bm25" not in str(resolved)
