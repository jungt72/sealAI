import os, sys
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import (
    PDFPlumberLoader, Docx2txtLoader, TextLoader, UnstructuredFileLoader
)

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "sealai-docs-bge-m3")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
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

def ingest_file(file_path: str, chunk_size: int = 700, chunk_overlap: int = 80):
    print(f"[INGEST] Lade: {file_path}")
    docs = load_document(file_path)
    print(f"[INGEST] Split: size={chunk_size}, overlap={chunk_overlap}")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        separators=["\\n\\n", "\\n", ".", " ", ""],
    )
    split_docs = splitter.split_documents(docs)

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
