# RAG Env Alignment (Ingest vs Retrieval)

## Required env vars
- `QDRANT_URL` (both ingest + retrieval)
- `QDRANT_COLLECTION` (shared collection name)
- `EMB_MODEL_NAME` or `EMBEDDINGS_MODEL` (shared embedding model)

## Defaults
- Retrieval defaults: `QDRANT_COLLECTION=sealai-docs`, `EMB_MODEL_NAME=intfloat/multilingual-e5-base` (`backend/app/services/rag/rag_orchestrator.py:21-27`).
- Ingest defaults are aligned to the same values (`backend/app/services/rag/rag_ingest.py:11-16`).

## Safe migration steps
1) Decide target `QDRANT_COLLECTION` and embedding model.
2) Set `QDRANT_COLLECTION` and `EMB_MODEL_NAME` (or `EMBEDDINGS_MODEL`) in the ingest environment.
3) Re-run ingest to populate the target collection with the chosen embedding model.
4) Set the same `QDRANT_COLLECTION` and `EMB_MODEL_NAME`/`EMBEDDINGS_MODEL` for the backend runtime.
