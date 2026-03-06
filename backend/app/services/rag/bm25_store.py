"""Simple BM25-backed index for RAG retrieval."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional

from app.services.rag.document import Document
from langchain_community.retrievers import bm25

_DEFAULT_UPLOAD_ROOT = "/app/data/uploads"
_DEFAULT_MODELS_ROOT = "/app/data/models"
_DEFAULT_BM25_SUBDIR = "bm25"
DEFAULT_BM25_TOP_K = int(os.getenv("RAG_BM25_TOP_K", "60"))


def _resolve_upload_root() -> Path:
    raw = (os.getenv("RAG_UPLOAD_DIR") or _DEFAULT_UPLOAD_ROOT).strip()
    candidate = Path(raw)
    if not candidate.is_absolute():
        return Path(_DEFAULT_UPLOAD_ROOT)
    return candidate


def _is_within(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def _resolve_bm25_dir() -> Path:
    upload_root = _resolve_upload_root().resolve()
    models_root = Path(_DEFAULT_MODELS_ROOT).resolve()
    default_dir = (upload_root / "tmp" / _DEFAULT_BM25_SUBDIR).resolve()
    configured = (os.getenv("RAG_BM25_DIR") or "").strip()

    configured_path: Path | None = None
    if configured:
        raw_path = Path(configured)
        if raw_path.is_absolute():
            candidate = raw_path.resolve()
            if _is_within(upload_root, candidate) or _is_within(models_root, candidate):
                configured_path = candidate

    candidates = [p for p in [configured_path, default_dir, (models_root / _DEFAULT_BM25_SUBDIR).resolve()] if p is not None]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except PermissionError:
            continue
    raise PermissionError(
        "No writable BM25 directory under allowed roots. "
        f"Tried: {[str(p) for p in candidates]}"
    )


def _resolve_explicit_bm25_dir(data_dir: str) -> Path:
    upload_root = _resolve_upload_root().resolve()
    models_root = Path(_DEFAULT_MODELS_ROOT).resolve()
    candidate_raw = Path(data_dir)
    if not candidate_raw.is_absolute():
        return _resolve_bm25_dir()
    candidate = candidate_raw.resolve()
    if not (_is_within(upload_root, candidate) or _is_within(models_root, candidate)):
        return _resolve_bm25_dir()
    return candidate


class BM25Repository:
    """Persistent BM25 store with per-collection retrievers."""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = _resolve_explicit_bm25_dir(data_dir) if data_dir else _resolve_bm25_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._documents: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._retrievers: Dict[str, bm25.BM25Retriever] = {}
        self._load_all()

    def _collection_path(self, collection: str) -> Path:
        safe_name = collection.replace("/", "_")
        return self.data_dir / f"{safe_name}.jsonl"

    def _load_all(self) -> None:
        for path in self.data_dir.glob("*.jsonl"):
            collection = path.stem
            self._load_collection_data(collection)

    def _load_collection_data(self, collection: str) -> None:
        path = self._collection_path(collection)
        data: Dict[str, Dict[str, Any]] = {}
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(entry, dict):
                        continue
                    key = entry.get("id")
                    if key:
                        data[key] = entry
        with self._lock:
            self._documents[collection] = data
            self._rebuild(collection)

    def _persist_collection(self, collection: str) -> None:
        path = self._collection_path(collection)
        data = self._documents.get(collection, {})
        with path.open("w", encoding="utf-8") as fh:
            for entry in sorted(data.values(), key=lambda x: x.get("id") or ""):
                json.dump(entry, fh, ensure_ascii=False)
                fh.write("\n")

    def _build_docs(self, entries: Iterable[Dict[str, Any]]) -> List[Document]:
        docs: List[Document] = []
        for entry in entries:
            text = entry.get("text")
            metadata = entry.get("metadata") or {}
            doc_id = entry.get("id")
            if not text:
                continue
            docs.append(Document(page_content=text, metadata=metadata, id=doc_id))
        return docs

    def _rebuild(self, collection: str) -> None:
        data = self._documents.get(collection, {})
        if not data:
            with self._lock:
                self._retrievers.pop(collection, None)
            return
        docs = self._build_docs(data.values())
        retriever = None
        if docs:
            try:
                retriever = bm25.BM25Retriever.from_documents(docs, k=DEFAULT_BM25_TOP_K)
            except Exception:
                retriever = None
        with self._lock:
            if retriever:
                self._retrievers[collection] = retriever
            else:
                self._retrievers.pop(collection, None)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(r"[a-z0-9]+", (text or "").lower())

    def _fallback_keyword_search(
        self,
        *,
        collection: str,
        query: str,
        top_k: int,
        metadata_filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        entries = list((self._documents.get(collection) or {}).values())
        scored: List[tuple[float, Dict[str, Any]]] = []
        for entry in entries:
            text = str(entry.get("text") or "")
            metadata = entry.get("metadata") or {}
            if metadata_filters and not all(metadata.get(k) == v for k, v in metadata_filters.items()):
                continue
            text_tokens = self._tokenize(text)
            if not text_tokens:
                continue
            token_set = set(text_tokens)
            overlap = sum(1 for token in query_tokens if token in token_set)
            if overlap <= 0:
                continue
            score = overlap / max(1, len(query_tokens))
            scored.append((float(score), entry))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        hits: List[Dict[str, Any]] = []
        for score, entry in scored[:top_k]:
            metadata = dict(entry.get("metadata") or {})
            hits.append(
                {
                    "text": str(entry.get("text") or ""),
                    "source": metadata.get("source") or metadata.get("document_title") or "keyword_fallback",
                    "metadata": metadata,
                    "sparse_score": float(score),
                }
            )
        return hits

    def upsert_documents(self, collection: str, documents: Iterable[Document]) -> None:
        entries = self._documents.setdefault(collection, {})
        updated = False
        for idx, doc in enumerate(documents):
            text = (doc.page_content or "").strip()
            if not text:
                continue
            metadata = dict(doc.metadata or {})
            doc_id = self._doc_id_from_metadata(metadata, idx)
            metadata.setdefault("chunk_id", doc_id)
            entries[doc_id] = {
                "id": doc_id,
                "text": text,
                "metadata": metadata,
            }
            updated = True
        if updated:
            self._persist_collection(collection)
            self._rebuild(collection)

    def _doc_id_from_metadata(self, metadata: Dict[str, Any], idx: int) -> str:
        base = metadata.get("chunk_id") or metadata.get("document_id") or metadata.get("source") or "chunk"
        chunk_index = metadata.get("chunk_index")
        if chunk_index is not None:
            return f"{base}#{chunk_index}"
        return f"{base}#{idx}"

    def search(
        self,
        collection: str,
        query: str,
        top_k: int = DEFAULT_BM25_TOP_K,
        metadata_filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        retriever = self._retrievers.get(collection)
        if not retriever:
            return self._fallback_keyword_search(
                collection=collection,
                query=query,
                top_k=top_k,
                metadata_filters=metadata_filters,
            )
        processed_query = retriever.preprocess_func(query)
        vectorizer = retriever.vectorizer
        scores = vectorizer.get_scores(processed_query)
        docs = retriever.docs
        hits: List[Dict[str, Any]] = []
        for score, doc in sorted(
            zip(scores, docs), key=lambda pair: pair[0], reverse=True
        ):
            if len(hits) >= top_k:
                break
            if score <= 0:
                continue
            metadata = dict(doc.metadata or {})
            if metadata_filters and not all(
                metadata.get(k) == v for k, v in metadata_filters.items()
            ):
                continue
            hits.append(
                {
                    "text": doc.page_content or "",
                    "source": metadata.get("source") or metadata.get("document_title") or "bm25",
                    "metadata": metadata,
                    "sparse_score": float(score),
                }
            )
        return hits


bm25_repo = BM25Repository()
