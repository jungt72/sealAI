# 🧠 LangGraph Cognitive Intelligence Report

## 1. Workflow Topology & Agents
- Das System ist ein hybrider **StateMachine-Graph mit regelbasiertem Supervisor-Orchestrator**: deterministische Router (`node_router`, `_frontdoor_router`, `_reducer_router`) steuern, während einzelne spezialisierte LLM-Nodes klassifizieren/extrahieren/generieren.
- **Agenten-Nodes:** `frontdoor_discovery_node`, `node_p1_context`, `smalltalk_node`, `material_comparison_node`, `leakage_troubleshooting_node`, `troubleshooting_explainer_node`, `final_answer_node` (zusätzlich vorhanden, aber im Graph aktuell nicht verdrahtet: `out_of_scope_node`).
- **Worker-Nodes:** `profile_loader_node`, `node_router`, `resume_router_node`, `node_p2_rag_lookup`, `node_p3_gap_detection`, `node_p3_5_merge`, `node_p4a_extract`, `node_p4b_calc_render`, `node_p4_5_qgate`, `p4_6_number_verification`, `node_p5_procurement`, `node_factcard_lookup_parallel`, `node_compound_filter_parallel`, `node_merge_deterministic`, `supervisor_policy_node`/`orchestrator_node`, `calculator_agent`, `pricing_agent`, `safety_agent`, `reducer_node`, `response_node`, `confirm_*`-Nodes.
- **State-Evolution & Memory (turn-übergreifend):**

| State-Pfad | Extraktion/Mutation | Speicherung | Konsum |
|---|---|---|---|
| `parameters.medium / pressure_bar / temperature_C` | `frontdoor_discovery_node` via `_extract_parameter_patch()` + `apply_parameter_patch_with_provenance(..., source="user")` | `state.parameters`, `state.parameter_provenance` | `supervisor_policy_node` (`_infer_missing_params`), `calculator_node`, Final-Prompt (`final_answer_*` Templates) |
| `working_profile.*` (z. B. `pressure_max_bar`, `temperature_max_c`, `material`) | `node_p1_context` (LLM-Structured Extraction) | `state.working_profile` | `node_p2_rag_lookup`, `node_p3_gap_detection`, `node_p4a_extract`, `node_p5_procurement` |
| `extracted_params` | `node_p4a_extract` (deterministisches Mapping `working_profile -> CalcInput`) | `state.extracted_params` | `node_p4b_calc_render` |
| `calculation_result` / `calc_results` | `node_p4b_calc_render` + `mcp_calc_gasket` | `state.calculation_result`, `state.calc_results` | `node_p4_5_qgate`, Final-Prompt (`calc_results`) |
| `context` / RAG-Blöcke | `node_p2_rag_lookup`, `material_agent_node`, `reducer_node` | `state.context`, `working_memory.panel_material.rag_context/reducer_context` | `_collect_retrieved_facts()` für finalen Systemprompt |
| HITL-Checkpoint | `reducer_node` setzt `requires_human_review=True` bei `safety_review.severity>=4`; `human_review_node` setzt `awaiting_user_confirmation=True` | `state.awaiting_user_confirmation`, `state.pending_action`, `state.confirm_*` | `node_router` (`resume`), `resume_router_node`, `confirm_resume_node`/`confirm_reject_node` |

## 2. Routing Intelligence
- Das Routing ist zweistufig: **(a) deterministischer Entry-Router** (`node_router`, Regex/State-Heuristik), danach **(b) LLM-basierte Frontdoor-Intent-Klassifikation** (`frontdoor_discovery_node`) plus deterministische Supervisor-Regeln.

| Intent / Condition | Trigger-Bedingung (LLM oder Heuristik?) | Ziel-Node (Next Step) | Fallback bei Unklarheit |
|---|---|---|---|
| `rfq_trigger` | `node_router`: `_RFQ_PATTERNS` Regex | `node_p5_procurement` | Wenn kein Match: weitere Router-Regeln, final `new_case` |
| `resume` | `node_router`: `awaiting_user_confirmation && confirm_decision` | `resume_router_node` | Wenn nicht erfüllt: normale Klassifikation |
| `new_case` explizit | `node_router`: `_NEW_CASE_PATTERNS` Regex | `node_p1_context` | `node_router` Default ist ebenfalls `new_case` |
| `follow_up` | `node_router`: vorhandene Parameter + `_PARAMETER_CHANGE_PATTERNS` | `node_p1_context` | Wenn Bedingung nicht greift: weitere Rules/Default |
| `clarification` | `node_router`: vorhandene Antwort + `_CLARIFICATION_PATTERNS` | `smalltalk_node` | Wenn nicht erkannt: `new_case` |
| `node_router` unknown class | `_node_router_dispatch` default branch | `node_p1_context` | Harte Default-Route `p1_context` |
| `resume: reject` | `_resume_router`: decision == `reject` | `confirm_reject_node` | Map enthält zusätzlich `default -> response_node` |
| `resume: approve/edit/...` | `_resume_router`: beliebiges decision != `reject` | `confirm_resume_node` | Bei fehlender Decision: `frontdoor_discovery_node` |
| `resume fallback` | `_resume_router`: kein valides Resume-Signal | `frontdoor_discovery_node` | Edge-Mapping enthält `default -> response_node` |
| `CHIT_CHAT` | `frontdoor_discovery_node` (LLM structured output) setzt `frontdoor_bypass_supervisor=True` | `smalltalk_node` | Bei LLM-Fehler Fallback-Intent `ENGINEERING_CALCULATION` |
| `GENERAL_KNOWLEDGE` / `MATERIAL_RESEARCH` / `COMMERCIAL` / `ENGINEERING_CALCULATION` | `frontdoor_discovery_node` (LLM) | `frontdoor_parallel_fanout_node` | Bei LLM-Fehler ebenfalls Supervisor-Pfad |
| Frontdoor LLM Exception | try/except in `frontdoor_discovery_node` | Supervisor-Pfad (über `frontdoor_parallel_fanout_node`) | Fixer Fallback-Intent `ENGINEERING_CALCULATION` |
| Deterministische KB-Antwort | `_merge_deterministic_router`: `kb_factcard_result.deterministic=True` | `response_node` | Sonst Supervisor |
| Kein deterministischer KB-Hit | `_merge_deterministic_router` else | `supervisor_policy_node` | Default ebenfalls Supervisor |
| Supervisor parallel fanout | `supervisor_policy_node`: `actions` nicht leer | `Send(...)` an `safety_agent`/`material_agent`/`pricing_agent`/`calculator_agent` | Bei keiner Action geht es zu Goal-Branches |
| Troubleshooting | `supervisor_policy_node`: `goal == troubleshooting_leakage` | `leakage_troubleshooting_node` | Sonst weitere Goal/Final-Regeln |
| Comparison/Explanation | `supervisor_policy_node`: `goal == explanation_or_comparison` (wenn keine Actions) | `material_comparison_node` | Sonst Finalize |
| Ask User | `supervisor_policy_node`: offene High-Priority-Fragen | `final_answer_node` (`next_action=ASK_USER`) | Sonst `ACTION_FINALIZE` |
| Reducer HITL | `_reducer_router`: `requires_human_review=True` | `human_review_node` | Sonst `final_answer_node` |
| Reducer Standard | `_reducer_router` else | `final_answer_node` | Standard-Default |
| Quality Gate blockiert | `_qgate_router`: `qgate_has_blockers=True` | `response_node` | Sonst Verifikation |
| Quality Gate frei | `_qgate_router` else | `p4_6_number_verification` | - |
| Number Verification pass | Edge-Lambda: `verification_passed=True` | `final_answer_node` | Default ist pass (`state.get(..., True)`) |
| Number Verification fail | Edge-Lambda: `verification_passed=False` | `request_clarification_node` | - |

- ⚠️ **Kognitive Gaps:**
- **Intent-Kollision Smalltalk + Fachfrage:** Wenn Frontdoor LLM fälschlich `CHIT_CHAT` setzt, wird Supervisor/RAG komplett umgangen (`smalltalk_node`), obwohl z. B. Material-/Normfrage enthalten ist.
- **Gemischte Deterministik:** Entry-Router ist robust deterministisch; Frontdoor ist nondeterministisch (LLM) und Single-Label. Multi-Intent Inputs (z. B. "Hi + Datasheet + Preis") werden nicht explizit als zusammengesetzter Intent modelliert.
- **Schema-Inkonsistenz:** `classify_input()` kann `"resume"` liefern, aber `SealAIState.router_classification` erlaubt laut Typ-Literal kein `resume`.
- **Verifikationsgate-Reihenfolge:** `p4_6_number_verification` läuft vor `final_answer_node`; es prüft `final_answer/final_text`, die zu diesem Zeitpunkt meist leer sind.

## 3. Context & Prompting Quality
- Final-Payload-Trace (Input -> Final LLM): `... -> final_answer_node._prepare_inputs() -> build_final_answer_context() -> _build_final_answer_template_context() -> _render_final_prompt_package() -> prepare_final_answer_llm_payload() -> LazyChatOpenAI.ainvoke()`.
- Der finale Prompt enthält mehrere Layer: `check_1.1.0.j2`, `senior_policy_de.j2`, goal-spezifisches `final_answer_*.j2`, Blueprint-Regeln, `RETRIEVED KNOWLEDGE BASE FACTS`, optional `USER CONTEXT (LONG-TERM MEMORY)`, plus `MCP TOOLS AVAILABLE`.
- **Context-Bloat-Risiken:**
- `_collect_retrieved_facts()` hängt `state.context`, `material_retrieved_context`, `panel_material.rag_context/reducer_context`, `comparison_notes.rag_context` zusammen; keine harte Token-Begrenzung/Trunkierung.
- `prepare_final_answer_llm_payload()` übernimmt Messages ohne input-token guard; nur Output ist via `max_tokens=800` begrenzt.
- `frontdoor_discovery_node` schickt vollständige `state.messages` an die Frontdoor-Klassifikation; keine History-Kürzung.
- Es werden potenziell irrelevante Felder in den Prompt injiziert (`user_context` roh als JSON, `available_mcp_tools`, große `working_memory`-Blöcke).
- **Umgang mit Konflikt-Daten (RAG vs User):** Es gibt keine explizite Konfliktauflösung (z. B. Prioritätsregeln/consistency scorer). Es gibt nur Guardrail-Instruktionen im Prompt; keine dedizierte "conflict arbitration"-Node.

## 4. MCP & Tooling
- Verfügbare MCP/Tool-Funktionen im System: `search_technical_docs`, `get_available_filters`, `pricing_tool`, `stock_check_tool`, `approve_discount`, zusätzlich LangChain-`@tool` `search_knowledge_base`.
- Tool-Discovery ist scope-basiert (`discover_tools_for_scopes`) und wird im finalen Prompt protokolliert (`mcp_tool_discovery`, `tool_count=...`).
- Tool-Nutzung im Graph ist überwiegend **deterministisch und statisch**, nicht agentisch-tool-call-gesteuert:
- `material_agent_node` ruft `get_available_filters` + `search_technical_docs` direkt auf.
- `node_p2_rag_lookup` ruft `search_technical_docs` mit Cache/Fallback (Qdrant -> BM25) auf.
- `rag_support_node` nutzt `search_knowledge_base.invoke(...)`.
- `node_p4b_calc_render` nutzt `mcp_calc_gasket` mit 3 Retries (deterministisch).
- LLM-Node-Matrix (vollständig):

| Node Name | Rolle (Agent/Extractor/Generator) | Hat Zugriff auf Tools? | Welche Tools? | Allowed Retries |
|---|---|---|---|---|
| `frontdoor_discovery_node` | Intent-Classifier (Agent) | Nein (direkt) | - | `ChatOpenAI(max_retries=2)` |
| `node_p1_context` | Extractor (Agent) | Nein (direkt) | - | `ChatOpenAI(max_retries=2)` |
| `smalltalk_node` | Generator (Agent) | Nein | - | `run_llm` -> Modell mit `max_retries=2` |
| `material_comparison_node` | Generator (Agent) | Nein | - | `run_llm_async`: 3 Tenacity-Versuche, Modell intern `max_retries=2` |
| `leakage_troubleshooting_node` | Generator (Agent) | Nein | - | `run_llm_async`: 3 Tenacity-Versuche, Modell intern `max_retries=2` |
| `troubleshooting_explainer_node` | Generator (Agent) | Nein | - | `run_llm_async`: 3 Tenacity-Versuche, Modell intern `max_retries=2` |
| `final_answer_node` | Final Generator (Agent) | Indirekt (Prompt-Discovery) | `discover_tools_for_scopes` (nur Sichtbarkeit, kein Tool-Call) | Kein explizites `max_retries` im `LazyChatOpenAI` gesetzt |
| `out_of_scope_node` (derzeit nicht verdrahtet) | Generator (Agent) | Nein | - | `run_llm` -> Modell mit `max_retries=2` |

## 🎯 Top 3 Empfehlungen zur "Brain-Optimierung"
1. Ersetze Single-Label-Frontdoor durch **Dual-Intent Routing** (z. B. `social_intent` + `task_intent`) und priorisiere technische Intents über Smalltalk, damit "Hi + Fachfrage" nicht auf `smalltalk_node` endet.
2. Baue ein **Context-Budgeting** vor `final_answer_node` ein: Top-k Chunk-Selection + harte Zeichen/Token-Grenze für `state.context`, `user_context`, `sources`; sonst steigt Halluzinations-/Drift-Risiko mit Promptlänge.
3. Verschiebe `p4_6_number_verification` **nach** `final_answer_node` (oder prüfe den Draft-Text explizit), damit tatsächlich generierte Zahlen verifiziert werden; aktuell ist das Gate kognitiv weitgehend wirkungslos.
