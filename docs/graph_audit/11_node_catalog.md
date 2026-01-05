# Phase 1 — Node Catalog (LangGraph v2)

Für jede Node: Purpose, Preconditions, State Reads/Writes, Side‑Effects, Tools, Prompts.

## `frontdoor_discovery_node`

- **Purpose:** Erste Intent‑Klassifikation + frühe Param‑Extraktion (Smalltalk fast‑path, LLM JSON).  
- **Reads:** `messages`, `parameters`, `working_memory`, `run_id/thread_id/user_id`. Siehe `backend/app/langgraph_v2/nodes/nodes_frontdoor.py:119-124`, `152-170`.  
- **Writes:** `intent`, `working_memory.frontdoor_reply`, `parameters` (merge). Siehe Return `backend/app/langgraph_v2/nodes/nodes_frontdoor.py:192-197`, `292-298`.  
- **Side‑effects:** LLM call `run_llm` (nano) `backend/app/langgraph_v2/nodes/nodes_frontdoor.py:170-182`; Regex param extraction `backend/app/langgraph_v2/nodes/nodes_frontdoor.py:274-280`.  
- **Tools:** keine LangGraph Tools; nur util `extract_parameters_from_text`.  
- **Prompts:** `frontdoor_discovery_prompt.jinja2` via `render_template` `backend/app/langgraph_v2/nodes/nodes_frontdoor.py:89-99`.  

## `supervisor_logic_node`

- **Purpose:** Setzt Phase, hält WorkingMemory stabil, heuristisch `recommendation_go` aus YES/NO Keywords; entscheidet Routing via `supervisor_route`.  
- **Reads:** `intent.goal`, `recommendation_ready/go`, `messages`, `working_memory`. Siehe `backend/app/langgraph_v2/nodes/nodes_supervisor.py:30-58`, `61-73`.  
- **Writes:** `working_memory`, `phase="intent"`, `last_node`. Siehe `backend/app/langgraph_v2/nodes/nodes_supervisor.py:30-39`.  
- **Side‑effects:** mutiert State inline (`state.recommendation_go = True/False`) `backend/app/langgraph_v2/nodes/nodes_supervisor.py:61-73`.  
- **Tools/Prompts:** keine.  

## `discovery_schema_node`

- **Purpose:** Definiert minimale Required‑Keys für Design‑Flow, setzt `missing_params` und Flags.  
- **Reads:** `parameters`, `messages`, `working_memory.design_notes`. Siehe `backend/app/langgraph_v2/nodes/nodes_flows.py:43-60`.  
- **Writes:** `missing_params`, `working_memory.design_notes.schema`, `flags.parameters_complete_for_material`, `phase`, `last_node`. Siehe `backend/app/langgraph_v2/nodes/nodes_flows.py:61-69`.  
- **Tools/Prompts:** keine.  

## `parameter_check_node`

- **Purpose:** Prüft ob `missing_params` leer; setzt Completeness‑Flag.  
- **Reads:** `missing_params`, `working_memory`. Siehe `backend/app/langgraph_v2/nodes/nodes_flows.py:74-79`.  
- **Writes:** `flags.parameters_complete_for_profile`, `analysis_complete=True`, `phase`, `last_node`. Siehe `backend/app/langgraph_v2/nodes/nodes_flows.py:80-87`.  

## `calculator_node`

- **Purpose:** Grobe technische Heuristik, füllt `calc_results` + `coverage_score` + Flags.  
- **Reads:** `parameters.*`. Siehe `backend/app/langgraph_v2/nodes/nodes_flows.py:92-110`.  
- **Writes:** `calc_results`, `calc_results_ok=True`, `coverage_score`, `coverage_gaps`, `recommendation_ready=True`, `phase="consulting"` (aus Return). Siehe Return im Block (teilweise truncation, aber Node ist im Flow registriert und führt danach zu `material_agent_node`; vgl. `backend/app/langgraph_v2/sealai_graph_v2.py:399-402`).  

## `material_agent_node` / `profile_agent_node` / `validation_agent_node`

- **Purpose:** LLM‑basierte Material‑, Profil‑, Validierungs‑Agenten im Design‑Flow.  
- **Reads/Writes:** **MISSING detaillierte line refs** (Funktionskörper in `backend/app/langgraph_v2/nodes/nodes_flows.py` im Scan nur teilweise sichtbar).  
- **Edges:** Sequenziell `calculator_node -> material_agent_node -> profile_agent_node -> validation_agent_node`. Siehe `backend/app/langgraph_v2/sealai_graph_v2.py:399-402`.  
- **Prompts:** **MISSING** (keine dedizierten Templates in `backend/app/prompts/` gefunden).  

## `critical_review_node`

- **Purpose:** Heuristische Qualitätskontrolle mit conditional routing.  
- **Reads:** `critical.status` (dict). Siehe Router `_critical_review_router` `backend/app/langgraph_v2/sealai_graph_v2.py:317-325` und Node Return `backend/app/langgraph_v2/nodes/nodes_flows.py:188-221`.  
- **Writes:** `critical`, `working_memory`, `phase="validation"`, `last_node`. Siehe `backend/app/langgraph_v2/nodes/nodes_flows.py:215-221`.  

## `product_match_node` / `product_explainer_node`

- **Purpose:** Optionaler Produkt‑Match/Explain auf Basis `plan.want_product_recommendation`.  
- **Reads:** `plan.want_product_recommendation`, `working_memory.design_notes`. Siehe `backend/app/langgraph_v2/nodes/nodes_flows.py:226-237`, `249-258`.  
- **Writes:** `products`, `working_memory.design_notes.*`, `phase="consulting"`, `last_node`. Siehe `backend/app/langgraph_v2/nodes/nodes_flows.py:238-244`, `259-264`.  

## `material_comparison_node`

- **Purpose:** LLM‑Materialvergleich.  
- **Reads:** `messages` (User Text). Siehe `backend/app/langgraph_v2/nodes/nodes_flows.py:269-287`.  
- **Writes:** `working_memory.comparison_notes.comparison_text`, `phase="knowledge"`, `last_node`. Siehe `backend/app/langgraph_v2/nodes/nodes_flows.py:288-296`.  
- **Prompts:** `material_comparison.j2` (System/User split via `---`) `backend/app/langgraph_v2/nodes/nodes_flows.py:271-279`.  

## `rag_support_node`

- **Purpose:** Ergänzt Vergleichs‑Flow um RAG‑Kontext (norms).  
- **Reads:** `messages`, `working_memory.comparison_notes`, `user_id`. Siehe `backend/app/langgraph_v2/nodes/nodes_flows.py:301-308`.  
- **Writes:** `working_memory.comparison_notes.rag_context`, `phase="rag"`, `last_node`. Siehe `backend/app/langgraph_v2/nodes/nodes_flows.py:309-317`.  
- **Tools:** `search_knowledge_base` Tool call `.invoke` `backend/app/langgraph_v2/nodes/nodes_flows.py:303-308`.  

## `leakage_troubleshooting_node` / `troubleshooting_pattern_node` / `troubleshooting_explainer_node`

- **Purpose:** Troubleshooting‑Flow.  
- **Reads/Writes:**  
  - `leakage_troubleshooting_node` reads user text, writes `troubleshooting` dict, `working_memory.troubleshooting_notes`, phase consulting. `backend/app/langgraph_v2/nodes/nodes_flows.py:320-358`.  
  - `troubleshooting_pattern_node` heuristic pattern match, updates `troubleshooting.pattern_match`. `backend/app/langgraph_v2/nodes/nodes_flows.py:361-386`.  
  - `troubleshooting_explainer_node` LLM explain, sets `troubleshooting.done=True`. `backend/app/langgraph_v2/nodes/nodes_flows.py:389-423`.  
- **Prompts:** `leakage_troubleshooting.j2`, `troubleshooting_explainer.j2`. `backend/app/langgraph_v2/nodes/nodes_flows.py:324-339`, `394-410`.  

## `confirm_recommendation_node`

- **Purpose:** UI/HITL: fragt User ob Recommendation generiert werden soll.  
- **Reads:** `parameters`, `coverage_score`, `coverage_gaps`. `backend/app/langgraph_v2/nodes/nodes_confirm.py:30-41`.  
- **Writes:** `final_text` question, `phase="confirm"`, `last_node`. `backend/app/langgraph_v2/nodes/nodes_confirm.py:43-53`.  

## `final_answer_node`

- **Purpose:** Final‑Answer LLM Chain: Draft via `final_answer_router.j2`, dann Ziel‑Template (smalltalk/discovery/recommendation) als SystemMessage + LLM streaming.  
- **Reads:** `messages`, `intent.goal`, `parameters`, `calc_results`, `recommendation`, `working_memory`, `coverage_*`, `flags`, `plan`. Siehe `_prepare_inputs` `backend/app/langgraph_v2/sealai_graph_v2.py:246-281` und context build `backend/app/langgraph_v2/nodes/nodes_flows.py:426-446`.  
- **Writes:** Appends `AIMessage`, sets `final_text`, `phase`, `last_node`. Siehe `map_final_answer_to_state` `backend/app/langgraph_v2/nodes/nodes_flows.py:454-465` and chain tail `backend/app/langgraph_v2/sealai_graph_v2.py:301-306`.  
- **Prompts:**  
  - Draft router `final_answer_router.j2` via `render_final_answer_draft` `backend/app/langgraph_v2/nodes/nodes_flows.py:449-451`.  
  - Final templates selected in `_select_final_answer_template` `backend/app/langgraph_v2/sealai_graph_v2.py:166-171` and rendered `backend/app/langgraph_v2/sealai_graph_v2.py:228-235`.  

