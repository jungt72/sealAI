# Phase 2 — RAG Pipeline (Qdrant / BM25 / Rerank)

Quelle: `backend/app/services/rag/rag_orchestrator.py`.

## Retrieval Flow

1. **Query embed (dense only)** via `FastEmbedEmbeddings` in `_embed` (lazy init). Query vector wird im Public API verwendet `backend/app/services/rag/rag_orchestrator.py:287-289`.  
2. **Qdrant vector search** via HTTP POST `/collections/{collection}/points/search` `_qdrant_search` `backend/app/services/rag/rag_orchestrator.py:175-208`.  
3. **Optional BM25** wenn `RAG_BM25_ENABLED=1` und Redis Index vorhanden. Init gating `backend/app/services/rag/rag_orchestrator.py:41-80`, Search `_bm25_search` `backend/app/services/rag/rag_orchestrator.py:214-221`.  
4. **RRF fusion** `_rrf_merge` (keine hard doc‑dedupe) `backend/app/services/rag/rag_orchestrator.py:125-151`, aufgerufen `backend/app/services/rag/rag_orchestrator.py:303-305`.  
5. **Per‑Document cap** `_dedupe_by_document` `backend/app/services/rag/rag_orchestrator.py:232-245`.  
6. **Cross‑encoder rerank** optional (default True), sigmoid‑normalized in `fused_score` `backend/app/services/rag/rag_orchestrator.py:247-270`, aufgerufen `backend/app/services/rag/rag_orchestrator.py:307-308`.  
7. **Score threshold** `RAG_SCORE_THRESHOLD` `backend/app/services/rag/rag_orchestrator.py:222-230`, aufgerufen `backend/app/services/rag/rag_orchestrator.py:308`.  
8. **External fallback** wenn leer `backend/app/services/rag/rag_orchestrator.py:310-314` → `_fallback_external_search` `backend/app/services/rag/rag_orchestrator.py:338-396`.  

## Tenant / Collection Logic

- Collection wird tenant‑abhängig gewählt via `_collection_for_tenant(tenant)` (Function body im Scan **MISSING line refs**, aber wird genutzt `backend/app/services/rag/rag_orchestrator.py:288-289`).  
- Nodes übergeben `tenant=state.user_id` z.B. `rag_support_node` `backend/app/langgraph_v2/nodes/nodes_flows.py:303-308`.  

## Citations / Formatting

- Tool rendert jede Hit in Markdown‑Block mit `doc_id`, `section`, `score`, `Quelle` `backend/app/langgraph_v2/utils/rag_tool.py:9-22`.  
- Keine formale Citation‑Policy im Prompt Layer gefunden (**MISSING**).  

