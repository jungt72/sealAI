# Phase 5 — Priorisierter Verbesserungsplan (für ChatGPT‑Niveau)

Dies ist **nur** ein Plan, noch keine Implementierung.

## P0 — Qualität & Stabilität

1. **SSE Contract entdriften:**  
   - Backend: nur **eine** Parameter‑Delta Quelle senden (entweder `state_update` oder `parameter_update`).  
   - Files: `backend/app/api/v1/endpoints/langgraph_v2.py` (param_delta/state_update Block `484-523`).  
   - Frontend ggf. vereinfachen: `frontend/src/lib/useChat.ts` (merge logic `830-867`).  
   - Ziel: deterministische Reihenfolge, kein Flackern.

2. **Final Draft Router halluzinationsfrei machen:**  
   - Entferne harte Prozent‑Claims oder binde sie an State‑Felder.  
   - File: `backend/app/prompts/final_answer_router.j2` (`49-50`, `84-85`).  

3. **Agent‑Prompts/Contracts definieren (Material/Profile/Validation):**  
   - Erstelle/vereinheitliche Templates und state‑slices für Outputs.  
   - Files: `backend/app/langgraph_v2/nodes/nodes_flows.py` (Agent bodies), `backend/app/prompts/` neue Templates, `backend/app/langgraph_v2/state/sealai_state.py` evtl. typed slices.  

## P1 — RAG & Tooling

1. **Knowledge‑Nodes auf v2 Utils vereinheitlichen:**  
   - `nodes_knowledge.py` auf `utils.llm_factory`/`utils.messages` umstellen.  
   - File: `backend/app/langgraph_v2/nodes/nodes_knowledge.py`.  

2. **Citation Policy:**  
   - Prompt‑Templates erweitern, um RAG Sources konsistent zu zitieren.  
   - Files: `backend/app/prompts/final_answer_recommendation_v2.j2`, `final_answer_discovery_v2.j2`, `utils/rag_tool.py`.  

## P2 — Polish

1. **Phasen‑Typen im Frontend aktualisieren:**  
   - `frontend/src/types/chat.ts` Phase Union erweitern oder string‑only.  

2. **Optional: node_start/node_end UI‑Timeline nutzen:**  
   - Frontend `LanggraphEvent` erweitern, Timeline Komponenten anbinden.  

