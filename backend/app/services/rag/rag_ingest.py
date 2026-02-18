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
import mimetypes
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from qdrant_client import QdrantClient, models

from langchain_community.document_loaders import Docx2txtLoader

try:
    from langchain_qdrant import QdrantVectorStore
except ImportError:
    QdrantVectorStore = None

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    HuggingFaceEmbeddings = None


def get_embedder() -> Any:
    raise NotImplementedError("Use IngestPipeline instead of the legacy helper.")

from app.services.rag.rag_schema import ChunkMetadata, EngineeringProps, Domain, MaterialFamily, SourceType

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
RAG_SHARED_TENANT_ENABLED = os.getenv("RAG_SHARED_TENANT_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
RAG_SHARED_TENANT_ID = (os.getenv("RAG_SHARED_TENANT_ID") or "").strip()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _ensure_tenant_allowed(tenant_id: str) -> None:
    if not tenant_id or not str(tenant_id).strip():
        raise ValueError("tenant_id required for ingest")
    if tenant_id == "sealai":
        shared_allowed = bool(RAG_SHARED_TENANT_ENABLED and RAG_SHARED_TENANT_ID == "sealai")
        if not shared_allowed:
            raise ValueError(
                "tenant_id 'sealai' is reserved; set RAG_SHARED_TENANT_ENABLED=1 and "
                "RAG_SHARED_TENANT_ID=sealai to allow shared ingestion"
            )


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


def _load_pdf_pages(file_path: str) -> List[tuple[int, str]]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"pypdf_unavailable: {type(exc).__name__}: {exc}") from exc

    try:
        with open(file_path, "rb") as f:
            reader = PdfReader(f)
            if reader.is_encrypted:
                try:
                    decrypted = reader.decrypt("")  # type: ignore[call-arg]
                except Exception:
                    decrypted = 0
                if not decrypted:
                    raise ValueError(f"encrypted_pdf_not_supported: {file_path}")

            pages: List[tuple[int, str]] = []
            has_text = False
            for idx, page in enumerate(reader.pages):
                try:
                    page_text = page.extract_text() or ""
                except Exception as exc:
                    print(f"[WARN] Could not extract PDF page {idx + 1} from {file_path}: {exc}")
                    page_text = ""
                if page_text.strip():
                    has_text = True
                pages.append((idx + 1, page_text))

            if not has_text:
                print(f"[WARN] No text extracted from PDF {file_path}")
                return []
            return pages
    except ValueError:
        raise
    except Exception as exc:
        print(f"[WARN] Could not load PDF {file_path}: {exc}")
        return []


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


def _load_pages(file_path: str) -> List[tuple[Optional[int], str]]:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return _load_pdf_pages(file_path)
    return [(None, _load_text(file_path))]


def load_document(file_path: str) -> List[Any]:
    from langchain_core.documents import Document

    docs: List[Any] = []
    for page_number, text in _load_pages(file_path):
        docs.append(
            Document(
                page_content=text,
                metadata={
                    "page": page_number,
                },
            )
        )
    return docs


def _chunk_pages(pages: List[tuple[Optional[int], str]]) -> List[tuple[str, Optional[int]]]:
    chunks: List[tuple[str, Optional[int]]] = []
    for page_number, text in pages:
        if not text.strip():
            continue
        for chunk in _semantic_paragraph_chunks(text):
            if chunk:
                chunks.append((chunk, page_number))
    return chunks


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


DOMAIN_MAPPING = {
    "Norm": "standard",
    "Product": "product",
    "Standard": "standard",
    "Technical": "material",
    "Datasheet": "material",
}

def _parse_domain(domain_str: str | None) -> Domain:
    if not domain_str:
        return Domain.MATERIAL
    s = str(domain_str).strip()
    if not s:
        return Domain.MATERIAL

    # Apply mapping
    mapped = DOMAIN_MAPPING.get(s)
    if mapped:
        s = mapped

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


def _parse_facets_from_tags(tags: Iterable[str] | None) -> dict[str, object]:
    facets = {
        "entity": None,
        "aspects": [],
        "language": None,
        "source_version": None,
        "effective_date": None,
    }
    seen_aspects: set[str] = set()
    for raw in tags or []:
        if not raw or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue
        if key in {"entity", "material"}:
            facets["entity"] = value
        elif key in {"aspect", "aspects"}:
            normalized = value.lower()
            if normalized not in seen_aspects:
                seen_aspects.add(normalized)
                facets["aspects"].append(value)
        elif key in {"lang", "language"}:
            facets["language"] = value
        elif key in {"version", "source_version"}:
            facets["source_version"] = value
        elif key in {"effective", "effective_date"}:
            facets["effective_date"] = value
    return facets


def _guess_entity_from_filename(filename: str) -> Optional[str]:
    name = os.path.splitext(filename or "")[0].upper()
    for member in MaterialFamily:
        if member.value.upper() in name:
            return member.value
    return None


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
        tags: list[str] | None = None,
    ) -> IngestStats:
        if args:
            if len(args) > 1:
                raise TypeError("process_document() takes at most 1 positional argument")
            if file_path is not None:
                raise TypeError("process_document() got multiple values for file_path")
            file_path = args[0]
        if not file_path:
            raise TypeError("process_document() missing required argument: file_path")
        _ensure_tenant_allowed(tenant_id)
        started = time.perf_counter()
        self._load_embedders()

        visibility = _coerce_visibility(visibility)
        filename = os.path.basename(file_path)
        doc_id = document_id or _hash_path(file_path)
        facets = _parse_facets_from_tags(tags)
        entity = facets.get("entity") or _guess_entity_from_filename(filename)
        aspects = facets.get("aspects") or []
        language = facets.get("language")
        source_version = facets.get("source_version")
        effective_date = facets.get("effective_date")

        pages = _load_pages(file_path)
        if not pages or not any(text.strip() for _, text in pages):
            print(f"[SKIP] Empty: {filename}")
            return IngestStats(chunks=0, elapsed_ms=int((time.perf_counter() - started) * 1000))

        raw_chunks = _chunk_pages(pages)
        if not raw_chunks:
            print(f"[SKIP] No chunks: {filename}")
            return IngestStats(chunks=0, elapsed_ms=int((time.perf_counter() - started) * 1000))

        dense_vecs = list(self._dense_embedder.embed([c[0] for c in raw_chunks]))  # type: ignore[union-attr]

        sparse_vecs = None
        if ENABLE_SPARSE:
            sparse_vecs = list(self._sparse_embedder.embed([c[0] for c in raw_chunks]))  # type: ignore[union-attr]

        points: List[models.PointStruct] = []
        seen_hashes: set[str] = set()
        for idx, (chunk_text, page_number) in enumerate(raw_chunks):
            chunk_hash = ChunkMetadata.compute_hash(chunk_text)
            if chunk_hash in seen_hashes:
                continue
            seen_hashes.add(chunk_hash)
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
                chunk_index=idx,
                entity=entity,
                aspect=aspects,
                language=language,
                source_version=source_version,
                effective_date=effective_date,
                title=filename,
                page_number=page_number,
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
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Backward-compatible entrypoint for the async job worker.
    """
    _ensure_tenant_allowed(tenant_id)
    domain = _parse_domain(category)
    canonical_doc_id = document_id or sha256 or _hash_path(file_path)

    # Backward-compatible ingest path used by contract tests and legacy workers.
    if QdrantVectorStore is not None and HuggingFaceEmbeddings is not None:
        docs = load_document(file_path)
        filename = os.path.basename(file_path)
        source_path = filename
        size_bytes = None
        try:
            size_bytes = os.path.getsize(file_path)
        except OSError:
            pass
        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        for doc in docs:
            meta = dict(getattr(doc, "metadata", {}) or {})
            section = meta.get("section") or meta.get("section_title")
            meta.update(
                {
                    "filename": filename,
                    "content_type": content_type,
                    "size_bytes": size_bytes,
                    "source_path": source_path,
                    "tenant_id": tenant_id,
                    "document_id": canonical_doc_id,
                    "visibility": _coerce_visibility(visibility),
                }
            )
            if section:
                meta["section"] = section
            doc.metadata = meta

        embeddings = HuggingFaceEmbeddings(model_name=DENSE_MODEL)
        QdrantVectorStore.from_documents(
            docs,
            embeddings,
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
            collection_name=COLLECTION_NAME,
        )
        return {
            "ok": True,
            "file_path": file_path,
            "tenant_id": tenant_id,
            "document_id": canonical_doc_id,
            "category": category,
            "domain": getattr(domain, "value", str(domain)),
            "visibility": _coerce_visibility(visibility),
            "tags": tags or [],
            "sha256": sha256,
            "source": source,
            "chunks": len(docs),
            "elapsed_ms": 0,
            "file_size": size_bytes,
            "collection": COLLECTION_NAME,
            "dense_model": DENSE_MODEL,
            "sparse_model": SPARSE_MODEL if ENABLE_SPARSE else None,
            "vector_name": QDRANT_VECTOR_NAME,
            "sparse_enabled": ENABLE_SPARSE,
        }

    pipe = IngestPipeline()
    stats = pipe.process_document(
        file_path=file_path,
        tenant_id=tenant_id,
        domain=domain,
        document_id=canonical_doc_id,
        visibility=visibility,
        source_type=SourceType.MANUAL,
        tags=tags,
    )
    return {
        "ok": True,
        "file_path": file_path,
        "tenant_id": tenant_id,
        "document_id": canonical_doc_id,
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
                if f.lower().endswith((".docx", ".pdf", ".txt", ".md", ".log", ".csv")):
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
