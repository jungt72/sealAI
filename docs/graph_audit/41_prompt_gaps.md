# Phase 4 — Prompt Gaps / Contract Mismatches

## Gaps (belegt)

1. **Zwei konkurrierende Frontdoor‑Nodes:**  
   - Graph registriert `frontdoor_discovery_node` aus `nodes_frontdoor.py` `backend/app/langgraph_v2/sealai_graph_v2.py:350`.  
   - `nodes_discovery.py` definiert ebenfalls `frontdoor_discovery_node` (legacy alias) `backend/app/langgraph_v2/nodes/nodes_discovery.py:47-159`.  
   → **Risiko:** Drift in Prompt/Parameter‑Extraction; nur eine Variante wird im Graph genutzt.

2. **Legacy Final Prompt aktiv, aber im Graph ungenutzt:**  
   - `answer_synthesizer_node` rendert `final_answer_v2.j2` `backend/app/langgraph_v2/nodes/nodes_validation.py:60`.  
   - Node ist nicht in `create_sealai_graph_v2` registriert (stattdessen `final_answer_node`) `backend/app/langgraph_v2/sealai_graph_v2.py:350-368`.  
   → `final_answer_v2.j2` ist faktisch **unused template** im v2 Graph.

3. **Final Draft Router: Tool-/RAG-Claims müssen state-gebunden sein (G2 Tool-Hallucinations).**  
   - RAG/DB‑Claims werden nur gezeigt, wenn `comparison_notes.rag_context`/`rag_reference` (oder `working_memory.comparison_notes.*`) vorhanden sind `backend/app/prompts/final_answer_router.j2:16-40`, `backend/app/prompts/final_answer_router.j2:119-125`.  
   - Contract‑Test: keine “RAG-basiert”/“SealAI-DB” Claims ohne Artifacts `backend/tests/contract/test_prompt_render_contract.py:123-133`.  

4. **Knowledge subgraph nutzt andere Utils/Imports (wahrscheinlich legacy):**  
   - `nodes_knowledge.py` importiert `app.core.llm_client` und `app.utils.message_helpers` `backend/app/langgraph_v2/nodes/nodes_knowledge.py:7-10`, während v2 sonst `utils.llm_factory` und `utils.messages` nutzt.  
   → potenzieller Prompt/Model‑Tier Drift.
