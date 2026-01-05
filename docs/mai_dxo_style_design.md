# MAI-DxO Style Supervisor Blueprint (LangGraph v2) - Audit and Design Plan

## Scope and constraints
- Keep current v2 endpoint contract and SSE behavior unchanged.
- Keep Redis checkpointer and Jinja2 pipeline.
- Phase 1 only: audit and design, no code changes.

## Phase 1 evidence audit

### Current supervisor logic (backend/app/langgraph_v2/nodes/nodes_supervisor.py)
- supervisor_logic_node:
  - Computes missing_params from _REQUIRED_PARAMS_FOR_READY.
  - Sets coverage_score, coverage_gaps, recommendation_ready.
  - Sets phase to "intent".
- supervisor_route:
  - design_recommendation -> intermediate if not ready, design_flow if go, else confirm.
  - explanation_or_comparison -> comparison.
  - troubleshooting_leakage -> troubleshooting.
  - out_of_scope -> out_of_scope.
  - fallback -> smalltalk.
- _maybe_set_recommendation_go: keyword based YES/NO gating from last user message.

### Current graph wiring (backend/app/langgraph_v2/sealai_graph_v2.py)
- Entry: START -> frontdoor_discovery_node -> supervisor_logic_node.
- Supervisor routing:
  - intermediate, smalltalk, out_of_scope -> final_answer_node.
  - confirm -> confirm_recommendation_node -> END.
  - design_flow -> calculator_node (design flow path).
  - comparison -> material_comparison_node -> optional rag_support_node.
  - troubleshooting -> leakage_troubleshooting_node -> troubleshooting_pattern_node -> troubleshooting_explainer_node.
- Design flow:
  - discovery_schema_node -> parameter_check_node -> calculator_node -> material_agent_node ->
    profile_agent_node -> validation_agent_node -> critical_review_node -> product_match_node ->
    product_explainer_node -> final_answer_node.
- Final: final_answer_node -> END.

### Current state fields (backend/app/langgraph_v2/state/sealai_state.py)
- Coverage/readiness: coverage_score, coverage_gaps, recommendation_ready, recommendation_go.
- Missing inputs: missing_params, discovery_missing, ask_missing_request, ask_missing_scope, awaiting_user_input.
- Outputs and working memory: working_memory (material_candidates, design_notes, comparison_notes, troubleshooting_notes),
  recommendation, calc_results, products, troubleshooting.
- RAG: requires_rag, sources.
- Missing for MAI-DxO: open_questions, candidates list (global), budget, decision_log, global confidence.

### Node mapping to ask-question, request-test (RAG), provide-final
- ask-question:
  - confirm_recommendation_node returns a checkpoint response with top questions when GO is false.
  - final_answer_node handles the "intermediate" path and can ask for missing params via templates.
  - ask_missing_node exists in nodes_preflight.py and is wired only in sealai_graph_v2_legacy.py, not in v2.
- request-test (RAG):
  - material_comparison_node can set requires_rag and routes to rag_support_node.
  - rag_support_node calls search_knowledge_base (norms evidence).
- provide-final:
  - final_answer_node builds and streams the final response via Jinja2 + LLM.
  - confirm_recommendation_node returns final_text directly and ends.

### Missing capabilities relative to MAI-DxO
- open_questions list: missing; only missing_params/discovery_missing exist without priority or ownership.
- hypotheses/candidates list: partially present (material_candidates, troubleshooting.hypotheses, products.matches)
  but no shared schema or ensemble tracking.
- cost/budget accounting: absent.
- aggregator/consensus node: absent; current flow is linear, no ensemble merge.
- stop criteria and decision ledger: no explicit decision_log or stop policy beyond thresholds.

## MAI-DxO to SealAI mapping (proposed)
| MAI-DxO concept | SealAI action |
| --- | --- |
| Iterative rounds | supervisor_policy_node loops until stop criteria, logs each round. |
| Panel roles | panel_material_node, panel_norms_rag_node, panel_calculator_node. |
| Evidence ledger | facts map + sources, updated by panels and aggregator. |
| Ensemble aggregation | aggregator_node merges panel outputs and flags contradictions. |
| Cost/value gating | budget remaining/spent; supervisor_policy_node chooses next_action by cost and risk. |
| Explicit stop criteria | stop when confidence is high, open_questions empty, or budget exhausted. |
| Final recommendation | final_answer_node (existing Jinja2 pipeline). |

## Proposed state schema additions (minimal skeleton)
Add to SealAIState:
- open_questions: List[QuestionItem] = []
- facts: Dict[str, FactItem] = {}
- candidates: List[CandidateItem] = []
- decision_log: List[DecisionEntry] = []
- budget: Dict[str, int] = {"remaining": 8, "spent": 0}
- confidence: float = 0.0

Suggested item shapes:
- QuestionItem: {id, question, reason, priority, source}
- FactItem: {value, source, confidence, evidence_refs}
- CandidateItem: {kind, value, rationale, evidence_refs, confidence}
- DecisionEntry: {round, action, reason, cost, open_questions, confidence}

Notes:
- intent.confidence remains intent classification; confidence is global solution confidence.
- existing missing_params/discovery_missing can seed open_questions.

## Proposed node graph (with edges)
High level routing (supervisor_policy -> ask_user | run_panel | finalize):
START
  -> frontdoor_discovery_node
  -> supervisor_policy_node

supervisor_policy_node
  -> ask_user_node -> final_answer_node -> END
  -> panel_material_node -> aggregator_node -> supervisor_policy_node
  -> panel_norms_rag_node -> aggregator_node -> supervisor_policy_node
  -> panel_calculator_node -> aggregator_node -> supervisor_policy_node
  -> finalize_node (final_answer_node) -> END

Panel wrappers (minimal skeleton):
- panel_material_node wraps material_agent_node (material selection hints).
- panel_norms_rag_node wraps rag_support_node or search_knowledge_base tool.
- panel_calculator_node wraps calculator_node (deterministic calc + notes).

Aggregator:
- Merges panel outputs into facts/candidates.
- Flags contradictions in decision_log.
- Updates confidence and open_questions.

Supervisor policy:
- Chooses next_action based on open_questions priority, confidence, contradictions, and budget.
- Emits DecisionEntry for each decision.

## Stop criteria definition (proposed)
Stop and finalize when any of:
- confidence >= 0.8 and no high priority open_questions remain.
- budget.remaining <= 0.
- max_rounds reached (e.g., 3) without new material facts.
- user explicitly asks to stop or confirms recommendation_go.

Continue asking user when:
- open_questions contains high priority items and budget allows ask_user cost.

Continue running panels when:
- contradictions exist or facts/candidates are insufficient and budget allows.

## Cost model (ordinal, simple)
Suggested levels (1 = low, 3 = high):
- 1: deterministic checks (parameter_check_node, calculator_node).
- 2: single LLM call (material panel, troubleshooting panel).
- 3: RAG retrieval or multi-step LLM (panel_norms_rag_node, final_answer_node).

Budget usage:
- budget.spent += cost_level, budget.remaining -= cost_level.

## Phase 2 diff plan (implementation plan only, no code changes yet)
1) State additions:
   - backend/app/langgraph_v2/state/sealai_state.py: add open_questions, facts, candidates,
     decision_log, budget, confidence (minimal shapes, default values).
2) Nodes:
   - backend/app/langgraph_v2/nodes/nodes_supervisor.py or new nodes file:
     add supervisor_policy_node, aggregator_node, panel_material_node,
     panel_norms_rag_node, panel_calculator_node.
   - Keep existing Jinja2 render + final_answer_node unchanged.
3) Routing:
   - backend/app/langgraph_v2/sealai_graph_v2.py: replace direct supervisor_route with
     supervisor_policy_node conditional routing: ask_user | run_panel | finalize.
4) Tests:
   - Add unit tests for supervisor_policy routing (>= 5 cases):
     coverage vs open_questions, budget exhausted, contradiction present, high confidence finalize,
     user denial (recommendation_go false).
5) Docs:
   - Update smoke/runbook docs to reflect new panel/aggregator topology.

## Implementation notes (Phase 2 skeleton)
- Feature flag: `LANGGRAPH_V2_SUPERVISOR_MODE=mai_dxo` enables the new supervisor loop.
- Default remains `legacy` to preserve current v2 behavior.
- New nodes: supervisor_policy_node -> panel_* -> aggregator_node -> supervisor_policy_node.
- Routing: frontdoor_discovery_node conditionally selects legacy or MAI-DxO supervisor.
