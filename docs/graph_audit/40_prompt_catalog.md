# Phase 4 — Prompt Catalog

## Renderer

- Jinja2 Renderer mit `StrictUndefined`; fehlende Variablen werfen Fehler. `backend/app/langgraph_v2/utils/jinja.py:15-37`.  
- Prompt‑Root ist `backend/app/prompts/` `backend/app/langgraph_v2/utils/jinja.py:11-13`.  

## Templates & Verwendung

| Template | Typ / Output | Verwendet in |
|---|---|---|
| `frontdoor_discovery_prompt.jinja2` | System‑Prompt, JSON only Intent | `frontdoor_discovery_node` `backend/app/langgraph_v2/nodes/nodes_frontdoor.py:89-99`. |
| `discovery_summarize.j2` | System‑Prompt, JSON `{summary,coverage,missing}` | `discovery_summarize_node` `backend/app/langgraph_v2/nodes/nodes_discovery.py:172-187`. |
| `confirm_gate.j2` | System+User Prompt (split by `---`) | `confirm_gate_node` `backend/app/langgraph_v2/nodes/nodes_discovery.py:252-267`. |
| `material_comparison.j2` | System+User Prompt | `material_comparison_node` `backend/app/langgraph_v2/nodes/nodes_flows.py:271-287`. |
| `leakage_troubleshooting.j2` | System+User Prompt | `leakage_troubleshooting_node` `backend/app/langgraph_v2/nodes/nodes_flows.py:324-339`. |
| `troubleshooting_explainer.j2` | System+User Prompt | `troubleshooting_explainer_node` `backend/app/langgraph_v2/nodes/nodes_flows.py:394-410`. |
| `response_router.j2` | Draft router for response_node | `response_node` `backend/app/langgraph_v2/nodes/response_node.py:24-36`. |
| `final_answer_router.j2` | Draft router (structure Tables/Sections) | `render_final_answer_draft` `backend/app/langgraph_v2/nodes/nodes_flows.py:449-451`. |
| `final_answer_discovery_v2.j2` | Final system prompt for discovery/intermediate | Final chain `backend/app/langgraph_v2/sealai_graph_v2.py:166-235`. |
| `final_answer_recommendation_v2.j2` | Final system prompt for recommendation | wie oben. |
| `final_answer_smalltalk_v2.j2` | Final system prompt for smalltalk | wie oben. |
| `final_answer_v2.j2` | Legacy final prompt; expects knowledge_* | `answer_synthesizer_node` `backend/app/langgraph_v2/nodes/nodes_validation.py:60` aber Node nicht verdrahtet. |

