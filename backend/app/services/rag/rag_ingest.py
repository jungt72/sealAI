"""
SealAI RAG Ingest (Qdrant)

Used by:
- async job worker (expects: ingest_file(...))
- optional CLI usage (python3 rag_ingest.py <path> --tenant ...)

Goals:
- Stable worker-compatible API: ingest_file(...)
- Payload schema: payload["metadata"].* is SoT (matches metadata.* filters)
- Keep backward-compatible top-level fields (text/source/filename/tenant_id/document_id/visibility)
- Respect env config for collection/vector naming and embedding models
- Deterministic chunk IDs (tenant_id + document_id + chunk_index)
- Safe text loading + bounded chunk sizes
"""

from __future__ import annotations

import argparse
import hashlib
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from qdrant_client import QdrantClient, models

from langchain_community.document_loaders import Docx2txtLoader

from app.services.rag.rag_schema import ChunkMetadata, EngineeringProps, Domain, SourceType

# -----------------------------------------------------------------------------
# Config (ENV-driven)
# -----------------------------------------------------------------------------

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None

# Collection must be consistent across worker + retrieval.
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "sealai-docs")

# Qdrant vector naming:
# - "" (empty) means: single unnamed vector collection (vectors: {"": {...}})
# - "dense" means: named vector collection (vectors: {"dense": {...}})
QDRANT_VECTOR_NAME = os.getenv("QDRANT_VECTOR_NAME", "")

# Embedding models (override via env)
DENSE_MODEL = os.getenv("RAG_DENSE_MODEL", "BAAI/bge-base-en-v1.5")
SPARSE_MODEL = os.getenv("RAG_SPARSE_MODEL", "prithivida/Splade_PP_en_v1")

# Chunking
MAX_CHUNK_CHARS = int(os.getenv("RAG_MAX_CHUNK_CHARS", "6000"))

# Sparse vectors only if the target collection supports it.
ENABLE_SPARSE = os.getenv("RAG_SPARSE_ENABLED", "0").strip().lower() not in ("0", "false", "no")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _coerce_visibility(v: str | None) -> str:
    v = (v or "public").strip().lower()
    return "private" if v == "private" else "public"


def _safe_read_text_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1", errors="replace") as f:
            return f.read()
    except Exception as e:
        print(f"[WARN] Could not read text file {path}: {e}")
        return ""


def _load_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".docx":
            try:
                loader = Docx2txtLoader(file_path)
                docs = loader.load()
                return "\n\n".join([d.page_content for d in docs if getattr(d, "page_content", None)])
            except Exception:
                import docx  # type: ignore
                doc = docx.Document(file_path)
                return "\n".join([p.text for p in doc.paragraphs if p.text])
        return _safe_read_text_file(file_path)
    except Exception as e:
        print(f"[WARN] Could not load {file_path}: {e}")
        return ""


def _semantic_paragraph_chunks(text: str) -> List[str]:
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paras:
        return []

    chunks: List[str] = []
    for p in paras:
        if len(p) <= MAX_CHUNK_CHARS:
            chunks.append(p)
            continue
        start = 0
        while start < len(p):
            chunks.append(p[start : start + MAX_CHUNK_CHARS])
            start += MAX_CHUNK_CHARS
    return chunks


def _parse_domain(domain_str: str | None) -> Domain:
    if not domain_str:
        return Domain.MATERIAL
    s = str(domain_str).strip()
    if not s:
        return Domain.MATERIAL

    # Enum name
    try:
        upper = s.upper()
        if hasattr(Domain, "__members__") and upper in Domain.__members__:
            return Domain.__members__[upper]  # type: ignore[index]
    except Exception:
        pass

    # Enum value
    try:
        return Domain(s)  # type: ignore[arg-type]
    except Exception:
        return Domain.MATERIAL


def _hash_path(path: str) -> str:
    return hashlib.md5(path.encode("utf-8")).hexdigest()[:12]


@dataclass
class IngestStats:
    chunks: int
    elapsed_ms: int
    file_size: Optional[int] = None


# -----------------------------------------------------------------------------
# Pipeline
# -----------------------------------------------------------------------------

class IngestPipeline:
    def __init__(self) -> None:
        self.client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        self.dense_model = DENSE_MODEL
        self.sparse_model = SPARSE_MODEL
        self._dense_embedder = None
        self._sparse_embedder = None

    def _load_embedders(self) -> None:
        if self._dense_embedder and (self._sparse_embedder or not ENABLE_SPARSE):
            return

        from fastembed import TextEmbedding  # type: ignore

        if not self._dense_embedder:
            print(f"[INIT] Loading Dense: {self.dense_model}")
            self._dense_embedder = TextEmbedding(model_name=self.dense_model)

        if ENABLE_SPARSE and not self._sparse_embedder:
            from fastembed import SparseTextEmbedding  # type: ignore
            print(f"[INIT] Loading Sparse: {self.sparse_model}")
            self._sparse_embedder = SparseTextEmbedding(model_name=self.sparse_model)

    def process_document(
        self,
        *args: str,
        file_path: str | None = None,
        tenant_id: str,
        domain: Domain = Domain.MATERIAL,
        document_id: str | None = None,
        visibility: str = "public",
        source_type: SourceType = SourceType.MANUAL,
    ) -> IngestStats:
        if args:
            if len(args) > 1:
                raise TypeError("process_document() takes at most 1 positional argument")
            if file_path is not None:
                raise TypeError("process_document() got multiple values for file_path")
            file_path = args[0]
        if not file_path:
            raise TypeError("process_document() missing required argument: file_path")
        started = time.perf_counter()
        self._load_embedders()

        visibility = _coerce_visibility(visibility)
        filename = os.path.basename(file_path)
        doc_id = document_id or _hash_path(file_path)

        text = _load_text(file_path)
        if not text.strip():
            print(f"[SKIP] Empty: {filename}")
            return IngestStats(chunks=0, elapsed_ms=int((time.perf_counter() - started) * 1000))

        raw_chunks = _semantic_paragraph_chunks(text)
        if not raw_chunks:
            print(f"[SKIP] No chunks: {filename}")
            return IngestStats(chunks=0, elapsed_ms=int((time.perf_counter() - started) * 1000))

        dense_vecs = list(self._dense_embedder.embed(raw_chunks))  # type: ignore[union-attr]

        sparse_vecs = None
        if ENABLE_SPARSE:
            sparse_vecs = list(self._sparse_embedder.embed(raw_chunks))  # type: ignore[union-attr]

        points: List[models.PointStruct] = []
        for idx, chunk_text in enumerate(raw_chunks):
            chunk_hash = ChunkMetadata.compute_hash(chunk_text)
            chunk_id = ChunkMetadata.generate_chunk_id(tenant_id, doc_id, idx)

            meta = ChunkMetadata(
                tenant_id=tenant_id,
                doc_id=doc_id,          # legacy
                document_id=doc_id,     # canonical
                chunk_id=chunk_id,
                chunk_hash=chunk_hash,
                source_uri=file_path,
                source_type=source_type,
                domain=domain,
                title=filename,
                text=chunk_text,
                created_at=time.time(),
                visibility=visibility,
                eng=EngineeringProps(material_family="PTFE" if "PTFE" in chunk_text else None),
            )
            meta_payload = meta.model_dump(mode="json")

            dense = dense_vecs[idx].tolist()

            # Vector shape must match the collection:
            # - unnamed collection => vector is list[float]
            # - named collection => vector is dict {name: list[float]} (plus optional sparse)
            if QDRANT_VECTOR_NAME:
                vector: Any
                if ENABLE_SPARSE and sparse_vecs is not None:
                    sparse = sparse_vecs[idx].as_object()
                    vector = {QDRANT_VECTOR_NAME: dense, "sparse": sparse}
                else:
                    vector = {QDRANT_VECTOR_NAME: dense}
            else:
                # Unnamed single-vector collection (like sealai-docs in your output)
                vector = dense

            points.append(
                models.PointStruct(
                    id=chunk_id,
                    vector=vector,
                    payload={
                        "metadata": meta_payload,
                        "text": chunk_text,
                        "source": str(file_path),
                        "filename": filename,
                        "tenant_id": tenant_id,
                        "document_id": doc_id,
                        "visibility": visibility,
                    },
                )
            )

        self.client.upsert(COLLECTION_NAME, points=points)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        file_size = None
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            pass

        print(
            f"[INGEST] Upserted {len(points)} chunks -> {COLLECTION_NAME} "
            f"(tenant={tenant_id}, doc={doc_id}, vis={visibility}, vector_name={QDRANT_VECTOR_NAME!r}, sparse={ENABLE_SPARSE})"
        )
        return IngestStats(chunks=len(points), elapsed_ms=elapsed_ms, file_size=file_size)


# -----------------------------------------------------------------------------
# Worker-compatible API (IMPORTANT)
# -----------------------------------------------------------------------------

def ingest_file(
    file_path: str,
    *,
    tenant_id: str,
    document_id: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    visibility: str = "public",
    sha256: str | None = None,
    source: str | None = None,
) -> Dict[str, Any]:
    """
    Backward-compatible entrypoint for the async job worker.
    """
    domain = _parse_domain(category)
    pipe = IngestPipeline()
    stats = pipe.process_document(
        file_path=file_path,
        tenant_id=tenant_id,
        domain=domain,
        document_id=document_id,
        visibility=visibility,
        source_type=SourceType.MANUAL,
    )
    return {
        "ok": True,
        "file_path": file_path,
        "tenant_id": tenant_id,
        "document_id": document_id,
        "category": category,
        "domain": getattr(domain, "value", str(domain)),
        "visibility": _coerce_visibility(visibility),
        "tags": tags or [],
        "sha256": sha256,
        "source": source,
        "chunks": stats.chunks,
        "elapsed_ms": stats.elapsed_ms,
        "file_size": stats.file_size,
        "collection": COLLECTION_NAME,
        "dense_model": DENSE_MODEL,
        "sparse_model": SPARSE_MODEL if ENABLE_SPARSE else None,
        "vector_name": QDRANT_VECTOR_NAME,
        "sparse_enabled": ENABLE_SPARSE,
    }


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def _iter_files(path: str) -> Iterable[str]:
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for f in files:
                if f.lower().endswith((".docx", ".txt", ".md", ".log", ".csv")):
                    yield os.path.join(root, f)
    else:
        yield path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SealAI RAG ingest into Qdrant.")
    parser.add_argument("path", help="File or Directory")
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--domain", default="material")
    parser.add_argument("--visibility", default="public", choices=["public", "private"])
    args = parser.parse_args()

    pipe = IngestPipeline()
    domain = _parse_domain(args.domain)
    visibility = _coerce_visibility(args.visibility)

    for p in _iter_files(args.path):
        pipe.process_document(
            file_path=p,
            tenant_id=args.tenant,
            domain=domain,
            document_id=None,
            visibility=visibility,
            source_type=SourceType.MANUAL,
        )
