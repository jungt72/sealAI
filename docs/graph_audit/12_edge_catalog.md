# Phase 1 — Edge / Routing Catalog

## Static Edges

| From → To | Bedingung | Failure Modes |
|---|---|---|
| `START → frontdoor_discovery_node → supervisor_logic_node` | linear entry | Wenn Frontdoor LLM failt, default Intent gesetzt (`backend/app/langgraph_v2/nodes/nodes_frontdoor.py:183-197`). |
| `discovery_schema_node → parameter_check_node` | linear | Missing list basiert auf hartem Required‑Set (`backend/app/langgraph_v2/nodes/nodes_flows.py:44-52`) → evtl. zu klein. |
| `calculator_node → material_agent_node → profile_agent_node → validation_agent_node → critical_review_node` | linear | Falls Agent‑Nodes Prompts/Contracts fehlen → Review kann falsche Defaults sehen (**siehe Findings**). |
| `material_comparison_node → rag_support_node → final_answer_node` | linear comparison flow | RAG Tool kann Fehlertext als “knowledge” liefern (`backend/app/langgraph_v2/utils/rag_tool.py:55-60`). |
| `leakage_troubleshooting_node → troubleshooting_pattern_node → troubleshooting_explainer_node → final_answer_node` | linear troubleshooting flow | Pattern‑Heuristik kann falsches match setzen (`backend/app/langgraph_v2/nodes/nodes_flows.py:364-373`). |
| `final_answer_node → END` | terminal | Final‑Chain soll immer einen Text patchen; falls LLM keine Tokens sendet, SSE Endpoint fallbacks zu `token` chunks (`backend/app/api/v1/endpoints/langgraph_v2.py:676-690`). |
| `confirm_recommendation_node → END` | terminal | Stops to ask user; SSE erkennt `awaiting_user_input` via Redis Snapshot `backend/app/api/v1/endpoints/langgraph_v2.py:665-674`. |

## Conditional Edges

### `supervisor_logic_node` routes via `supervisor_route`

Router: `backend/app/langgraph_v2/nodes/nodes_supervisor.py:42-58`.  
Mapping: `backend/app/langgraph_v2/sealai_graph_v2.py:373-386`.

| Route Key | Condition | To |
|---|---|---|
| `intermediate` | goal=`design_recommendation` AND `recommendation_ready` False | `final_answer_node` |
| `confirm` | goal=`design_recommendation` AND ready True AND go False | `confirm_recommendation_node` |
| `design_flow` | goal=`design_recommendation` AND ready True AND go True | `calculator_node` |
| `comparison` | goal=`explanation_or_comparison` | `material_comparison_node` |
| `troubleshooting` | goal=`troubleshooting_leakage` | `leakage_troubleshooting_node` |
| `smalltalk` | goal=`smalltalk` | `final_answer_node` |
| `out_of_scope` | goal=`out_of_scope` | `final_answer_node` |
| `__else__` | fallback | `final_answer_node` |

Failure modes:
- `recommendation_go` wird via Keyword‑Heuristik aus User‑Text gemutiert (`backend/app/langgraph_v2/nodes/nodes_supervisor.py:61-73`) → kann “Ja” in anderem Kontext triggern.

### `parameter_check_node` routes via `_parameter_check_router`

Router: `backend/app/langgraph_v2/sealai_graph_v2.py:332-338` and mapping `backend/app/langgraph_v2/sealai_graph_v2.py:390-398`.

| Route Key | Condition | To |
|---|---|---|
| `calculator_node` | `recommendation_ready` True AND `recommendation_go` True | `calculator_node` |
| `supervisor_logic_node` | else | `supervisor_logic_node` |

### `critical_review_node` routes via `_critical_review_router`

Router: `backend/app/langgraph_v2/sealai_graph_v2.py:317-325`.

| Route Key | Condition on `critical.status` | To |
|---|---|---|
| `refine` | `needs_refinement` | `discovery_schema_node` |
| `reject` | `reject` | `final_answer_node` |
| `continue` | default | `product_match_node` |

### `product_match_node` routes via `_product_router`

Router: `backend/app/langgraph_v2/sealai_graph_v2.py:327-330`.

| Route Key | Condition | To |
|---|---|---|
| `include` | `plan.want_product_recommendation` True | `product_explainer_node` |
| `skip` | else | `final_answer_node` |

