# Phase 0 — Datei‑Landkarte (SealAI LangGraph v2)

Stand: 2025‑12‑12. Alle Aussagen referenzieren den aktuellen Repo‑Stand und sind mit Datei+Zeile belegt. Wenn etwas nicht auffindbar war, ist es als **MISSING** markiert.

## Backend — Entry Points / Runtime

| Datei | Zweck | Relevanz für Graph/Streaming |
|---|---|---|
| `backend/app/main.py` | FastAPI App‑Init, Router‑Mounts | Mountet v1‑API unter `/api/v1`, inkl. LangGraph v2 Endpoints. Siehe `backend/app/main.py:31-74`. |
| `backend/app/api/v1/api.py` | v1 Router‑Komposition | Mountet LangGraph v2 Router unter `/api/v1/langgraph` und State‑Endpoints. Siehe `backend/app/api/v1/api.py:4-37`. |
| `backend/app/api/v1/endpoints/langgraph_v2.py` | Zentraler LangGraph v2 SSE Endpoint + Stream‑Adapter | Implementiert POST `/api/v1/langgraph/chat/v2` (SSE), Event‑Queue, `astream_events`‑Loop, Parameter/State Deltas. Siehe `backend/app/api/v1/endpoints/langgraph_v2.py:37-768`. |
| `backend/app/api/v1/endpoints/state.py` | Graph‑State GET/POST (Frontend State Pull) | Frontend lädt hier initiale Parameter/Meta; siehe Fetch in `frontend/src/lib/useChat.ts:608-651` und Endpoint‑Definitionen (nicht komplett gelesen, **MISSING line refs**). |
| `backend/app/services/chat/ws_streaming.py` | WebSocket Streaming für legacy Chat | Paralleler Streaming‑Pfad (WS) neben SSE; erwähnte Event‑V1 in Docs. Siehe Referenzen in `backend/docs/audit_websocket_streaming.md:11-31`. |
| `backend/app/services/chat/conversations.py` | Conversation Metadata in Redis | SSE Endpoint persistiert Conversation via `upsert_conversation` Call. Siehe `backend/app/api/v1/endpoints/langgraph_v2.py:710-718` und `backend/app/services/chat/conversations.py` (**MISSING line refs**). |

## Backend — LangGraph v2

| Datei | Zweck | Relevanz |
|---|---|---|
| `backend/app/langgraph_v2/sealai_graph_v2.py` | Graph‑Build/Compile, Node‑Registration, Router/Edges, Final‑Answer Chain | Definitive v2 Graph‑Definition. Nodes/Edges ab `backend/app/langgraph_v2/sealai_graph_v2.py:345-441`. Config/Namespace ab `backend/app/langgraph_v2/sealai_graph_v2.py:466-491`. |
| `backend/app/langgraph_v2/sealai_graph_v2_legacy.py` | Legacy‑Graph v2 | Existiert als Alternative, wird aber im SSE Endpoint nicht importiert. **MISSING: runtime use**. |
| `backend/app/langgraph_v2/state/sealai_state.py` | Pydantic State Modell (SealAIState) inkl. Parameter/WM/Flags | Vollständiges State‑Schema. Siehe Felder ab `backend/app/langgraph_v2/state/sealai_state.py:33-340`. |
| `backend/app/langgraph_v2/nodes/*` | Node‑Implementierungen | Graph‑Nodes wie in `sealai_graph_v2.py` registriert. |
| `backend/app/langgraph_v2/tools/*` | Tool‑Implementierungen | Derzeit nur Parameter‑Tool `set_parameters`. Siehe `backend/app/langgraph_v2/tools/parameter_tools.py:17-132`. |
| `backend/app/langgraph_v2/utils/*` | Shared Utils (Jinja, LLM Factory, RAG Tool, Checkpointer, JSON Sanitizer) | Prompt Rendering `utils/jinja.py`, Checkpointer `utils/checkpointer.py`, RAG Tool `utils/rag_tool.py`. |

## Backend — Prompts (Jinja2)

| Datei | Zweck | Nodes |
|---|---|---|
| `backend/app/prompts/frontdoor_discovery_prompt.jinja2` | System‑Prompt für Frontdoor Intent Klassifikation (JSON only) | `frontdoor_discovery_node`. Siehe Nutzung `backend/app/langgraph_v2/nodes/nodes_frontdoor.py:89-99`. |
| `backend/app/prompts/discovery_summarize.j2` | System‑Prompt für Discovery Summary (JSON schema) | `discovery_summarize_node` in `backend/app/langgraph_v2/nodes/nodes_discovery.py:172-187`. |
| `backend/app/prompts/confirm_gate.j2` | Prompt für Confirm Gate (System + User getrennt durch `---`) | `confirm_gate_node` in `backend/app/langgraph_v2/nodes/nodes_discovery.py:246-267`. |
| `backend/app/prompts/material_comparison.j2` | Prompt für Material‑Vergleich | `material_comparison_node` in `backend/app/langgraph_v2/nodes/nodes_flows.py:271-287`. |
| `backend/app/prompts/leakage_troubleshooting.j2` | Prompt für Leckage‑Troubleshooting | `leakage_troubleshooting_node` in `backend/app/langgraph_v2/nodes/nodes_flows.py:324-339`. |
| `backend/app/prompts/troubleshooting_explainer.j2` | Prompt für Troubleshooting‑Erklärung | `troubleshooting_explainer_node` in `backend/app/langgraph_v2/nodes/nodes_flows.py:394-410`. |
| `backend/app/prompts/final_answer_router.j2` | Draft‑Router (mermaid‑ähnliche Ergebnis‑Cards, “Results/References”) | `render_final_answer_draft` in `backend/app/langgraph_v2/nodes/nodes_flows.py:449-451` und Final‑Answer Chain in `backend/app/langgraph_v2/sealai_graph_v2.py:251-305`. |
| `backend/app/prompts/final_answer_discovery_v2.j2` | Final Prompt für Discovery/Intermediate Antworten | Final‑Answer Chain: Auswahl in `backend/app/langgraph_v2/sealai_graph_v2.py:166-171` und Rendering `backend/app/langgraph_v2/sealai_graph_v2.py:228-235`. |
| `backend/app/prompts/final_answer_recommendation_v2.j2` | Final Prompt für Recommendation Flow | Wie oben. |
| `backend/app/prompts/final_answer_smalltalk_v2.j2` | Final Prompt für Smalltalk | Wie oben. |
| `backend/app/prompts/final_answer_v2.j2` | Legacy/Alternative Final Prompt (v3 comment) | `answer_synthesizer_node` nutzt dies, aber Node ist im Graph v2 **nicht registriert**. Siehe `backend/app/langgraph_v2/nodes/nodes_validation.py:60` vs. Graph‑Registration `backend/app/langgraph_v2/sealai_graph_v2.py:350-367`. |
| `backend/app/prompts/response_router.j2` | Zentraler Text‑Router für `response_node` | `response_node` in `backend/app/langgraph_v2/nodes/response_node.py:13-44`. |

## Backend — RAG / External Services

| Datei | Zweck | Relevanz |
|---|---|---|
| `backend/app/langgraph_v2/utils/rag_tool.py` | LangChain Tool Wrapper für RAG | Tool `search_knowledge_base` ruft `hybrid_retrieve` und rendert Markdown. Siehe `backend/app/langgraph_v2/utils/rag_tool.py:25-67`. |
| `backend/app/services/rag/rag_orchestrator.py` | Hybrid Retrieval Qdrant + BM25 + Rerank + External Fallback | Definitive Retrieval‑Pipeline. Siehe `hybrid_retrieve` `backend/app/services/rag/rag_orchestrator.py:275-320`. |
| `backend/app/services/rag/bm25_store.py` | Optionaler BM25 Index (Redis‑gated) | Wird von `rag_orchestrator` genutzt. Siehe `backend/app/services/rag/bm25_store.py:18-155`. |

## Backend — Auth / User Isolation

| Datei | Zweck | Relevanz |
|---|---|---|
| `backend/app/services/auth/dependencies.py` | JWT Verify + `CurrentUser` | SSE Endpoint setzt `request.user_id = current_user.sub`. Siehe `backend/app/api/v1/endpoints/langgraph_v2.py:740-764` und User‑Build `backend/app/services/auth/dependencies.py:22-60`. |
| `backend/app/services/auth/jwt_utils.py` | JWT Decode/Verify (Keycloak RS256) | Token‑Verifikation für HTTP/WS. Siehe `backend/app/services/auth/jwt_utils.py:29-71`. |

## Frontend — SSE Bridge / State Sync

| Datei | Zweck | Relevanz |
|---|---|---|
| `frontend/src/lib/langgraphApi.ts` | Endpoint‑Resolver für Backend URLs | `CHAT_ENDPOINT=/api/v1/langgraph/chat/v2`, `STATE_ENDPOINT=/api/v1/langgraph/state`. Siehe `frontend/src/lib/langgraphApi.ts:27-31`. |
| `frontend/src/lib/useChat.ts` | SSE Parsing, Event‑Normalisierung, UI‑State Merge | Erwartete Event Types ab `frontend/src/lib/useChat.ts:382-390`, Normalisierung `frontend/src/lib/useChat.ts:503-573`, State Pull `frontend/src/lib/useChat.ts:608-651`. |
| `frontend/src/types/chat.ts` | Message/Meta Typen | UI‑Meta enthält `phase?: Phase | string` (v1‑Legacy Phase Union). Siehe `frontend/src/types/chat.ts:1-18`. |

