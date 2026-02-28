# OVERENGINEERING Audit: KB Fast Path vs V3 Answer Subgraph

## 1) Routing Audit (Current Behavior)

Observed execution path for simple material/explanation queries:

1. `frontdoor_discovery_node` classifies material/info query (`MATERIAL_RESEARCH` or `requires_rag=true`).
2. `route_after_frontdoor_node` sends it to `frontdoor_parallel_fanout_node` via `route_after_frontdoor.kb_fast_path`.
3. Deterministic branch falls back to `supervisor_policy_node` when no deterministic answer is produced.
4. `supervisor_policy_node` sets `requires_rag` and dispatches `Send("material_agent", ...)`.
5. `material_agent` fetches docs and stores context under:
   - `state.working_memory.panel_material.rag_context`
   - `state.context`
   - `state.sources`
6. `material_agent -> reducer_node`.
7. `_reducer_router` routes `standard -> final_answer_node`.
8. `final_answer_node` is wired to `answer_subgraph_node(_async)` (contract-first V3 subgraph).

Conclusion: `kb_fast_path` informational queries do not end after retrieval; they are funneled into the strict contract/verification subgraph.

## 2) Why This Causes Over-Engineering Failures

The V3 answer subgraph enforces strict contract verification (`prepare_contract -> draft_answer -> verify_claims -> patch loop/fallback`).
For qualitative RAG explanations, this can fail verification or hit conservative fallback behavior, producing brittle/non-conversational responses.

So the architecture mismatch is:
- Query type: lightweight explanatory QA.
- Current answer path: heavy, contract-first compliance path optimized for tightly verifiable outputs.

## 3) Simplification Plan (Bypass V3 for Simple Explanations)

### New Node: `conversational_rag_node`

Purpose: directly answer informational RAG questions from retrieved context, without contract-first verification.

Input used:
- user query from latest user message
- RAG context from `state.working_memory.panel_material.rag_context` (fallback `state.context`)
- optional `state.sources` for lightweight grounding mention

System behavior:
- Prompt style: helpful sidekick, concise explanation from provided context.
- If context is empty/irrelevant: explicitly say no exact datasheet detail is available and ask for specifics (material/trade name, medium, temperature, pressure).

Output patch:
- `final_text`
- `final_answer`
- appended AI message
- `last_node="conversational_rag_node"`
- optional `phase=KNOWLEDGE`

### Graph Rewire

For explanation/info intents, route as:

`material_agent -> conversational_rag_node -> END`

and bypass:

`material_agent -> reducer_node -> final_answer_node(answer_subgraph)`

Recommended minimal wiring strategy:
1. Add `conversational_rag_node` to graph registration.
2. Introduce a reducer route key (e.g., `conversational_rag`) when:
   - intent goal is `explanation_or_comparison`, and
   - material RAG context/docs exist.
3. Map reducer conditional edges:
   - `human_review -> human_review_node`
   - `conversational_rag -> conversational_rag_node`
   - `standard -> final_answer_node`
4. Add `builder.add_edge("conversational_rag_node", END)`.

This preserves existing V3 path for design/calculation/strict responses while unblocking natural QA for `kb_fast_path` explanations.

## 4) Scope Boundary

Do **not** remove the V3 subgraph globally.
Only bypass it for lightweight explanatory/material research requests where conversational RAG is the intended UX.
