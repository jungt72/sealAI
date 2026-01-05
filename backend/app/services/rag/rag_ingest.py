import mimetypes
import os
import sys
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import (
    PDFPlumberLoader, Docx2txtLoader, TextLoader, UnstructuredFileLoader
)

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "sealai-docs")
EMBEDDING_MODEL = os.getenv(
    "EMB_MODEL_NAME",
    os.getenv("EMBEDDINGS_MODEL", "intfloat/multilingual-e5-base"),
)
SUPPORTED_EXTENSIONS = [".pdf", ".txt", ".docx", ".md"]

def load_document(file_path: str):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return PDFPlumberLoader(file_path).load()
    elif ext == ".docx":
        return Docx2txtLoader(file_path).load()
    elif ext in (".txt", ".md"):
        return TextLoader(file_path).load()
    else:
        return UnstructuredFileLoader(file_path).load()

def ingest_file(
    file_path: str,
    chunk_size: int = 700,
    chunk_overlap: int = 80,
    *,
    tenant_id: str | None = None,
    document_id: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    visibility: str | None = None,
    sha256: str | None = None,
    source: str | None = "upload",
):
    print(f"[INGEST] Lade: {file_path}")
    filename = os.path.basename(file_path)
    content_type, _ = mimetypes.guess_type(file_path)
    try:
        size_bytes = os.path.getsize(file_path)
    except OSError:
        size_bytes = None
    docs = load_document(file_path)
    print(f"[INGEST] Split: size={chunk_size}, overlap={chunk_overlap}")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        separators=["\\n\\n", "\\n", ".", " ", ""],
    )
    split_docs = splitter.split_documents(docs)
    for idx, doc in enumerate(split_docs):
        metadata = dict(getattr(doc, "metadata", {}) or {})
        if tenant_id:
            metadata["tenant_id"] = tenant_id
        if document_id:
            metadata["document_id"] = document_id
        if category:
            metadata["category"] = category
        if tags:
            metadata["tags"] = tags
        if visibility:
            metadata["visibility"] = visibility
        if sha256:
            metadata["sha256"] = sha256
        if source:
            metadata["source"] = source
        if filename and "filename" not in metadata:
            metadata["filename"] = filename
        if content_type and "content_type" not in metadata:
            metadata["content_type"] = content_type
        if size_bytes is not None and "size_bytes" not in metadata:
            metadata["size_bytes"] = size_bytes
        if filename and "source_path" not in metadata:
            metadata["source_path"] = filename
        if "page" not in metadata:
            page_value = metadata.get("page_number")
            if page_value is not None:
                try:
                    metadata["page"] = int(page_value)
                except (TypeError, ValueError):
                    pass
        if "section" not in metadata:
            section_value = metadata.get("section_title") or metadata.get("chunk_title")
            if isinstance(section_value, str) and section_value.strip():
                metadata["section"] = section_value.strip()
        metadata["chunk_index"] = idx
        doc.metadata = metadata

    print(f"[INGEST] HF-Embeddings: {EMBEDDING_MODEL} (normalize=True)")
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )

    print(f"[INGEST] Schreibe nach Qdrant: {QDRANT_COLLECTION}")
    _ = QdrantVectorStore.from_documents(
        split_docs, embeddings,
        url=QDRANT_URL, api_key=QDRANT_API_KEY,
        collection_name=QDRANT_COLLECTION,
    )
    print(f"[INGEST] OK: {file_path}")

def ingest_directory(directory: str):
    files = [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
    ]
    if not files:
        print(f"[INGEST] Keine unterstützten Dateien in {directory}")
    for fp in files:
        ingest_file(fp)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Nutzung: python rag_ingest.py <file_or_directory>")
        sys.exit(1)
    target = sys.argv[1]
    if os.path.isdir(target):
        ingest_directory(target)
    else:
        ingest_file(target)
