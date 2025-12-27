# Phase 2 — Tool Catalog

## `set_parameters`

- **Name:** `set_parameters`  
- **Implementation:** `backend/app/langgraph_v2/tools/parameter_tools.py:17-132`.  
- **Signature:** Many optional keyword args + injected state. Returns dict `{"parameters": TechnicalParameters(**merged)}` `backend/app/langgraph_v2/tools/parameter_tools.py:17-61`, `128-131`.  
- **Timeout/Retry:** none.  
- **Error handling:** minimal (dict merge; Pydantic validate at return).  
- **Called by nodes:** `backend/app/langgraph_v2/nodes/nodes_discovery.py` nutzt `ChatOpenAI.bind_tools([set_parameters])` zur Extraction `backend/app/langgraph_v2/nodes/nodes_discovery.py:91-116`.  
- **Contract expected by prompts:** `parameters` field in State; templates iterieren `.items()` in `final_answer_*` Templates, z.B. `backend/app/prompts/final_answer_discovery_v2.j2:25-32`.  

## `search_knowledge_base`

- **Name:** `search_knowledge_base` (LangChain `@tool`).  
- **Implementation:** `backend/app/langgraph_v2/utils/rag_tool.py:25-67`.  
- **Signature:** `query: str, category?: str, k: int=5, tenant?: str` `backend/app/langgraph_v2/utils/rag_tool.py:25-31`.  
- **Backend calls:** `hybrid_retrieve` `backend/app/langgraph_v2/utils/rag_tool.py:48-54`.  
- **Output:** Markdown string with bullet list + source lines. `backend/app/langgraph_v2/utils/rag_tool.py:62-66`.  
- **Error handling:** returns user‑visible error string on exception `backend/app/langgraph_v2/utils/rag_tool.py:55-58`.  
- **Called by nodes:**  
  - `rag_support_node` `.invoke({...})` `backend/app/langgraph_v2/nodes/nodes_flows.py:303-308`.  
  - Knowledge subgraph nodes also `.invoke` (see `backend/app/langgraph_v2/nodes/nodes_knowledge.py:61-66`, `122-127`, `185-189`).  

## External / HTTP Tools

- **Qdrant HTTP retrieval:** `_qdrant_search` in `backend/app/services/rag/rag_orchestrator.py:175-212`.  
- **External microservice fallback:** `_fallback_external_search` in `backend/app/services/rag/rag_orchestrator.py:338-396` uses env `AGENT_NORMEN_URL`, `AGENT_MATERIAL_URL`.  

No weiteren Tools in `backend/app/langgraph_v2/tools/` gefunden (**MISSING: weitere Tool‑Module**).

