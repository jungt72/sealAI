# backend/app/services/rag/rag_ingest.py

"""
RAG Ingest: Dokumente (PDF, DOCX, TXT) einlesen, segmentieren, embeddieren und in Qdrant indexieren.
Modular für Produktion, Hot-Reload und Monitoring ausgelegt. Unterstützt beliebige Dokumente.
"""

import os
import sys
from typing import List
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    TextLoader, PDFPlumberLoader, UnstructuredFileLoader, Docx2txtLoader
)
from langchain_community.vectorstores import Qdrant
from langchain_huggingface import HuggingFaceEmbeddings
from app.core.config import settings

# Qdrant/Embedding-Config aus zentraler settings.py
QDRANT_URL = settings.qdrant_url
QDRANT_API_KEY = settings.qdrant_api_key
QDRANT_COLLECTION = settings.qdrant_collection
EMBEDDING_MODEL = settings.embedding_model

SUPPORTED_EXTENSIONS = [".pdf", ".txt", ".docx"]

def load_document(file_path: str):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return PDFPlumberLoader(file_path).load()
    elif ext == ".docx":
        return Docx2txtLoader(file_path).load()
    elif ext == ".txt":
        return TextLoader(file_path).load()
    else:
        # fallback für andere Formate (z.B. .eml, .html, .md, ...)
        return UnstructuredFileLoader(file_path).load()

def ingest_file(file_path: str, chunk_size: int = 700, chunk_overlap: int = 80):
    print(f"Dokument wird geladen: {file_path}")
    docs = load_document(file_path)
    print(f"Text-Splitting...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    split_docs = splitter.split_documents(docs)

    print(f"Embeddings werden erzeugt mit: {EMBEDDING_MODEL}")
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

    print(f"Vektoren werden nach Qdrant ({QDRANT_COLLECTION}) geschrieben...")
    vectorstore = Qdrant.from_documents(
        split_docs,
        embeddings,
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        collection_name=QDRANT_COLLECTION,
    )
    print(f"Fertig. Dokument '{file_path}' wurde erfolgreich indexiert.")

def ingest_directory(directory: str):
    files = [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
    ]
    for file_path in files:
        ingest_file(file_path)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Nutzung: python rag_ingest.py <file_or_directory>")
        sys.exit(1)
    target = sys.argv[1]
    if os.path.isdir(target):
        ingest_directory(target)
    else:
        ingest_file(target)
