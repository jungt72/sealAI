
import os
import sys
import time
import hashlib
import uuid
import argparse
from typing import List
from qdrant_client import QdrantClient, models
from qdrant_client.http.models import VectorParams, SparseVectorParams

# Valid Import for loaders
from langchain_community.document_loaders import Docx2txtLoader

# Strict Schema
from app.services.rag.rag_schema import ChunkMetadata, EngineeringProps, Domain, SourceType

# Config
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
COLLECTION_NAME = "sealai_knowledge_v2" 

class IngestPipeline:
    def __init__(self):
        self.client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        self.dense_model = "intfloat/multilingual-e5-large"
        self.sparse_model = "prithivida/Splade_PP_en_v1"
        self._dense_embedder = None
        self._sparse_embedder = None

    def _load_embedders(self):
        if not self._dense_embedder:
            from fastembed import TextEmbedding, SparseTextEmbedding
            print(f"[INIT] Loading Dense: {self.dense_model}")
            self._dense_embedder = TextEmbedding(model_name=self.dense_model)
            print(f"[INIT] Loading Sparse: {self.sparse_model}")
            self._sparse_embedder = SparseTextEmbedding(model_name=self.sparse_model)

    def _load_text(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".docx":
                try:
                    loader = Docx2txtLoader(file_path)
                    docs = loader.load()
                    return "\n\n".join([d.page_content for d in docs])
                except Exception:
                    import docx
                    doc = docx.Document(file_path)
                    return "\n".join([p.text for p in doc.paragraphs])
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception as e:
            print(f"[WARN] Could not load {file_path}: {e}")
            return ""

    def process_document(self, file_path: str, tenant_id: str, domain: Domain = Domain.MATERIAL):
        self._load_embedders()
        
        doc_id = hashlib.md5(file_path.encode()).hexdigest()[:12]
        filename = os.path.basename(file_path)
        
        text = self._load_text(file_path)
        if not text.strip():
            print(f"[SKIP] Empty: {filename}")
            return

        # Simple semantic chunking (splitting by empty lines)
        raw_chunks = [p.strip() for p in text.split("\n\n") if p.strip()]
        
        # Batch Embed
        dense_vecs = list(self._dense_embedder.embed(raw_chunks))
        sparse_vecs = list(self._sparse_embedder.embed(raw_chunks))
        
        points = []
        for idx, chunk_text in enumerate(raw_chunks):
            # Deterministic ID
            chunk_hash = ChunkMetadata.compute_hash(chunk_text)
            chunk_id = ChunkMetadata.generate_chunk_id(tenant_id, doc_id, idx)
            
            # Metadata
            meta = ChunkMetadata(
                tenant_id=tenant_id,
                doc_id=doc_id,
                chunk_id=chunk_id,
                chunk_hash=chunk_hash,
                source_uri=file_path,
                source_type=SourceType.MANUAL,
                domain=domain,
                title=filename,
                text=chunk_text,
                created_at=time.time(),
                eng=EngineeringProps(material_family="PTFE" if "PTFE" in chunk_text else None)
            )
            
            points.append(models.PointStruct(
                id=chunk_id,
                vector={
                    "dense": dense_vecs[idx].tolist(),
                    "sparse": sparse_vecs[idx].as_object(),
                },
                payload=meta.model_dump(mode='json')
            ))
            
        self.client.upsert(COLLECTION_NAME, points=points)
        print(f"[INGEST] Upserted {len(points)} chunks -> {COLLECTION_NAME}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="File or Directory")
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--domain", default="material")
    args = parser.parse_args()

    pipe = IngestPipeline()
    
    target = args.path
    if os.path.isdir(target):
         for root, _, files in os.walk(target):
            for f in files:
                if f.lower().endswith(('.pdf', '.docx', '.txt', '.md')):
                    pipe.process_document(os.path.join(root, f), args.tenant, args.domain)
    else:
        pipe.process_document(target, args.tenant, args.domain)
