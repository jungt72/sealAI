# Phase 5 — Wiring & Quality Findings

Severity: **P0** kritisch (Format/State/Tool break), **P1** Qualität/Determinismus, **P2** Polish.

## P0

1. **Final Draft Router: Tool-/RAG-Claim Hallucination (G2) möglich, wenn Claims unconditionally gerendert werden.**  
   - Fix: RAG/DB‑Claims werden nur gezeigt, wenn RAG‑Artifacts existieren (`comparison_notes.rag_context`/`rag_reference` oder `working_memory.comparison_notes.*`) `backend/app/prompts/final_answer_router.j2:16-40`, `backend/app/prompts/final_answer_router.j2:119-125`.  
   - Contract‑Test: keine “RAG-basiert”/“SealAI-DB” Claims ohne Artifacts `backend/tests/contract/test_prompt_render_contract.py:123-133`.  

## P1

1. **Zwei verschiedene Frontdoor/Discovery Implementierungen im v2‑Tree.**  
   - Aktiver Graph nutzt `nodes_frontdoor.py` `backend/app/langgraph_v2/sealai_graph_v2.py:350`.  
   - Legacy `nodes_discovery.py` hat eigene Frontdoor/Confirm‑Gates `backend/app/langgraph_v2/nodes/nodes_discovery.py:47-327`.  
   - **Risiko:** Wartungs‑ und Prompt‑Drift.

2. **Knowledge‑Nodes nutzen legacy LLM/Message Utils.**  
   - Imports `backend/app/langgraph_v2/nodes/nodes_knowledge.py:7-10`.  
   - **Risiko:** andere Model‑Tiers/Token‑Policies; mögliche Runtime‑Error falls Pfade nicht existieren.

3. **SSE Events `node_start/node_end` werden vom Frontend ignoriert.**  
   - Backend emittiert `node_start/node_end` `backend/app/api/v1/endpoints/langgraph_v2.py:541-560`.  
   - TS Union kennt sie nicht `frontend/src/lib/useChat.ts:382-390`.  
   - **Impact:** keine Timeline/UX‑Updates möglich.

4. **SSE Parameter‑Deltas: Backend sendet nur `state_update` (kein `parameter_update`).**  
   - Backend Contract: `state_update` only `backend/app/api/v1/endpoints/langgraph_v2.py:484-515`.  
   - Abgesichert durch Contract‑Test `backend/tests/contract/test_sse_contract.py:157-190`.  

## P2

1. **Frontend Phase Union ist v1‑legacy und deckt v2 Phasen nicht ab.**  
   - `frontend/src/types/chat.ts:1-8` listet alte Phasen.  
   - v2 nutzt `frontdoor/entry/intent/preflight_parameters/consulting/knowledge/rag/final/confirm` etc. `backend/app/langgraph_v2/state/sealai_state.py:229-255`, `phase`‑Writes in Nodes.  
